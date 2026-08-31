#!/usr/bin/env python3
"""Momentum Radar — Dip Radar's sibling scanner. Finds S&P 500 (+ a small
supplemental list, see data/momentum_universe.json) stocks that are
(1) breaking out — strong recent gains, near their 52-week high,
(2) fundamentally sound, (3) seeing analyst feedback turn positive, and
(4) still confirmed rising. Emails an alert on the run where all four
first line up.

This deliberately reuses as much of Dip Radar's own machinery as
possible: Foundation (radar/foundation.py) and Analyst turn
(radar/analyst.py) are identical to the dip scanner — a breakout
candidate should be just as fundamentally sound and just as genuinely
backed by the Street as a dip candidate. Only Gate 1 (radar/momentum_gates.py,
the mirror image of gates.gate_dip) and the universe (radar/momentum_universe.py)
are different. Gate 4 (still rising) is reused unchanged from gates.py.

State, alerts log, and email are all kept in their own files/inbox
distinct from the dip scanner (see MOMENTUM_STATE / MOMENTUM_ALERTS_LOG
below) so the two scanners' histories never mix.

Usage:
  python3 run_momentum.py                 # scheduled mode: self-guards on NY clock + NASDAQ calendar
  python3 run_momentum.py --force         # run now regardless of clock (label 'manual')
  python3 run_momentum.py --force --no-email --max 60   # dev: limit universe, print only

Not yet wired into GitHub Actions — run manually (or via /value-dip-scanner
momentum, once that's added) until its track record earns a schedule slot
next to the dip scanner's.
"""
import argparse
import csv
import os
import sys
from datetime import datetime

import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from radar import gates, momentum_gates, state as st
from radar.analyst import analyst_momentum
from radar.foundation import FOUNDATION_THRESHOLD, foundation_score
from radar.guard import NY, resolve_run
from radar.momentum_emailer import send_alerts, send_digest
from radar.momentum_universe import load_momentum_universe
from radar.scorecard import grade_alerts, summary_line

import config

MAX_DEEP_CANDIDATES = 80  # cap on per-ticker deep fetches per run
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MOMENTUM_STATE = os.path.join(DATA_DIR, "momentum_state.json")
MOMENTUM_ALERTS_LOG = os.path.join(DATA_DIR, "momentum_alerts_log.csv")

# Composite conviction: same philosophy and weights as the dip scanner —
# analyst turn is still the star, foundation still anchors it. Only the
# price-quality term swaps dip_quality for breakout_quality.
W_ANALYST, W_FOUNDATION, W_BREAKOUT, W_RISING = 0.35, 0.30, 0.15, 0.20

STALE_HOURS = 96


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

    universe = load_momentum_universe()
    meta = {u["symbol"]: u for u in universe}
    symbols = [u["symbol"] for u in universe][: args.max or None]
    print(f"Universe: {len(symbols)} tickers")

    closes = gates.fetch_closes(symbols)
    stats = gates.price_stats(closes)
    print(f"Price history OK for {len(stats)} tickers")

    stats["breakout"] = stats.apply(momentum_gates.gate_breakout, axis=1)
    stats["rising"] = stats.apply(gates.gate_rising, axis=1)
    breakouts = stats[stats["breakout"]].sort_values("chg_1m", ascending=False).head(MAX_DEEP_CANDIDATES)
    print(f"Gate 1' (breakout): {len(breakouts)} candidates -> deep analysis on "
          f"{min(len(breakouts), MAX_DEEP_CANDIDATES)}")

    app_state = st.load_state(MOMENTUM_STATE)
    alerts, watchlist, triggered_now = [], [], []

    for sym, row in breakouts.iterrows():
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
            entry.update({"status": "breakout", "foundation": f_score})
            continue

        a_score, a_detail, events = analyst_momentum(tkr, entry.get("target_history", []))
        st.record_target(entry, (info.get("targetMeanPrice") or 0), today)

        analyst_turn = a_score > 0
        fresh_turn = analyst_turn and (prev_analyst is not None and prev_analyst <= 0)
        rising = bool(row["rising"])

        composite = (
            W_ANALYST * max(0.0, min(100.0, 50 + a_score))
            + W_FOUNDATION * f_score
            + W_BREAKOUT * momentum_gates.breakout_quality(row)
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

        all_four = analyst_turn and rising  # breakout + foundation already true here
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
            "gates": {"breakout": True, "foundation": True,
                      "analyst_turn": analyst_turn, "rising": rising},
            "last_seen": f"{today} {label}", "prev_status": prev_status,
        })

    alerts.sort(key=lambda a: -a["composite"])
    watchlist.sort(key=lambda a: -a["composite"])

    try:
        scorecard = grade_alerts(MOMENTUM_ALERTS_LOG)
    except Exception as e:
        print(f"Scorecard skipped: {e}")
        scorecard = []

    _print_report(label, alerts, triggered_now, watchlist, scorecard)

    emailed = False
    if alerts and not args.no_email:
        emailed = send_alerts(alerts, label, config, scorecard)
        print(f"Email: {'sent to ' + config.ALERT_TO if emailed else 'NOT sent (disabled or failed)'}")
    _log_alerts(alerts, label, today)

    if args.digest and not args.no_email:
        sent = send_digest(triggered_now, watchlist, scorecard, label, config)
        print(f"Digest: {'sent to ' + config.ALERT_TO if sent else 'NOT sent'}")

    app_state.setdefault("runs", []).append({
        "date": today, "label": label, "at": now.isoformat(), "breakouts": int(len(breakouts)),
        "watch": len(watchlist), "triggered": len(triggered_now),
        "alerted": len(alerts), "emailed": emailed,
    })
    st.save_state(app_state, MOMENTUM_STATE)
    print("State saved.")


def _print_report(label, alerts, triggered_now, watchlist, scorecard=None):
    print(f"\n=== MOMENTUM RADAR [{label}] ===")
    print(f"TRIGGERED (all 4 gates): {len(triggered_now)} | new alerts: {len(alerts)}")
    for a in triggered_now:
        flag = "📧" if a in alerts else "(cooldown)"
        print(f"  {flag} {a['symbol']:6s} {a['composite']:5.1f}/100  "
              f"1M {a['chg_1m']:+6.1f}%  off-high {a['from_high']:+5.1f}%  "
              f"analyst {a['analyst_score']:+5.1f}  foundation {a['foundation']:.0f}")
    print(f"WATCH (breakout + foundation, waiting on turn/rise): {len(watchlist)}")
    for a in watchlist[:15]:
        missing = []
        if a["analyst_score"] <= 0:
            missing.append("analyst turn")
        if not a["rising"]:
            missing.append("rising")
        print(f"    {a['symbol']:6s} {a['composite']:5.1f}/100  "
              f"analyst {a['analyst_score']:+5.1f}  missing: {', '.join(missing)}")
    if scorecard:
        print(f"SCORECARD: {summary_line(scorecard)}")


def _log_alerts(alerts, label, today):
    if not alerts:
        return
    new_file = not os.path.exists(MOMENTUM_ALERTS_LOG)
    with open(MOMENTUM_ALERTS_LOG, "a", newline="") as f:
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
    p.add_argument("--digest", action="store_true", help="send the full current-state digest email")
    p.add_argument("--max", type=int, help="limit universe size (dev/testing)")
    return p.parse_args()


if __name__ == "__main__":
    main()
