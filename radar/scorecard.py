"""Scorecard — grades every past alert against SPY.

This is the measurement half of the feedback loop. Thresholds stay
human-tuned: the scorecard reports what's working, it doesn't silently
rewrite the gates (sample sizes are far too small for auto-tuning).

Verdicts are based on alpha (return vs SPY over the same window):
  Working  alpha >= +2%
  Flat     -2% .. +2%
  Failed   alpha <= -2%
Alerts younger than 3 trading days are shown as "Too fresh".

CLI: python3 -m radar.scorecard
"""
import csv
import os
from datetime import datetime

import pandas as pd
import yfinance as yf

ALERTS_LOG = os.path.join(os.path.dirname(__file__), "..", "data", "alerts_log.csv")
FRESH_DAYS = 3  # calendar days before a verdict means anything


def grade_alerts():
    """Returns a list of dicts, newest alert first. Empty list if no log."""
    rows = _read_log()
    if not rows:
        return []

    tickers = sorted({r["ticker"] for r in rows})
    closes = yf.download(
        tickers + ["SPY"], period="6mo", interval="1d",
        auto_adjust=True, threads=True, progress=False, group_by="column",
    )["Close"]
    if isinstance(closes, pd.Series):
        closes = closes.to_frame()

    graded = []
    today = datetime.now()
    for r in rows:
        sym = r["ticker"]
        try:
            alert_dt = datetime.strptime(r["date"], "%Y-%m-%d")
            entry = float(r["price"])
            s = closes[sym].dropna()
            spy = closes["SPY"].dropna()
            cur = float(s.iloc[-1])
            ret = (cur - entry) / entry * 100

            spy_window = spy[spy.index >= r["date"]]
            spy_entry = float(spy_window.iloc[0]) if len(spy_window) else float(spy.iloc[-1])
            spy_ret = (float(spy.iloc[-1]) - spy_entry) / spy_entry * 100
            alpha = ret - spy_ret

            age = (today - alert_dt).days
            if age < FRESH_DAYS:
                verdict = "Too fresh"
            elif alpha >= 2:
                verdict = "Working"
            elif alpha <= -2:
                verdict = "Failed"
            else:
                verdict = "Flat"

            stage = "early" if age < 7 else ("1w" if age < 28 else "1m+")
            graded.append({
                "date": r["date"], "run": r.get("run", ""), "ticker": sym,
                "entry": entry, "current": cur, "ret": round(ret, 1),
                "spy_ret": round(spy_ret, 1), "alpha": round(alpha, 1),
                "age_days": age, "stage": stage, "verdict": verdict,
            })
        except Exception:
            continue

    graded.sort(key=lambda g: g["date"], reverse=True)
    return graded


def summary_line(graded):
    """One line on how the radar itself is doing (excludes too-fresh picks)."""
    judged = [g for g in graded if g["verdict"] != "Too fresh"]
    if not judged:
        return f"{len(graded)} alert(s) logged, all too fresh to judge."
    working = sum(1 for g in judged if g["verdict"] == "Working")
    avg_alpha = sum(g["alpha"] for g in judged) / len(judged)
    return (f"{working}/{len(judged)} judged alerts beating SPY | "
            f"avg alpha {avg_alpha:+.1f}%")


def _read_log():
    if not os.path.exists(ALERTS_LOG):
        return []
    with open(ALERTS_LOG, newline="") as f:
        return list(csv.DictReader(f))


if __name__ == "__main__":
    graded = grade_alerts()
    if not graded:
        print("No alerts logged yet.")
    else:
        print(f"{'Date':<11}{'Run':<10}{'Ticker':<7}{'Entry':>8}{'Now':>8}"
              f"{'Ret':>8}{'SPY':>7}{'Alpha':>8}  {'Age':<6}{'Verdict'}")
        for g in graded:
            print(f"{g['date']:<11}{g['run'][:9]:<10}{g['ticker']:<7}"
                  f"{g['entry']:>8.2f}{g['current']:>8.2f}{g['ret']:>+7.1f}%"
                  f"{g['spy_ret']:>+6.1f}%{g['alpha']:>+7.1f}%  "
                  f"{g['stage']:<6}{g['verdict']}")
        print("\n" + summary_line(graded))
