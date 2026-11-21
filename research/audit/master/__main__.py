"""CLI: python -m research.audit.master <command> <file.json|file.csv> [options]

commands: leakage | quality | largest | calibration | bias | disagreement |
          backtest | bootstrap | correlation | gates | postgame |
          simnoise | dispersion | challenge | full
Input: JSON list of prediction rows or CSV (inputs column may hold JSON).
Output: JSON report to stdout (or --out file). Read-only.
"""
import argparse, csv, json, sys
from . import audits, stats, props_corr, pipeline, uncertainty


def load(path):
    if path.endswith(".json"):
        return json.load(open(path))
    rows = list(csv.DictReader(open(newline="", file=path)))
    for r in rows:
        if r.get("inputs"):
            try: r["inputs"] = json.loads(r["inputs"])
            except ValueError: pass
        if r.get("prices"):
            try: r["prices"] = json.loads(r["prices"])
            except ValueError: pass
    return rows


def challenge(rows, rules=()):
    """Rusty's Universal Model Challenge: run every check, rank issues by importance,
    say how to test each fix on unseen data. Changes nothing."""
    issues = []
    add = lambda sev, area, what, test: issues.append({"severity": sev, "area": area, "finding": what, "how_to_test_fix": test})
    for f in audits.leakage_audit(rows):
        add(f["severity"], "data leakage", f"{f['code']} {f['pred_id']} {f['detail']}",
            "Rebuild the prediction using only inputs stamped before pred_ts; re-score on a later window.")
    for f in audits.data_quality(rows)["issues"]:
        add(f["severity"], "unreliable inputs", f"{f['code']} {f['pred_id'] or ''} {f['detail']}".strip(),
            "Fix the record at the source; re-run the backtest and confirm results on unseen games.")
    le = audits.largest_edge_stress(rows, 10)
    for i in le["top"]:
        if i["status"] != "PLAUSIBLE":
            add("CRITICAL" if i["status"] == "BLOCKED" else "HIGH", "overconfident edges",
                f"{i['pred_id']} edge {i['edge']:.1%}: {', '.join(i['flags'])}",
                "Diagnose the inputs driving it; if a bug, fix and re-test on games after the fix date.")
    wl = [r for r in rows if r.get("result") in ("W", "L")]
    if wl:
        for b in stats.calibration_table([float(r["model_prob"]) for r in wl], [int(r["result"] == "W") for r in wl]):
            if b["verdict"] in ("OVERCONFIDENT", "UNDERCONFIDENT"):
                add("HIGH", "overconfident probabilities",
                    f"{b['bucket']} predicted {b['mean_pred']:.1%} vs actual {b['observed']:.1%} (n={b['n']})",
                    "Fit a recalibration on older games only; accept it only if newer games improve.")
        md = audits.market_disagreement(rows)
        if md["trend"] == "BIGGER_DISAGREEMENT_WORSE":
            add("HIGH", "model vs market", f"Bigger disagreements do worse: {md['weakness_buckets']}",
                "Cap or review large edges; test the cap on a forward window.")
    d = uncertainty.dispersion_audit(rows)
    if d.get("status") not in (None, "OK", "SMALL_SAMPLE"):
        add("HIGH", "uncertainty", f"{d['status']}: model uses {d['spread_used']:.0%} of the real spread",
            "Apply the recommended SD multiplier on the later half only; keep it if accuracy improves.")
    sn = uncertainty.sim_noise_check([r for r in rows if r.get("odds") not in (None, "")])
    if sn["flagged"]:
        add("MEDIUM", "simulation count", f"{sn['flagged']} picks have sim noise > 10% of edge (max sims needed {sn['max_sims_needed']})",
            "Raise sim count for those picks only; confirm probabilities stop moving between seeds.")
    if rules:
        bt = audits.backtest_audit(rows, rules)
        if bt["retrospective"]["n"]:
            add("HIGH", "track record", f"{bt['retrospective']['n']} picks qualified by rules adopted later",
                "Report them separately; judge the model only on prospective picks.")
    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    issues.sort(key=lambda x: order.get(x["severity"], 9))
    return {"n_issues": len(issues), "issues": issues,
            "note": "Unnecessary features: run ablation.ablation with your variable groups. No formulas or model logic were changed."}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="master_audit")
    ap.add_argument("cmd"); ap.add_argument("file")
    ap.add_argument("--rules", help="JSON [{rule_version, active_ts}]")
    ap.add_argument("--history", help="out-of-sample graded rows for calibration gate")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--now"); ap.add_argument("--out")
    a = ap.parse_args(argv)
    rows = load(a.file)
    rules = json.load(open(a.rules)) if a.rules else []
    wl = [r for r in rows if r.get("result") in ("W", "L")]
    P = lambda: [float(r["model_prob"]) for r in wl]
    O = lambda: [int(r["result"] == "W") for r in wl]
    cmds = {
        "leakage": lambda: audits.sort_findings(audits.leakage_audit(rows)),
        "quality": lambda: {k: v for k, v in audits.data_quality(rows).items() if k != "cleaned"},
        "largest": lambda: audits.largest_edge_stress(rows, a.top),
        "calibration": lambda: {"brier": stats.brier(P(), O()), "log_loss": stats.log_loss(P(), O()),
                                "ece": stats.ece(P(), O()), "table": stats.calibration_table(P(), O())},
        "bias": lambda: audits.bias_breakdown(rows),
        "disagreement": lambda: audits.market_disagreement(rows),
        "backtest": lambda: audits.backtest_audit(rows, rules),
        "bootstrap": lambda: stats.bootstrap_roi(rows),
        "correlation": lambda: props_corr.joint_hit_rates(rows),
        "gates": lambda: pipeline.run_gates(rows, load(a.history) if a.history else (), a.now),
        "postgame": lambda: pipeline.postgame_report(rows, rules),
        "simnoise": lambda: uncertainty.sim_noise_check(rows),
        "dispersion": lambda: uncertainty.dispersion_audit(rows),
    }
    if a.cmd == "challenge":
        rep = challenge(rows, rules)
    elif a.cmd == "full":
        rep = {k: f() for k, f in cmds.items() if k not in ("gates",) and (k != "backtest" or rules)}
    elif a.cmd in cmds:
        rep = cmds[a.cmd]()
    else:
        ap.error(f"unknown command {a.cmd}")
    s = json.dumps(rep, indent=2, default=str)
    (open(a.out, "w").write(s) if a.out else print(s))


if __name__ == "__main__":
    sys.exit(main())
