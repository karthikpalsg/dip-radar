"""Gate 3 — Analyst Momentum Score: the derivative of analyst sentiment.

Signed score, roughly -100..+100. Four inputs:
  1. Dated analyst actions, last 30 days (yfinance upgrades_downgrades)
  2. Forward EPS estimate drift, now vs 30 days ago (yfinance eps_trend)
  3. Buy/hold/sell mix shift over the last 3 months (yfinance recommendations)
  4. Consensus mean-target drift from our own stored history (state.json)

Score > 0 = analyst feedback is net-turning positive. The alert fires on the
*transition* into positive, tracked by the state machine in run.py.
"""
from datetime import datetime, timedelta, timezone

import pandas as pd

BULL_GRADES = {"buy", "strong buy", "outperform", "overweight", "positive",
               "accumulate", "add", "market outperform", "sector outperform"}


def analyst_momentum(tkr, target_history):
    """tkr: yfinance Ticker. target_history: list of {d, mean} from state.json.
    Returns (score, detail, events) — events is a list of human-readable
    recent analyst actions used in the alert email."""
    actions_pts, events = _recent_actions(tkr)
    eps_pts, eps_note = _eps_drift(tkr)
    mix_pts, mix_note = _mix_shift(tkr)
    tgt_pts, tgt_note = _target_drift(tkr, target_history)

    score = actions_pts + eps_pts + mix_pts + tgt_pts
    detail = (f"actions {actions_pts:+.0f} | est {eps_pts:+.0f} ({eps_note}) | "
              f"mix {mix_pts:+.0f} ({mix_note}) | target {tgt_pts:+.0f} ({tgt_note})")
    return round(score, 1), detail, events


def _recent_actions(tkr):
    """Upgrades/downgrades and PT changes in the last 30 days.
    Last 7 days count double. Capped at +/-50."""
    try:
        ud = tkr.upgrades_downgrades
        if ud is None or len(ud) == 0:
            return 0.0, []
        ud = ud.reset_index()
        date_col = "GradeDate" if "GradeDate" in ud.columns else ud.columns[0]
        now = datetime.now(timezone.utc)
        pts, events = 0.0, []
        for _, row in ud.iterrows():
            d = pd.Timestamp(row[date_col])
            d = d.tz_localize("UTC") if d.tzinfo is None else d.tz_convert("UTC")
            age = (now - d.to_pydatetime()).days
            if age > 30:
                continue
            weight = 2.0 if age <= 7 else 1.0
            action = str(row.get("Action", "")).lower()
            pt_action = str(row.get("priceTargetAction", "")).lower()
            to_grade = str(row.get("ToGrade", "")).strip()
            firm = str(row.get("Firm", "?"))
            pt = row.get("currentPriceTarget")
            prior_pt = row.get("priorPriceTarget")
            pt_str = (f" ${prior_pt:.0f}->${pt:.0f}"
                      if _is_num(pt) and _is_num(prior_pt) and prior_pt > 0
                      else (f" (PT ${pt:.0f})" if _is_num(pt) and pt > 0 else ""))

            delta = 0.0
            label = None
            if action == "up":
                delta, label = 15.0, f"{firm} upgrade to {to_grade}{pt_str}"
            elif action == "down":
                delta, label = -20.0, f"{firm} downgrade to {to_grade}{pt_str}"
            elif action == "init" and to_grade.lower() in BULL_GRADES:
                delta, label = 8.0, f"{firm} initiated at {to_grade}{pt_str}"
            elif pt_action == "raises":
                delta, label = 10.0, f"{firm} PT raise{pt_str} ({to_grade})"
            elif pt_action == "lowers":
                delta, label = -10.0, f"{firm} PT cut{pt_str} ({to_grade})"

            if label:
                pts += delta * weight
                events.append(f"{d.strftime('%b %d')}: {label}")
        return max(-50.0, min(50.0, pts)), events[:6]
    except Exception:
        return 0.0, []


def _eps_drift(tkr):
    """Forward EPS estimates now vs 30 days ago, current + next fiscal year."""
    try:
        et = tkr.eps_trend
        if et is None or len(et) == 0:
            return 0.0, "no est data"
        changes = []
        for period in ("0y", "+1y"):
            if period in et.index:
                row = et.loc[period]
                cur, base = row.get("current"), row.get("30daysAgo")
                if base is None or pd.isna(base):
                    base = row.get("60daysAgo")
                if _is_num(cur) and _is_num(base) and abs(base) > 0.01:
                    changes.append((cur - base) / abs(base) * 100)
        if not changes:
            return 0.0, "no est history"
        avg = sum(changes) / len(changes)
        if avg >= 2:
            return 25.0, f"est {avg:+.1f}% 30d"
        if avg >= 0.5:
            return 12.0, f"est {avg:+.1f}% 30d"
        if avg > -0.5:
            return 0.0, f"est flat ({avg:+.1f}%)"
        if avg > -2:
            return -12.0, f"est {avg:+.1f}% 30d"
        return -25.0, f"est {avg:+.1f}% 30d"
    except Exception:
        return 0.0, "est unavailable"


def _mix_shift(tkr):
    """Bullish share of ratings (strongBuy+buy) now vs 2 months ago."""
    try:
        rec = tkr.recommendations
        if rec is None or len(rec) < 3:
            return 0.0, "no mix data"
        rec = rec.set_index("period") if "period" in rec.columns else rec

        def bullish_pct(row):
            total = sum(row.get(c, 0) for c in
                        ("strongBuy", "buy", "hold", "sell", "strongSell"))
            return (row.get("strongBuy", 0) + row.get("buy", 0)) / total * 100 if total else None

        now_pct = bullish_pct(rec.loc["0m"]) if "0m" in rec.index else None
        old_pct = bullish_pct(rec.loc["-2m"]) if "-2m" in rec.index else None
        if now_pct is None or old_pct is None:
            return 0.0, "mix incomplete"
        shift = now_pct - old_pct
        if shift >= 5:
            return 15.0, f"bulls {old_pct:.0f}%->{now_pct:.0f}%"
        if shift >= 2:
            return 8.0, f"bulls {old_pct:.0f}%->{now_pct:.0f}%"
        if shift > -2:
            return 0.0, f"bulls steady {now_pct:.0f}%"
        if shift > -5:
            return -8.0, f"bulls {old_pct:.0f}%->{now_pct:.0f}%"
        return -15.0, f"bulls {old_pct:.0f}%->{now_pct:.0f}%"
    except Exception:
        return 0.0, "mix unavailable"


def _target_drift(tkr, target_history):
    """Consensus mean target now vs our stored history (7-30 days back).
    Returns 0 until the app has accumulated a week of state."""
    try:
        apt = tkr.analyst_price_targets or {}
        mean_now = apt.get("mean")
        if not _is_num(mean_now) or not target_history:
            return 0.0, "no target history yet"
        cutoff_new = datetime.now() - timedelta(days=7)
        cutoff_old = datetime.now() - timedelta(days=35)
        past = [h for h in target_history
                if cutoff_old <= datetime.strptime(h["d"], "%Y-%m-%d") <= cutoff_new]
        if not past:
            return 0.0, "target history <7d"
        base = past[0]["mean"]
        if not base:
            return 0.0, "target history empty"
        drift = (mean_now - base) / base * 100
        if drift >= 2:
            return 10.0, f"target {drift:+.1f}%"
        if drift <= -2:
            return -10.0, f"target {drift:+.1f}%"
        return 0.0, f"target flat ({drift:+.1f}%)"
    except Exception:
        return 0.0, "target unavailable"


def _is_num(x):
    try:
        return x is not None and not pd.isna(x)
    except Exception:
        return False
