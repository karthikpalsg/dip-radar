"""Momentum scanner's own Gate 1 — the mirror image of gates.gate_dip.

Where Dip Radar's Gate 1 looks for stocks down hard and off their highs,
this looks for stocks that have already broken out: strong recent gains,
sitting near their 52-week high. Everything else (Foundation, Analyst
turn, and the "still rising" confirmation) is reused unchanged from
gates.py and foundation.py/analyst.py — a real breakout candidate should
still be a fundamentally sound business with analysts actively warming
up to it, same as a dip candidate has to be.

price_stats() itself (chg_1m, from_high, ma5, off_low, etc.) is also
reused as-is from gates.py; only the gate/quality functions differ.
"""

# Gate 1' thresholds
BREAKOUT_1M_PCT = 15.0           # up at least 15% over ~1 month
BREAKOUT_FROM_HIGH_PCT = -10.0   # within 10% of the 52-week high

# Where breakout_quality() starts tapering off — not a hard cutoff (a name
# can be up 90% and still pass the gate), just a signal that a move this
# extended carries real chase risk, mirrored from dip_quality's own taper
# past -25%.
QUALITY_SWEET_SPOT_PCT = 40.0


def gate_breakout(row):
    """Gate 1' — a real, recent breakout, not just noise off a 52w low."""
    if row["chg_1m"] < BREAKOUT_1M_PCT:
        return False
    if row["from_high"] < BREAKOUT_FROM_HIGH_PCT:
        return False
    return True


def breakout_quality(row):
    """0-100: how attractive the breakout entry is. Healthy momentum scores
    highest; a name that's gone parabolic (40%+ in a month) tapers off the
    same way an overly-deep dip does in gates.dip_quality — still a real
    signal, just flagged as more extended and lower-conviction as an entry."""
    g = row["chg_1m"]  # already positive by construction (gate requires >= 15%)
    if g < BREAKOUT_1M_PCT:
        return 0.0
    if g <= QUALITY_SWEET_SPOT_PCT:
        return 60 + (g - BREAKOUT_1M_PCT) / (QUALITY_SWEET_SPOT_PCT - BREAKOUT_1M_PCT) * 40
    return max(40.0, 100 - (g - QUALITY_SWEET_SPOT_PCT) * 1.5)
