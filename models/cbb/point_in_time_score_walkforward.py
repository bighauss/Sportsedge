"""CBB prospective score/market walk-forward audit (stdlib, PRIVATE inputs only).

A record must contain the original research-only prediction produced by
torvik_point_in_time_baseline.project(), a final-score receipt and optionally
a same-event same-book pre-freeze two-sided quote. Historical user-declared
timestamps and hash strings are not external source attestation.

NO betting recommendations or production model changes. Paper / 0 units.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import mean, stdev

UTC = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?Z$")
DIGEST = re.compile(r"^[0-9a-fA-F]{64}$")
ROOT = Path(__file__).resolve().parents[2]


class Blocked(ValueError):
    pass


def _time(value, name):
    if not isinstance(value, str) or not UTC.fullmatch(value):
        raise Blocked(f"{name}: UTC_Z_TIMESTAMP_REQUIRED")
    try:
        return datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise Blocked(f"{name}: INVALID_TIMESTAMP") from exc


def _hash(value, name):
    if not isinstance(value, str) or not DIGEST.fullmatch(value):
        raise Blocked(f"{name}: INVALID_SHA256")
    return value.lower()


def _num(value, name, lower, upper):
    if isinstance(value, bool):
        raise Blocked(f"{name}: INVALID_NUMBER")
    try:
        f = float(value)
    except (ValueError, TypeError) as exc:
        raise Blocked(f"{name}: INVALID_NUMBER") from exc
    if not math.isfinite(f) or not lower <= f <= upper:
        raise Blocked(f"{name}: OUT_OF_RANGE")
    return f


def _integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise Blocked(f"{name}: INVALID_INTEGER")
    return value


def _price(value, name):
    p = _integer(value, name, -100000, 100000)
    if abs(p) < 100:
        raise Blocked(f"{name}: INVALID_AMERICAN_ODDS")
    return p


def _novig(home, away):
    def implied(price):
        return 100 / (100 + price) if price > 0 else -price / (-price + 100)
    h, a = implied(home), implied(away)
    return h / (h + a)


def _parse_prediction(record):
    if not isinstance(record, dict):
        raise Blocked("PREDICTION_REQUIRED")
    if record.get("status") != "PAPER_NON_COUNTED_UNCALIBRATED" or record.get("official") is not False or record.get("stake_u") != 0:
        raise Blocked("UNEXPECTED_PREDICTION_ADMISSION_STATE")
    event = record.get("game_id")
    if not isinstance(event, str) or not event.strip():
        raise Blocked("GAME_ID_REQUIRED")
    season = _integer(record.get("season"), "season", 2000, 2100)
    home, away = record.get("home_team_id"), record.get("away_team_id")
    if any(not isinstance(x, str) or not x.strip() for x in (home, away)) or home == away:
        raise Blocked("TEAM_IDS_INVALID")
    freeze = _time(record.get("freeze_utc"), "freeze_utc")
    tip = _time(record.get("tipoff_utc"), "tipoff_utc")
    if freeze >= tip:
        raise Blocked("PREDICTION_NOT_FROZEN_PRE_TIP")
    _hash(record.get("model_sha256"), "model_sha256")
    sources = record.get("source_clock_consistent_not_authenticated")
    if not isinstance(sources, dict) or not {"home", "away", "league"}.issubset(sources):
        raise Blocked("PREDICTION_SOURCE_MANIFEST_MISSING")
    for name, source in sources.items():
        if not isinstance(source, dict):
            raise Blocked(f"{name}: INVALID_MANIFEST")
        _hash(source.get("sha256"), f"{name}.sha256")
        if _time(source.get("captured_utc"), f"{name}.captured_utc") > freeze:
            raise Blocked(f"{name}: FUTURE_CAPTURE")
    hp = _num(record.get("home_points"), "home_points", 0, 250)
    ap = _num(record.get("away_points"), "away_points", 0, 250)
    if abs(_num(record.get("margin_home"), "margin_home", -250, 250) - (hp-ap)) > 1e-7:
        raise Blocked("PREDICTION_MARGIN_INCONSISTENT")
    if abs(_num(record.get("total"), "total", 0, 500) - (hp+ap)) > 1e-7:
        raise Blocked("PREDICTION_TOTAL_INCONSISTENT")
    return dict(id=event, season=season, home=home, away=away,
                freeze=freeze, tip=tip, home_p=hp, away_p=ap,
                margin_p=hp-ap, total_p=hp+ap)


def _parse_final(final, p):
    if final is None:
        return None
    if not isinstance(final, dict):
        raise Blocked("FINAL_RECEIPT_INVALID")
    if final.get("game_id") != p["id"] or final.get("season") != p["season"] or final.get("home_team_id") != p["home"] or final.get("away_team_id") != p["away"]:
        raise Blocked("FINAL_IDENTITY_MISMATCH")
    _hash(final.get("sha256"), "final.sha256")
    if final.get("status") != "FINAL" or final.get("period") != "FG_INCL_OT":
        raise Blocked("FINAL_SETTLEMENT_STATUS_OR_PERIOD_INVALID")
    published = _time(final.get("published_utc"), "final.published_utc")
    captured = _time(final.get("captured_utc"), "final.captured_utc")
    if not p["tip"] < published <= captured:
        raise Blocked("FINAL_RELEASE_OR_CAPTURE_CLOCK_INVALID")
    h = _integer(final.get("home_score"), "final.home_score", 0, 250)
    a = _integer(final.get("away_score"), "final.away_score", 0, 250)
    if h == a:
        raise Blocked("FULL_GAME_FINAL_TIE_OR_NON_FINAL")
    return dict(published=published, home=h, away=a, margin=h-a, total=h+a)


def _parse_quote(quote, p, max_quote_age_hours):
    if quote is None:
        return None
    if not isinstance(quote, dict):
        raise Blocked("QUOTE_INVALID")
    if quote.get("game_id") != p["id"] or quote.get("season") != p["season"]:
        raise Blocked("QUOTE_EVENT_MISMATCH")
    if quote.get("period") != "FG" or not isinstance(quote.get("book"), str) or not quote["book"].strip():
        raise Blocked("QUOTE_PERIOD_OR_BOOK_INVALID")
    _hash(quote.get("sha256"), "quote.sha256")
    capture = _time(quote.get("captured_utc"), "quote.captured_utc")
    if capture > p["freeze"] or capture >= p["tip"]:
        raise Blocked("QUOTE_NOT_CAPTURED_BEFORE_MODEL_FREEZE")
    if (p["freeze"]-capture).total_seconds() > max_quote_age_hours*3600:
        raise Blocked("QUOTE_STALE")
    markets = {}
    configs = (
        ("spread", ("home_spread", "home_price", "away_price")),
        ("total", ("total_line", "over_price", "under_price")),
        ("ml", ("home_ml", "away_ml")),
    )
    for family, keys in configs:
        exists = [key in quote and quote[key] is not None for key in keys]
        if any(exists) and not all(exists):
            raise Blocked("PARTIAL_TWO_SIDED_" + family.upper())
        if not all(exists):
            continue
        if family == "spread":
            line = _num(quote["home_spread"], "home_spread", -100, 100)
            _price(quote["home_price"], "home_price")
            _price(quote["away_price"], "away_price")
            markets[family] = -line  # home score margin implied by home spread
        elif family == "total":
            line = _num(quote["total_line"], "total_line", 0.5, 500)
            _price(quote["over_price"], "over_price")
            _price(quote["under_price"], "under_price")
            markets[family] = line
        else:
            markets[family] = _novig(_price(quote["home_ml"], "home_ml"),
                                   _price(quote["away_ml"], "away_ml"))
    if not markets:
        raise Blocked("QUOTE_HAS_NO_COMPLETE_TWO_SIDED_MARKET")
    return markets


def _one(row, index, dup_count, max_quote_age_hours):
    event = (row.get("prediction", {}).get("game_id")
             if isinstance(row, dict) and isinstance(row.get("prediction"), dict) else None)
    output = {"input_index": index, "game_id": event, "status": "BLOCKED",
              "official": False, "stake_u": 0}
    try:
        if not isinstance(row, dict):
            raise Blocked("ROW_NOT_OBJECT")
        p = _parse_prediction(row.get("prediction"))
        key = (p["season"], p["id"])
        if dup_count[key] > 1:
            raise Blocked("DUPLICATE_EVENT_ALL_COPIES_QUARANTINED")
        f = _parse_final(row.get("final"), p)
        if f is None:
            output.update(status="PENDING_FINAL", reason="NO_FINAL_RECEIPT")
            return output, None
        output.update(status="VALID_SCORE_RECEIPTS_UNAUTHENTICATED")
        try:
            q = _parse_quote(row.get("quote"), p, max_quote_age_hours)
            output["quote_status"] = "VALID_CLOCK_UNAUTHENTICATED" if q is not None else "NOT_CAPTURED"
        except (Blocked, KeyError, TypeError, AttributeError) as exc:
            q = None
            output["quote_status"] = "BLOCKED_QUOTE"
            output["quote_reason"] = str(exc)
        return output, {**p, **f, "quote": q, "input_index": index}
    except (Blocked, KeyError, TypeError, AttributeError, OverflowError) as exc:
        output["reason"] = str(exc)
        return output, None


def _normal_cdf(z):
    return (1 + math.erf(z/math.sqrt(2))) / 2


def _paired_ci(values):
    """Normal-approximate event-level CI, descriptive only, n>=30."""
    if len(values) < 30:
        return None
    mu = mean(values)
    radius = 1.96*stdev(values)/math.sqrt(len(values))
    return [mu-radius, mu+radius]


def _summarize_pairs(pairs, metric):
    if not pairs:
        return dict(n=0, metric=metric, model_average=None, market_average=None,
                    improvement_market_minus_model=None, event_ci95=None)
    return dict(n=len(pairs), metric=metric,
                model_average=mean(x[0] for x in pairs),
                market_average=mean(x[1] for x in pairs),
                improvement_market_minus_model=mean(x[1]-x[0] for x in pairs),
                event_ci95=_paired_ci([x[1]-x[0] for x in pairs]))


def audit(rows, *, min_prior=30, max_quote_age_hours=24):
    """Only a prequential evaluation. Never fit on result unavailable at freeze.

    Keep every source row and fail duplicates on BOTH copies.
    """
    if not isinstance(rows, list):
        raise ValueError("INPUT_MUST_BE_LIST")
    if type(min_prior) is not int or min_prior < 30:
        raise ValueError("MIN_PRIOR_MUST_BE_AT_LEAST_30_PRE_REGISTERED")
    if isinstance(max_quote_age_hours, bool) or not isinstance(max_quote_age_hours, (float,int)) or not 0 < max_quote_age_hours <= 168:
        raise ValueError("MAX_QUOTE_AGE_HOURS_INVALID")
    dup = Counter((r["prediction"].get("season"),r["prediction"].get("game_id"))
                  for r in rows if isinstance(r,dict) and isinstance(r.get("prediction"),dict))
    all_reports, valid = [], []
    for i, r in enumerate(rows):
        report, parsed = _one(r,i,dup,max_quote_age_hours)
        all_reports.append(report)
        if parsed is not None:
            valid.append(parsed)
    by_season = defaultdict(list)
    for v in valid:
        by_season[v["season"]].append(v)
    paired = defaultdict(list)
    season_totals = defaultdict(lambda: {"n_evaluated":0,"n_eligible":0})
    for season, records in sorted(by_season.items()):
        # Strict earlier publication time, not simply earlier tipoff.
        releases = sorted(records,key=lambda x:(x["published"],x["id"]))
        predictions = sorted(records,key=lambda x:(x["freeze"],x["id"]))
        ix = 0
        n = 0
        residual_mean = 0.0
        residual_m2 = 0.0
        for p in predictions:
            while ix < len(releases) and releases[ix]["published"] < p["freeze"]:
                t = releases[ix]
                resid = t["margin"]-t["margin_p"]
                n += 1
                delta = resid-residual_mean
                residual_mean += delta/n
                residual_m2 += delta*(resid-residual_mean)
                ix += 1
            out = all_reports[p["input_index"]]
            season_totals[season]["n_eligible"] += 1
            if n < min_prior:
                out["evaluation_status"] = "INSUFFICIENT_PRIOR_PUBLISHED_FINALS"
                out["train_n"] = n
                continue
            out["evaluation_status"] = "WALK_FORWARD_SCORED_PAPER_0U"
            out["train_n"] = n
            season_totals[season]["n_evaluated"] += 1
            m_err = abs(p["margin"]-p["margin_p"])
            t_err = abs(p["total"]-p["total_p"])
            out["model_margin_abs_error"] = m_err
            out["model_total_abs_error"] = t_err
            q = p["quote"]
            if q is not None:
                if "spread" in q:
                    market_err = abs(p["margin"]-q["spread"])
                    paired["spread"].append((m_err, market_err))
                    out["spread_line_abs_error"] = market_err
                if "total" in q:
                    market_err = abs(p["total"]-q["total"])
                    paired["total"].append((t_err, market_err))
                    out["total_line_abs_error"] = market_err
                if "ml" in q and n>=2 and residual_m2/(n-1) > 1e-18:
                    # Strictly earlier released outcomes only; research distribution.
                    resid_sd = math.sqrt(residual_m2/(n-1))
                    mp = min(1-1e-12,max(1e-12,_normal_cdf((p["margin_p"]+residual_mean)/resid_sd)))
                    bp = min(1-1e-12,max(1e-12,q["ml"]))
                    y = int(p["margin"]>0)
                    paired["moneyline"].append(((mp-y)**2,(bp-y)**2))
                    out["model_ml_brier"] = (mp-y)**2
                    out["market_ml_brier"] = (bp-y)**2
    scored = [r for r in all_reports if r.get("evaluation_status")=="WALK_FORWARD_SCORED_PAPER_0U"]
    return {
        "status": "CBB_FROZEN_WALKFORWARD_RESEARCH_UNAUTHENTICATED_PAPER_0U",
        "official": False, "stake_u": 0, "input_rows": len(rows),
        "row_statuses": dict(Counter(x["status"] for x in all_reports)),
        "quote_statuses": dict(Counter(x.get("quote_status","NOT_EVALUATED") for x in all_reports)),
        "walkforward_evaluated_n": len(scored),
        "model_margin_mae": mean(r["model_margin_abs_error"] for r in scored) if scored else None,
        "model_total_mae": mean(r["model_total_abs_error"] for r in scored) if scored else None,
        "paired_spread": _summarize_pairs(paired["spread"], "MAE_MARGIN_POINTS"),
        "paired_total": _summarize_pairs(paired["total"], "MAE_TOTAL_POINTS"),
        "paired_ml_brier": _summarize_pairs(paired["moneyline"], "MONEYLINE_BRIER"),
        "per_season": {str(k):v for k,v in sorted(season_totals.items())},
        "rows": all_reports,
        "warnings": [
            "SELF_ASSERTED_TIMESTAMPS_AND_SHA_DIGESTS_NOT_PROVIDER_AUTHENTICATION",
            "REQUIRES_UNALTERED_PRE_TIP_PREDICTIONS_AND_AUTHENTIC_POSTGAME_RESULTS",
            "NO_LATE_MARKET_DATA_RECONSTRUCTION_OR_CLV",
            "MONEYLINE_NORMAL_RESIDUAL_BASELINE_UNCALIBRATED",
            "NO_BETTING_EV_OR_AUTOMATIC_MODEL_PROMOTION"
        ]
    }


def _no_duplicate_keys(pairs):
    out={}
    for key, value in pairs:
        if key in out:
            raise ValueError("DUPLICATE_JSON_KEY:" + key)
        out[key]=value
    return out


def _reject_constant(v):
    raise ValueError("NONFINITE_JSON_CONSTANT:" + v)


def _private(path):
    resolved = Path(path).expanduser().resolve()
    if resolved == ROOT or ROOT in resolved.parents:
        raise ValueError("PRIVATE_SOURCE_AND_REPORT_REQUIRED_OUTSIDE_PUBLIC_REPO")
    return resolved


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_json")
    parser.add_argument("--report",required=True)
    parser.add_argument("--min-prior",type=int,default=30)
    parser.add_argument("--max-quote-age-hours",type=float,default=24)
    args=parser.parse_args(argv)
    source=_private(args.source_json)
    report=_private(args.report)
    if source==report:
        raise ValueError("INPUT_OUTPUT_COLLISION")
    if report.exists():
        raise FileExistsError("CREATE_ONLY_REPORT")
    raw=source.read_bytes()
    records=json.loads(raw.decode("utf-8-sig"),
                       object_pairs_hook=_no_duplicate_keys,
                       parse_constant=_reject_constant)
    output=audit(records,min_prior=args.min_prior,
                 max_quote_age_hours=args.max_quote_age_hours)
    output["source_sha256"]=hashlib.sha256(raw).hexdigest()
    # The report itself contains only provider-supplied records already included
    # in the private input; NEVER write it into public Git.
    with report.open("x",encoding="utf-8") as f:
        json.dump(output,f,indent=2,sort_keys=True,allow_nan=False)
        f.write("\n")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
