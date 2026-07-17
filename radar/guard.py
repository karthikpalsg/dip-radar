"""Self-guard: which of the three daily runs is this, and is the market open today?

Run windows (America/New_York, NASDAQ trades 9:30-16:00):
  open+1h   10:30 ET  (cron 14:30/15:30 UTC)
  midday    12:45 ET  (cron 16:45/17:45 UTC)
  close-1h  15:00 ET  (cron 19:00/20:00 UTC)

The workflow fires 6 UTC crons (EDT+EST pairs); this guard checks the actual
New York clock so exactly one label matches per trading day slot, and skips
holidays/half-days via the NASDAQ calendar.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
WINDOWS = {  # label -> (hour, minute), matched with a +/-20 min tolerance
    "open+1h": (10, 30),
    "midday": (12, 45),
    "close-1h": (15, 0),
}
TOLERANCE_MIN = 20


def resolve_run(now=None):
    """Returns (label, reason). label=None means skip this trigger."""
    now = now or datetime.now(NY)
    if now.tzinfo is None:
        now = now.replace(tzinfo=NY)
    now = now.astimezone(NY)

    if now.weekday() >= 5:
        return None, "weekend"

    open_today, close_dt = _market_hours(now)
    if not open_today:
        return None, "market holiday"

    minutes_now = now.hour * 60 + now.minute
    for label, (h, m) in WINDOWS.items():
        if abs(minutes_now - (h * 60 + m)) <= TOLERANCE_MIN:
            # Half-day: skip the close-1h run if the market closes early (13:00)
            if label == "close-1h" and close_dt and now >= close_dt:
                return None, "half-day, market already closed"
            return label, f"NY time {now.strftime('%H:%M')}"
    return None, f"NY time {now.strftime('%H:%M')} matches no run window"


def _market_hours(now):
    """(is_trading_day, close_datetime). Falls back to weekday-only if the
    calendar package is missing."""
    try:
        import pandas_market_calendars as mcal
        nasdaq = mcal.get_calendar("NASDAQ")
        day = now.strftime("%Y-%m-%d")
        sched = nasdaq.schedule(start_date=day, end_date=day)
        if sched.empty:
            return False, None
        close_dt = sched.iloc[0]["market_close"].tz_convert(NY).to_pydatetime()
        return True, close_dt
    except Exception:
        return True, None
