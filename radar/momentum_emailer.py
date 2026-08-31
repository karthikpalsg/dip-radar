"""Alert email for the momentum scanner — same plumbing as radar.emailer
(_send, _FOOTER, _scorecard_html are reused directly), but its own card
layout and copy: a breakout isn't a dip, and coloring a +40% monthly move
red (as the dip emailer does, since there it signals decline) would be
backwards here.
"""
from datetime import datetime

from radar.emailer import _scorecard_html, _send

RUN_EMOJI = {"open+1h": "🚀", "midday": "🕛", "close-1h": "🌆", "manual": "🔧"}

_MOMENTUM_FOOTER = """
      <div style="padding:14px 22px;background:#f4f4f4;border-radius:0 0 8px 8px;
                  font-size:11px;color:#888;">
        Alert = new entry into TRIGGERED state (7-day cooldown per ticker).
        Momentum Radar looks for breakouts, not dips — a high 1M change here
        is the signal, not a warning sign. This is an automated screening
        tool, not financial advice — do your own research before investing.
      </div>"""


def send_alerts(alerts, run_label, cfg, scorecard=None):
    """alerts: list of dicts (see run_momentum.py). Returns True if sent."""
    if not alerts or not cfg.SEND_EMAIL:
        return False

    tickers = ", ".join(a["symbol"] for a in alerts)
    emoji = RUN_EMOJI.get(run_label, "📡")
    subject = f"{emoji} Momentum Radar: {len(alerts)} signal{'s' if len(alerts) > 1 else ''} — {tickers}"

    cards = "".join(_card(a) for a in alerts)
    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#222;">
      <div style="background:#111;padding:18px 22px;border-radius:8px 8px 0 0;">
        <h2 style="color:#fff;margin:0;">{emoji} Momentum Radar — {run_label}</h2>
        <p style="color:#aaa;margin:6px 0 0;font-size:13px;">
          {datetime.now().strftime('%d %B %Y, %H:%M')} local &nbsp;|&nbsp;
          breakout + foundation + analyst turn + still rising — all four gates passed
        </p>
      </div>
      {cards}
      {_scorecard_html(scorecard)}
      {_MOMENTUM_FOOTER}
    </body></html>"""

    return _send(subject, html, cfg)


def send_digest(triggered, watchlist, scorecard, run_label, cfg):
    """Full current-state snapshot: what's triggered, what's brewing, how
    past picks did. Mirrors radar.emailer.send_digest exactly in shape;
    only the copy and the missing-gates labels differ (breakout, not dip)."""
    if not cfg.SEND_EMAIL:
        return False

    subject = (f"📊 Momentum Radar digest — {len(triggered)} triggered, "
               f"{len(watchlist)} on watch")

    trig_html = ""
    for a in triggered:
        trig_html += (f"<tr><td style='padding:5px 8px;font-weight:bold;'>{a['symbol']}</td>"
                      f"<td style='padding:5px 8px;'>{a['composite']:.0f}/100</td>"
                      f"<td style='padding:5px 8px;'>${a['price']:.2f}</td>"
                      f"<td style='padding:5px 8px;color:#1a7a3f;'>{a['chg_1m']:+.1f}%</td>"
                      f"<td style='padding:5px 8px;'>{a['analyst_score']:+.0f}</td></tr>")
    if not trig_html:
        trig_html = "<tr><td colspan='5' style='padding:5px 8px;color:#888;'>None this run</td></tr>"

    watch_html = ""
    for a in watchlist[:12]:
        missing = []
        if a["analyst_score"] <= 0:
            missing.append("analyst turn")
        if not a["rising"]:
            missing.append("rising")
        watch_html += (f"<tr><td style='padding:5px 8px;font-weight:bold;'>{a['symbol']}</td>"
                       f"<td style='padding:5px 8px;'>{a['composite']:.0f}/100</td>"
                       f"<td style='padding:5px 8px;'>{a['analyst_score']:+.0f}</td>"
                       f"<td style='padding:5px 8px;'>{a['foundation']:.0f}</td>"
                       f"<td style='padding:5px 8px;color:#b8860b;'>{', '.join(missing)}</td></tr>")

    head = "<tr style='color:#888;font-size:11px;text-align:left;'>"
    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#222;">
      <div style="background:#111;padding:18px 22px;border-radius:8px 8px 0 0;">
        <h2 style="color:#fff;margin:0;">📊 Momentum Radar — digest</h2>
        <p style="color:#aaa;margin:6px 0 0;font-size:13px;">
          {datetime.now().strftime('%d %B %Y')} &nbsp;|&nbsp; run: {run_label}</p>
      </div>
      <div style="border:1px solid #ddd;border-top:none;padding:14px 22px;">
        <h3 style="margin:0 0 6px;font-size:14px;">Triggered (all 4 gates)</h3>
        <table style="width:100%;font-size:13px;border-collapse:collapse;">
          {head}<th>Ticker</th><th>Score</th><th>Price</th><th>1M</th><th>Analyst</th></tr>
          {trig_html}
        </table>
        <h3 style="margin:16px 0 6px;font-size:14px;">Watch list (breakout + foundation, waiting)</h3>
        <table style="width:100%;font-size:13px;border-collapse:collapse;">
          {head}<th>Ticker</th><th>Score</th><th>Analyst</th><th>Foundation</th><th>Missing</th></tr>
          {watch_html}
        </table>
      </div>
      {_scorecard_html(scorecard, always=True)}
      {_MOMENTUM_FOOTER}
    </body></html>"""

    return _send(subject, html, cfg)


def _card(a):
    events_html = "".join(f"<li>{e}</li>" for e in a["events"]) or "<li>No dated action — turn driven by estimates/mix</li>"
    upside_str = f"${a['target']:.0f} ({a['upside']:+.0f}%)" if a.get("target") else "n/a"
    return f"""
      <div style="border:1px solid #ddd;border-top:none;padding:16px 22px;">
        <div style="display:flex;justify-content:space-between;">
          <span style="font-size:19px;font-weight:bold;">{a['symbol']}
            <span style="color:#888;font-size:13px;font-weight:normal;">{a['name']}</span>
          </span>
          <span style="font-size:17px;font-weight:bold;color:#1a7a3f;">
            {a['composite']:.0f}/100</span>
        </div>
        <table style="width:100%;font-size:13px;margin-top:10px;border-collapse:collapse;">
          <tr>
            <td style="padding:4px 0;color:#666;">Price</td><td>${a['price']:.2f}</td>
            <td style="color:#666;">1M change</td><td style="color:#1a7a3f;">{a['chg_1m']:+.1f}%</td>
          </tr><tr>
            <td style="padding:4px 0;color:#666;">Off 52w high</td><td>{a['from_high']:+.1f}%</td>
            <td style="color:#666;">Off 21d low</td><td style="color:#1a7a3f;">{a['off_low']:+.1f}%</td>
          </tr><tr>
            <td style="padding:4px 0;color:#666;">Foundation</td><td>{a['foundation']:.0f}/100</td>
            <td style="color:#666;">Analyst momentum</td>
            <td style="color:#1a7a3f;font-weight:bold;">{a['analyst_score']:+.0f}
              {'(turned positive)' if a.get('fresh_turn') else ''}</td>
          </tr><tr>
            <td style="padding:4px 0;color:#666;">Consensus target</td><td>{upside_str}</td>
            <td style="color:#666;">Sector</td><td>{a.get('sector', '')}</td>
          </tr>
        </table>
        <div style="font-size:12px;margin-top:8px;color:#444;">
          <b>Analyst actions (30d):</b>
          <ul style="margin:4px 0 0 18px;padding:0;">{events_html}</ul>
        </div>
        <div style="font-size:11px;margin-top:6px;color:#888;">{a['analyst_detail']}<br>{a['foundation_detail']}</div>
        {_extension_note(a)}
      </div>"""


def _extension_note(a):
    """Flag when breakout_quality has already tapered off — the move is
    real, but extended enough that chasing it carries real risk."""
    if a.get("chg_1m", 0) <= 40:
        return ""
    return (
        '<div style="font-size:11px;margin-top:8px;padding:8px 10px;'
        'background:#fff6e6;border:1px solid #f0d999;border-radius:4px;color:#8a6300;">'
        f"⚠️ Up {a['chg_1m']:+.0f}% in a month — well past this scanner's 40% \"sweet "
        "spot,\" where breakout_quality starts tapering off. Real momentum, real chase risk.</div>"
    )
