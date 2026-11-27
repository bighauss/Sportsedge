"""Research-only pricing entry point with chronological admission."""
from research.sportsleader.chronological_residuals import select
from research.sportsleader.residual_calibration import price

def calibrated_price(home, away, records, target_season, market, line, side, decimal_odds):
    pairs=select(records,target_season)
    result=price(home,away,pairs,market,line,side,decimal_odds)
    return dict(result,target_season=target_season,
                provenance="UNAUTHENTICATED_METADATA",
                calibration_status="RESEARCH_ONLY")
