"""Universe for the momentum scanner: the same S&P 500 list Dip Radar uses,
unioned with a small, hand-maintained supplemental list of large, liquid
names that show real momentum but aren't S&P 500 constituents (Atlassian
being the case that prompted this — dual-class-adjacent index quirks keep
some well-known growth names out of the index entirely).

Add to data/momentum_universe.json as more of these come up; there's no
attempt here to auto-discover the full Nasdaq-100 or similar — a short,
deliberately curated list is easier to trust than a large scraped one.
"""
import json
import os

from radar.universe import load_universe as load_sp500

SUPPLEMENTAL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "data", "momentum_universe.json"
)


def load_momentum_universe():
    """Returns list of dicts: {symbol, name, sector} — S&P 500 plus the
    supplemental list, de-duplicated by symbol (S&P 500 entry wins on
    overlap, since it's the richer/refreshed source)."""
    sp500 = load_sp500()
    seen = {row["symbol"] for row in sp500}

    supplemental = []
    try:
        with open(SUPPLEMENTAL_PATH) as f:
            supplemental = json.load(f)
    except Exception:
        pass

    extra = [row for row in supplemental if row["symbol"] not in seen]
    return sp500 + extra
