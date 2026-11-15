# Polymarket / prediction-market open-source research watchlist

Verified public GitHub repository names on 2026-11-15. They are **external references**, not SportsEdge dependencies, installed plugins, or trusted production code.

| Research target | Repo | Intended evaluation | Current disposition |
| --- | --- | --- | --- |
| AI multi-strategy workstation | https://github.com/recogardtech/AutoPilotPM | Sandboxed research assistant, strategy catalogue and local dashboard | **Read only**; repo advertises live account execution; do not install unattended |
| Market strategy backtesting | https://github.com/evan-kolberg/prediction-market-backtesting | Walk-forward backtest, costs, order-book depth, drawdown and slippage comparisons | **Evaluate** data provenance, mixed licensing and Python/Rust setup before reuse |
| Execution toolkit | https://github.com/tarpboi/Prediction-Markets-Trading-Bot-Toolkits | Reference architecture for copy trading, event streaming, and correlation monitoring | **Read only**; never enable order placement/copy trading without independent security review |
| Temperature-settlement forecasting | https://github.com/yangyuan-zhen/PolyWeather | Observation/settlement-station matching, METAR/SPECI, forecast error bands | **Research only**; public repo is not a guarantee of a complete free trading bot |
| Limit-order liquidity toolkit | https://github.com/lihanyu81/polymarket_lp_tool | Reward formulas, fill risk, cancellation, repricing and order book behavior | **Research only**; live orders/keys not authorized |

## Safe evaluation plan
1. Pin a commit SHA, inspect licenses, README, dependencies, external downloads and any secrets handling before running.
2. Use historical/public/read-only or locally fabricated synthetic data, **never keys**, copied accounts, wallets, or private SportsEdge capture data.
3. Compare proposed model evidence with an unchanged baseline and chronological splits. Include fees, slippage, execution probability, resolution rules and capital-at-risk.
4. Keep prediction-market prices and SportsEdge sportsbook prices on separate contract schemas; no cross-market 'arbitrage' is inferred from price similarity.
5. Any execution capability stays disabled until explicit approval, applicable location eligibility, account permissions and independent financial/risk safeguards are verified.

These five tools are **not** deployed, and no orders were created.
