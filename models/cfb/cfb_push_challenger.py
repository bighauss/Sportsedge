"""Push-aware CHALLENGER repricing for frozen CFB card rows. PAPER / 0u.

The frozen model (sportsedge_cfb_model.py, sha-pinned in cfb_run_it.py) prices
spreads/totals with a continuous Normal, so a whole-number line gets 0 push mass
and EV = p*d - 1. This module does NOT modify the frozen file or its rows. It
recomputes, beside each row, the same Normal with integer lines treated as the
[line-0.5, line+0.5) bucket and push-refund EV:
    EV = p_win*(d-1) - p_loss,  p_loss = 1 - p_win - p_push
Blend: 0.30*p_win_model + 0.70*p_novig*(1 - p_push) (frozen weights).
Rows the challenger cannot reprice are returned unchanged with a reason.
"""
from __future__ import annotations

from statistics import NormalDist

import sportsedge_cfb_model as M

N = NormalDist()


def _sd(market):
    if market in ("Spread", "Total"):
        return M.SD_MARGIN if market == "Spread" else M.SD_TOTAL
    if market.startswith("1H"):
        return M.SD_1H
    if market.endswith(" TT"):
        return M.SD_TT
    return None


def push_split(mean, line, sd):
    """(P(X > line), P(push)) for X ~ Normal(mean, sd) on an integer-scored outcome."""
    line = float(line)
    if line != int(line):
        return 1 - N.cdf((line - mean) / sd), 0.0
    hi = 1 - N.cdf((line + 0.5 - mean) / sd)
    return hi, (1 - N.cdf((line - 0.5 - mean) / sd)) - hi


def reprice(row):
    """Return a copy of a frozen card row with challenger_* fields added."""
    out = dict(row)
    mk, line, mean = row.get("market", ""), row.get("line"), row.get("proj")
    sd = _sd(mk)
    if mk == "ML" or line is None or mean is None or sd is None:
        out["challenger_status"] = "UNCHANGED_NO_PUSH_MARKET" if mk == "ML" else "UNCHANGED_UNSUPPORTED"
        return out
    d = M.dec(row["odds"])
    if mk.endswith("Spread"):
        # rows store the side's own margin mean and its own spread; side covers if margin + line > 0
        p_win, p_push = push_split(mean, -float(line), sd)
    elif row.get("direction") == "over":
        p_win, p_push = push_split(mean, line, sd)
    elif row.get("direction") == "under":
        over, p_push = push_split(mean, line, sd)
        p_win = 1 - over - p_push
    else:
        out["challenger_status"] = "UNCHANGED_UNKNOWN_DIRECTION"
        return out
    p_blend = M.P_BLEND_MODEL * p_win + (1 - M.P_BLEND_MODEL) * row["p_market"] * (1 - p_push)
    out.update(challenger_status="REPRICED_PUSH_AWARE", challenger_p_win=p_win, challenger_p_push=p_push,
               challenger_ev_raw=p_win * (d - 1) - (1 - p_win - p_push),
               challenger_ev_blend=p_blend * (d - 1) - (1 - p_blend - p_push))
    return out
