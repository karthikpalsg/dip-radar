"""Price download and the two price gates: Gate 1 (in a dip), Gate 4 (beginning to rise)."""
import numpy as np
import pandas as pd
import yfinance as yf

# Gate 1 thresholds
DIP_1M_PCT = -8.0          # down at least 8% over ~1 month
DIP_FROM_HIGH_PCT = -15.0  # at least 15% below 52w high
COLLAPSE_FROM_HIGH = -50.0 # >50% off high = structural collapse, not a dip
COLLAPSE_3M_PCT = -40.0    # >40% down in 3 months = deterioration, not a dip

# Gate 4 thresholds
RISE_OFF_LOW_PCT = 3.0     # last close at least 3% above the 21-day low


def fetch_closes(symbols, period="1y"):
    """Batch daily closes for the whole universe in one threaded download."""
    data = yf.download(
        symbols, period=period, interval="1d",
        auto_adjust=True, threads=True, progress=False, group_by="column",
    )
    closes = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data[["Close"]]
    return closes.dropna(axis=1, how="all")


def price_stats(closes):
    """Per-ticker stats DataFrame from the closes matrix."""
    stats = {}
    for sym in closes.columns:
        s = closes[sym].dropna()
        if len(s) < 70:  # need ~3 months of history minimum
            continue
        price = float(s.iloc[-1])
        chg_1w = _pct(price, s.iloc[-6]) if len(s) >= 6 else np.nan
        chg_1m = _pct(price, s.iloc[-22])
        chg_3m = _pct(price, s.iloc[-64])
        high_52w = float(s.max())
        from_high = _pct(price, high_52w)
        ma5 = float(s.iloc[-5:].mean())
        low_21d = float(s.iloc[-21:].min())
        off_low = _pct(price, low_21d)
        stats[sym] = {
            "price": price, "chg_1w": chg_1w, "chg_1m": chg_1m, "chg_3m": chg_3m,
            "high_52w": high_52w, "from_high": from_high,
            "ma5": ma5, "low_21d": low_21d, "off_low": off_low,
        }
    return pd.DataFrame.from_dict(stats, orient="index")


def gate_dip(row):
    """Gate 1 — a real dip, not a collapse."""
    if row["chg_1m"] > DIP_1M_PCT:
        return False
    if row["from_high"] > DIP_FROM_HIGH_PCT:
        return False
    if row["from_high"] <= COLLAPSE_FROM_HIGH or row["chg_3m"] <= COLLAPSE_3M_PCT:
        return False
    return True


def gate_rising(row):
    """Gate 4 — the turn has started: above the 5-day MA and lifting off the 21-day low."""
    return row["price"] > row["ma5"] and row["off_low"] >= RISE_OFF_LOW_PCT


def dip_quality(row):
    """0-100: how attractive the dip entry is. Deeper is better until it
    approaches collapse territory, then it tapers off."""
    d = -row["chg_1m"]  # positive magnitude
    if d < 8:
        return 0.0
    if d <= 25:
        return 60 + (d - 8) / 17 * 40      # -8% -> 60, -25% -> 100
    return max(40.0, 100 - (d - 25) * 4)   # beyond -25% confidence decays


def rising_strength(row):
    """0-100: how convincingly the rise has begun."""
    if row["price"] <= row["ma5"]:
        return min(40.0, max(0.0, row["off_low"] * 4))
    lift = row["off_low"]                   # % above 21-day low
    return float(min(100.0, 50 + (lift - 3) * 50 / 7))  # 3% -> 50, 10%+ -> 100


def _pct(now, base):
    return float((now - base) / base * 100) if base else np.nan
