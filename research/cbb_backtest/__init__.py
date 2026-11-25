"""CBB rolling-origin backtest (research only; PAPER / 0u; NON_COUNTED).

The frozen native model lives in models/cbb/ (imported read-only as `cbbd_native_score_model`);
make it importable without a manual PYTHONPATH. Appended (not prepended) so an explicit
PYTHONPATH always takes precedence.
"""
import sys
from pathlib import Path

_NATIVE_DIR = str(Path(__file__).resolve().parents[2] / "models" / "cbb")
if Path(_NATIVE_DIR).is_dir() and _NATIVE_DIR not in sys.path:
    sys.path.append(_NATIVE_DIR)
