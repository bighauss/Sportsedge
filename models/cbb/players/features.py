"""Point-in-time matchup features for CBB player props (stdlib only).

Inputs are public sportsdataverse ESPN player boxes. Every feature for a
target game on ET date d uses only games dated <= d - LAG_DAYS (the #519
two-day chronology proxy). Prior-season per-minute rates (same ESPN athlete
id, any team) serve only as a shrinkage prior. Appearance-conditional: a
row exists only when the player recorded minutes; non-participation is never
read as zero.
"""
from collections import Counter, defaultdict, deque
import csv
from datetime import date, timedelta
import math

LAG_DAYS = 2
MIN_PRIOR = 5          # same as #519 eligibility
RECENT = 8             # #519 recent window
RATE_WINDOW = 15       # appearances used for per-minute rates
K_RATE_MIN = 100.0     # pseudo-minutes of prior in rate shrinkage (preregistered)
K_TEAM_GAMES = 5.0     # pseudo-games shrinking team pace / allowed rates to league
PRIOR_SEASON_MIN = 150.0
STATS = ("POINTS", "REBOUNDS", "ASSISTS", "THREES")
COMBOS = {"PRA": ("POINTS", "REBOUNDS", "ASSISTS"), "PR": ("POINTS", "REBOUNDS"),
          "PA": ("POINTS", "ASSISTS"), "RA": ("REBOUNDS", "ASSISTS")}
COLS = {"POINTS": "points", "REBOUNDS": "rebounds", "ASSISTS": "assists",
        "THREES": "three_point_field_goals_made"}
POSS_COLS = ("field_goals_attempted", "offensive_rebounds", "turnovers", "free_throws_attempted")


def _int(x):
    if x is None or (isinstance(x, str) and not x.strip()):
        raise ValueError("MISSING")
    v = float(x)
    if not math.isfinite(v) or v < 0 or v > 250 or not v.is_integer():
        raise ValueError("INVALID")
    return int(v)


def _id(x):
    s = str(x or "").strip()
    if not (s.isdigit() and int(s) > 0 and s == str(int(s))):
        raise ValueError("INVALID_ID")
    return s


def load_player_box(path, *, final_game_ids=None):
    """Admit SDV player box rows. Returns (appearances, team_games, census).

    appearances: one per (athlete, game) with minutes > 0, all copies of a
    duplicated (athlete, game) dropped. team_games: per (game, team) totals
    from every admitted row (DNP rows contribute zeros).
    """
    census = Counter()
    groups = defaultdict(list)
    with open(path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            census["input_rows"] += 1
            try:
                groups[(_id(r["athlete_id"]), _id(r["game_id"]))].append(r)
            except (ValueError, KeyError):
                census["INVALID_PLAYER_OR_GAME_ID"] += 1
    apps, tg = [], {}
    for (pid, gid), rr in groups.items():
        if len(rr) != 1:
            census["DUPLICATE_PLAYER_GAME_ALL_COPIES"] += len(rr)
            continue
        r = rr[0]
        if final_game_ids is not None and gid not in final_game_ids:
            census["GAME_NOT_FINAL_IN_SCHEDULE"] += 1
            continue
        dnp = str(r.get("did_not_play", "")).lower() == "true"
        if dnp and not str(r.get("points") or "").strip():
            census["DID_NOT_PLAY_ROW"] += 1   # roster listing only; never a zero stat line
            continue
        try:
            tid, oid = _id(r["team_id"]), _id(r["opponent_team_id"])
            d = date.fromisoformat(r["game_date"])
            stats = {k: _int(r[c]) for k, c in COLS.items()}
            poss = [_int(r[c]) for c in POSS_COLS]
        except (ValueError, KeyError, TypeError):
            census["INVALID_CORE_FIELDS"] += 1
            continue
        m_raw = r.get("minutes")
        try:
            m = float(m_raw) if m_raw not in (None, "") else 0.0
        except ValueError:
            census["INVALID_MINUTES"] += 1
            continue
        if not math.isfinite(m) or m < 0 or m > 100:
            census["INVALID_MINUTES"] += 1
            continue
        t = tg.setdefault((gid, tid), dict(game_id=gid, team_id=tid, opp_id=oid, day=d,
                                              fga=0, oreb=0, tov=0, fta=0, n=0,
                                              **{k: 0 for k in STATS}))
        t["n"] += 1
        for k in STATS:
            t[k] += stats[k]
        t["fga"] += poss[0]; t["oreb"] += poss[1]; t["tov"] += poss[2]; t["fta"] += poss[3]
        if dnp or m <= 0:
            census["NON_APPEARANCE_ROW"] += 1
            continue
        apps.append(dict(player_id=pid, name=r.get("athlete_display_name", ""), team_id=tid,
                         opp_id=oid, game_id=gid, day=d, minutes=m,
                         starter=str(r.get("starter", "")).lower() == "true", stats=stats))
    for t in tg.values():
        t["poss"] = t["fga"] - t["oreb"] + t["tov"] + 0.475 * t["fta"]
    census["appearances"] = len(apps)
    census["team_games"] = len(tg)
    return apps, tg, dict(census)


def prior_season_rates(apps):
    """Per-athlete per-minute rates from a completed earlier season."""
    tot = defaultdict(lambda: {"min": 0.0, **{k: 0 for k in STATS}})
    for a in apps:
        t = tot[a["player_id"]]
        t["min"] += a["minutes"]
        for k in STATS:
            t[k] += a["stats"][k]
    return {pid: {"minutes": t["min"], **{k: t[k] / t["min"] for k in STATS}}
            for pid, t in tot.items() if t["min"] >= PRIOR_SEASON_MIN}


class Engine:
    """Chronological state. commit(day) folds in all games dated <= day."""

    def __init__(self, apps, team_games, prior_rates=None):
        self.prior_rates = prior_rates or {}
        self.apps_by_day = defaultdict(list)
        for a in apps:
            self.apps_by_day[a["day"]].append(a)
        self.tg_by_day = defaultdict(list)
        for t in team_games.values():
            self.tg_by_day[t["day"]].append(t)
        self.team_games = team_games
        self.days = sorted(set(self.apps_by_day) | set(self.tg_by_day))
        self.committed_through = None
        self._i = 0
        self.player_hist = defaultdict(list)
        self.team_hist = defaultdict(list)       # (poss, stats, allowed stats, game poss)
        self.team_last_game = {}
        self.team_last_players = {}
        self.lg = {"poss": 0.0, "games": 0, "min": 0.0, **{k: 0.0 for k in STATS}}

    def commit(self, through):
        while self._i < len(self.days) and self.days[self._i] <= through:
            d = self.days[self._i]
            for t in self.tg_by_day[d]:
                o = self.team_games.get((t["game_id"], t["opp_id"]))
                if o is None:
                    continue   # one-sided box: no allowed stats or game pace
                gp = 0.5 * (t["poss"] + o["poss"])
                self.team_hist[t["team_id"]].append(dict(
                    day=d, game_id=t["game_id"], poss=t["poss"], game_poss=gp,
                    allowed={k: o[k] for k in STATS}, opp_poss=o["poss"]))
                self.lg["poss"] += t["poss"]; self.lg["games"] += 1
                for k in STATS:
                    self.lg[k] += t[k]
                self.team_last_game[t["team_id"]] = (d, t["game_id"])
            played = defaultdict(set)
            for a in self.apps_by_day[d]:
                t = self.team_games.get((a["game_id"], a["team_id"]))
                o = self.team_games.get((a["game_id"], a["opp_id"]))
                gp = 0.5 * (t["poss"] + o["poss"]) if t and o else None
                self.player_hist[a["player_id"]].append(dict(a, game_poss=gp))
                self.lg["min"] += a["minutes"]
                played[(a["team_id"], a["game_id"])].add(a["player_id"])
            for (tid, gid), s in played.items():
                if self.team_last_game.get(tid, (None, None))[1] == gid:
                    self.team_last_players[tid] = s
            self.committed_through = d
            self._i += 1

    # ---- league / team aggregates (as of committed state) ----
    def league(self):
        g = self.lg["games"]
        if g < 50 or self.lg["min"] <= 0:
            return None
        return {"pace": self.lg["poss"] / g,
                "per_poss": {k: self.lg[k] / self.lg["poss"] for k in STATS},
                "per_min": {k: self.lg[k] / self.lg["min"] for k in STATS}}

    def team_pace(self, tid, lg):
        h = self.team_hist.get(tid, [])
        n = len(h)
        return (sum(x["poss"] for x in h) + K_TEAM_GAMES * lg["pace"]) / (n + K_TEAM_GAMES), n

    def opp_factor(self, oid, lg):
        h = self.team_hist.get(oid, [])
        n = len(h)
        out = {}
        for k in STATS:
            # Opponent's allowed stat per opponent possession, shrunk toward league.
            if n:
                rate = sum(x["allowed"][k] for x in h) / max(1e-9, sum(x["opp_poss"] for x in h))
                w = n / (n + K_TEAM_GAMES)
                rate = w * rate + (1 - w) * lg["per_poss"][k]
            else:
                rate = lg["per_poss"][k]
            out[k] = rate / lg["per_poss"][k]
        return out, n

    def features(self, pid, tid, oid, day, *, cutoff=None):
        """Raw components for (player, team, opponent, ET date). Returns (row, hold)."""
        cut = cutoff if cutoff is not None else day - timedelta(days=LAG_DAYS)
        if self.committed_through is not None and self.committed_through > cut:
            raise RuntimeError("ENGINE_COMMITTED_PAST_CUTOFF")
        self.commit(cut)
        prior = [p for p in self.player_hist.get(pid, []) if p["day"] <= cut]
        recent = prior[-RECENT:]
        if len(recent) < MIN_PRIOR:
            return None, "INSUFFICIENT_PRIOR_APPEARANCES"
        if len({p["team_id"] for p in recent} | {tid}) != 1:
            return None, "TEAM_TRANSFER_OR_MIXED_HISTORY"
        if len({p["day"] for p in recent}) != len(recent):
            return None, "AMBIGUOUS_MULTIPLE_APPEARANCES_SAME_DATE"
        lg = self.league()
        if lg is None:
            return None, "LEAGUE_BASELINE_UNAVAILABLE"
        mins = [p["minutes"] for p in recent]
        w = [0.5 ** ((len(mins) - 1 - i) / 3.0) for i in range(len(mins))]
        ewma = sum(a * b for a, b in zip(w, mins)) / sum(w)
        proj_min = 0.6 * ewma + 0.4 * (sum(mins) / len(mins))
        rw = [p for p in prior[-RATE_WINDOW:] if p["team_id"] == tid]
        tot_min = sum(p["minutes"] for p in rw)
        pr = self.prior_rates.get(pid)
        prior_rate = {k: (pr[k] if pr else lg["per_min"][k]) for k in STATS}
        rate = {k: (sum(p["stats"][k] for p in rw) + K_RATE_MIN * prior_rate[k]) / (tot_min + K_RATE_MIN)
                for k in STATS}
        gps = [p["game_poss"] for p in rw if p["game_poss"]]
        hist_poss = sum(gps) / len(gps) if gps else lg["pace"]
        tp, tn = self.team_pace(tid, lg)
        op, on = self.team_pace(oid, lg)
        exp_poss = tp * op / lg["pace"]
        ofac, _ = self.opp_factor(oid, lg)
        last = self.team_last_game.get(tid)
        missed_last = bool(last and last[0] > recent[-1]["day"])
        row = dict(player_id=pid, team_id=tid, opp_id=oid, day=day.isoformat(),
                   proj_minutes=proj_min, recent_mean_minutes=sum(mins) / len(mins),
                   base={k: rate[k] * proj_min for k in STATS},
                   pace_ratio=exp_poss / hist_poss, opp_factor=ofac,
                   prior_source="PRIOR_SEASON_SAME_ATHLETE" if pr else "LEAGUE_PER_MINUTE",
                   team_games_prior=tn, opp_games_prior=on, missed_last_team_game=missed_last,
                   history_game_ids=[p["game_id"] for p in recent],
                   native5={k: sum(p["stats"][k] for p in recent[-5:]) / len(recent[-5:]) for k in STATS},
                   recent_values={k: [p["stats"][k] for p in recent] for k in STATS})
        return row, None


def mean_for(row, stat, params):
    """Matchup mean for a single stat under fitted params."""
    p = params["stats"][stat]
    return (p["calibration"] * row["base"][stat] * row["pace_ratio"] ** p["b_pace"]
            * row["opp_factor"][stat] ** p["b_opp"])


def walk_season(apps, team_games, prior_rates=None, *, lag_days=LAG_DAYS):
    """Feature rows for every admitted appearance in date order, plus holds."""
    eng = Engine(apps, team_games, prior_rates)
    rows, holds = [], Counter()
    for d in sorted(eng.apps_by_day):
        for a in sorted(eng.apps_by_day[d], key=lambda x: (x["game_id"], x["player_id"])):
            row, hold = eng.features(a["player_id"], a["team_id"], a["opp_id"], d,
                                     cutoff=d - timedelta(days=lag_days))
            if hold:
                holds[hold] += 1
                continue
            row["game_id"] = a["game_id"]
            row["actual"] = dict(a["stats"], MINUTES=a["minutes"])
            rows.append(row)
    return rows, dict(holds)
