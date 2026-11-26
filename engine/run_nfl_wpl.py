#!/usr/bin/env python3
"""NFL RUN IT with explicit simulator win/push/loss columns. Wraps run_nfl.main; frozen v5 untouched.

Usage:  python engine/run_nfl_wpl.py board.csv
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nfl_wpl_capture  # noqa: E402
import run_nfl  # noqa: E402


def main(path):
    nfl_wpl_capture.install()
    return run_nfl.main(path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "board.csv")
