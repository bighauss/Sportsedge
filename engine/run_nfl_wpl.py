#!/usr/bin/env python3
"""NFL RUN IT with simulator win/push/loss pricing. Run as its own process; frozen v5 untouched.

Usage:  python engine/run_nfl_wpl.py board.csv
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_wpl_capture  # noqa: E402
import run_nfl  # noqa: E402


def main(path):
    with nfl_wpl_capture.installed():
        return run_nfl.main(path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "board.csv")
