"""S&P 500 universe loader with a 7-day local cache."""
import io
import json
import os
import time

import pandas as pd
import requests

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "sp500.json")
CACHE_TTL_DAYS = 7
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def load_universe():
    """Returns list of dicts: {symbol, name, sector}. Symbol is yfinance-ready
    (dots swapped for dashes, e.g. BRK.B -> BRK-B)."""
    cache = _read_cache()
    if cache is not None:
        return cache

    r = requests.get(WIKI_URL, headers=UA, timeout=30)
    r.raise_for_status()
    table = pd.read_html(io.StringIO(r.text))[0]
    rows = [
        {
            "symbol": str(row["Symbol"]).replace(".", "-").strip(),
            "name": str(row["Security"]).strip(),
            "sector": str(row["GICS Sector"]).strip(),
        }
        for _, row in table.iterrows()
    ]
    if len(rows) < 400:
        raise RuntimeError(f"Universe fetch suspicious: only {len(rows)} rows")
    _write_cache(rows)
    return rows


def _read_cache():
    try:
        if not os.path.exists(CACHE_PATH):
            return None
        age_days = (time.time() - os.path.getmtime(CACHE_PATH)) / 86400
        with open(CACHE_PATH) as f:
            rows = json.load(f)
        if age_days > CACHE_TTL_DAYS:
            return None if len(rows) else None
        return rows if len(rows) >= 400 else None
    except Exception:
        return None


def _write_cache(rows):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(rows, f)
