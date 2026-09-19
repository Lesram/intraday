"""Out-of-sample replay of the production mean-reversion rules on cached minute bars.

Implements the exact rules from backend/organism/mean_reversion_scanner.py
(production defaults: 4.0 ATR displacement, 0.8 retracement target, 1.0 ATR stop,
5bps stop floor, 9:45-15:30 entry window, 60-min cooldown, long-only),
with both optimistic (same-bar close) and realistic (next-bar open) fills,
and explicit cost scenarios. Conservative same-bar stop-vs-target: stop first.
"""
import pickle, glob
import numpy as np
import pandas as pd
from pandas._libs.arrays import NDArrayBacked
from pandas.core.arrays.string_ import StringArray

ROOT = "/sessions/relaxed-peaceful-maxwell/mnt/intra"

# ---- pandas-3 pickle compat ----
class CompatString(StringArray):
    def __init__(self, *a, **k): pass
    def __setstate__(self, state):
        arr = None
        if isinstance(state, tuple):
            for s in state:
                if isinstance(s, np.ndarray): arr = s
        elif isinstance(state, dict):
            arr = state.get("_ndarray")
        NDArrayBacked.__init__(self, np.asarray(arr, dtype=object), pd.StringDtype())

def _shim(typ, checksum, state):
    obj = CompatString.__new__(CompatString)
    if state is not None: obj.__setstate__(state)
    return obj

class U(pickle.Unpickler):
    def find_class(self, module, name):
        if module == "pandas._libs.arrays" and name.startswith("__pyx_unpickle"):
            return _shim
        return super().find_class(module, name)

def load_bars(path):
    try:
        with open(path, "rb") as f:
            return U(f).load()
    except Exception:
        return None

# ---- collect unique (symbol, date) frames across all cached pickles ----
frames = {}  # (symbol, date) -> df
for p in sorted(glob.glob(f"{ROOT}/artifacts/**/bars*.pkl", recursive=True)):
    b = load_bars(p)
    if not isinstance(b, dict): continue
    for sym, df in b.items():
        if not isinstance(df, pd.DataFrame) or "close" not in df.columns: continue
        df = df.copy()
        df["ts"] = pd.to_datetime(df["timestamp"].astype(str), utc=True)
        df["et"] = df["ts"].dt.tz_convert("America/New_York")
        for date, day in df.groupby(df["et"].dt.date):
            key = (sym, str(date))
            if key not in frames or len(day) > len(frames[key]):
                frames[key] = day.sort_values("ts").reset_index(drop=True)

print(f"unique symbol-days: {len(frames)}; dates: {sorted(set(d for _, d in frames))}")

# ---- production MR params ----
MIN_DISP, RETRACE, STOP_ATR, MIN_STOP_BPS = 4.0, 0.8, 1.0, 5.0
COOLDOWN_MIN, MIN_PRICE, MIN_VWAP_BARS = 60, 5.0, 10
ENTRY_START, ENTRY_END = (9, 45), (15, 30)
FLATTEN = (15, 58)

def atr14(day, i):
    """ATR-14 from bars [0..i] (true range, prior close)."""
    lo_i = max(1, i - 13)
    h = day["high"].values[lo_i:i+1]; l = day["low"].values[lo_i:i+1]
    pc = day["close"].values[lo_i-1:i]
    tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return float(tr.mean()) if len(tr) else 0.0

def run(fill_mode, cost_bps_side):
    trades = []
    for (sym, date), day in frames.items():
        if len(day) < MIN_VWAP_BARS + 2: continue
        cooldown_until = None
        h = day["high"].values; l = day["low"].values
        c = day["close"].values; o = day["open"].values; v = day["volume"].values
        typ = (h + l + c) / 3.0
        cum_pv = np.cumsum(typ * v); cum_v = np.cumsum(v)
        et = day["et"]
        i = MIN_VWAP_BARS
        while i < len(day) - 1:
            t = et.iloc[i]
            tt = (t.hour, t.minute)
            if not (ENTRY_START <= tt < ENTRY_END): i += 1; continue
            if cooldown_until is not None and t < cooldown_until: i += 1; continue
            price = c[i]
            if price < MIN_PRICE or cum_v[i] <= 0: i += 1; continue
            vwap = cum_pv[i] / cum_v[i]
            a = atr14(day, i)
            if a <= 0: i += 1; continue
            disp = (price - vwap) / a
            if disp > -MIN_DISP:  # long-only: oversold fade
                i += 1; continue
            # entry
            if fill_mode == "next_open":
                entry = o[i+1]; start = i + 1
            else:
                entry = price; start = i + 1
            entry *= (1 + cost_bps_side / 1e4)  # pay cost on entry
            target = price + RETRACE * (vwap - price)
            stop_dist = max(STOP_ATR * a, MIN_STOP_BPS / 1e4 * price)
            stop = price - stop_dist
            exit_px, reason = None, None
            for j in range(start, len(day)):
                tj = et.iloc[j]
                if (tj.hour, tj.minute) >= FLATTEN:
                    exit_px, reason = c[j], "eod"; break
                if l[j] <= stop:           # conservative: stop checked first
                    exit_px, reason = stop, "stop"; break
                if h[j] >= target:
                    exit_px, reason = target, "target"; break
            if exit_px is None:
                exit_px, reason = c[-1], "eod"
            exit_px *= (1 - cost_bps_side / 1e4)  # pay cost on exit
            trades.append(dict(sym=sym, date=date, entry=entry, exit=exit_px,
                               pnl_ps=exit_px - entry, ret=(exit_px - entry) / entry,
                               reason=reason))
            cooldown_until = t + pd.Timedelta(minutes=COOLDOWN_MIN)
            i += 1
        # symbol-day done
    return pd.DataFrame(trades)

for fill, cost, label in [("same_close", 0.0, "OPTIMISTIC (same-bar close, zero cost)"),
                          ("next_open", 0.0, "next-bar open, zero cost"),
                          ("next_open", 3.0, "REALISTIC (next-bar open, 3bps/side)")]:
    t = run(fill, cost)
    if t.empty:
        print(f"\n== {label}: NO TRADES"); continue
    wr = (t.pnl_ps > 0).mean()
    gp = t.loc[t.pnl_ps > 0, "ret"].sum(); gl = abs(t.loc[t.pnl_ps < 0, "ret"].sum())
    print(f"\n== {label} ==")
    print(f"n={len(t)}  win-rate={wr:.3f}  mean ret/trade={t.ret.mean()*1e4:.1f}bps  "
          f"median={t.ret.median()*1e4:.1f}bps  PF={gp/gl if gl>0 else float('inf'):.3f}")
    print(f"total ret (sum of per-trade): {t.ret.sum()*100:.2f}%  | t-stat={t.ret.mean()/(t.ret.std()/np.sqrt(len(t))):.2f}")
    print(t.reason.value_counts().to_dict())
    print("by date:", t.groupby("date").ret.sum().round(4).to_dict())
