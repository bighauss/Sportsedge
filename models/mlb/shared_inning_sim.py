"""Experimental MLB player/inning scenarios from existing independent batter inputs.

Opt-in, research-only. One set of seeded PA outcomes feeds score, F5, NRFI,
team-total, alternate and batter H/HR/TB probabilities. No bookmaker prices enter
the simulation; no implied settlement of unresolved extra innings. A fixed
runner-advancement simplification and league BB fallback are UNCALIBRATED.
This does not alter the frozen native MLB pricing path.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import random


class NoForecast(ValueError):
    pass


def _float(value, label, *, low=0., high=1.):
    if isinstance(value, bool) or value is None or str(value).strip() == "":
        raise NoForecast("MISSING_OR_INVALID_" + label)
    try:
        n = float(value)
    except (ValueError, TypeError, OverflowError) as e:
        raise NoForecast("MISSING_OR_INVALID_" + label) from e
    if not math.isfinite(n) or n < low or n > high:
        raise NoForecast("MISSING_OR_INVALID_" + label)
    return n


def _rates(batter, *, league_bb=0.083):
    """Convert BA/ISO/HR-per-PA into a toy six-outcome PA distribution.

    BA and ISO are per AB; walk probability comes from source BB% if given,
    otherwise a labelled (untested) league-rate assumption. Never use odds.
    """
    ba = _float(batter.get("ba"), "BA")
    iso = _float(batter.get("iso"), "ISO")
    hr = _float(batter.get("hr_per_pa"), "HR_PER_PA")
    bb_raw = batter.get("bb_percent")
    if bb_raw is None or str(bb_raw).strip() == "":
        bb, bb_assumed = league_bb, True
    else:
        bb = _float(bb_raw, "BB_PERCENT", high=100.) / 100.
        bb_assumed = False
    hit = ba * (1 - bb)
    bonus = iso * (1 - bb) - 3 * hr
    if bonus < -1e-9 or hr > hit:
        raise NoForecast("INCONSISTENT_BATTING_RATE_COMPONENTS")
    bonus = max(0., bonus)
    triple = bonus * .04
    double = bonus - 2 * triple
    single = hit - double - triple - hr
    out = 1 - hit - bb
    if min(single, double, triple, hr, bb, out) < -1e-9 or out < .35:
        raise NoForecast("INCONSISTENT_OR_UNSTABLE_PA_DISTRIBUTION")
    return {"OUT":out, "BB":bb, "1B":single, "2B":double,
            "3B":triple, "HR":hr}, bb_assumed


def player_profiles(inp, game, project):
    """Admit only exact native nine-slot, same-team, independently sourced lineup.

    project is the native project's pregame score output. Its team means are
    retained for diagnostics but never used as a fabricated individual PA rate.
    """
    from models.mlb import sportsedge_mlb_model as native
    reasons = native.preflight_game_inputs(inp, game)
    if reasons:
        raise NoForecast("NATIVE_INPUT_GUARD:" + ",".join(reasons))
    profiles, assumptions = {}, []
    for side in ("away", "home"):
        rows = project[side]["lu"]["rows"]
        if len(rows) != 9:
            raise NoForecast("LINEUP_NOT_NINE_PLAYERS:" + side)
        team = game[side]
        team_rows, seen = [], set()
        for row in rows:
            pid = str(row["pid"])
            if pid in seen or pid not in inp["batters"] or row["b"].get("team") != team:
                raise NoForecast("PLAYER_TEAM_OR_DUPLICATE_ID:" + side)
            seen.add(pid)
            rates, assumed = _rates(row["b"], league_bb=native.W["lg_bb_pct"] / 100.)
            if assumed:
                assumptions.append("BB_PERCENT_LEAGUE_FALLBACK:" + pid)
            team_rows.append({"player_id":pid, "rates":rates})
        profiles[side] = team_rows
    return profiles, assumptions


def _pa(rng, rates):
    u, acc = rng.random(), 0.
    for event in ("OUT","BB","1B","2B","3B","HR"):
        acc += rates[event]
        if u < acc:
            return event
    return "OUT"  # floating-point rounding only


def _half(rng, lineup, position, bat_stats, *, second_base=False, walkoff_need=None):
    """Synthetic half-inning; simple fixed advancement, no steals/errors/DP."""
    outs, runs, bases = 0, 0, [False, bool(second_base), False]
    for _ in range(90):   # fail closed on pathologically low out rates
        player = lineup[position[0] % 9]
        position[0] += 1
        outcome = _pa(rng, player["rates"])
        stats = bat_stats[player["player_id"]]
        stats["PA"] += 1
        if outcome == "OUT":
            outs += 1
        elif outcome == "BB":
            if bases[0] and bases[1] and bases[2]:
                runs += 1
            bases[2] = bases[2] or (bases[1] and bases[0])
            bases[1] = bases[1] or bases[0]
            bases[0] = True
        else:
            n = {"1B":1, "2B":2, "3B":3, "HR":4}[outcome]
            stats["HITS"] += 1
            stats["TB"] += n
            stats["HR"] += (n == 4)
            old = bases
            runs += sum(bool(v) and k + n >= 4 for k,v in enumerate(old, 1))
            if n == 4:
                runs += 1
                bases = [False, False, False]
            else:
                bases = [False, False, False]
                for k,occupied in enumerate(old, 1):
                    if occupied and k+n < 4:
                        bases[k+n-1] = True
                bases[n-1] = True
        if walkoff_need is not None and runs >= walkoff_need:
            return runs
        if outs == 3:
            return runs
    raise NoForecast("HALF_INNING_PLATE_APPEARANCE_CAP")


def simulate(game_id, profiles, *, draws=1024, seed=7, max_innings=12):
    if not isinstance(game_id, str) or not game_id.strip():
        raise NoForecast("MISSING_GAME_ID")
    if (isinstance(draws,bool) or not isinstance(draws,int) or not 1 <= draws <= 100000 or
            isinstance(seed,bool) or not isinstance(seed,int) or
            isinstance(max_innings,bool) or not isinstance(max_innings,int) or
            not 9 <= max_innings <= 18):
        raise NoForecast("INVALID_SIM_CONTROL")
    if set(profiles) != {"away","home"}:
        raise NoForecast("SIDES_REQUIRED")
    ids = []
    for side in ("away","home"):
        players = profiles[side]
        if not isinstance(players, list) or len(players) != 9:
            raise NoForecast("NINE_HITTERS_REQUIRED")
        for p in players:
            pid = p.get("player_id")
            if not isinstance(pid,str) or not pid.strip() or pid in ids:
                raise NoForecast("INVALID_OR_DUPLICATE_PLAYER_ID")
            ids.append(pid)
            rates = p.get("rates", {})
            if set(rates) != {"OUT","BB","1B","2B","3B","HR"} or any(
                    not isinstance(v,(int,float)) or isinstance(v,bool) or
                    not math.isfinite(v) or v < 0 for v in rates.values()):
                raise NoForecast("INVALID_PA_RATES")
            if abs(sum(rates.values())-1) > 1e-10 or rates["OUT"] < .35:
                raise NoForecast("UNSTABLE_PA_RATES")
    rng = random.Random(seed)
    all_draws = []
    stream_hash = hashlib.sha256()
    # Bind the transcript fingerprint to exact game, seed, model inputs and rules.
    header = {"game_id":game_id,"seed":seed,"max_innings":max_innings,
              "draws":draws,"profiles":profiles,"model_schema":"mlb-pa-inning-v1"}
    stream_hash.update(json.dumps(header,sort_keys=True,separators=(",",":"),
                                  allow_nan=False).encode())
    for _ in range(draws):
        scores = {"away":0,"home":0}
        positions = {"away":[0],"home":[0]}
        stats = {pid:{"PA":0,"HITS":0,"TB":0,"HR":0} for pid in ids}
        first = f5 = None
        innings = 0
        for inning in range(1,max_innings+1):
            extra = inning > 9
            scores["away"] += _half(rng,profiles["away"],positions["away"],stats,
                                    second_base=extra)
            # After the top of ninth or later, a winning home team does not bat.
            if inning < 9 or scores["home"] <= scores["away"]:
                need = scores["away"] - scores["home"] + 1 if inning >= 9 else None
                scores["home"] += _half(rng,profiles["home"],positions["home"],stats,
                                        second_base=extra,walkoff_need=need)
            innings = inning
            if inning == 1:
                first = (scores["away"],scores["home"])
            if inning == 5:
                f5 = (scores["away"],scores["home"])
            if inning >= 9 and scores["home"] != scores["away"]:
                break
        d = {"away":scores["away"],"home":scores["home"],
             "f5_away":f5[0],"f5_home":f5[1],
             "first_away":first[0],"first_home":first[1],
             "innings":innings,"unresolved":scores["home"]==scores["away"],
             "players":stats}
        raw = json.dumps(d,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
        stream_hash.update(len(raw).to_bytes(4,"big"))
        stream_hash.update(raw)
        all_draws.append(d)
    return {"game_id":game_id,"seed":seed,"draws":draws,"max_innings":max_innings,
            "scenario_sha256":stream_hash.hexdigest(),"scenarios":all_draws,
            "unresolved_extra_innings":sum(d["unresolved"] for d in all_draws),
            "source_authenticated":False,"official_counted":0,"approved_stake_u":0,
            "method":"UNCALIBRATED_FIXED_ADVANCEMENT_PA_INNING_RESEARCH"}


def settle(samples, market, selection, line=None, *, player_id=None):
    """P(W), P(push), P(L) from the SAME simulated game/player outcomes.

    Never silently divide out games unresolved after the extra-inning cap.
    """
    n = samples["draws"]
    game_markets = {"ML","RL","TOTAL","TT_AWAY","TT_HOME",
                    "F5_ML","F5_TOTAL","F5_RL","NRFI","INNING_1_TOTAL"}
    batter_markets = {"HITS","TB","HR"}
    if market not in game_markets | batter_markets:
        return {"status":"NO_FORECAST","reason":"UNSUPPORTED_MARKET"}
    valid_side = selection in ("home","away") if market in ("ML","RL","F5_ML","F5_RL") else (
        selection in ("nrfi","yrfi") if market == "NRFI" else selection in ("over","under"))
    if not valid_side:
        return {"status":"UNRESOLVED_MARKET","reason":"BAD_SELECTION"}
    if market not in {"ML","F5_ML","NRFI"}:
        try:
            line = _float(line,"LINE",low=-1000.,high=1000.)
        except NoForecast as e:
            return {"status":"UNRESOLVED_MARKET","reason":str(e)}
        if market not in {"RL","F5_RL"} and line < 0:
            return {"status":"UNRESOLVED_MARKET","reason":"NEGATIVE_NON_SPREAD_LINE"}
    if market in batter_markets:
        if not isinstance(player_id,str) or not player_id or any(
                player_id not in d["players"] for d in samples["scenarios"]):
            return {"status":"NO_FORECAST","reason":"PLAYER_ID_NOT_IN_LINEUP"}
    # Batter props also depend on a completed game: a capped, still-tied
    # extra-inning draw can add future PA/HITS/TB/HR and cannot be settled.
    if market in ({"ML","RL","TOTAL","TT_AWAY","TT_HOME"} | batter_markets) and samples["unresolved_extra_innings"]:
        return {"status":"UNRESOLVED_MARKET","reason":"UNSETTLED_EXTRA_INNINGS",
                "unresolved_draws":samples["unresolved_extra_innings"],"n":n}
    counts = Counter()
    for d in samples["scenarios"]:
        if market in ("ML","RL","F5_ML","F5_RL"):
            pref = "f5_" if market.startswith("F5_") else ""
            diff = d[pref+selection] - d[pref+("away" if selection=="home" else "home")]
            value = diff + (line if market in ("RL","F5_RL") else 0.)
        elif market == "NRFI":
            value = d["first_away"] + d["first_home"]
            counts["W" if ((value==0) == (selection=="nrfi")) else "L"] += 1
            continue
        elif market in batter_markets:
            value = d["players"][player_id][market] - line
        else:
            if market == "TOTAL":
                value = d["away"] + d["home"] - line
            elif market == "TT_AWAY":
                value = d["away"] - line
            elif market == "TT_HOME":
                value = d["home"] - line
            elif market == "F5_TOTAL":
                value = d["f5_away"] + d["f5_home"] - line
            else:
                value = d["first_away"] + d["first_home"] - line
        if abs(value) < 1e-9:
            counts["P"] += 1
        elif (value > 0) == (selection in ("over","home","away")):
            counts["W"] += 1
        else:
            counts["L"] += 1
    assert sum(counts.values()) == n
    return {"status":"SIMULATED_RESEARCH","n":n,"wins":counts["W"],
            "pushes":counts["P"],"losses":counts["L"],
            "p_win":counts["W"]/n,"p_push":counts["P"]/n,
            "p_loss":counts["L"]/n,"scenario_sha256":samples["scenario_sha256"],
            "source_authenticated":False,"official_counted":0}


def _odds(raw):
    try:
        x = int(str(raw).strip())
        if x == 0 or abs(x) < 100 or abs(x) > 100000:
            raise ValueError
        return x
    except (TypeError,ValueError,OverflowError):
        return None


def _offered(samples, inp, game):
    """Every supplied offer gets a status; prices never feed the simulation."""
    gid = game["game_id"]
    rows = []
    for offer in inp.get("odds",[]):
        if offer.get("game_id") != gid:
            continue
        rows.append((offer.get("market",""),offer.get("selection",""),
                     offer.get("line"),None,offer.get("price"),offer.get("book","")))
    for offer in inp.get("prop_odds",[]):
        if offer.get("game_id") != gid:
            continue
        for selection,price_key in (("over","over_price"),("under","under_price")):
            rows.append((offer.get("market",""),selection,offer.get("line"),
                         offer.get("player_id"),offer.get(price_key),offer.get("book","")))
    output = []
    for market,side,line,pid,price,book in rows:
        result = settle(samples,market,side,line,player_id=pid)
        odds = _odds(price)
        status = result["status"]
        raw_ev = None
        if status == "SIMULATED_RESEARCH":
            if odds is None:
                status = "NO_BENCHMARK"
            else:
                dec_profit = odds/100 if odds > 0 else 100/(-odds)
                raw_ev = result["p_win"]*dec_profit-result["p_loss"]
                status = "RESEARCH_RAW_EV_ONLY"
        output.append({"market":market,"selection":side,"line":line,
                       "player_id":pid,"book":book,"price":price,
                       "status":status,"reason":result.get("reason"),
                       "p_win":result.get("p_win"),"p_push":result.get("p_push"),
                       "p_loss":result.get("p_loss"),"raw_ev":raw_ev,
                       "no_vig":None,"blended_ev":None,
                       "source_authenticated":False,"official_counted":0})
    return output


def run_research(inp, *, draws=1024, seed=7):
    """Native-input bridge with an attempted-game and offered-market census."""
    from models.mlb import sportsedge_mlb_model as native
    if isinstance(inp,str):
        inp = native.load_inputs(inp)
    report = {"schema":"sportsedge-mlb-shared-inning-research-v1",
              "state":"PAPER_RESEARCH_NOT_CERTIFIED","games":[],
              "game_count":len(inp.get("games",[])), "official_counted":0,
              "approved_stake_u":0,"source_clock_verified":False,
              "no_vig_verified":False,"model_validated":False}
    for i,game in enumerate(inp.get("games",[])):
        gid = game.get("game_id","")
        item = {"game_id":gid,"status":"NO_FORECAST","reason":None,
                "source_authenticated":False}
        try:
            projection = native.project_game(inp,game) if not native.preflight_game_inputs(inp,game) else None
            if projection is None:
                raise NoForecast("NATIVE_INPUT_GUARD:"+
                                 ",".join(native.preflight_game_inputs(inp,game)))
            profiles, assumptions = player_profiles(inp,game,projection)
            samples = simulate(gid,profiles,draws=draws,seed=seed+i)
            offers = _offered(samples,inp,game)
            item.update(status="SIMULATED_RESEARCH",reason=None,
                        scenario_sha256=samples["scenario_sha256"],
                        n_sims=samples["draws"],unresolved_extra_innings=samples["unresolved_extra_innings"],
                        native_runs_away=projection["away"]["runs"],
                        native_runs_home=projection["home"]["runs"],
                        # Surface model/sim disagreement; uncalibrated PA rates
                        # must not be advertised as matching the native means.
                        simulated_runs_away=sum(d["away"] for d in samples["scenarios"])/samples["draws"],
                        simulated_runs_home=sum(d["home"] for d in samples["scenarios"])/samples["draws"],
                        assumptions=assumptions,offers=offers,
                        census=dict(sorted(Counter(o["status"] for o in offers).items())))
        except (NoForecast,KeyError,TypeError,ValueError,ArithmeticError) as e:
            item["reason"] = str(e)
            # Preserve the entire original offered denominator, including BOTH
            # sides stored together in one prop_odds row.
            blocked = [{"market":r.get("market"),"selection":r.get("selection"),
                        "line":r.get("line"),"player_id":None,
                        "price":r.get("price"),"book":r.get("book"),
                        "status":"NO_FORECAST","reason":"GAME_MODEL_UNAVAILABLE"}
                       for r in inp.get("odds",[]) if r.get("game_id")==gid]
            for r in inp.get("prop_odds",[]):
                if r.get("game_id") != gid:
                    continue
                for side,field in (("over","over_price"),("under","under_price")):
                    blocked.append({"market":r.get("market"),"selection":side,
                                    "line":r.get("line"),"player_id":r.get("player_id"),
                                    "price":r.get(field),"book":r.get("book"),
                                    "status":"NO_FORECAST","reason":"GAME_MODEL_UNAVAILABLE"})
            item["offers"] = blocked
            item["census"] = {"NO_FORECAST":len(blocked)}
        report["games"].append(item)
    # Every offered side (including blocked pitcher/alt props) stays counted.
    report["attempted_offer_sides"] = sum(len(g.get("offers",[])) for g in report["games"])
    report["simulated_games"] = sum(g["status"]=="SIMULATED_RESEARCH" for g in report["games"])
    report["blocked_games"] = report["game_count"] - report["simulated_games"]
    report["offer_status_census"] = dict(sorted(Counter(
        o["status"] for g in report["games"] for o in g.get("offers",[])
    ).items()))
    return report
