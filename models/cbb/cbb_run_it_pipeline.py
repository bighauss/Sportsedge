#!/usr/bin/env python3
"""RUN IT CBB full pipeline (PAPER / 0u, NON_COUNTED):

    capture -> validate -> project -> simulate -> price -> rank -> research card -> freeze
    -> grade -> audit

Stage contracts are in ``contracts.py``. Stages are pluggable adapters:

* capture:  BoardFileCapture (CSV transcribed from PDF / screenshot / operator transcript,
            always labeled UNAUTHENTICATED_*), AuthenticatedDkCapture (manifest + raw-byte hashes;
            the only path labeled AUTHENTICATED_DK_CAPTURE; credentials are refused, never stored).
* project:  frozen_native_cbbd (DEFAULT, production: the unchanged cbb_run_it.build path with live
            CBBD captures and the frozen native model), native_formula_public_replay (the SAME frozen
            native formula fed by a disclosed public ESPN reconstruction of team efficiencies; for
            environments without a CBBD key; never production), fullgame (WS1 module, behind a flag;
            ADAPTER_NOT_LANDED until models/cbb/fullgame exists). Halves/players: halves/ and players/
            adapters behind flags; NOT_IMPLEMENTED with reason codes until they land.
* simulate: seeded Monte Carlo of the joint (margin, total) projection -> integer team scores with
            overtime resolution, so game, team-total and (when wired) half/player outcomes come from
            the SAME draws.
* price:    every market priced from the simulation (push-aware on whole lines), with the closed-form
            normal value retained for an audit parity check.
* grade:    W/L/P and flat 1u return on the best positive-EV side of every priced row, Brier / log
            loss / calibration on every side, CLV when a later pre-tip close board is supplied.
* audit:    EV>30% flags, orientation checks, bias, calibration, leakage, correlation/consistency,
            coverage per catalogued market family with reason codes, and pin verification.

Nothing in this module edits the frozen model, cbb_pricing.py, or any board file. Every output row is
PAPER_0U and NON_COUNTED with approved_stake_u 0.
"""
from __future__ import annotations

import argparse, csv, hashlib, io, json, math, os, random, re, sys
from collections import Counter, defaultdict
from dataclasses import replace, is_dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import NormalDist, mean
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(ROOT))
import contracts as C                         # noqa: E402
import cbb_pricing as PR                      # noqa: E402
import cbbd_native_score_model as NM          # noqa: E402
import cbb_numeric as NUM                      # noqa: E402

CT = ZoneInfo("America/Chicago")
PIPELINE_VERSION = "cbb-run-it-pipeline-v1"
STAGES = ("capture", "validate", "project", "simulate", "price", "rank", "card", "freeze", "grade", "audit")
ND = NormalDist()


def utcz(d):
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_z(s):
    s = str(s).strip().replace("Z", "+00:00")
    if re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d\+00:00", s):
        s = s.replace("+00:00", ":00+00:00")
    d = datetime.fromisoformat(s)
    if d.tzinfo is None:
        raise ValueError("TIME_NOT_UTC")
    return d.astimezone(timezone.utc)


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def digest(obj):
    return sha_bytes(json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def ct_time(tip):
    return parse_z(tip).astimezone(CT).strftime("%-I:%M %p CT")


# ====================================================================== capture
CREDENTIAL_KEYS = re.compile(r"(cookie|password|passwd|token|authorization|session|bearer|secret)", re.I)


def infer_provenance(path, rows):
    """Label by declared source columns, then by file name. Never AUTHENTICATED from a CSV."""
    labels = {str(r.get("provenance") or "").strip() for r in rows} - {""}
    if labels:
        mapped = {C.UPSTREAM_PROVENANCE.get(x) for x in labels} - {None}
        if len(mapped) == 1:
            return mapped.pop()
        return "UNAUTHENTICATED_CSV"   # mixed file; every row still carries its own label
    srcs = {str(r.get("source") or "").lower() for r in rows}
    name = Path(path).name.lower()
    if any("operator" in s for s in srcs) or "operator_transcript" in name:
        return "UNAUTHENTICATED_OPERATOR_TRANSCRIPT"
    if "pdf" in name or any(str(r.get("source_pdf_time_ct") or "").strip() for r in rows[:5]):
        return "UNAUTHENTICATED_PDF"
    if "screenshot" in name or any("screenshot" in s for s in srcs):
        return "UNAUTHENTICATED_SCREENSHOT"
    return "UNAUTHENTICATED_CSV"


class BoardFileCapture:
    """Committed board CSV (PDF / screenshot / operator transcript / hand CSV). Read-only."""
    adapter = "board_file"

    def __init__(self, path, captured_utc, provenance=None):
        self.path, self.captured_utc, self.provenance = Path(path), captured_utc, provenance

    def capture(self):
        raw = self.path.read_bytes()
        rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        prov = self.provenance or infer_provenance(self.path, rows)
        if prov == C.AUTHENTICATED:
            raise ValueError("PROVENANCE_AUTHENTICATED_REQUIRES_DK_MANIFEST")
        if prov not in C.PROVENANCE:
            raise ValueError("PROVENANCE_UNKNOWN")
        return {"rows": rows, "provenance": prov, "source_sha256": sha_bytes(raw), "bytes": len(raw),
                "path": str(self.path), "board_captured_utc": self.captured_utc, "adapter": self.adapter}


AUTH_CAPTURE_REQUIREMENTS = {
    "format": "DK_AUTH_CAPTURE_V1",
    "what_an_authenticated_capture_must_provide": [
        "raw response bytes of each DraftKings event/market payload, stored PRIVATELY (encrypted artifact), "
        "with sha256 and byte length recorded in the manifest",
        "per row: dk_event_id, dk_market_id, dk_selection_id for BOTH sides, period, market type, line, both "
        "American prices, captured_utc (exact request time, UTC), event start time (UTC), live/in-play flag",
        "team names exactly as DK displays them plus home/away designation from the payload",
        "the capturing session's observation clock (request start and response time)",
    ],
    "never_in_repo_or_manifest": ["passwords", "session cookies", "bearer/auth tokens", "geo/KYC data"],
    "session_requirements": [
        "a signed-in DraftKings account in a legal state (geolocation check passes) in the box browser; "
        "the user completes sign-in and any 2FA themselves",
        "capture runs read-only (no bet slip interaction)",
    ],
    "fallbacks_still_supported": ["UNAUTHENTICATED_PDF", "UNAUTHENTICATED_SCREENSHOT", "UNAUTHENTICATED_CSV",
                                  "UNAUTHENTICATED_OPERATOR_TRANSCRIPT"],
}


class AuthenticatedDkCapture:
    """Manifest-backed authenticated capture. Verifies hashes; refuses credential material."""
    adapter = "dk_authenticated"

    def __init__(self, manifest_path):
        self.manifest_path = Path(manifest_path) if manifest_path else None

    def capture(self):
        if not self.manifest_path or not self.manifest_path.is_file():
            raise ValueError("DK_AUTH_CAPTURE_NOT_CONFIGURED")
        raw = self.manifest_path.read_bytes()
        if CREDENTIAL_KEYS.search(raw.decode("utf-8", "replace")):
            raise ValueError("CREDENTIAL_MATERIAL_PRESENT")
        man = json.loads(raw)
        if man.get("format") != AUTH_CAPTURE_REQUIREMENTS["format"]:
            raise ValueError("DK_AUTH_MANIFEST_FORMAT")
        base = self.manifest_path.parent
        for f in man.get("raw_files", []):
            b = (base / f["path"]).read_bytes()
            if sha_bytes(b) != f.get("sha256") or len(b) != f.get("bytes"):
                raise ValueError("DK_AUTH_RAW_HASH_MISMATCH")
        rows_raw = (base / man["rows_path"]).read_bytes()
        if sha_bytes(rows_raw) != man.get("rows_sha256"):
            raise ValueError("DK_AUTH_ROWS_HASH_MISMATCH")
        rows = list(csv.DictReader(io.StringIO(rows_raw.decode("utf-8-sig"))))
        for r in rows:
            if not (r.get("dk_event_id") and r.get("dk_market_id") and r.get("price_a") and r.get("price_b")):
                raise ValueError("DK_AUTH_ROW_MISSING_IDS_OR_SIDE")
        return {"rows": rows, "provenance": C.AUTHENTICATED, "source_sha256": sha_bytes(rows_raw),
                "bytes": len(rows_raw), "path": str(base / man["rows_path"]),
                "board_captured_utc": man["captured_utc"], "adapter": self.adapter}


def _int_price(v):
    return NUM.strict_price(v)      # None | int | "BAD"; never raises


def _num(v):
    return NUM.strict_line(v)       # None | finite float | "BAD"; never raises


SIDES = {"SPREAD": ("home", "away"), "ALT_SPREAD": ("home", "away"), "ML": ("home", "away")}


def normalize_quotes(cap, *, totals_order_verified):
    """Board rows -> MarketQuote (one per input row, input order kept) + Rejection rows."""
    quotes, rejects = [], []
    for i, r in enumerate(cap["rows"]):
        fam = C.catalog_market(r.get("period", "FG"), r.get("market"))
        prov = cap["provenance"]
        if fam is None:
            rejects.append(C.Rejection("capture", str(r.get("period")), str(r.get("market")),
                                       "UNSUPPORTED_MARKET", board_index=i, provenance=prov))
            continue
        period, market = fam
        label = str(r.get("provenance") or "").strip()
        if label:
            if label not in C.UPSTREAM_PROVENANCE:
                rejects.append(C.Rejection("capture", period, market, "PROVENANCE_UNVERIFIED",
                                           f"unknown upstream label {label}", i, provenance=prov)); continue
            if C.UPSTREAM_PROVENANCE[label] is None or str(r.get("authenticated") or "0").strip() not in ("0", ""):
                rejects.append(C.Rejection("capture", period, market, "PROVENANCE_UNVERIFIED",
                                           f"{label}: authenticated claim without a DK manifest", i,
                                           provenance=prov)); continue
            prov = C.UPSTREAM_PROVENANCE[label]
        line, pa, pb = _num(r.get("line")), _int_price(r.get("price_a")), _int_price(r.get("price_b"))
        sa, sb = SIDES.get(market, ("over", "under"))
        if market.endswith("_AT_LEAST"):
            sa, sb = "yes", "no"
        cap_utc = str(r.get("captured_utc") or cap["board_captured_utc"] or "").strip() or None
        tip = str(r.get("tip_utc") or r.get("start_utc") or "").strip() or None
        live = False
        try:
            live = bool(cap_utc and tip and parse_z(cap_utc) >= parse_z(tip))
        except ValueError:
            pass
        order = str(r.get("totals_order") or "").strip().lower()
        if market in ("TOTAL", "ALT_TOTAL", "TT_HOME", "TT_AWAY") and order == "under_over" \
                and isinstance(pa, int) and isinstance(pb, int):
            pa, pb = pb, pa
        q = C.MarketQuote(board_index=i, period=period, market=market, home=str(r.get("home") or ""),
                          away=str(r.get("away") or ""), line=line if line != "BAD" else None,
                          price_a=pa if isinstance(pa, int) else None,
                          price_b=pb if isinstance(pb, int) else None, side_a=sa, side_b=sb,
                          dk_event_id=str(r.get("dk_event_id") or r.get("event_id") or "").strip() or None,
                          dk_market_id=str(r.get("dk_market_id") or "").strip() or None,
                          captured_utc=cap_utc, tip_utc=tip, live=live, provenance=prov,
                          player=str(r.get("player") or "").strip() or None,
                          source_sha256=cap["source_sha256"], source_label=label or None,
                          row_key=str(r.get("row_key") or "").strip() or None)
        quotes.append((q, {"line_bad": line == "BAD", "price_bad": "BAD" in (pa, pb),
                           "order": order, "raw": r}))
    return quotes, rejects


# ====================================================================== validate
_MATCH_CODES = {
    "home/away orientation mismatch": "ORIENTATION_MISMATCH",
    "no CBBD game within 15 min of board tip time": "TIP_MISMATCH",
    "board tip time unparsable": "TIP_MISMATCH",
    "ambiguous CBBD game": "NO_GAME_MATCH",
    "no unique CBBD game for names": "NO_GAME_MATCH",
    "invalid or overlapping board team identities": "NO_GAME_MATCH",
}
LADDERS = ("ALT_SPREAD", "ALT_TOTAL", "TT_HOME", "TT_AWAY")
OU_MARKETS = ("TOTAL", "ALT_TOTAL", "TT_HOME", "TT_AWAY")


def validate(quotes, slate_rows, freeze_utc, *, totals_order_verified, match, adapters,
             max_quote_age_hours=24.0, as_of_utc=None):
    """Gate every quote. Returns (accepted [(quote, game_id)], rejections)."""
    accepted, rejects, realigned = [], [], []
    freeze = parse_z(freeze_utc)
    pre = []
    for q, meta in quotes:
        def rej(code, detail=""):
            rejects.append(C.Rejection("validate", q.period, q.market, code, detail, q.board_index,
                                       f"{q.away} @ {q.home}", q.provenance))
        if q.live:
            rej("LIVE_GAME"); continue
        if q.period == "2H_HALFTIME_ADJUSTED":
            rej("HALFTIME_ADJUSTED_IS_LIVE"); continue
        if q.period != "FG" and "halves" not in adapters:
            rej("PERIOD_NOT_IMPLEMENTED", f"{q.period}: models/cbb/halves adapter not landed"); continue
        if q.market.startswith("PLAYER_") and "players" not in adapters:
            note = str(meta["raw"].get("note") or meta["raw"].get("notes") or "")
            rej("PLAYER_MODEL_NOT_IMPLEMENTED", "player team not established" if "team not established" in note else "")
            continue
        if meta["price_bad"]:
            rej("PRICE_INVALID"); continue
        if q.price_a is None or q.price_b is None:
            rej("ONE_SIDED_QUOTE"); continue
        if meta["line_bad"] or (q.market != "ML" and q.line is None):
            rej("LINE_INVALID"); continue
        if q.market in OU_MARKETS and not (meta["order"] in ("over_under", "under_over") or totals_order_verified):
            rej("TOTALS_ORDER_UNVERIFIED"); continue
        try:
            cap = parse_z(q.captured_utc)
        except (TypeError, ValueError):
            rej("STALE_QUOTE", "capture time missing"); continue
        if cap > freeze:
            rej("QUOTE_AFTER_FREEZE"); continue
        if (freeze - cap).total_seconds() > max_quote_age_hours * 3600:
            rej("STALE_QUOTE"); continue
        g, why = match(slate_rows, q.home, q.away, meta["raw"])
        if not g and why == "home/away orientation mismatch" and q.market in ("TOTAL", "ALT_TOTAL") \
                and q.dk_event_id and q.tip_utc:
            # Orientation-invariant game totals only, at a confirmed neutral site, with a dated DK event
            # (mirrors cbb_run_it.align_neutral_totals). Line and over/under prices are never changed.
            g2, _ = match(slate_rows, q.away, q.home, meta["raw"])
            if g2 and g2.get("neutral") == "1":
                g, why = g2, None
                realigned.append(q.board_index)
        if not g:
            rej(_MATCH_CODES.get(why, "NO_GAME_MATCH"), why or ""); continue
        if cap >= parse_z(g["tipoff_utc"]):
            rej("LIVE_GAME", "capture at/after slate tip"); continue
        if as_of_utc and parse_z(g["tipoff_utc"]) <= parse_z(as_of_utc):
            rej("STARTED_BEFORE_AS_OF", f"tip {g['tipoff_utc']} <= as-of {as_of_utc}"); continue
        if q.market in LADDERS and not q.dk_event_id:
            rej("MISSING_DK_EVENT_ID", "ladder/team-total rows require a DK event id"); continue
        pre.append((q, g["game_id"]))
    ev_games, game_evs = defaultdict(set), defaultdict(set)
    for q, gid in pre:
        if q.dk_event_id:
            ev_games[q.dk_event_id].add(gid); game_evs[gid].add(q.dk_event_id)
    keyed = defaultdict(list)
    for q, gid in pre:
        if q.dk_event_id and (len(ev_games[q.dk_event_id]) > 1 or len(game_evs[gid]) > 1):
            rejects.append(C.Rejection("validate", q.period, q.market, "DK_EVENT_ID_CONFLICT", "",
                                       q.board_index, f"{q.away} @ {q.home}", q.provenance)); continue
        keyed[NUM.semantic_identity(gid, q.period, q.market, q.line, q.player)].append(q)
    for key, qs in keyed.items():
        if len({(q.price_a, q.price_b) for q in qs}) > 1:
            for q in qs:
                rejects.append(C.Rejection("validate", q.period, q.market, "DUPLICATE_QUOTE",
                                           "conflicting prices for identical line; all copies withheld",
                                           q.board_index, f"{q.away} @ {q.home}", q.provenance))
            continue
        for dup in qs[1:]:
            rejects.append(C.Rejection("validate", dup.period, dup.market, "DUPLICATE_QUOTE",
                                       "identical duplicate; first kept", dup.board_index,
                                       f"{dup.away} @ {dup.home}", dup.provenance))
        accepted.append((qs[0], key[0]))
    # orientation: main spread sign must agree with the moneyline favourite (home perspective)
    by_game = defaultdict(dict)
    for q, gid in accepted:
        if q.period == "FG" and q.market in ("SPREAD", "ML"):
            by_game[gid][q.market] = q
    bad = set()
    for gid, d in by_game.items():
        if "SPREAD" in d and "ML" in d and d["SPREAD"].line not in (None, 0):
            ph, pa_, _ = NM.no_vig(d["ML"].price_a, d["ML"].price_b)
            if (ph > pa_) != (d["SPREAD"].line < 0) and abs(ph - pa_) > 0.04:
                bad.add(gid)
    out = []
    for q, gid in accepted:
        if gid in bad and q.period == "FG" and q.market in ("SPREAD", "ML", "ALT_SPREAD"):
            rejects.append(C.Rejection("validate", q.period, q.market, "ORIENTATION_INCONSISTENT",
                                       "spread sign disagrees with moneyline favourite", q.board_index,
                                       f"{q.away} @ {q.home}", q.provenance)); continue
        out.append((q, gid))
    validate.last_neutral_total_realignments = realigned
    return out, rejects


# ====================================================================== project adapters
def market_view(gid, accepted, cfg):
    """Vegas/no-vig projection from the main FG spread and total (never feeds the independent view)."""
    sp = next((q for q, g in accepted if g == gid and q.period == "FG" and q.market == "SPREAD"), None)
    to = next((q for q, g in accepted if g == gid and q.period == "FG" and q.market == "TOTAL"), None)
    if sp is None or to is None:
        return C.Projection(gid, "MARKET_NOVIG", None, None, None, None, None, None, "dk_board_novig",
                            "NO_MARKET", "NO_QUOTE:main spread and total both required")
    ph, _, _ = NM.no_vig(sp.price_a, sp.price_b)
    po, _, _ = NM.no_vig(to.price_a, to.price_b)
    m = -sp.line + cfg["sd_margin"] * ND.inv_cdf(min(max(ph, 1e-6), 1 - 1e-6))
    t = to.line + cfg["sd_total"] * ND.inv_cdf(min(max(po, 1e-6), 1 - 1e-6))
    return C.Projection(gid, "MARKET_NOVIG", (t + m) / 2, (t - m) / 2, m, t, cfg["sd_margin"],
                        cfg["sd_total"], "dk_board_novig", "PROJECTED")


def hybrid_view(indep, mkt, w):
    if indep.status != "PROJECTED" or mkt.status != "PROJECTED":
        return C.Projection(indep.game_id, "HYBRID", None, None, None, None, None, None, "blend",
                            "NO_MARKET" if indep.status == "PROJECTED" else "PASS", indep.reason_code, w)
    f = lambda a, b: w * a + (1 - w) * b
    return C.Projection(indep.game_id, "HYBRID", f(indep.home_points, mkt.home_points),
                        f(indep.away_points, mkt.away_points), f(indep.margin, mkt.margin),
                        f(indep.total, mkt.total), indep.sd_margin, indep.sd_total, "blend",
                        C.HYBRID_UNVALIDATED, None, w)


def challenger_views(challenger, games, slate_ids, market_views):
    """CHALLENGER view per game plus the validation-selected HYBRID_CHALLENGER view (margin weight = spread
    weight 0, total weight 0.125 at the open). Failures are PASS rows with a reason code."""
    proj, views, hyb = {}, {}, {}
    ws, wt = CHALLENGER_BLEND_W_OPEN["SPREAD"], CHALLENGER_BLEND_W_OPEN["TOTAL"]
    for gid in slate_ids:
        g = games[gid]
        try:
            r = challenger.project(g["home_id"], g["away_id"], g["neutral"], g.get("venue_id"))
        except ValueError as exc:
            views[gid] = C.Projection(gid, "CHALLENGER", None, None, None, None, None, None, "fullgame_FG1C",
                                      "PASS", f"CHALLENGER_PASS:{exc}")
            hyb[gid] = C.Projection(gid, "HYBRID_CHALLENGER", None, None, None, None, None, None, "logit_blend",
                                    "PASS", f"CHALLENGER_PASS:{exc}")
            continue
        proj[gid] = r
        dm, dt = challenger.dists["margin"][r["phase"]], challenger.dists["total"][r["phase"]]
        views[gid] = C.Projection(gid, "CHALLENGER", r["home_points"], r["away_points"], r["margin"], r["total"],
                                  dm.sd, dt.sd, f"fullgame_FG1C:{r['site']}:phase{r['phase']}", "PROJECTED")
        mk = market_views.get(gid)
        if mk is None or mk.status != "PROJECTED":
            hyb[gid] = C.Projection(gid, "HYBRID_CHALLENGER", None, None, None, None, None, None, "logit_blend",
                                    "NO_MARKET", "NO_QUOTE:main spread and total both required")
            continue
        m = ws * r["margin"] + (1 - ws) * mk.margin
        t = wt * r["total"] + (1 - wt) * mk.total
        hyb[gid] = C.Projection(gid, "HYBRID_CHALLENGER", (t + m) / 2, (t - m) / 2, m, t, dm.sd, dt.sd,
                                f"validation_selected_open_w_spread{ws:g}_total{wt:g}", C.HYBRID_UNVALIDATED,
                                None, wt)
    return proj, views, hyb


def projections_from_card(card, cfg, source="frozen_native_cbbd"):
    """Production adapter: read the frozen card's own projections (no recomputation)."""
    out = {}
    for r in card["rows"]:
        p = r.get("projection")
        if r["status"] != "PROJECTED" or not p:
            out[r["game_id"]] = C.Projection(r["game_id"], "INDEPENDENT", None, None, None, None, None, None,
                                             source, "PASS", "GAME_NOT_PROJECTED:" + str(r.get("pass_reason")))
            continue
        out[r["game_id"]] = C.Projection(r["game_id"], "INDEPENDENT", p["home_points"], p["away_points"],
                                         p["margin"], p["total"], cfg["sd_margin"], cfg["sd_total"],
                                         source, "PROJECTED")
    return out


HALVES_PERIOD = {"1H": "H1", "2H_PREGAME": "H2"}
HALVES_MARKET = {"SPREAD": "SPREAD", "ALT_SPREAD": "SPREAD", "TOTAL": "TOTAL", "ALT_TOTAL": "TOTAL",
                 "TT_HOME": "TEAM_TOTAL_HOME", "TT_AWAY": "TEAM_TOTAL_AWAY", "ML": "MONEYLINE"}
# The board's half moneylines are two-way; DK's tied-half settlement is not captured on the board,
# so the runner states its assumption explicitly (the halves module has no default by design).
HALVES_ML_TIE_RULE = "TIE_PUSH"
HALVES_CAVEAT = ("RESEARCH: half means come from models/cbb/halves (cbb-halves-v1-research), scaled to its "
                 "fitting research projector, not the production model; its totals ran ~1.1-1.4 points UNDER on "
                 "the held-out 2026 season; margin/total/period correlation not modelled; half moneylines assume "
                 "TIE_PUSH (unverified DK rule).")


def load_halves(path=None):
    """Import the halves stream (models/cbb/halves) if present, optionally from another checkout."""
    if path:
        sys.path.insert(0, str(Path(path)))
    try:
        from halves import halves_model as HM, halves_pricing as HP
    except ImportError:
        return None
    if not (hasattr(HM, "project_period") and hasattr(HP, "price_half_market")):
        return None
    coef = HM.load_coefficients()
    return {"HM": HM, "HP": HP, "coef": coef, "sha256": coef.get("_sha256"), "version": coef.get("model_version")}


# ---------------------------------------------------------------- fullgame CHALLENGER (models/cbb/fullgame)
FG1_TUNED = {"carry": 0.85, "carry_pace": 0.7, "lam": 4, "lam_pace": 4, "half_life": 40, "hca_lam": 400}
# Blend weights chosen by the fullgame stream's chronological validation (2024-25) and scored once on
# 2026-27: model weight 0 at the close for every market; at the open ML 0.125, spread 0, total 0.125.
# The Nov 25 board is a morning (open-side) capture, so the OPEN selection is used and labelled.
CHALLENGER_BLEND_W_OPEN = {"ML": 0.125, "SPREAD": 0.0, "ALT_SPREAD": 0.0, "TOTAL": 0.125, "ALT_TOTAL": 0.125,
                           "TT_HOME": 0.125, "TT_AWAY": 0.125}
CHALLENGER_CAVEAT = ("CHALLENGER (research): FG1C from models/cbb/fullgame (schedule-adjusted ridge + prior-season prior + "
                     "recency + verified-venue HCA + chronological de-bias; Student-t residual pricing). Not production; "
                     "the frozen model stays the default. Hybrid = logit blend at the validation-selected model weight "
                     "(open: ML 0.125 / spread 0 / total 0.125; at the close validation chose 0 everywhere). Team-total "
                     "hybrid weight 0.125 is the runner's assumption (not separately validated).")


class Challenger:
    """Per-game FG1C projection + fullgame.pricing probabilities, read from a fullgame checkout."""

    def __init__(self, fullgame_root, games_csv, finals_json, summary_json, season, freeze):
        import importlib.util
        root = Path(fullgame_root)
        if str(root) not in sys.path:
            sys.path.append(str(root))              # appended: never shadows the runner's own modules
        from fullgame import ratings as FR, pricing as FP, backtest as FB, evaluate as FE, sdv_loader as FL
        spec = importlib.util.spec_from_file_location("cbb_pricing_fullgame_challenger", root / "cbb_pricing.py")
        CPR = importlib.util.module_from_spec(spec); spec.loader.exec_module(CPR)
        self.module_paths = {"fullgame": str(Path(FR.__file__).parent), "cbb_pricing": str(root / "cbb_pricing.py")}
        if not hasattr(CPR, "logit_blend"):
            raise ImportError("cbb_pricing.logit_blend missing (fullgame branch not on path)")
        self.FR, self.FP, self.FE, self.logit_blend = FR, FP, FE, CPR.logit_blend
        self.ev_sanity_audit = getattr(CPR, "ev_sanity_audit", None)
        summ = json.loads(Path(summary_json).read_text())
        finals = {int(k): tuple(v) for k, v in json.loads(Path(finals_json).read_text()).items()}
        prev = finals[season - 1]
        hist = [finals[k][3] for k in finals if k < season]
        cfg = FB.fg1_config(prev, sum(hist) / len(hist), FG1_TUNED)
        f = FR.AdjustedFit(lam=cfg["lam"], lam_pace=cfg["lam_pace"], half_life=cfg["half_life"], prior=cfg["prior"],
                           hca_prior=cfg["hca_prior"], hca_lam=cfg["hca_lam"], mu0=cfg["mu0"], pi0=cfg["pi0"])
        f.default_prior = cfg["new_team"]
        games = FL.read_csv(games_csv)
        self.home_venue = {}
        for g in games:
            if g.get("home_venue_id"):
                self.home_venue[g["home"]] = g["home_venue_id"]
        prior = [g for g in games if FR.usable(g) and g.get("tip_utc")
                 and parse_z(g["tip_utc"]) + timedelta(hours=3) <= freeze]
        today = freeze.astimezone(CT).date()
        f.fit(prior, today)
        self.f, self.n = f, Counter(t for g in prior for t in (g["home"], g["away"]))
        self.recal = summ["recalibration"][str(season)]
        d = summ["dists_2027"]["FG1C"] if season == 2027 else None
        if d is None:
            raise ValueError("CHALLENGER_DISTS_ONLY_FOR_2027")
        self.dists = {k: {int(i) if i != "all" else i: FP.Dist(v["loc"], v["sd"], v["df"]) for i, v in d[k].items()}
                      for k in ("margin", "total", "team")}
        self.meta = {"prior_games": len(prior), "max_prior_tip_utc": max(g["tip_utc"] for g in prior),
                     "games_csv_sha256": sha_bytes(Path(games_csv).read_bytes()),
                     "summary_sha256": sha_bytes(Path(summary_json).read_bytes()), "hca_fit": f.h, "params": FG1_TUNED}

    def project(self, home_id, away_id, neutral, venue_id):
        if neutral is None:
            raise ValueError("NEUTRAL_UNKNOWN")
        if neutral:
            site = "NEUTRAL"
        else:
            hv = self.home_venue.get(home_id)
            site = self.FR.HOME if (venue_id and hv and str(venue_id) == str(hv)) else "UNVERIFIED"
        if not (self.f.has(home_id) and self.f.has(away_id)):
            raise ValueError("CHALLENGER_TEAM_UNRATED")
        hp, ap, poss = self.f.project(home_id, away_id, site)
        nh, na = self.n.get(home_id, 0), self.n.get(away_id, 0)
        r = self.FE.apply_recalibration({"margin": hp - ap, "total": hp + ap, "possessions": poss}, self.recal, min(nh, na))
        ph = self.FP.phase_of(nh, na)
        return {**r, "site": site, "phase": ph, "n_min": min(nh, na)}

    def probs(self, proj, market, line):
        """(p_a, p_push, p_b) in the runner's side order (home/over first)."""
        ph = proj["phase"]
        if market == "ML":
            pa_, pb_ = self.FP.ml_probs(self.dists["margin"][ph], proj["margin"]); return pa_, 0.0, pb_
        if market in ("SPREAD", "ALT_SPREAD"):
            return self.FP.line_probs(self.dists["margin"][ph], proj["margin"], -line)
        if market in ("TOTAL", "ALT_TOTAL"):
            return self.FP.line_probs(self.dists["total"][ph], proj["total"], line)
        mu = proj["home_points"] if market == "TT_HOME" else proj["away_points"]
        return self.FP.line_probs(self.dists["team"][ph], mu, line)

    def audit(self, ev, price, p_model, p_novig):
        return self.FP.ev_audit({"ev": ev, "price": price, "p_model": p_model, "p_novig": p_novig})


def load_adapter_flags(requested, loaded=None):
    """Adapter status by flag. ``loaded`` maps a stream name to an object the caller already built from
    that stream's checkout (halves: load_halves(); fullgame: Challenger) -> ACTIVE. Missing or failed
    streams are reported, never faked."""
    loaded = loaded or {}
    status, active = {}, set()
    for name in ("fullgame", "halves", "players"):
        if name not in requested:
            status[name] = "OFF"
            continue
        obj = loaded.get(name)
        if isinstance(obj, str):
            status[name] = obj                      # failure reason from the loader
        elif obj is not None:
            status[name] = "ACTIVE" if name != "fullgame" else "ACTIVE_CHALLENGER_DEFAULT_STAYS_FROZEN"
            active.add(name)
        else:
            status[name] = "ADAPTER_NOT_LANDED"
    return status, active


# ---------------------------------------------------------------- public replay inputs (ESPN)
ESPN = "https://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball"


def _espn_get(url, p, fetch):
    import urllib.request
    if p.exists():
        return p.read_bytes()
    if not fetch:
        raise FileNotFoundError(str(p))
    b = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "SportsEdgeResearchCapture/1.0"}),
                               timeout=40).read()
    p.write_bytes(b); (p.parent / (p.name + ".obs")).write_text(utcz(datetime.now(timezone.utc)))
    return b


def espn_capture(day_from, day_to, raw_dir, fetch=True, refresh_days=()):
    """Public ESPN scoreboards + box summaries for completed games (no credential). Raw bytes stay in
    raw_dir (private, not committed); derived rows carry each file's sha256."""
    raw_dir = Path(raw_dir); (raw_dir / "sb").mkdir(parents=True, exist_ok=True)
    (raw_dir / "sum").mkdir(parents=True, exist_ok=True)
    d, days = day_from, []
    while d <= day_to:
        k = d.strftime("%Y%m%d"); days.append(k)
        p = raw_dir / "sb" / f"{k}.json"
        if k in refresh_days and p.exists() and fetch:
            p.rename(p.with_suffix(f".json.{int(datetime.now().timestamp())}.prev"))
        b = _espn_get(f"{ESPN}/scoreboard?dates={k}&groups=50&limit=500", p, fetch)
        for e in json.loads(b).get("events", []):
            if e["status"]["type"].get("completed"):
                try:
                    _espn_get(f"{ESPN}/summary?event={e['id']}", raw_dir / "sum" / f"{e['id']}.json", fetch)
                except (OSError, ValueError):
                    pass
        d += timedelta(days=1)
    return days


def espn_games(raw_dir, days):
    """Derived compact game rows (+ box possessions estimate) with per-file hashes."""
    raw_dir = Path(raw_dir)
    games, files = {}, {}
    for k in days:
        p = raw_dir / "sb" / f"{k}.json"
        b = p.read_bytes(); files[f"sb/{k}.json"] = sha_bytes(b)
        for e in json.loads(b).get("events", []):
            c = (e.get("competitions") or [{}])[0]
            comp = {x["homeAway"]: x for x in c.get("competitors", []) if x.get("homeAway") in ("home", "away")}
            if set(comp) != {"home", "away"}:
                continue
            row = {"id": str(e["id"]), "tip_utc": utcz(parse_z(c.get("date") or e["date"])),
                   "completed": bool(e["status"]["type"].get("completed")),
                   "state": e["status"]["type"].get("name"),
                   "neutral": c.get("neutralSite") if type(c.get("neutralSite")) is bool else None,
                   "venue": (c.get("venue") or {}).get("fullName"),
                   "venue_id": (c.get("venue") or {}).get("id"),
                   "home_id": str(comp["home"]["team"]["id"]), "away_id": str(comp["away"]["team"]["id"]),
                   "home": comp["home"]["team"].get("location"), "away": comp["away"]["team"].get("location"),
                   "home_alt": [comp["home"]["team"].get(k2) for k2 in ("shortDisplayName", "displayName")],
                   "away_alt": [comp["away"]["team"].get(k2) for k2 in ("shortDisplayName", "displayName")],
                   "home_score": None, "away_score": None, "possessions": None, "h1": None}
            if row["completed"]:
                try:
                    row["home_score"], row["away_score"] = int(comp["home"]["score"]), int(comp["away"]["score"])
                    ls = [[int(float(x.get("value", x.get("displayValue")))) for x in comp[s].get("linescores", [])]
                          for s in ("home", "away")]
                    if all(len(l) >= 2 for l in ls):
                        row["h1"] = [ls[0][0], ls[1][0]]
                except (TypeError, ValueError, KeyError):
                    row["completed"] = False
            games[row["id"]] = row
    for gid, row in games.items():
        p = raw_dir / "sum" / f"{gid}.json"
        if not row["completed"] or not p.exists():
            continue
        b = p.read_bytes(); files[f"sum/{gid}.json"] = sha_bytes(b)
        try:
            ests = []
            for t in json.loads(b)["boxscore"]["teams"]:
                st = {s["name"]: s.get("displayValue") for s in t.get("statistics", [])}
                fga = int(st["fieldGoalsMade-fieldGoalsAttempted"].split("-")[1])
                fta = int(st["freeThrowsMade-freeThrowsAttempted"].split("-")[1])
                orb, tov = int(st["offensiveRebounds"]), int(st.get("totalTurnovers") or st["turnovers"])
                ests.append(fga - orb + tov + 0.475 * fta)
            if len(ests) == 2:
                row["possessions"] = round(sum(ests) / 2, 2)
        except (KeyError, ValueError, TypeError, IndexError):
            pass
    return games, files


def d1_filter(prior, min_games=3):
    """Drop games involving teams with fewer than ``min_games`` prior finals in the D1 scoreboard feed
    (in practice non-D1 visitors that appear only once or twice). Iterated to a fixed point."""
    keep = list(prior)
    while True:
        n = Counter(t for g in keep for t in (g["home_id"], g["away_id"]))
        nxt = [g for g in keep if n[g["home_id"]] >= min_games and n[g["away_id"]] >= min_games]
        if len(nxt) == len(keep):
            return keep
        keep = nxt


def public_ratings(prior, season, shrink_games=2.0, iters=25):
    """Opponent- and venue-adjusted efficiencies from prior finals only (public reconstruction,
    disclosed): additive opponent adjustment, a pooled home edge h (points per 100 possessions,
    re-estimated each iteration from non-neutral games) removed half from each side, then shrinkage
    toward the league mean by ``shrink_games``.

    Raises ValueError("RATINGS_INSUFFICIENT_SAMPLE") with a coverage diagnostic when the filtered
    prior set is empty. Does not invent ratings or lower the min-games threshold.
    """
    if not prior:
        raise ValueError("RATINGS_INSUFFICIENT_SAMPLE:no_prior_games_after_d1_filter")
    per = defaultdict(list)
    for g in prior:
        p = g["possessions"]
        v = 0 if g["neutral"] is not False else 1
        per[g["home_id"]].append((g["away_id"], 100 * g["home_score"] / p, 100 * g["away_score"] / p, v))
        per[g["away_id"]].append((g["home_id"], 100 * g["away_score"] / p, 100 * g["home_score"] / p, -v))
    if not per:
        raise ValueError("RATINGS_INSUFFICIENT_SAMPLE:no_teams_after_build")
    lg = mean(o for v in per.values() for _, o, _, _ in v)
    off = {t: lg for t in per}; de = {t: lg for t in per}; h = 0.0
    for _ in range(iters):
        no = {t: mean(o - (de[opp] - lg) - v_ * h / 2 for opp, o, _, v_ in x) for t, x in per.items()}
        nd = {t: mean(d - (off[opp] - lg) + v_ * h / 2 for opp, _, d, v_ in x) for t, x in per.items()}
        off, de = no, nd
        res = [(o - d) - ((off[t] + de[opp]) - (off[opp] + de[t])) for t, x in per.items()
               for opp, o, d, v_ in x if v_ == 1]
        h = mean(res) if res else 0.0
    body = []
    for t, v in sorted(per.items(), key=lambda x: int(x[0])):
        n = len(v)
        o = min(max((n * off[t] + shrink_games * lg) / (n + shrink_games), 61.0), 159.0)
        d = min(max((n * de[t] + shrink_games * lg) / (n + shrink_games), 61.0), 159.0)
        body.append({"season": season, "teamId": int(t), "team": t, "offensiveRating": round(o, 3),
                     "defensiveRating": round(d, 3), "netRating": round(round(o, 3) - round(d, 3), 3), "games": n})
    public_ratings.last_home_edge_per100 = h
    return json.dumps(body, sort_keys=True).encode(), lg


def public_replay_project(games, slate_ids, season, freeze_utc, cfg):
    """Frozen native formula (cbbd_native_score_model.fit_context/project, unchanged) on ESPN data."""
    freeze = parse_z(freeze_utc)
    prior = [g for g in games.values() if g["completed"] and g["possessions"] and 40 <= g["possessions"] <= 110
             and parse_z(g["tip_utc"]) + timedelta(hours=3) <= freeze and g["home_score"] != g["away_score"]]
    n_all = len(prior)
    filtered = d1_filter(prior)
    # Early-season path: if national filter empties, still rate teams that have >=2 prior games
    # and project only matchups where both teams qualify. Does not lower the global min_games
    # used by d1_filter; this is a separate eligibility for sparse samples.
    if not filtered:
        from collections import Counter
        n = Counter(t for g in prior for t in (g["home_id"], g["away_id"]))
        eligible_teams = {t for t, c in n.items() if c >= 2}
        filtered = [g for g in prior if g["home_id"] in eligible_teams and g["away_id"] in eligible_teams]
        early = True
    else:
        early = False
    try:
        body, lg = public_ratings(filtered, season)
    except ValueError as e:
        if "RATINGS_INSUFFICIENT_SAMPLE" in str(e):
            return {}, {"reason": str(e), "prior_raw": n_all, "prior_after_filter": len(filtered), "early_season": early}, b""
        raise
    # Continue with the filtered prior for context fit
    prior = filtered
    rows = [{"game_id": g["id"], "season": season, "tipoff_utc": g["tip_utc"],
             "final_captured_utc": utcz(parse_z(g["tip_utc"]) + timedelta(hours=3)),
             "home_team_id": g["home_id"], "away_team_id": g["away_id"], "neutral": g["neutral"],
             "home_points": g["home_score"], "away_points": g["away_score"], "possessions": g["possessions"]}
            for g in prior]
    ctx = NM.fit_context(body, rows, season=season, freeze_utc=NM.stamp(freeze))
    out = {}
    for gid in slate_ids:
        g = games[gid]
        try:
            if g["neutral"] is None:
                raise NM.Pass("NEUTRAL_SITE_UNKNOWN")
            p = NM.project(ctx, g["home_id"], g["away_id"], neutral=g["neutral"], _need_sd=False)
            out[gid] = C.Projection(gid, "INDEPENDENT", p["home_points"], p["away_points"], p["margin"], p["total"],
                                    cfg["sd_margin"], cfg["sd_total"], "native_formula_public_replay", "PROJECTED")
        except NM.Pass as exc:
            out[gid] = C.Projection(gid, "INDEPENDENT", None, None, None, None, None, None,
                                    "native_formula_public_replay", "PASS", "GAME_NOT_PROJECTED:" + str(exc))
    leak = {"prior_finals_used": len(prior), "prior_finals_dropped_low_count_teams": n_all - len(prior), "max_prior_tip_utc": max((g["tip_utc"] for g in prior), default=None),
            "freeze_utc": utcz(freeze), "prior_rule": "tip + 3h <= freeze (final availability ASSUMED, not observed)",
            "ratings_sha256": sha_bytes(body), "league_ortg": lg,
            "reconstruction_home_edge_per100": getattr(public_ratings, "last_home_edge_per100", None), "hca": ctx["hca"], "fitted_sd": ctx["sd"],
            "league_pace": ctx["league_pace"], "prior_census": ctx["prior_game_census"]}
    return out, leak, body


# ====================================================================== simulate
def simulate(proj, n, seed):
    """Joint seeded draws: margin M ~ N(mu_m, sd_m), total T ~ N(mu_t, sd_t) independent; team scores
    are rounded (T+-M)/2; regulation ties go to 5-minute overtime periods drawn from the same team means
    scaled by 5/40, repeated until decided (max 4, then a seeded coin). Game, team-total and total
    outcomes share every draw."""
    rng = random.Random(f"{seed}:{proj.game_id}")
    sm, st = proj.sd_margin, proj.sd_total
    sd_team = math.sqrt(sm * sm + st * st) / 2
    hs, as_ = [], []
    for _ in range(n):
        m, t = rng.gauss(proj.margin, sm), rng.gauss(proj.total, st)
        h, a = round((t + m) / 2), round((t - m) / 2)
        k = 0
        while h == a and k < 4:
            h += round(rng.gauss(proj.home_points * 5 / 40, sd_team * math.sqrt(5 / 40)))
            a += round(rng.gauss(proj.away_points * 5 / 40, sd_team * math.sqrt(5 / 40)))
            k += 1
        if h == a:
            if rng.random() < 0.5:
                h += 1
            else:
                a += 1
        hs.append(h); as_.append(a)
    return {"home": hs, "away": as_, "n": n, "seed": f"{seed}:{proj.game_id}"}


def sim_probs(sim, market, line):
    """(p_a, p_push, p_b) from draws. Spread line is the HOME line."""
    h, a, n = sim["home"], sim["away"], sim["n"]
    if market == "ML":
        w = sum(x > y for x, y in zip(h, a)); return w / n, 0.0, 1 - w / n
    if market in ("SPREAD", "ALT_SPREAD"):
        v = [x - y + line for x, y in zip(h, a)]
    elif market in ("TOTAL", "ALT_TOTAL"):
        v = [x + y - line for x, y in zip(h, a)]
    elif market == "TT_HOME":
        v = [x - line for x in h]
    elif market == "TT_AWAY":
        v = [y - line for y in a]
    else:
        raise ValueError("SIM_MARKET_UNSUPPORTED")
    pa_ = sum(x > 0 for x in v) / n; pp = sum(x == 0 for x in v) / n
    return pa_, pp, 1 - pa_ - pp


def closed_probs(proj, market, line, cfg):
    if market == "ML":
        p = NM._cdf(proj.margin / proj.sd_margin); return p, 0.0, 1 - p
    if market in ("SPREAD", "ALT_SPREAD"):
        return NM._line_probs(proj.margin, proj.sd_margin, -line)
    if market in ("TOTAL", "ALT_TOTAL"):
        return NM._line_probs(proj.total, proj.sd_total, line)
    mu = proj.home_points if market == "TT_HOME" else proj.away_points
    return NM._line_probs(mu, proj.sd_total * cfg["team_total_sd_factor"], line)


def fair_american(p_win, p_push):
    q = p_win / (1 - p_push) if p_push < 1 else None
    if not q or q <= 0 or q >= 1:
        return None
    return int(round(-100 * q / (1 - q))) if q >= 0.5 else int(round(100 * (1 - q) / q))


# ====================================================================== price / rank
def price(accepted, projections, sims, w, cfg, halves=None, challenger=None, challenger_proj=None):
    priced, rejects, parity, half_cache = [], [], [], {}
    challenger_proj = challenger_proj or {}
    for q, gid in accepted:
        pj = projections.get(gid)
        if pj is None or pj.status != "PROJECTED":
            rejects.append(C.Rejection("price", q.period, q.market, "GAME_NOT_PROJECTED",
                                       pj.reason_code if pj else "", q.board_index, gid, q.provenance)); continue
        src = "SIMULATION"
        if q.period != "FG":
            if not halves or q.period not in HALVES_PERIOD:
                rejects.append(C.Rejection("price", q.period, q.market, "PERIOD_NOT_IMPLEMENTED", "",
                                           q.board_index, gid, q.provenance)); continue
            try:
                key = (gid, q.period)
                if key not in half_cache:
                    half_cache[key] = halves["HM"].project_period(HALVES_PERIOD[q.period], pj.home_points,
                                                                  pj.away_points, coefficients=halves["coef"])
                d = half_cache[key]
                hm = HALVES_MARKET[q.market]
                tie = HALVES_ML_TIE_RULE if hm == "MONEYLINE" else None
                if hm == "SPREAD":
                    ra = halves["HP"].price_half_market(d, market=hm, side="home", line=q.line, tie_rule=tie)
                    rb = halves["HP"].price_half_market(d, market=hm, side="away", line=-q.line, tie_rule=tie)
                else:
                    sa_, sb_ = ("home", "away") if hm == "MONEYLINE" else ("over", "under")
                    ra = halves["HP"].price_half_market(d, market=hm, side=sa_, line=q.line, tie_rule=tie)
                    rb = halves["HP"].price_half_market(d, market=hm, side=sb_, line=q.line, tie_rule=tie)
            except (ValueError, KeyError, TypeError) as exc:
                rejects.append(C.Rejection("price", q.period, q.market, "PERIOD_NOT_IMPLEMENTED",
                                           f"halves adapter refused: {exc}", q.board_index, gid, q.provenance)); continue
            pa_, pp, pb_ = ra["p_win"], ra["p_push"], rb["p_win"]
            src = f"HALVES_{halves['version']}"
        else:
            pa_, pp, pb_ = sim_probs(sims[gid], q.market, q.line)
            ca, _, _ = closed_probs(pj, q.market, q.line, cfg)
            parity.append({"game_id": gid, "market": q.market, "line": q.line, "sim_a": pa_, "closed_a": ca,
                           "abs_diff": abs(pa_ - ca)})
        ma, mb, _ = NM.no_vig(q.price_a, q.price_b)
        cprobs = None
        if challenger and q.period == "FG" and gid in challenger_proj:
            cprobs = challenger.probs(challenger_proj[gid], q.market, q.line)
        for side, p, pm, price_ in ((q.side_a, pa_, ma, q.price_a), (q.side_b, pb_, mb, q.price_b)):
            pc = evc = None
            flags = ()
            if cprobs is not None:
                pc = cprobs[0] if side == q.side_a else cprobs[2]
                cpush = cprobs[1]
                evc = NM.ev_per_unit(pc, cpush, price_)
                wc = CHALLENGER_BLEND_W_OPEN.get(q.market, 0.0)
                ph = challenger.logit_blend(pc, pm, wc, push=cpush)
                hmethod = f"LOGIT_BLEND_CHALLENGER_W{wc:g}_VALIDATION_SELECTED_OPEN"
                flags = tuple(challenger.audit(evc, price_, pc, pm))
            else:
                ph = PR.blend(p, pm, w, push=pp)
                hmethod = f"LINEAR_BLEND_FROZEN_W{w:g}_UNVALIDATED"
            ev_frozen = NM.ev_per_unit(p, pp, price_)
            if ev_frozen > 0.30:
                flags = tuple(sorted(set(flags) | {"FROZEN_EV_GT_30_PCT"}))
            row = C.PricedMarket(game_id=gid, period=q.period, market=q.market,
                                 line=(-q.line if q.market in ("SPREAD", "ALT_SPREAD") and side == "away" else q.line),
                                 side=side, price=price_, prob_model=p, prob_push=pp, prob_market_novig=pm,
                                 prob_hybrid=ph, fair_american=fair_american(p, pp),
                                 ev_model=ev_frozen,
                                 ev_hybrid=NM.ev_per_unit(ph, cprobs[1] if cprobs is not None else pp, price_),
                                 prob_challenger=pc, ev_challenger=evc, hybrid_method=hmethod, audit_flags=flags,
                                 dk_event_id=q.dk_event_id, captured_utc=q.captured_utc, provenance=q.provenance,
                                 prob_source=src)
            C.check_paper(row)
            priced.append((row, q))
    return priced, rejects, parity


def rank(priced):
    return sorted(priced, key=lambda x: (-x[0].ev_model, x[0].game_id, x[0].market, x[0].side))


def stars_for(row, calibration):
    """Stars only when a calibration record marks this (period, market) VALIDATED. None exist today."""
    rec = (calibration or {}).get(f"{row.period}:{row.market}")
    if not rec or rec.get("status") != "VALIDATED":
        return C.STARS_UNCALIBRATED
    n = max(0, min(5, int(row.ev_model / rec["ev_per_star"])))
    return "★" * n if n else C.STARS_UNCALIBRATED


# ====================================================================== grade
def outcome(market, line, h, a):
    if market == "ML":
        return "home" if h > a else "away"
    if market in ("SPREAD", "ALT_SPREAD"):
        v = h - a + line
        return "push" if v == 0 else ("home" if v > 0 else "away")
    val = {"TOTAL": h + a, "ALT_TOTAL": h + a, "TT_HOME": h, "TT_AWAY": a}[market]
    return "push" if val == line else ("over" if val > line else "under")


def _home_line(r):
    if r["line"] is None:
        return None
    if r["market"] in ("SPREAD", "ALT_SPREAD") and r["side"] == "away":
        return -r["line"]
    return r["line"]


def grade(frozen, finals, close_quotes=None):
    """Grade a FROZEN pipeline card. Selection = best positive-EV side per (game, period, market, line).
    Every side also feeds calibration (push outcomes excluded)."""
    groups = defaultdict(list)
    for r in frozen["priced"]:
        groups[(r["game_id"], r["period"], r["market"], _home_line(r))].append(r)
    grades, cal = [], []
    for key, sides in sorted(groups.items(), key=lambda kv: str(kv[0])):
        gid, period, market, hl = key
        f = finals.get(gid)
        best = max(sides, key=lambda r: (r["ev_model"], r["side"]))
        if f is None:
            grades += [C.GradeRow(gid, period, market, r["line"], r["side"], r["price"], "PENDING_NO_FINAL", None,
                                  r["prob_model"]) for r in sides]
            continue
        if period != "FG":
            grades.append(C.GradeRow(gid, period, market, best["line"], best["side"], best["price"], "NOT_GRADABLE",
                                     None, best["prob_model"]))
            continue
        oc = outcome(market, hl, f["home"], f["away"])
        if oc != "push":
            for r in sides:
                cal.append({"market": market, "p_model": r["prob_model"] / (1 - r["prob_push"]),
                            "p_market": r["prob_market_novig"], "y": int(oc == r["side"])})
        if best["ev_model"] <= 0:
            grades.append(C.GradeRow(gid, "FG", market, best["line"], best["side"], best["price"], "NO_SELECTION",
                                     None, best["prob_model"]))
            continue
        dec = NM.decimal_odds(best["price"])
        res, ret = ("P", 0.0) if oc == "push" else (("W", dec - 1) if oc == best["side"] else ("L", -1.0))
        clv = None
        cq = (close_quotes or {}).get((gid, "FG", market, hl))
        if cq:
            ca, cb, _ = NM.no_vig(cq.price_a, cq.price_b)
            clv = round(100 * ((ca if best["side"] in ("home", "over") else cb) - best["prob_market_novig"]), 3)
        grades.append(C.GradeRow(gid, "FG", market, best["line"], best["side"], best["price"], res, ret,
                                 best["prob_model"], clv))
    return grades, cal


def calibration_summary(cal):
    def ll(p, y):
        p = min(1 - 1e-9, max(1e-9, p)); return -math.log(p if y else 1 - p)
    out = {}
    for fam in sorted({c["market"] for c in cal}) + ["ALL"]:
        xs = [c for c in cal if fam == "ALL" or c["market"] == fam]
        if not xs:
            continue
        bins = defaultdict(list)
        for c in xs:
            bins[min(9, int(c["p_model"] * 10))].append(c)
        out[fam] = {"n_sides": len(xs),
                    "brier_model": mean((c["p_model"] - c["y"]) ** 2 for c in xs),
                    "brier_market": mean((c["p_market"] - c["y"]) ** 2 for c in xs),
                    "logloss_model": mean(ll(c["p_model"], c["y"]) for c in xs),
                    "logloss_market": mean(ll(c["p_market"], c["y"]) for c in xs),
                    "reliability": {f"{b/10:.1f}-{(b+1)/10:.1f}": {"n": len(v), "mean_p": mean(c["p_model"] for c in v),
                                                                     "hit": mean(c["y"] for c in v)}
                                    for b, v in sorted(bins.items())},
                    "note": "paired complementary sides, ladder rungs are highly correlated; one slate cannot "
                            "validate calibration"}
    return out


def grade_summary(grades):
    sel = [g for g in grades if g.result in ("W", "L", "P")]
    by = defaultdict(list)
    for g in sel:
        by[g.market].append(g)

    def s(xs):
        n = len(xs); ret = sum(g.return_1u for g in xs)
        dd = peak = cum = 0.0
        for g in xs:
            cum += g.return_1u; peak = max(peak, cum); dd = min(dd, cum - peak)
        return {"n": n, "W": sum(g.result == "W" for g in xs), "L": sum(g.result == "L" for g in xs),
                "P": sum(g.result == "P" for g in xs), "units": round(ret, 4),
                "roi": round(ret / n, 4) if n else None, "max_drawdown_u": round(dd, 4),
                "clv_rows": sum(g.clv_cents is not None for g in xs)}
    return {"ALL": s(sel), **{k: s(v) for k, v in sorted(by.items())},
            "results": dict(sorted(Counter(g.result for g in grades).items()))}


# ====================================================================== audit
def pin_verification(root=ROOT):
    """Compare current git blob SHAs of CBB files with research/freezes pins (read-only)."""
    pins_path = Path(root) / "research/freezes/frozen_baselines_20261115.json"
    try:
        doc = json.loads(pins_path.read_text())
    except (OSError, ValueError):
        return [{"state": "PIN_FILE_UNREADABLE"}]
    found = []

    def walk(o, key=None):
        if isinstance(o, dict):
            for k, v in o.items():
                if isinstance(v, str) and re.fullmatch(r"[0-9a-f]{7,40}", v) and isinstance(k, str) and "/" in k:
                    found.append((k, v))
                walk(v, k)
            p = o.get("path") or o.get("file")
            s = next((o[k] for k in ("blob_sha", "git_blob_sha", "blob", "sha") if isinstance(o.get(k), str)), None)
            if isinstance(p, str) and s:
                found.append((p, s))
        elif isinstance(o, list):
            for v in o:
                walk(v, key)
    walk(doc)
    out = []
    for p, want in sorted(set(found)):
        if "cbb" not in p.lower():
            continue
        f = Path(root) / p
        if not f.exists():
            out.append({"path": p, "pinned": want, "actual": None, "state": "MISSING"}); continue
        b = f.read_bytes()
        actual = hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()
        out.append({"path": p, "pinned": want, "actual": actual,
                    "state": "MATCH" if actual.startswith(want) or want.startswith(actual) else "DRIFT"})
    return out or [{"state": "NO_CBB_PIN_ENTRIES_FOUND"}]


def coverage(quotes, cap_rejects, val_rejects, price_rejects, priced, adapters):
    fam_rows = Counter((q.period, q.market) for q, _ in quotes)
    for r in cap_rejects:
        fam_rows[(r.period, r.market)] += 0
    rej = defaultdict(Counter)
    for r in cap_rejects + val_rejects + price_rejects:
        rej[(r.period, r.market)][r.reason_code] += 1
    sides, quotes_priced, seen = Counter(), Counter(), set()
    for r, q in priced:
        sides[(q.period, q.market)] += 1
        if q.board_index not in seen:
            seen.add(q.board_index); quotes_priced[(q.period, q.market)] += 1
    out = []
    for fam in C.MARKET_CATALOG:
        p, m = fam
        if p == "2H_HALFTIME_ADJUSTED":
            model = "NOT_IMPLEMENTED:HALFTIME_ADJUSTED_IS_LIVE"
        elif p != "FG":
            model = "ACTIVE" if "halves" in adapters else "NOT_IMPLEMENTED:PERIOD_NOT_IMPLEMENTED"
        elif m.startswith("PLAYER_"):
            model = "ACTIVE" if "players" in adapters else "NOT_IMPLEMENTED:PLAYER_MODEL_NOT_IMPLEMENTED"
        else:
            model = "ACTIVE"
        rows = fam_rows.get(fam, 0)
        status = model if model != "ACTIVE" else ("NO_QUOTE" if rows == 0 else
                                                  "PRICED_PAPER" if quotes_priced.get(fam) else "REJECTED")
        out.append({"period": p, "market": m, "model": model, "board_rows": rows,
                    "quotes_priced": quotes_priced.get(fam, 0), "priced_sides": sides.get(fam, 0),
                    "rejected_by_reason": dict(sorted(rej.get(fam, {}).items())), "status": status,
                    "label": "PAPER_0U/NON_COUNTED"})
    other = {f"{k[0]}:{k[1]}": dict(v) for k, v in rej.items() if k not in C.MARKET_CATALOG}
    return out, other


def _binom_p(k, n):
    if not n:
        return None
    z = (k - n / 2) / math.sqrt(n / 4)
    return round(2 * (1 - ND.cdf(abs(z))), 4)


def audit(*, priced, projections, market_views, parity, sims, quotes, cap_rejects, val_rejects, price_rejects,
          adapters, leakage, calibration, grades_summary, cfg, freeze_utc):
    rows = [r for r, _ in priced]
    a = {}
    hi = [r for r in rows if r.ev_model > 0.30]
    a["ev_gt_30"] = {
        "count": len(hi), "of_priced_sides": len(rows),
        "longshot_price_ge_plus300": sum(r.price >= 300 for r in hi),
        "mean_model_minus_novig_prob": round(mean(r.prob_model - r.prob_market_novig for r in hi), 4) if hi else None,
        "rows": [{"game_id": r.game_id, "market": r.market, "side": r.side, "line": r.line, "price": r.price,
                  "p_model": round(r.prob_model, 4), "p_novig": round(r.prob_market_novig, 4), "ev": round(r.ev_model, 4)}
                 for r in sorted(hi, key=lambda r: -r.ev_model)],
        "diagnosis": "EV>30% rows are independent-vs-no-vig disagreements (mostly long prices / far ladder rungs), "
                     "not validated edge. Flagged; no EV cap applied."}
    mono, lad = [], defaultdict(list)
    for r, q in priced:
        if q.market in ("ALT_SPREAD", "SPREAD", "ALT_TOTAL", "TOTAL") and r.side in ("home", "over"):
            lad[(r.game_id, "S" if "SPREAD" in q.market else "T")].append((q.line, r.prob_market_novig))
    for (gid, kind), pts in lad.items():
        pts = sorted(set(pts))
        for (l1, p1), (l2, p2) in zip(pts, pts[1:]):
            if (kind == "S" and p2 < p1 - 0.02) or (kind == "T" and p2 > p1 + 0.02):
                mono.append({"game_id": gid, "kind": kind, "lines": [l1, l2], "novig": [round(p1, 4), round(p2, 4)]})
    a["orientation"] = {"spread_ml_inconsistent_rejected": sum(r.reason_code == "ORIENTATION_INCONSISTENT" for r in val_rejects),
                        "orientation_mismatch_rejected": sum(r.reason_code == "ORIENTATION_MISMATCH" for r in val_rejects),
                        "ladder_monotonicity_violations": mono}
    dm, dt = [], []
    for gid, pj in projections.items():
        mv = market_views.get(gid)
        if pj.status == "PROJECTED" and mv and mv.status == "PROJECTED":
            dm.append(pj.margin - mv.margin); dt.append(pj.total - mv.total)
    best = {}
    for r in rows:
        k = (r.game_id, r.period, r.market, abs(r.line) if r.line is not None and "SPREAD" in r.market else r.line)
        if r.ev_model > 0 and (k not in best or r.ev_model > best[k].ev_model):
            best[k] = r
    picks = list(best.values())
    fav = sum(r.prob_market_novig > 0.5 for r in picks)
    ou = [r for r in picks if r.side in ("over", "under")]
    over = sum(r.side == "over" for r in ou)
    flags = [n for n, p in (("FAV_DOG_IMBALANCE", _binom_p(fav, len(picks))), ("OVER_UNDER_IMBALANCE", _binom_p(over, len(ou))))
             if p is not None and p < 0.05]
    a["bias"] = {"games_with_both_views": len(dm),
                 "mean_model_minus_market_home_margin": round(mean(dm), 3) if dm else None,
                 "mean_abs_model_minus_market_margin": round(mean(abs(x) for x in dm), 3) if dm else None,
                 "mean_model_minus_market_total": round(mean(dt), 3) if dt else None,
                 "positive_ev_selections": len(picks), "favorite_selections": fav, "underdog_selections": len(picks) - fav,
                 "fav_dog_balance_p": _binom_p(fav, len(picks)), "over_selections": over, "under_selections": len(ou) - over,
                 "over_under_balance_p": _binom_p(over, len(ou)), "flags": flags,
                 "note": "selections within a game/ladder are correlated, so balance p-values are optimistic"}
    lf = []
    if leakage.get("max_prior_tip_utc") and parse_z(leakage["max_prior_tip_utc"]) + timedelta(hours=3) > parse_z(freeze_utc):
        lf.append("PRIOR_FINAL_NOT_BEFORE_FREEZE")
    if any(r.captured_utc and parse_z(r.captured_utc) > parse_z(freeze_utc) for r in rows):
        lf.append("QUOTE_AFTER_FREEZE_PRICED")
    a["leakage"] = {**leakage, "flags": lf, "independent_view_reads_prices": False,
                    "finals_used_before_grade": False,
                    "note": "independent projections are computed before and without quotes; market view separate"}
    ml_dev = 0.0
    for gid, s in sims.items():
        pj = projections[gid]
        p_sim = sum(h > y for h, y in zip(s["home"], s["away"])) / s["n"]
        ml_dev = max(ml_dev, abs(p_sim - NM._cdf(pj.margin / pj.sd_margin)))
    sm, st = cfg["sd_margin"], cfg["sd_total"]
    a["consistency"] = {
        "simulated_games": len(sims), "draws_per_game": next(iter(sims.values()))["n"] if sims else 0,
        "ml_sim_vs_closed_max_abs": round(ml_dev, 4),
        "sim_vs_closed_form_max_abs": round(max((p["abs_diff"] for p in parity), default=0), 4),
        "sim_vs_closed_form_by_market": {m: round(max(p["abs_diff"] for p in parity if p["market"] == m), 4)
                                         for m in sorted({p["market"] for p in parity})},
        "joint_team_sd": round(math.sqrt(sm * sm + st * st) / 2, 3),
        "closed_form_team_sd_in_cbb_pricing": round(st * cfg["team_total_sd_factor"], 3),
        "implied_home_away_score_corr": round((st * st - sm * sm) / (st * st + sm * sm), 3),
        "note": "pipeline prices every family from the same joint draws (spread, total, ML, team totals, alts are "
                "mutually consistent by construction); cbb_pricing's closed-form team-total SD assumes zero "
                "home/away correlation and differs (reported, not changed: WS1 owns cbb_pricing). Halves and players "
                "are not simulated until their adapters land."}
    cov, other = coverage(quotes, cap_rejects, val_rejects, price_rejects, priced, adapters)
    a["coverage"] = cov
    a["coverage_unsupported_markets"] = other
    a["calibration"] = calibration or {"state": "NO_GRADED_SIDES"}
    a["stars"] = "n/a uncalibrated for every family: no calibration record marks any family VALIDATED"
    a["grades"] = grades_summary
    a["pins"] = pin_verification()
    a["provenance_census"] = dict(Counter(q.provenance for q, _ in quotes))
    a["authenticated_rows"] = sum(q.provenance == C.AUTHENTICATED for q, _ in quotes)
    return a


# ====================================================================== card
def _mean_or_none(xs):
    return round(mean(xs), 3) if xs else None


def _f(v, fmt="{:.1f}"):
    return "—" if v is None else fmt.format(v)


def render(meta, games, projections, market_views, hybrids, ranked, rejects, a, gsum):
    o = [f"# RUN IT CBB — full pipeline research card ({meta['date_ct']})", "",
         f"**PAPER / 0u · NON_COUNTED · research only, not recommendations.** Pipeline {PIPELINE_VERSION} · "
         f"projection adapter `{meta['projection_adapter']}` · freeze {meta['freeze_ct']} · card sha `{meta['card_sha256'][:12]}`", "",
         (f"Board `{meta['board_path']}` (sha256 `{meta['board_sha256'][:12]}`), provenance **{meta['provenance']}**: "
          "not an authenticated DraftKings capture.") if meta["provenance"] != C.AUTHENTICATED else
         f"Board: authenticated DK capture `{meta['board_path']}`.", ""]
    o += [f"> {w}" for w in meta.get("warnings", [])]
    w = meta["blend_weight_model"]
    chv, chh = meta.get("challenger_views") or {}, meta.get("challenger_hybrids") or {}
    if chv:
        o += ["", "Views: **FROZEN** (default; frozen native formula), **CHALLENGER** (fullgame FG1C, research), "
              "**MARKET** (DK no-vig), **HYBRID** = logit blend of the challenger with the market at the "
              "validation-selected model weight (open: ML 0.125, spread 0, total 0.125; at the close validation chose "
              "0 for every market). The hybrid is therefore mostly the market; it is a research view, PAPER/0u, "
              "NON_COUNTED, not production-validated. Stars: n/a uncalibrated.", "",
              "## Projections per game (frozen · challenger · market no-vig · hybrid)", "",
              "| Tip (CT) | Game | Frozen margin | Frozen total | Chal away | Chal home | Chal margin | Chal total | "
              "Mkt margin | Mkt total | Hyb margin | Hyb total | Status |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    else:
        o += ["", f"Hybrid = {100*w:.1f}% model / {100*(1-w):.1f}% market: **UNVALIDATED** (no blend weight has passed "
              "chronological validation). Canonical nine weights are recorded per side in pipeline_card.json. "
              "Stars: n/a uncalibrated.", "",
              "## Projections per game (independent · Vegas no-vig · hybrid UNVALIDATED)", "",
              "| Tip (CT) | Game | Ind away | Ind home | Ind margin | Ind total | Mkt margin | Mkt total | Hyb margin | Hyb total | Status |",
              "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for g in sorted(games, key=lambda g: (g.tipoff_utc, g.game_id)):
        pj, mv, hy = projections[g.game_id], market_views[g.game_id], hybrids[g.game_id]
        st = "PROJECTED" if pj.status == "PROJECTED" else f"PASS {pj.reason_code}"
        if pj.status == "PROJECTED" and mv.status != "PROJECTED":
            st += " · market NO_QUOTE"
        if chv:
            cv, chy = chv.get(g.game_id), chh.get(g.game_id)
            if cv is not None and cv.status != "PROJECTED":
                st += f" · {cv.reason_code}"
            cz = cv if cv is not None else C.Projection(g.game_id, "CHALLENGER", *([None] * 6), "", "PASS")
            hz = chy if chy is not None else C.Projection(g.game_id, "HYBRID_CHALLENGER", *([None] * 6), "", "PASS")
            o.append(f"| {g.tip_ct} | {g.away} @ {g.home} | {_f(pj.margin, '{:+.1f}')} | {_f(pj.total)} | "
                     f"{_f(cz.away_points)} | {_f(cz.home_points)} | {_f(cz.margin, '{:+.1f}')} | {_f(cz.total)} | "
                     f"{_f(mv.margin, '{:+.1f}')} | {_f(mv.total)} | {_f(hz.margin, '{:+.1f}')} | {_f(hz.total)} | {st} |")
            continue
        o.append(f"| {g.tip_ct} | {g.away} @ {g.home} | {_f(pj.away_points)} | {_f(pj.home_points)} | "
                 f"{_f(pj.margin, '{:+.1f}')} | {_f(pj.total)} | {_f(mv.margin, '{:+.1f}')} | {_f(mv.total)} | "
                 f"{_f(hy.margin, '{:+.1f}')} | {_f(hy.total)} | {st} |")
    names = {g.game_id: g for g in games}
    o += ["", "## Priced markets (ranked by frozen-model paper EV; FG probabilities from the seeded joint simulation, "
          "half probabilities from the halves adapter; challenger from fullgame.pricing Student-t residuals)", "",
          "| # | Tip (CT) | Game | Per | Market | Side | Line | DK odds | p frozen | p push | p chal | p no-vig | p hybrid | "
          "Fair (frozen) | EV frozen | EV chal | EV hybrid | Audit flags | Stars | Status | Provenance |",
          "|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|---|"]
    for i, (r, q) in enumerate(ranked, 1):
        g = names[r.game_id]
        fl = ",".join(r.audit_flags) or ("FROZEN_EV_GT_30_PCT" if r.ev_model > 0.30 else "—")
        o.append(f"| {i} | {g.tip_ct} | {g.away} @ {g.home} | {r.period} | {r.market} | {r.side} | "
                 f"{_f(r.line, '{:g}')} | {r.price:+d} | {r.prob_model:.3f} | {r.prob_push:.3f} | "
                 f"{_f(r.prob_challenger, '{:.3f}')} | {r.prob_market_novig:.3f} | {r.prob_hybrid:.3f} | "
                 f"{_f(r.fair_american, '{:+d}')} | {100*r.ev_model:+.1f}% | "
                 f"{_f(None if r.ev_challenger is None else 100*r.ev_challenger, '{:+.1f}%')} | "
                 f"{100*r.ev_hybrid:+.1f}% | {fl} | {r.stars} | {r.status}/{r.counted} | {r.provenance} |")
    o += ["", "## Market coverage (every catalogued CBB family has a status or reason code)", "",
          "| Period | Market | Model | Board rows | Quotes priced | Status | Rejections by reason |",
          "|---|---|---|---:|---:|---|---|"]
    for c in a["coverage"]:
        rj = ", ".join(f"{k} {v}" for k, v in c["rejected_by_reason"].items()) or "—"
        o.append(f"| {c['period']} | {c['market']} | {c['model']} | {c['board_rows']} | {c['quotes_priced']} | {c['status']} | {rj} |")
    if a["coverage_unsupported_markets"]:
        o += ["", f"Board market strings outside the catalog: {a['coverage_unsupported_markets']}"]
    o += ["", "## Rejection census", "", "| Stage | Reason code | Rows |", "|---|---|---:|"]
    for (st, rc), n in sorted(Counter((r.stage, r.reason_code) for r in rejects).items()):
        o.append(f"| {st} | {rc} | {n} |")
    b, c, l = a["bias"], a["consistency"], a["leakage"]
    o += ["", "## Audit", "",
          f"- EV>30%: {a['ev_gt_30']['count']} of {a['ev_gt_30']['of_priced_sides']} priced sides "
          f"({a['ev_gt_30']['longshot_price_ge_plus300']} at +300 or longer). Flagged, not capped.",
          f"- Orientation: spread/ML inconsistent rejected {a['orientation']['spread_ml_inconsistent_rejected']}; "
          f"home/away mismatch rejected {a['orientation']['orientation_mismatch_rejected']}; ladder monotonicity "
          f"violations {len(a['orientation']['ladder_monotonicity_violations'])}.",
          f"- Bias: model−market home margin {b['mean_model_minus_market_home_margin']} (mean abs {b['mean_abs_model_minus_market_margin']}), "
          f"total {b['mean_model_minus_market_total']} over {b['games_with_both_views']} games; +EV selections fav/dog "
          f"{b['favorite_selections']}/{b['underdog_selections']} (p {b['fav_dog_balance_p']}), over/under "
          f"{b['over_selections']}/{b['under_selections']} (p {b['over_under_balance_p']}); flags {b['flags'] or 'none'}.",
          f"- Leakage: prior finals {l.get('prior_finals_used')}, latest prior tip {l.get('max_prior_tip_utc')}, flags {l['flags'] or 'none'}.",
          f"- Consistency: sim vs closed-form max |Δp| {c['sim_vs_closed_form_max_abs']} {c['sim_vs_closed_form_by_market']}; "
          f"joint team SD {c['joint_team_sd']} vs cbb_pricing closed-form {c['closed_form_team_sd_in_cbb_pricing']}; "
          f"implied home/away score corr {c['implied_home_away_score_corr']}.",
          "- Pins: " + "; ".join(f"{p.get('path', '')} {p.get('state')}" for p in a["pins"]),
          f"- Provenance: {a['provenance_census']}; authenticated rows {a['authenticated_rows']}.", "", "## Grade", ""]
    if gsum:
        g = gsum["ALL"]
        o += [f"Result census {gsum['results']}. Graded selections {g['n']}: W {g['W']} / L {g['L']} / P {g['P']}, "
              f"units {g['units']:+.2f}, ROI {g['roi']}, max drawdown {g['max_drawdown_u']}u. CLV rows {g['clv_rows']} "
              "(no later pre-tip close board supplied, so CLV is unavailable).", "",
              "| Market | n | W | L | P | Units | ROI |", "|---|---:|---:|---:|---:|---:|---:|"]
        for k, v in gsum.items():
            if k not in ("ALL", "results"):
                o.append(f"| {k} | {v['n']} | {v['W']} | {v['L']} | {v['P']} | {v['units']:+.2f} | {v['roi']} |")
        cal = a["calibration"].get("ALL") if isinstance(a["calibration"], dict) else None
        if cal:
            o += ["", f"Calibration (graded sides, paired): Brier model {cal['brier_model']:.4f} vs market "
                  f"{cal['brier_market']:.4f}; log loss model {cal['logloss_model']:.4f} vs market {cal['logloss_market']:.4f}; "
                  f"n {cal['n_sides']}. One slate cannot validate calibration."]
    else:
        o.append("Not graded in this run.")
    return "\n".join(o) + "\n"


# ====================================================================== orchestration
def _slate_rows_from_espn(games, ids, short=False):
    return [{"game_id": gid, "tipoff_utc": games[gid]["tip_utc"],
             "_home": (games[gid]["home_alt"][0] if short else games[gid]["home"]) or "",
             "_away": (games[gid]["away_alt"][0] if short else games[gid]["away"]) or "",
             "neutral": "1" if games[gid]["neutral"] else "0"} for gid in ids]


def run_public_replay(*, date_ct, board, board_captured_utc, freeze_utc, season, raw_dir, out_dir,
                      totals_order_verified, n_sims=20000, seed=20261125, grade_finals=True,
                      adapters_requested=(), provenance=None, fetch=True, refresh_finals=False, now=None,
                      team_crosswalk=None, halves_path=None, fullgame_root=None, challenger_inputs=None):
    """Whole pipeline in one call on public ESPN inputs (research replay; never production)."""
    import cbb_run_it as R
    now = now or datetime.now(timezone.utc)
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    cfg = PR.make_config()
    w = cfg["blend_weight_model"]
    req = set(adapters_requested)
    freeze = parse_z(freeze_utc)
    loaded, halves, challenger = {}, None, None
    if "halves" in req:
        halves = load_halves(halves_path)
        loaded["halves"] = halves or "ADAPTER_NOT_LANDED"
    if "fullgame" in req:
        try:
            ci = challenger_inputs or {}
            challenger = Challenger(fullgame_root, ci["games_csv"], ci["finals_json"], ci["summary_json"], season, freeze)
            loaded["fullgame"] = challenger
        except (ImportError, KeyError, ValueError, OSError, TypeError) as exc:
            loaded["fullgame"] = f"LOAD_FAILED:{type(exc).__name__}:{exc}"
    adapter_status, active = load_adapter_flags(req, loaded)
    active.discard("fullgame")                      # challenger never replaces the default projection
    day = datetime.fromisoformat(date_ct).date()
    season_start = datetime(day.year if day.month >= 8 else day.year - 1, 11, 1).date()
    freeze = parse_z(freeze_utc)
    # ---- capture
    cap = BoardFileCapture(board, board_captured_utc, provenance).capture()
    days = espn_capture(season_start, day, raw_dir, fetch=fetch,
                        refresh_days={day.strftime("%Y%m%d")} if refresh_finals else ())
    games, files = espn_games(raw_dir, days)
    quotes, cap_rejects = normalize_quotes(cap, totals_order_verified=totals_order_verified)
    day_ids = sorted(gid for gid, g in games.items() if parse_z(g["tip_utc"]).astimezone(CT).date() == day)
    slate_ids = [gid for gid in day_ids if parse_z(games[gid]["tip_utc"]) > freeze]
    started_ids = [gid for gid in day_ids if parse_z(games[gid]["tip_utc"]) <= freeze]
    gm = {gid: C.GameRow(gid, season, games[gid]["tip_utc"], ct_time(games[gid]["tip_utc"]), games[gid]["home"] or "",
                         games[gid]["away"] or "", games[gid]["home_id"], games[gid]["away_id"], games[gid]["neutral"],
                         "UNVERIFIED_SINGLE_SOURCE_ESPN", id_source="ESPN_PUBLIC_REPLAY") for gid in slate_ids}
    # ---- validate: exact normalized names (runner aliases), ESPN location then ESPN short name
    # matching uses EVERY game on the date so a started game's quotes get STARTED_BEFORE_AS_OF, not NO_GAME_MATCH
    s1, s2 = _slate_rows_from_espn(games, day_ids), _slate_rows_from_espn(games, day_ids, short=True)

    xw = {}
    if team_crosswalk:
        for r in csv.DictReader(io.StringIO(Path(team_crosswalk).read_text(encoding="utf-8-sig"))):
            if r.get("board_name") and r.get("espn_team_id"):
                xw[r["board_name"]] = str(r["espn_team_id"])
    by_id = {(games[g]["home_id"], games[g]["away_id"]): g for g in day_ids}
    match_census = Counter()

    def match(_slate, home, away, row):
        g, why = R._match(s1, home, away, row)
        if g:
            match_census["ESPN_LOCATION_EXACT"] += 1; return g, None
        g2, _ = R._match(s2, home, away, row)
        if g2:
            match_census["ESPN_SHORT_NAME_EXACT"] += 1; return g2, None
        # Pass 3: models/cbb/dk team crosswalk (board name -> ESPN team id), exact ids + 15-minute tip window.
        h, a = xw.get(home), xw.get(away)
        if h and a:
            tip = str((row or {}).get("tip_utc") or "").strip()
            for key, rev in (((h, a), False), ((a, h), True)):
                gid = by_id.get(key)
                if gid and (not tip or abs((parse_z(games[gid]["tip_utc"]) - parse_z(tip)).total_seconds()) <= 900):
                    if rev:
                        return None, "home/away orientation mismatch"
                    match_census["DK_TEAM_CROSSWALK_ESPN_ID"] += 1
                    return next(r for r in s1 if r["game_id"] == gid), None
        return None, why
    accepted, val_rejects = validate(quotes, s1, freeze_utc, totals_order_verified=totals_order_verified,
                                     match=match, adapters=active, as_of_utc=utcz(freeze))
    for q, gid in accepted:
        if q.dk_event_id and gm[gid].dk_event_id is None:
            gm[gid] = replace(gm[gid], dk_event_id=q.dk_event_id)
    # ---- project: independent first (reads no quotes), then market and hybrid views
    projections, leakage, ratings_body = public_replay_project(games, slate_ids, season, freeze_utc, cfg)
    # Ensure every slate game has a Projection so later stages do not KeyError.
    reason = (leakage or {}).get("reason", "RATINGS_INSUFFICIENT_SAMPLE") if isinstance(leakage, dict) else "NO_PROJECTION"
    for gid in slate_ids:
        if gid not in projections or projections[gid] is None:
            projections[gid] = C.Projection(gid, "INDEPENDENT", None, None, None, None, None, None,
                                            "", "PASS", reason_code=reason)
    market_views = {gid: market_view(gid, accepted, cfg) for gid in slate_ids}
    hybrids = {}
    for gid in slate_ids:
        hybrids[gid] = hybrid_view(projections[gid], market_views[gid], w)
    ch_proj, ch_views, ch_hyb = (challenger_views(challenger, games, slate_ids, market_views) if challenger
                                 else ({}, {}, {}))
    # ---- simulate
    sims = {gid: simulate(p, n_sims, seed) for gid, p in projections.items() if p.status == "PROJECTED"}
    # ---- price / rank
    priced, price_rejects, parity = price(accepted, projections, sims, w, cfg, halves=halves,
                                          challenger=challenger, challenger_proj=ch_proj)
    priced = [(replace(r, stars=stars_for(r, None)), q) for r, q in priced]
    ranked = rank(priced)
    rejects = cap_rejects + val_rejects + price_rejects
    # ---- freeze
    kind = "PROSPECTIVE" if now <= freeze + timedelta(minutes=10) else "REPLAY_RECORD_NOT_PROSPECTIVE"
    frozen = {"schema": C.SCHEMA_VERSION, "pipeline": PIPELINE_VERSION, "label": C.PAPER_0U, "counted": C.NON_COUNTED,
              "approved_stake_u": 0, "freeze_utc": utcz(freeze), "date_ct": date_ct, "freeze_kind": kind,
              "projection_adapter": "native_formula_public_replay",
              "board": {"path": cap["path"], "sha256": cap["source_sha256"], "provenance": cap["provenance"],
                        "rows": len(cap["rows"])},
              "inputs": {"espn_files": len(files), "espn_files_digest": digest(files),
                         "ratings_sha256": sha_bytes(ratings_body)},
              "config": cfg, "blend_weight_model": w, "hybrid_status": C.HYBRID_UNVALIDATED,
              "canonical_blend_weights": list(C.CANONICAL_BLEND_WEIGHTS), "sim": {"n": n_sims, "seed": seed},
              "games": [C.row_dict(g) for g in gm.values()],
              "projections": [C.row_dict(p) for d in (projections, ch_views, market_views, hybrids, ch_hyb)
                              for p in d.values() if is_dataclass(p)],
              "challenger": ({"meta": challenger.meta, "module_paths": challenger.module_paths,
                              "blend_weights_open": CHALLENGER_BLEND_W_OPEN, "caveat": CHALLENGER_CAVEAT}
                             if challenger else None),
              "halves": ({"version": halves["version"], "coefficients_sha256": halves["sha256"],
                          "ml_tie_rule": HALVES_ML_TIE_RULE, "caveat": HALVES_CAVEAT} if halves else None),
              "priced": [C.row_dict(r) for r, _ in ranked],
              "nine_weight_grid": [[r.game_id, r.market, r.line, r.side] +
                                   [round(PR.blend(r.prob_model, r.prob_market_novig, wt, push=r.prob_push), 5)
                                    for wt in C.CANONICAL_BLEND_WEIGHTS] for r, _ in ranked],
              "rejections": [C.row_dict(r) for r in rejects], "adapters": adapter_status}
    frozen["card_sha256"] = digest(frozen)
    (out / "pipeline_card.json").write_text(json.dumps(frozen, indent=1, sort_keys=True))
    log = out / "freeze_log.jsonl"
    prev = log.read_text().strip().splitlines()[-1] if log.exists() and log.read_text().strip() else None
    with log.open("a") as f:
        f.write(json.dumps({"card_sha256": frozen["card_sha256"], "freeze_utc": frozen["freeze_utc"],
                            "recorded_utc": utcz(now), "kind": kind,
                            "prev_entry_sha256": sha_bytes(prev.encode()) if prev else None}, sort_keys=True) + "\n")
    # ---- grade: reads only the frozen card after verifying its digest
    grades, cal, gsum = [], [], None
    if grade_finals:
        reread = json.loads((out / "pipeline_card.json").read_text())
        if digest({k: v for k, v in reread.items() if k != "card_sha256"}) != reread["card_sha256"]:
            raise ValueError("FROZEN_CARD_DIGEST_MISMATCH")
        finals = {gid: {"home": games[gid]["home_score"], "away": games[gid]["away_score"]}
                  for gid in slate_ids if games[gid]["completed"] and games[gid]["home_score"] is not None}
        grades, cal = grade(reread, finals)
        gsum = grade_summary(grades)
        (out / "grades.json").write_text(json.dumps(
            {"label": C.PAPER_0U, "counted": C.NON_COUNTED, "finals_source": "ESPN public scoreboard (unauthenticated)",
             "finals_observed_utc": utcz(now), "finals_available": len(finals), "slate_games": len(slate_ids),
             "graded_card_sha256": reread["card_sha256"], "summary": gsum,
             "rows": [C.row_dict(g) for g in grades]}, indent=1, sort_keys=True))
    calib = calibration_summary(cal) if cal else None
    # ---- audit
    a = audit(priced=priced, projections=projections, market_views=market_views, parity=parity, sims=sims,
              quotes=quotes, cap_rejects=cap_rejects, val_rejects=val_rejects, price_rejects=price_rejects,
              adapters=active, leakage=leakage, calibration=calib, grades_summary=gsum, cfg=cfg, freeze_utc=freeze_utc)
    a["adapter_status"] = adapter_status
    if challenger:
        fl = Counter(f for r, _ in priced for f in r.audit_flags)
        cr = [r for r, _ in priced if r.ev_challenger is not None]
        a["challenger"] = {"projected": sum(v.status == "PROJECTED" for v in ch_views.values()),
                           "pass_reasons": dict(Counter(v.reason_code for v in ch_views.values() if v.status != "PROJECTED")),
                           "sites": dict(Counter(v["site"] for v in ch_proj.values())),
                           "priced_sides": len(cr), "ev_gt_30": sum(r.ev_challenger > 0.30 for r in cr),
                           "hybrid_ev_gt_30": sum(r.ev_hybrid > 0.30 for r in cr),
                           "audit_flag_census": dict(fl),
                           "mean_chal_minus_market_margin": _mean_or_none(
                               [ch_views[g].margin - market_views[g].margin for g in ch_views
                                if ch_views[g].status == "PROJECTED" and market_views[g].status == "PROJECTED"]),
                           "mean_chal_minus_market_total": _mean_or_none(
                               [ch_views[g].total - market_views[g].total for g in ch_views
                                if ch_views[g].status == "PROJECTED" and market_views[g].status == "PROJECTED"]),
                           "ev_audit": "fullgame.pricing.ev_audit per side (flag only, no caps); identical rule to "
                                       "cbb_pricing.ev_sanity_audit, which takes the production card shape",
                           "meta": challenger.meta}
    a["match_census"] = dict(match_census)
    a["neutral_total_realignments"] = list(getattr(validate, "last_neutral_total_realignments", []))
    a["dk_auth_capture_requirements"] = AUTH_CAPTURE_REQUIREMENTS
    a["slate"] = {"espn_games_on_date_after_freeze": len(slate_ids), "espn_games_started_before_as_of": len(started_ids),
                  "games_with_accepted_quotes": len({g for _, g in accepted}),
                  "projected": sum(p.status == "PROJECTED" for p in projections.values()),
                  "pass_reasons": dict(Counter(p.reason_code for p in projections.values() if p.status != "PROJECTED"))}
    (out / "audit.json").write_text(json.dumps(a, indent=1, sort_keys=True, default=str))
    meta = {"date_ct": date_ct, "projection_adapter": "native_formula_public_replay",
            "freeze_ct": freeze.astimezone(CT).strftime("%Y-%m-%d %-I:%M %p CT"),
            "card_sha256": frozen["card_sha256"], "board_path": cap["path"].split("Sportsedge/")[-1].split("ws_runner/")[-1],
            "board_sha256": cap["source_sha256"], "provenance": cap["provenance"], "blend_weight_model": w,
            "warnings": [
                "Projection inputs are a PUBLIC ESPN reconstruction (opponent-adjusted efficiencies from box-score "
                "possession estimates), NOT the production CBBD ratings. The frozen native formula is unchanged; this run "
                "tests the pipeline end to end, not production model quality.",
                "Venue: ESPN neutral flag only (single source, unverified); production requires CBBD+ESPN agreement.",
                f"Freeze kind: {kind}. ESPN data was observed {utcz(now)}; leakage control uses tip times "
                "(prior final assumed available at tip+3h).",
                "First-half, second-half and player markets are NOT_IMPLEMENTED in this runner (see coverage).",
                "Game ids are ESPN event ids in this replay (production uses CBBD ids)."]}
    meta["challenger_views"], meta["challenger_hybrids"] = ch_views, ch_hyb
    if challenger:
        meta["warnings"].append(CHALLENGER_CAVEAT)
    if halves:
        meta["warnings"] = [x for x in meta["warnings"] if not x.startswith("First-half, second-half")]
        meta["warnings"].append(HALVES_CAVEAT + " Player markets remain NOT_IMPLEMENTED (see coverage).")
    (out / "pipeline_card.md").write_text(render(meta, list(gm.values()), projections, market_views, hybrids,
                                                 ranked, rejects, a, gsum))
    summary = {"date_ct": date_ct, "freeze_utc": utcz(freeze), "freeze_kind": kind, "slate_games": len(slate_ids),
               "started_before_as_of": len(started_ids),
               "projected": a["slate"]["projected"], "games_with_accepted_quotes": a["slate"]["games_with_accepted_quotes"],
               "board_rows": len(cap["rows"]), "board_provenance": cap["provenance"],
               "priced_quotes": len({q.board_index for _, q in ranked}), "priced_sides": len(ranked),
               "rejections": len(rejects), "rejections_by_code": dict(sorted(Counter(r.reason_code for r in rejects).items())),
               "ev_gt_30": a["ev_gt_30"]["count"], "graded": gsum["ALL"] if gsum else None,
               "results_census": gsum["results"] if gsum else None, "card_sha256": frozen["card_sha256"],
               "label": C.PAPER_0U, "counted": C.NON_COUNTED}
    (out / "run_summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True))
    return summary


def run_from_card(card, names, board_path, board_captured_utc, out_dir, *, totals_order_verified=False,
                  n_sims=20000, seed=20261125, adapters_requested=()):
    """Production path (frozen_native_cbbd, the DEFAULT adapter): stages after the unchanged
    cbb_run_it.build card. Projections are read from the frozen card (never recomputed); the CBBD
    ledger freeze already happened inside build(). Adds validate (contract reason codes), market +
    hybrid views, simulate, price, rank, pipeline freeze record, audit and the full card."""
    import cbb_run_it as R
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    cfg = PR.make_config()
    w = cfg["blend_weight_model"]
    adapter_status, active = load_adapter_flags(set(adapters_requested))
    freeze = parse_z(card["freeze_utc"])
    cap = BoardFileCapture(board_path, board_captured_utc).capture()
    quotes, cap_rejects = normalize_quotes(cap, totals_order_verified=totals_order_verified)
    rows = {r["game_id"]: r for r in card["rows"]}
    slate = [{"game_id": gid, "tipoff_utc": tip, "_home": h, "_away": a,
              "neutral": "1" if rows.get(gid, {}).get("neutral") else "0"} for gid, (a, h, tip) in names.items()]
    accepted, val_rejects = validate(quotes, slate, card["freeze_utc"], totals_order_verified=totals_order_verified,
                                     match=R._match, adapters=active, as_of_utc=card["freeze_utc"])
    projections = projections_from_card(card, cfg)
    gm = {}
    for gid, (a, h, tip) in names.items():
        r = rows.get(gid, {})
        gm[gid] = C.GameRow(gid, int(card["season"]), tip, ct_time(tip), h, a, str(r.get("home_team_id")),
                            str(r.get("away_team_id")), r.get("neutral"),
                            "VERIFIED_TWO_SOURCE" if r.get("neutral") in (True, False) else "UNKNOWN")
        projections.setdefault(gid, C.Projection(gid, "INDEPENDENT", None, None, None, None, None, None,
                                                 "frozen_native_cbbd", "PASS", "GAME_NOT_PROJECTED:NOT_ON_CARD"))
    market_views = {gid: market_view(gid, accepted, cfg) for gid in gm}
    hybrids = {gid: hybrid_view(projections[gid], market_views[gid], w) for gid in gm}
    sims = {gid: simulate(p, n_sims, seed) for gid, p in projections.items() if p.status == "PROJECTED"}
    priced, price_rejects, parity = price(accepted, projections, sims, w, cfg)
    ranked = rank(priced)
    rejects = cap_rejects + val_rejects + price_rejects
    frozen = {"schema": C.SCHEMA_VERSION, "pipeline": PIPELINE_VERSION, "label": C.PAPER_0U, "counted": C.NON_COUNTED,
              "approved_stake_u": 0, "freeze_utc": card["freeze_utc"], "date_ct": freeze.astimezone(CT).date().isoformat(),
              "freeze_kind": "PROSPECTIVE_WITH_CBBD_LEDGER", "projection_adapter": "frozen_native_cbbd",
              "parent_card_sha256": card["card_sha256"],
              "board": {"path": cap["path"], "sha256": cap["source_sha256"], "provenance": cap["provenance"],
                        "rows": len(cap["rows"])},
              "config": cfg, "blend_weight_model": w, "hybrid_status": C.HYBRID_UNVALIDATED,
              "canonical_blend_weights": list(C.CANONICAL_BLEND_WEIGHTS), "sim": {"n": n_sims, "seed": seed},
              "games": [C.row_dict(g) for g in gm.values()],
              "projections": [C.row_dict(p) for d in (projections, market_views, hybrids) for p in d.values()],
              "priced": [C.row_dict(r) for r, _ in ranked], "rejections": [C.row_dict(r) for r in rejects],
              "adapters": adapter_status}
    frozen["card_sha256"] = digest(frozen)
    (out / "pipeline_card.json").write_text(json.dumps(frozen, indent=1, sort_keys=True))
    leakage = {"prior_finals_used": (card.get("context") or {}).get("prior_games_used"), "max_prior_tip_utc": None,
               "freeze_utc": card["freeze_utc"], "prior_rule": "cbbd_native_score_model.eligible_prior_games (captured < freeze)"}
    a = audit(priced=priced, projections=projections, market_views=market_views, parity=parity, sims=sims,
              quotes=quotes, cap_rejects=cap_rejects, val_rejects=val_rejects, price_rejects=price_rejects,
              adapters=active, leakage=leakage, calibration=None, grades_summary=None, cfg=cfg,
              freeze_utc=card["freeze_utc"])
    # production parity: pipeline (simulated) vs frozen card (closed-form) main-market probabilities
    par = []
    for r, q in priced:
        cm = next((m for m in rows.get(r.game_id, {}).get("markets", []) if m.get("status") == "PRICED_PAPER"
                   and {"SPREAD": "spread", "TOTAL": "total", "ML": "moneyline"}.get(q.market) == m["market"]
                   and (m["quote"]["line"] == q.line or q.market == "ML")), None)
        if cm and r.side in cm["model_prob"]:
            par.append(abs(cm["model_prob"][r.side] - r.prob_model))
    a["card_parity_max_abs"] = round(max(par), 4) if par else None
    a["adapter_status"] = adapter_status
    (out / "audit.json").write_text(json.dumps(a, indent=1, sort_keys=True, default=str))
    meta = {"date_ct": frozen["date_ct"], "projection_adapter": "frozen_native_cbbd",
            "freeze_ct": freeze.astimezone(CT).strftime("%Y-%m-%d %-I:%M %p CT"), "card_sha256": frozen["card_sha256"],
            "board_path": str(board_path), "board_sha256": cap["source_sha256"], "provenance": cap["provenance"],
            "blend_weight_model": w,
            "warnings": ["Projections are the frozen production card's (CBBD ratings, frozen native model).",
                         "First-half, second-half and player markets are NOT_IMPLEMENTED in this runner (see coverage)."]}
    (out / "pipeline_card.md").write_text(render(meta, list(gm.values()), projections, market_views, hybrids, ranked,
                                                 rejects, a, None))
    return {"pipeline_card_sha256": frozen["card_sha256"], "priced_sides": len(ranked), "rejections": len(rejects)}


def grade_frozen_card(card_path, raw_dir, out_dir, *, fetch=True, refresh=True, now=None):
    """Grade stage on a PRIOR frozen pipeline card: verify its digest, (re)capture that date's public
    finals, grade W/L/P + ROI + calibration, and write grades.json / grade_report.md next to out_dir."""
    now = now or datetime.now(timezone.utc)
    card = json.loads(Path(card_path).read_text())
    if digest({k: v for k, v in card.items() if k != "card_sha256"}) != card.get("card_sha256"):
        raise ValueError("FROZEN_CARD_DIGEST_MISMATCH")
    if card.get("label") != C.PAPER_0U or card.get("counted") != C.NON_COUNTED:
        raise ValueError("FROZEN_CARD_NOT_PAPER")
    day = datetime.fromisoformat(card["date_ct"]).date()
    k = day.strftime("%Y%m%d")
    if refresh and fetch:
        espn_capture(day, day, raw_dir, fetch=True, refresh_days={k})
    games, _ = espn_games(raw_dir, [k])
    ids = {g["game_id"] for g in card["games"]}
    finals = {gid: {"home": games[gid]["home_score"], "away": games[gid]["away_score"]}
              for gid in ids if gid in games and games[gid]["completed"] and games[gid]["home_score"] is not None}
    grades, cal = grade(card, finals)
    gsum = grade_summary(grades)
    calib = calibration_summary(cal) if cal else {"state": "NO_GRADED_SIDES"}
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    doc = {"label": C.PAPER_0U, "counted": C.NON_COUNTED, "graded_card_sha256": card["card_sha256"],
           "date_ct": card["date_ct"], "finals_source": "ESPN public scoreboard (unauthenticated)",
           "finals_observed_utc": utcz(now), "finals_available": len(finals), "card_games": len(ids),
           "summary": gsum, "calibration": calib, "clv": "UNAVAILABLE: no later pre-tip close board captured",
           "rows": [C.row_dict(g) for g in grades]}
    (out / "grades.json").write_text(json.dumps(doc, indent=1, sort_keys=True))
    g = gsum["ALL"]
    md = [f"# RUN IT CBB grade — card {card['card_sha256'][:12]} ({card['date_ct']})", "",
          "**PAPER / 0u · NON_COUNTED.** Finals: ESPN public scoreboard (unauthenticated), observed "
          f"{utcz(now)}. Finals available {len(finals)} of {len(ids)} card games.", "",
          f"Result census {gsum['results']}. Graded selections {g['n']}: W {g['W']} / L {g['L']} / P {g['P']}, units "
          f"{g['units']:+.2f}, ROI {g['roi']}, max drawdown {g['max_drawdown_u']}u. CLV: unavailable (no close board).", "",
          "| Market | n | W | L | P | Units | ROI |", "|---|---:|---:|---:|---:|---:|---:|"]
    md += [f"| {m} | {v['n']} | {v['W']} | {v['L']} | {v['P']} | {v['units']:+.2f} | {v['roi']} |"
           for m, v in gsum.items() if m not in ("ALL", "results")]
    if "ALL" in calib:
        c = calib["ALL"]
        md += ["", f"Calibration (paired sides; ladder rungs correlated): Brier model {c['brier_model']:.4f} vs market "
               f"{c['brier_market']:.4f}; log loss model {c['logloss_model']:.4f} vs market {c['logloss_market']:.4f}; "
               f"n {c['n_sides']}.", "", "| p model bin | n | mean p | hit rate |", "|---|---:|---:|---:|"]
        md += [f"| {b} | {v['n']} | {v['mean_p']:.3f} | {v['hit']:.3f} |" for b, v in c["reliability"].items()]
        for fam, c2 in calib.items():
            if fam != "ALL":
                md.append(f"- {fam}: n {c2['n_sides']}, Brier model {c2['brier_model']:.4f} vs market {c2['brier_market']:.4f}")
    (out / "grade_report.md").write_text("\n".join(md) + "\n")
    return {"card_sha256": card["card_sha256"], "finals_available": len(finals), "card_games": len(ids),
            "graded": g, "results": gsum["results"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description="RUN IT CBB full pipeline (PAPER/0u, NON_COUNTED)")
    ap.add_argument("--mode", choices=("public-replay", "grade", "auth-requirements"), required=True)
    ap.add_argument("--card", help="grade mode: frozen pipeline_card.json to grade")
    ap.add_argument("--grade-prior-card", help="public-replay: also grade this earlier frozen card in the same command")
    ap.add_argument("--date-ct"); ap.add_argument("--board"); ap.add_argument("--board-captured-utc")
    ap.add_argument("--freeze-utc", help="default: --as-of, else board capture time")
    ap.add_argument("--as-of", help="UTC run time; games tipped at/before it are dropped (STARTED_BEFORE_AS_OF) "
                                    "and the card freezes at this time; 'now' = current clock")
    ap.add_argument("--season", type=int, default=2027)
    ap.add_argument("--raw-dir", help="private cache for public ESPN raw bytes (never committed)")
    ap.add_argument("--out")
    ap.add_argument("--totals-order-verified", action="store_true")
    ap.add_argument("--board-provenance", choices=C.PROVENANCE[1:])
    ap.add_argument("--n-sims", type=int, default=20000); ap.add_argument("--seed", type=int, default=20261125)
    ap.add_argument("--adapters", default="", help="comma list behind flags: fullgame,halves,players")
    ap.add_argument("--no-fetch", action="store_true", help="cached raw files only (offline reproduction)")
    ap.add_argument("--refresh-finals", action="store_true", help="re-fetch the slate date's scoreboard for grading")
    ap.add_argument("--no-grade", action="store_true")
    ap.add_argument("--team-crosswalk", help="models/cbb/dk team crosswalk CSV (board_name -> espn_team_id)")
    ap.add_argument("--halves-path", help="models/cbb dir of a checkout containing halves/ (grok-cbb/halves-*)")
    ap.add_argument("--fullgame-root", help="models/cbb dir of a checkout containing fullgame/ (challenger)")
    ap.add_argument("--challenger-games", help="fullgame games_<season>.csv (sportsdataverse-derived, private)")
    ap.add_argument("--challenger-finals", help="fullgame wf/season_finals.json")
    ap.add_argument("--challenger-summary", help="fullgame evidence/summary.json (dists + recalibration)")
    x = ap.parse_args(argv)
    if x.mode == "auth-requirements":
        print(json.dumps(AUTH_CAPTURE_REQUIREMENTS, indent=1)); return 0
    as_of = utcz(datetime.now(timezone.utc)) if x.as_of == "now" else x.as_of
    if x.mode == "grade":
        if not (x.card and x.raw_dir and x.out):
            print("BLOCKED Hold: CARD_RAWDIR_OUT_REQUIRED", file=sys.stderr); return 2
        try:
            print(json.dumps(grade_frozen_card(x.card, x.raw_dir, x.out, fetch=not x.no_fetch), sort_keys=True))
        except (ValueError, OSError, KeyError) as e:
            print(f"BLOCKED {type(e).__name__}: {e}", file=sys.stderr); return 2
        return 0
    if not (x.date_ct and x.board and x.board_captured_utc and x.raw_dir and x.out):
        print("BLOCKED Hold: DATE_BOARD_CAPTURE_RAWDIR_OUT_REQUIRED", file=sys.stderr); return 2
    try:
        s = run_public_replay(date_ct=x.date_ct, board=x.board, board_captured_utc=x.board_captured_utc,
                              freeze_utc=x.freeze_utc or as_of or x.board_captured_utc, season=x.season, raw_dir=x.raw_dir,
                              out_dir=x.out, totals_order_verified=x.totals_order_verified, n_sims=x.n_sims,
                              seed=x.seed, grade_finals=not x.no_grade, provenance=x.board_provenance,
                              adapters_requested=[a for a in x.adapters.split(",") if a], fetch=not x.no_fetch,
                              refresh_finals=x.refresh_finals, team_crosswalk=x.team_crosswalk,
                              halves_path=x.halves_path, fullgame_root=x.fullgame_root,
                              challenger_inputs={"games_csv": x.challenger_games, "finals_json": x.challenger_finals,
                                                 "summary_json": x.challenger_summary or (
                                                     str(Path(x.fullgame_root) / "fullgame/evidence/summary.json")
                                                     if x.fullgame_root else None)})
    except (ValueError, OSError, KeyError, NM.Pass) as e:
        print(f"BLOCKED {type(e).__name__}: {e}", file=sys.stderr); return 2
    if x.grade_prior_card:
        try:
            s["prior_card_grade"] = grade_frozen_card(x.grade_prior_card, x.raw_dir, Path(x.out) / "prior_card_grade",
                                                      fetch=not x.no_fetch)
        except (ValueError, OSError, KeyError) as e:
            print(f"BLOCKED prior-card grade {type(e).__name__}: {e}", file=sys.stderr); return 2
    print(json.dumps(s, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
