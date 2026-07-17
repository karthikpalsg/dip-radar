"""Persistent per-ticker state in data/state.json.

Status ladder: dormant -> dip -> watch (dip+foundation) -> triggered -> cooling.
An email fires only on entry into 'triggered', subject to the cooldown.
"""
import json
import os
from datetime import datetime, timedelta

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "state.json")
COOLDOWN_DAYS = 7
REALERT_SCORE_JUMP = 10  # re-alert inside cooldown only if composite jumps this much
TARGET_HISTORY_MAX = 90


def load_state():
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {"tickers": {}, "runs": []}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    state["runs"] = state.get("runs", [])[-30:]
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=1)


def get_ticker(state, sym):
    return state["tickers"].setdefault(sym, {
        "status": "dormant", "analyst_score": None, "composite": None,
        "last_alert": None, "last_alert_composite": None,
        "target_history": [], "notes": [],
    })


def record_target(entry, mean_target, today):
    """One mean-target sample per calendar day, capped history."""
    hist = entry.setdefault("target_history", [])
    if mean_target and (not hist or hist[-1]["d"] != today):
        hist.append({"d": today, "mean": round(float(mean_target), 2)})
        entry["target_history"] = hist[-TARGET_HISTORY_MAX:]


def should_alert(entry, composite, now):
    """True if this trigger deserves an email (fresh trigger or big improvement)."""
    if entry.get("status") == "triggered":
        last = entry.get("last_alert")
        if last:
            last_dt = datetime.strptime(last, "%Y-%m-%d %H:%M")
            if now - last_dt < timedelta(days=COOLDOWN_DAYS):
                prev = entry.get("last_alert_composite") or 0
                return composite >= prev + REALERT_SCORE_JUMP
        return True
    return True  # entering triggered from any other status


def mark_alerted(entry, composite, now):
    entry["last_alert"] = now.strftime("%Y-%m-%d %H:%M")
    entry["last_alert_composite"] = composite
