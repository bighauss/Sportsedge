"""SportsEdge Master Audit layer (Theo 50 + Rusty_Bill + PlusEVAnalytics).

Read-only research/audit package. Standard library only. Never imports or edits
engine/sportsedge_v5.py. See docs/research/MASTER_AUDIT_SPEC.md.
"""
from . import odds, stats, audits, props_corr, projections, pipeline  # noqa: F401
__version__ = "1.0.0"
