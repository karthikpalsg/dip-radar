"""Copy to config.py and fill in. config.py is gitignored — in GitHub Actions
these come from repository secrets via environment variables."""
import os

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")       # sender gmail
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
ALERT_TO = os.environ.get("ALERT_TO", "")                 # alert recipient

SEND_EMAIL = bool(GMAIL_ADDRESS and GMAIL_APP_PASSWORD)
