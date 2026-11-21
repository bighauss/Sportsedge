"""CLI: python -m research.audit.master <command> <file.json|file.csv> [options]

commands: leakage | quality | largest | calibration | clv | bias | disagreement |
          backtest | bootstrap | correlation | gates | postgame |
          simnoise | dispersion | full
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
        "clv": lambda: audits.clv_report(rows),
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
    if a.cmd == "full":
        rep = {k: f() for k, f in cmds.items() if k not in ("gates",) and (k != "backtest" or rules)}
    elif a.cmd in cmds:
        rep = cmds[a.cmd]()
    else:
        ap.error(f"unknown command {a.cmd}")
    s = json.dumps(rep, indent=2, default=str)
    (open(a.out, "w").write(s) if a.out else print(s))


if __name__ == "__main__":
    sys.exit(main())
