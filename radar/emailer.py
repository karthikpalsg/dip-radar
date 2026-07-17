"""Alert email: one message per run listing every newly triggered ticker.
Sends from GMAIL_ADDRESS to ALERT_TO (both configured via secrets/config.py)."""
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

RUN_EMOJI = {"open+1h": "🌅", "midday": "🕛", "close-1h": "🌆", "manual": "🔧"}


def send_alerts(alerts, run_label, cfg, scorecard=None):
    """alerts: list of dicts (see run.py). Returns True if sent."""
    if not alerts or not cfg.SEND_EMAIL:
        return False

    tickers = ", ".join(a["symbol"] for a in alerts)
    emoji = RUN_EMOJI.get(run_label, "📡")
    subject = f"{emoji} Dip Radar: {len(alerts)} signal{'s' if len(alerts) > 1 else ''} — {tickers}"

    cards = "".join(_card(a) for a in alerts)
    html = f"""
    <html><body style="font-family:Arial,sans-serif;max-width:680px;margin:auto;color:#222;">
      <div style="background:#111;padding:18px 22px;border-radius:8px 8px 0 0;">
        <h2 style="color:#fff;margin:0;">{emoji} Dip Radar — {run_label}</h2>
        <p style="color:#aaa;margin:6px 0 0;font-size:13px;">
          {datetime.now().strftime('%d %B %Y, %H:%M')} local &nbsp;|&nbsp;
          dip + foundation + analyst turn + rising — all four gates passed
        </p>
      </div>
      {cards}
      {_scorecard_html(scorecard)}
      {_FOOTER}
    </body></html>"""

    return _send(subject, html, cfg)


def send_digest(triggered, watchlist, scorecard, run_label, cfg):
    """Weekly digest: what's triggered, what's brewing, how past picks did.
    Sent on the Friday close-1h run (or --digest). Returns True if sent."""
    if not cfg.SEND_EMAIL:
        return False

    subject = (f"📊 Dip Radar weekly digest — {len(triggered)} triggered, "
               f"{len(watchlist)} on watch")

    trig_html = ""
    for a in triggered:
        trig_html += (f"<tr><td style='padding:5px 8px;font-weight:bold;'>{a['symbol']}</td>"
                      f"<td style='padding:5px 8px;'>{a['composite']:.0f}/100</td>"
                      f"<td style='padding:5px 8px;'>${a['price']:.2f}</td>"
                      f"<td style='padding:5px 8px;'>{a['chg_1m']:+.1f}%</td>"
                      f"<td style='padding:5px 8px;'>{a['analyst_score']:+.0f}</td></tr>")
    if not trig_html:
        trig_html = "<tr><td colspan='5' style='padding:5px 8px;color:#888;'>None this week</td></tr>"

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
        <h2 style="color:#fff;margin:0;">📊 Dip Radar — weekly digest</h2>
        <p style="color:#aaa;margin:6px 0 0;font-size:13px;">
          {datetime.now().strftime('%d %B %Y')} &nbsp;|&nbsp; run: {run_label}</p>
      </div>
      <div style="border:1px solid #ddd;border-top:none;padding:14px 22px;">
        <h3 style="margin:0 0 6px;font-size:14px;">Triggered (all 4 gates)</h3>
        <table style="width:100%;font-size:13px;border-collapse:collapse;">
          {head}<th>Ticker</th><th>Score</th><th>Price</th><th>1M</th><th>Analyst</th></tr>
          {trig_html}
        </table>
        <h3 style="margin:16px 0 6px;font-size:14px;">Watch list (3 of 4 gates, waiting)</h3>
        <table style="width:100%;font-size:13px;border-collapse:collapse;">
          {head}<th>Ticker</th><th>Score</th><th>Analyst</th><th>Foundation</th><th>Missing</th></tr>
          {watch_html}
        </table>
      </div>
      {_scorecard_html(scorecard, always=True)}
      {_FOOTER}
    </body></html>"""

    return _send(subject, html, cfg)


def _scorecard_html(scorecard, always=False):
    """Compact 'how past alerts are doing' section. Hidden when empty."""
    if not scorecard:
        return ("<div style='border:1px solid #ddd;border-top:none;padding:12px 22px;"
                "font-size:12px;color:#888;'>Scorecard: no graded alerts yet.</div>"
                if always else "")
    from radar.scorecard import summary_line
    rows = ""
    for g in scorecard[:10]:
        color = ("#1a7a3f" if g["verdict"] == "Working" else
                 "#c0392b" if g["verdict"] == "Failed" else "#888")
        rows += (f"<tr><td style='padding:4px 8px;'>{g['date']}</td>"
                 f"<td style='padding:4px 8px;font-weight:bold;'>{g['ticker']}</td>"
                 f"<td style='padding:4px 8px;'>${g['entry']:.2f}</td>"
                 f"<td style='padding:4px 8px;'>{g['ret']:+.1f}%</td>"
                 f"<td style='padding:4px 8px;'>{g['alpha']:+.1f}%</td>"
                 f"<td style='padding:4px 8px;color:{color};font-weight:bold;'>"
                 f"{g['verdict']}</td></tr>")
    return f"""
      <div style="border:1px solid #ddd;border-top:none;padding:14px 22px;">
        <h3 style="margin:0 0 6px;font-size:14px;">Scorecard — past alerts vs SPY</h3>
        <table style="width:100%;font-size:12px;border-collapse:collapse;">
          <tr style='color:#888;font-size:11px;text-align:left;'>
            <th>Alerted</th><th>Ticker</th><th>Entry</th><th>Return</th>
            <th>Alpha</th><th>Verdict</th></tr>
          {rows}
        </table>
        <p style="font-size:12px;color:#666;margin:8px 0 0;">{summary_line(scorecard)}</p>
      </div>"""


_FOOTER = """
      <div style="padding:14px 22px;background:#f4f4f4;border-radius:0 0 8px 8px;
                  font-size:11px;color:#888;">
        Alert = new entry into TRIGGERED state (7-day cooldown per ticker).
        This is an automated screening tool, not financial advice —
        do your own research before investing.
      </div>"""


def _send(subject, html, cfg):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = cfg.GMAIL_ADDRESS
    msg["To"] = cfg.ALERT_TO
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as server:
        server.starttls()
        server.login(cfg.GMAIL_ADDRESS, cfg.GMAIL_APP_PASSWORD)
        server.sendmail(cfg.GMAIL_ADDRESS, [cfg.ALERT_TO], msg.as_string())
    return True


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
            <td style="color:#666;">1M change</td><td style="color:#c0392b;">{a['chg_1m']:+.1f}%</td>
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
      </div>"""
