"""Opt-in native MLB RUN IT source -> shared player/inning simulation dry run.

No bookmaker data used as simulation features. No historical source backfill.
Output is a research JSON census; does not call legacy RUN IT card/pricing.
Usage: python -m models.mlb.shared_inning_run models/mlb/sample_inputs --draws 128 --summary
"""
import argparse
import json

from models.mlb.shared_inning_sim import run_research


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", help="existing native MLB CSV input directory")
    parser.add_argument("--draws", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--summary", action="store_true", help="omit individual price/selection rows")
    args = parser.parse_args(argv)
    report = run_research(args.inputs, draws=args.draws, seed=args.seed)
    if args.summary:
        for g in report["games"]:
            g.pop("offers", None)
    print(json.dumps(report,sort_keys=True,allow_nan=False))
    return 0 if all(g["status"] == "SIMULATED_RESEARCH" for g in report["games"]) and report["games"] else 2


if __name__=="__main__":
    raise SystemExit(main())
