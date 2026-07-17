#!/usr/bin/env python3
"""Dip Radar — finds S&P 500 stocks that are (1) in a dip, (2) fundamentally
sound, (3) seeing analyst feedback turn positive, and (4) beginning to rise.
Emails an alert on the run where all four first line up.

Usage:
  python3 run.py                 # scheduled mode: self-guards on NY clock + NASDAQ calendar
  python3 run.py --force         # run now regardless of clock (label 'manual')
  python3 run.py --force --no-email --max 60   # dev: limit universe, print only
"""
import argparse
import csv
import os
import sys
from datetime import datetime

import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from radar import gates, state as st
from radar.analyst import analyst_momentum
from radar.emailer import send_alerts
from radar.foundation import FOUNDATION_THRESHOLD, foundation_score
from radar.guard import resolve_run
from radar.universe import load_universe

import config

MAX_DEEP_CANDIDATES = 80  # cap on per-ticker deep fetches per run
ALERTS_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "alerts_log.csv")

# Composite conviction: analyst turn is the star, foundation anchors it.
W_ANALYST, W_FOUNDATION, W_DIP, W_RISING = 0.35, 0.30, 0.15, 0.20


def main():
    args = _parse_args()

    if args.force:
        label = args.label or "manual"
    else:
        label, reason = resolve_run()
        if label is None:
            print(f"SKIP: {reason}")
            return
        print(f"Run window: {label} ({reason})")

    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    universe = load_universe()
    meta = {u["symbol"]: u for u in universe}
    symbols = [u["symbol"] for u in universe][: args.max or None]
    print(f"Universe: {len(symbols)} tickers")

    closes = gates.fetch_closes(symbols)
    stats = gates.price_stats(closes)
    print(f"Price history OK for {len(stats)} tickers")

    stats["dip"] = stats.apply(gates.gate_dip, axis=1)
    stats["rising"] = stats.apply(gates.gate_rising, axis=1)
    dippers = stats[stats["dip"]].sort_values("chg_1m").head(MAX_DEEP_CANDIDATES)
    print(f"Gate 1 (dip): {len(dippers)} candidates -> deep analysis on "
          f"{min(len(dippers), MAX_DEEP_CANDIDATES)}")

    app_state = st.load_state()
    alerts, watchlist, triggered_now = [], [], []

    for sym, row in dippers.iterrows():
        entry = st.get_ticker(app_state, sym)
        prev_analyst = entry.get("analyst_score")
        prev_status = entry.get("status", "dormant")

        tkr = yf.Ticker(sym)
        try:
            info = tkr.info
        except Exception:
            info = {}
        f_score, f_detail = foundation_score(info)

        if f_score < FOUNDATION_THRESHOLD:
            entry.update({"status": "dip", "foundation": f_score})
            continue

        a_score, a_detail, events = analyst_momentum(tkr, entry.get("target_history", []))
        st.record_target(entry, (info.get("targetMeanPrice") or 0), today)

        analyst_turn = a_score > 0
        fresh_turn = analyst_turn and (prev_analyst is not None and prev_analyst <= 0)
        rising = bool(row["rising"])

        composite = (
            W_ANALYST * max(0.0, min(100.0, 50 + a_score))
            + W_FOUNDATION * f_score
            + W_DIP * gates.dip_quality(row)
            + W_RISING * gates.rising_strength(row)
        )
        composite = round(composite, 1)

        target = info.get("targetMeanPrice") or 0
        upside = ((target - row["price"]) / row["price"] * 100) if target else None
        record = {
            "symbol": sym, "name": meta.get(sym, {}).get("name", sym),
            "sector": meta.get(sym, {}).get("sector", ""),
            "price": row["price"], "chg_1m": row["chg_1m"], "chg_1w": row["chg_1w"],
            "from_high": row["from_high"], "off_low": row["off_low"],
            "foundation": f_score, "foundation_detail": f_detail,
            "analyst_score": a_score, "analyst_detail": a_detail, "events": events,
            "composite": composite, "target": target, "upside": upside,
            "fresh_turn": fresh_turn, "rising": rising,
        }

        all_four = analyst_turn and rising  # dip + foundation already true here
        if all_four:
            triggered_now.append(record)
            if st.should_alert(entry, composite, now):
                alerts.append(record)
                st.mark_alerted(entry, composite, now)
            entry["status"] = "triggered"
        else:
            entry["status"] = "watch"
            watchlist.append(record)

        entry.update({
            "analyst_score": a_score, "foundation": f_score, "composite": composite,
            "gates": {"dip": True, "foundation": True,
                      "analyst_turn": analyst_turn, "rising": rising},
            "last_seen": f"{today} {label}", "prev_status": prev_status,
        })

    alerts.sort(key=lambda a: -a["composite"])
    watchlist.sort(key=lambda a: -a["composite"])

    _print_report(label, alerts, triggered_now, watchlist)

    emailed = False
    if alerts and not args.no_email:
        emailed = send_alerts(alerts, label, config)
        print(f"Email: {'sent to ' + config.ALERT_TO if emailed else 'NOT sent (disabled or failed)'}")
    _log_alerts(alerts, label, today)

    app_state.setdefault("runs", []).append({
        "date": today, "label": label, "dippers": int(len(dippers)),
        "watch": len(watchlist), "triggered": len(triggered_now),
        "alerted": len(alerts), "emailed": emailed,
    })
    st.save_state(app_state)
    print("State saved.")


def _print_report(label, alerts, triggered_now, watchlist):
    print(f"\n=== DIP RADAR [{label}] ===")
    print(f"TRIGGERED (all 4 gates): {len(triggered_now)} | new alerts: {len(alerts)}")
    for a in triggered_now:
        flag = "📧" if a in alerts else "(cooldown)"
        print(f"  {flag} {a['symbol']:6s} {a['composite']:5.1f}/100  "
              f"1M {a['chg_1m']:+6.1f}%  off-low {a['off_low']:+5.1f}%  "
              f"analyst {a['analyst_score']:+5.1f}  foundation {a['foundation']:.0f}")
    print(f"WATCH (dip + foundation, waiting on turn/rise): {len(watchlist)}")
    for a in watchlist[:15]:
        missing = []
        if a["analyst_score"] <= 0:
            missing.append("analyst turn")
        if not a["rising"]:
            missing.append("rising")
        print(f"    {a['symbol']:6s} {a['composite']:5.1f}/100  "
              f"analyst {a['analyst_score']:+5.1f}  missing: {', '.join(missing)}")


def _log_alerts(alerts, label, today):
    if not alerts:
        return
    new_file = not os.path.exists(ALERTS_LOG)
    with open(ALERTS_LOG, "a", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["date", "run", "ticker", "price", "composite",
                        "analyst_score", "foundation", "chg_1m", "off_low",
                        "target", "fresh_turn"])
        for a in alerts:
            w.writerow([today, label, a["symbol"], f"{a['price']:.2f}",
                        a["composite"], a["analyst_score"], a["foundation"],
                        f"{a['chg_1m']:.1f}", f"{a['off_low']:.1f}",
                        f"{a['target']:.0f}" if a["target"] else "",
                        a["fresh_turn"]])


def _parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--force", action="store_true", help="bypass the run-window guard")
    p.add_argument("--label", help="run label when forced (default: manual)")
    p.add_argument("--no-email", action="store_true")
    p.add_argument("--max", type=int, help="limit universe size (dev/testing)")
    return p.parse_args()


if __name__ == "__main__":
    main()
