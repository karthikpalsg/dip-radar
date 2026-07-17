"""Alert email: one message per run listing every newly triggered ticker.
Sends from GMAIL_ADDRESS to ALERT_TO (both configured via secrets/config.py)."""
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

RUN_EMOJI = {"open+1h": "🌅", "midday": "🕛", "close-1h": "🌆", "manual": "🔧"}


def send_alerts(alerts, run_label, cfg):
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
      <div style="padding:14px 22px;background:#f4f4f4;border-radius:0 0 8px 8px;
                  font-size:11px;color:#888;">
        Alert = new entry into TRIGGERED state (7-day cooldown per ticker).
        This is an automated screening tool, not financial advice —
        do your own research before investing.
      </div>
    </body></html>"""

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
