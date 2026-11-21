"""Ensure Stage 2's own eleven tests are actually run by quant-eightpack CI.

The audit workflow currently discovers only test_quant_*.py. The original
Stage 2 tests have a different basename, and generic green CI alone did not
execute them. Importing Stage2Checks here makes unittest discovery execute
the complete original suite without copying or changing test assertions.

Synthetic/offline regression only. Does not authenticate historical wagers,
market prices, odds timestamps, model calibration, source feeds, or any EV.
"""
from test_sportsedge_stage2_readonly_audit import Stage2Checks

# Expose original TestCase to the existing unittest discover loader.
__all__ = ("Stage2Checks",)
