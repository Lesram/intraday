# Gap-up momentum — pre-registration (written 2026-10-21 ~01:40Z, before any gap data is fetched)

Question: on full-market (SIP) data, does the live momentum entry rule earn money after costs
on gap-up mornings, the only time the live regime label opens (an IEX artifact)?

Data: Alpaca SIP 1-minute bars 09:30-14:01 ET for the 20 live symbols; daily bars (split-adjusted)
for gaps. Sessions 2024-01-02 .. 2026-10-20. In-sample (IS) = 2024; out-of-sample (OOS) = 2025-01-02 .. 2026-10-20.

Gap = SPY daily open / prior daily close - 1. Buckets: G+ >= +0.30%; G0 |gap| < 0.30%; G- <= -0.30%. Also report G++ >= +0.50%.
Entry rules (decision at a 1-min bar close t, 10:00 <= t < 13:00 ET; fill at the next bar's open):
  E1 = live trigger: ret5 = c_t/c_{t-5}-1 > 0.005 OR ret20 = c_t/c_{t-20}-1 > 0.010; at most one entry per symbol per 30 min.
  E0 = unconditional: every symbol at the 10:00 bar close.
Exit: close of the bar H minutes after the entry bar, H in {15, 30, 60}; entries whose exit bar is missing are dropped.
Costs: 3 bps per side (6 bps round trip) = primary; gross and 3 bps round trip also shown.
Statistic: mean net return per trade (bps); t = session-clustered (mean of per-session averages / SE over sessions).

PRIMARY cell: G+ x E1 x H30, OOS. KILL BAR: OOS net mean <= 0 or session-clustered t < 2.0 -> gap-up momentum DEAD here.
Secondary: G+ x E0 x H60 (does a gap-up morning drift up by itself?); controls G0 and G- with E1 x H30.
Variant (secondary, not a rescue): E1 with a 3.5 x ATR14 stop (ATR on SIP bars x 0.78 to mimic IEX ATR), H30 cap.
No parameter search. Anything outside the primary cell is descriptive only.
