"""One-command fail-closed all-market research runner (no bookmaker network calls).

Usage:
  python -m sportsedge.markets.cli RUN_INPUT.json RESEARCH_OUTPUT.json

RUN_INPUT.json supplies pre-frozen model score means, an explicit *uncalibrated*
dispersion contract, frozen roster IDs and exact observed opposing quote receipts.
Optional player moment input is a separate independently sourced forecast CSV;
never use bookmaker lines to construct model projections. Write is create-only.

No CLI flag lifts PAPER/0u or generates an OFFICIAL betting card. This is a
research audit tool, not a DraftKings/BestBook adapter or trade execution agent.
"""
from __future__ import annotations

from datetime import datetime,timezone,timedelta
from pathlib import Path
from hashlib import sha256
import json
import sys

from .allmarkets_research import Market,PriceReceipt
from .projection_bridge import TeamProjection, from_claude_sport, from_nfl_ridge
from .pit_source_manifest import verify_model_feature_manifest
from .projection_distribution import DistributionInput,generate_score_scenarios
from .score_dispersion_fit import fit_score_residuals, private_path, MAX_BYTES as MAX_FIT_BYTES
from .period_share_fit import fit_period_shares, _private_path as period_private_path, MAX_SIZE as MAX_PERIOD_BYTES
from .player_forecast_intake import ingest_player_forecast_csv
from .run_it_research import MarketCandidate,run_research_board
from .source_ingestion import SOURCES
from sportsedge.odds.storage import EvidenceChain


MAX_MANIFEST_BYTES = 20_000_000


def _unique_json_keys(pairs):
    """Never let JSON last-key-wins silently rewrite a quote or forecast."""
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("RUN_MANIFEST_DUPLICATE_JSON_KEY:" + key)
        result[key] = value
    return result


def _deny_nonfinite_json(value):
    # CPython's json.loads permits NaN/Infinity by default, though they
    # are not valid JSON numbers and must never reach a betting model.
    raise ValueError("RUN_MANIFEST_NONFINITE_JSON_NUMBER:" + str(value))


def _iso(s:str)->datetime:
    if not isinstance(s,str) or not s:
        raise ValueError("UTC_TIMESTAMP_MISSING")
    try:
        d=datetime.fromisoformat(s.replace("Z","+00:00"))
    except ValueError as exc:
        raise ValueError("UTC_TIMESTAMP_INVALID") from exc
    if d.tzinfo is None or d.utcoffset().total_seconds()!=0:
        raise ValueError("UTC_TIMESTAMP_REQUIRED")
    return d.astimezone(timezone.utc)


def _only_keys(record:dict,allowed:set[str],label:str)->dict:
    if not isinstance(record,dict) or set(record)-allowed:
        raise ValueError("UNSUPPORTED_OR_SECRET_FIELD:"+label)
    return record


def _market(info:dict)->Market:
    allowed={"sport","event_id","kind","period","selection","line",
             "team_id","player_id","stat","settlement"}
    _only_keys(info,allowed,"market")
    return Market(**info)


def _quote(data:dict|None)->PriceReceipt|None:
    if data is None:
        return None
    allowed={"market","odds_american","book","provider_id","provider_event_id",
             "provider_market_id","quote_id","receipt_id","raw_payload_sha256",
             "observed_at_utc","received_at_utc","event_start_utc"}
    _only_keys(data,allowed,"quote")
    r=dict(data)
    r["market"]=_market(r["market"])
    for k in ("observed_at_utc","received_at_utc","event_start_utc"):
        r[k]=_iso(r[k])
    return PriceReceipt(**r)


def run_from_manifest(payload:dict, *, chain:EvidenceChain|None=None)->dict:
    _only_keys(payload,{"projection","projection_ref","distribution","dispersion_fit_ref",
                        "period_fit_ref","markets","player_file","roster_ids","event_team_ids",
                        "simulation_count","simulation_seed"},"root")
    if ("projection" in payload)==("projection_ref" in payload):
        raise ValueError("EXACTLY_ONE_TEAM_PROJECTION_SOURCE_REQUIRED")
    pit_manifest_audit=None
    if "projection_ref" in payload:
        ref=_only_keys(payload["projection_ref"],
            {"sport","event_id","asof_utc","feature_paths",
             "ratings_csv","forecast","source_manifest"},"projection_ref")
        sport=ref.get("sport")
        asof=_iso(ref["asof_utc"])
        if "source_manifest" not in ref:
            raise ValueError("PIT_SOURCE_MANIFEST_REQUIRED_FOR_DIRECT_MODEL")
        if sport=="NFL":
            if "feature_paths" in ref or not ref.get("ratings_csv") or not isinstance(ref.get("forecast"),dict):
                raise ValueError("NFL_RIDGE_FORECAST_SOURCE_REQUIRED")
            paths={"ratings_csv":ref["ratings_csv"]}
            pit_manifest_audit=verify_model_feature_manifest(
                ref["source_manifest"],paths,sport=sport,
                event_id=ref["event_id"],forecast_asof_utc=asof)
            projection=from_nfl_ridge(ref["ratings_csv"],ref["forecast"],
                event_id=ref["event_id"],frozen_asof_utc=asof)
        elif sport in ("CFB","CBB","NBA","MLB"):
            if "forecast" in ref or "ratings_csv" in ref or not isinstance(ref.get("feature_paths"),dict):
                raise ValueError("CLAUDE_MODEL_FEATURE_FILES_REQUIRED")
            paths=ref["feature_paths"]
            pit_manifest_audit=verify_model_feature_manifest(
                ref["source_manifest"],paths,sport=sport,
                event_id=ref["event_id"],forecast_asof_utc=asof)
            projection=from_claude_sport(sport,paths,
                ref["event_id"],asof_utc=asof)
        else:
            raise ValueError("MODEL_BRIDGE_NOT_AVAILABLE")
        # Defend against local feature files changing while the recovered model
        # reads them. The signed/independent provider provenance gate remains
        # separate: repeated local hashes cannot authenticate remote authors.
        second_audit=verify_model_feature_manifest(
            ref["source_manifest"],paths,sport=sport,
            event_id=ref["event_id"],forecast_asof_utc=asof)
        if second_audit.data_sha256 != pit_manifest_audit.data_sha256:
            raise ValueError("PIT_FILE_CHANGED_WHILE_MODEL_WAS_RUNNING")
    else:
        p=_only_keys(payload["projection"],{
            "sport","event_id","home_id","away_id","expected_home","expected_away",
            "model_sha256","feature_sha256","asof_utc"},"projection")
        q=dict(p);q["asof_utc"]=_iso(q["asof_utc"])
        projection=TeamProjection(**q)
    fitted_dispersion=None
    if "dispersion_fit_ref" in payload:
        # Only fit the residual widths from the actual, prior-to-forecast
        # saved result ledger. Period shares are still explicit UNCALIBRATED
        # inputs; real PIT/forward calibration and provider auth remain open.
        ref=_only_keys(payload["dispersion_fit_ref"],
            {"path","raw_sha256","fit_asof_utc"},"dispersion_fit_ref")
        settings=_only_keys(payload["distribution"],
            {"sport","period_shares","status"},"fitted_distribution")
        if settings["sport"] != projection.sport:
            raise ValueError("DISPERSION_FIT_SPORT_MISMATCH")
        if _iso(ref["fit_asof_utc"])>=projection.asof_utc:
            raise ValueError("DISPERSION_FIT_AFTER_PROJECTION_FREEZE")
        source=Path(ref["path"])
        if source.is_symlink():
            raise ValueError("DISPERSION_FIT_SOURCE_SYMLINK_REFUSED")
        source=private_path(ref["path"])
        if not source.is_file() or not 0<source.stat().st_size<=MAX_FIT_BYTES:
            raise ValueError("DISPERSION_FIT_SOURCE_MISSING_OR_TOO_LARGE")
        original=source.read_bytes()
        actual_digest="sha256:"+sha256(original).hexdigest()
        if ref["raw_sha256"]!=actual_digest:
            raise ValueError("DISPERSION_FIT_ORIGINAL_LEDGER_HASH_MISMATCH")
        fitted_dispersion=fit_score_residuals(
            original,sport=projection.sport,cutoff_utc=ref["fit_asof_utc"])
        if fitted_dispersion["status"]!="TRAIN_ONLY_WIDTHS_READY_RESEARCH_NOT_CALIBRATED":
            raise ValueError("DISPERSION_TRAINING_CENSUS_INCOMPLETE_OR_LEAKED")
        if fitted_dispersion["training_model_sha256"]!=projection.model_sha256:
            raise ValueError("DISPERSION_TRAINING_MODEL_MISMATCH")
        dd={"sport":projection.sport,
            "sd_margin":fitted_dispersion["sd_margin"],
            "sd_total":fitted_dispersion["sd_total"],
            "period_shares":tuple(settings["period_shares"]),
            "model_sha256":fitted_dispersion["fitter_model_sha256"],
            "training_end_utc":_iso(ref["fit_asof_utc"]),
            "status":settings["status"]}
    else:
        dispersion=_only_keys(payload["distribution"],{
            "sport","sd_margin","sd_total","period_shares","model_sha256",
            "training_end_utc","status"},"distribution")
        dd=dict(dispersion)
        dd["training_end_utc"]=_iso(dd["training_end_utc"])
        dd["period_shares"]=tuple(dd["period_shares"])
    distribution=DistributionInput(**dd)
    roster=frozenset(payload.get("roster_ids",()))
    if any(not isinstance(p,str) or not p.strip() for p in roster):
        raise ValueError("INVALID_FROZEN_ROSTER_IDS")
    players=()
    if "player_file" in payload:
        info=_only_keys(payload["player_file"],
            {"path","raw_sha256","odds_observed_at_utc"},"player_file")
        src=Path(info["path"])
        if not src.is_file():
            raise ValueError("PLAYER_FORECAST_FILE_NOT_FOUND")
        raw=src.read_bytes()
        intake=ingest_player_forecast_csv(raw,sport=projection.sport,
            event_id=projection.event_id,game_roster_ids=roster,
            event_team_ids=frozenset({projection.home_id,projection.away_id}),
            forecast_freeze_utc=projection.asof_utc,
            odds_observed_at_utc=_iso(info["odds_observed_at_utc"]),
            expected_file_sha256=info["raw_sha256"])
        players=intake.moments
    now=datetime.now(timezone.utc)
    if projection.asof_utc>now:
        raise ValueError("MODEL_PROJECTION_DATED_IN_FUTURE")
    if not isinstance(payload.get("markets"),list) or len(payload["markets"])>5000:
        raise ValueError("INVALID_MARKET_LIST")
    batch=generate_score_scenarios(projection,distribution,
        roster_ids=roster,player_moments=players,
        count=payload.get("simulation_count",2000),
        seed=payload.get("simulation_seed",10),generated_at_utc=now)
    candidates=[]
    for item in payload["markets"]:
        _only_keys(item,{"market","dk_quote","dk_opposite_quote","v21_inputs"},"candidate")
        m=_market(item["market"])
        candidates.append(MarketCandidate(
            market=m,dk_quote=_quote(item.get("dk_quote")),
            dk_other_side=_quote(item.get("dk_opposite_quote")),
            v21_inputs=item.get("v21_inputs",{})))
    results=run_research_board(batch,tuple(candidates),
                               datetime.now(timezone.utc),chain=chain)
    results["input_version"]="SPORTSEDGE_FIVE_SPORT_RESEARCH_CLI_V1"
    results["generated_at_utc"]=datetime.now(timezone.utc).isoformat()
    results["generator_unvalidated"]=True
    results["dispersion_fit_status"]=(
        fitted_dispersion["status"] if fitted_dispersion else "NOT_TRAINED_FROM_LEDGER")
    results["dispersion_fit_source_sha256"]=(
        fitted_dispersion["source_file_sha256"] if fitted_dispersion else None)
    results["dispersion_fit_accepted_n"]=(
        fitted_dispersion["accepted_rows"] if fitted_dispersion else 0)
    results["dispersion_fit_model_sha256"]=(
        fitted_dispersion["fitter_model_sha256"] if fitted_dispersion else None)
    results["period_share_calibration_verified"]=False
    results["pit_file_manifest_status"]=(
        pit_manifest_audit.status if pit_manifest_audit else "NOT_CHECKED")
    results["pit_file_hash"]=(
        pit_manifest_audit.data_sha256 if pit_manifest_audit else None)
    results["pit_file_count"]=(
        pit_manifest_audit.file_count if pit_manifest_audit else 0)
    results["pit_manifest_source_authenticated"]=False
    results["model_projection_method"]=("RECOVERED_MODEL_FUNCTION"
            if "projection_ref" in payload else "CALLER_SUPPLIED_UNVERIFIED_MEAN")
    results["source_transport_authentication"]=False
    results["historical_backtest_certified"]=False
    return results


def main(argv:list[str]|None=None)->int:
    argv=sys.argv[1:] if argv is None else argv
    if len(argv)!=2:
        print("Usage: python -m sportsedge.markets.cli INPUT.json OUTPUT.json",file=sys.stderr)
        return 2
    input_path=Path(argv[0])
    output_path=Path(argv[1])
    if input_path.resolve()==output_path.resolve():
        raise ValueError("REFUSE_INPUT_OVERWRITE")
    input_bytes=input_path.read_bytes()
    if len(input_bytes)>MAX_MANIFEST_BYTES:
        raise ValueError("RUN_MANIFEST_TOO_LARGE")
    data=json.loads(input_bytes.decode("utf-8"),
                    object_pairs_hook=_unique_json_keys,
                    parse_constant=_deny_nonfinite_json)
    # Output is create-only. Never mutate an existing archived card.
    result=run_from_manifest(data)
    result["manifest_sha256"]="sha256:"+sha256(input_bytes).hexdigest()
    # Serialize to validated, standard JSON BEFORE opening the destination.
    # A failed serializer must never strand a half-written audit artifact.
    serialized=json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+"\n"
    created=False
    try:
        with output_path.open("x",encoding="utf-8") as f:
            created=True
            f.write(serialized)
    except Exception:
        if created:
            output_path.unlink(missing_ok=True)
        raise
    print(json.dumps({
        "status":result["status"],"markets":result["submitted_candidates"],
        "approved_stake_u":0,"official_counted":0,
        "saved_to":str(output_path)},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
