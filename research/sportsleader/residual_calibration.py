"""Empirical paired score residual pricing; caller must supply prior-only residuals."""
import math

def price(home, away, residuals, market, line, side, decimal_odds):
    if market not in {"margin","total","home_total","away_total"} or side not in {"over","under"}:
        raise ValueError("unsupported market or side")
    if not all(math.isfinite(x) for x in (home,away,line,decimal_odds)) or min(home,away)<0 or decimal_odds<=1:
        raise ValueError("invalid inputs")
    residuals=list(residuals)
    if len(residuals)<100:
        raise ValueError("insufficient residual sample")
    wins=losses=pushes=0
    for dh,da in residuals:
        if not math.isfinite(dh) or not math.isfinite(da):
            raise ValueError("nonfinite residual")
        h=max(0,round(home+dh))
        a=max(0,round(away+da))
        value={"margin":h-a,"total":h+a,"home_total":h,"away_total":a}[market]
        diff=(value-line)*(1 if side=="over" else -1)
        wins+=diff>0
        losses+=diff<0
        pushes+=diff==0
    n=len(residuals)
    return dict(win=wins/n,loss=losses/n,push=pushes/n,
                ev=(wins*(decimal_odds-1)-losses)/n,n=n,
                release_state="PAPER_0U_NON_COUNTED")
