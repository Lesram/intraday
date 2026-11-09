# ORB on stocks in play — pre-registration (written 2026-10-21 ~04:10Z, before any bar data for this test is fetched)

Question: does the published 5-minute opening-range breakout on "stocks in play" (Zarattini, Barbon & Aziz, 2024)
earn money after costs on data after the paper's 2016-2023 sample?

Period: sessions 2025-01-02 .. 2026-10-20 (all out of sample for the paper).
Symbols: current NASDAQ/NYSE/AMEX stock listings (rreichel3/US-Stock-Symbols, fetched 2026-10-21; ETFs not listed),
excluding symbols with ^ / . and names with Warrant, Unit(s), Right(s), Preferred, "Depositary Shares, each representing",
Notes due, Subordinated. Delisted names are missing (survivorship bias, disclosed).
Daily filters on day d, from SIP daily bars (raw) through d-1: prior close > $5; mean volume over the prior 14 sessions
>= 1,000,000 shares; ATR14 (mean true range, prior 14 sessions) > $0.50.
Opening bar: SIP 5-minute bar 09:30-09:35 ET. RV = its volume / mean of that bar's volume over the prior 14 sessions
(at least 10 available). Stocks in play: RV >= 1.0, top 20 by RV. Direction: opening bar close > open -> long only;
close < open -> short only; equal -> skip.
Entry: stop order at the opening-bar high (long) / low (short) from 09:35; fills on the first SIP 1-minute bar that trades
through: long fill = max(level, bar open), short fill = min(level, bar open). Not triggered by the close -> no trade.
Stop: 10% of ATR14 from the fill. Checked on 1-minute highs/lows from the fill bar on; if the fill bar touches it, stopped
in that bar at the stop; later bars fill at the stop or the bar open if it opens beyond. Otherwise exit at the last 1-minute
close before 16:00 ET.
Costs: 3 bps per side (primary); 1 bp per side (sensitivity).
Metrics: per-trade net R = net return / (0.1 x ATR14 / fill); t = session-clustered (per-session mean R, SE over sessions).
Portfolio (descriptive): 1% of equity at risk per trade, total notional capped at 4x equity pro rata; daily return; Sharpe.
PRIMARY: all trades (long and short, as published), net mean R at 3 bps per side.
KILL BAR: net mean R <= 0 or session-clustered t < 2.0 -> DEAD for this period.
Secondary (descriptive only): long trades only (the platform is long-only); 1 bp per side; 2025 vs 2026; portfolio stats.
No parameter search.
