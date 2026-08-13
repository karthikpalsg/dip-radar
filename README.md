# Dip Radar

Scans the S&P 500 three times per NASDAQ trading day and emails an alert when a
stock passes **all four gates** at once:

| Gate | Meaning | Threshold |
|------|---------|-----------|
| 1. In a dip | Real pullback, not a collapse | 1M ≤ -8%, ≥15% off 52w high, NOT >50% off high or >40% down in 3M |
| 2. Foundation | The business is sound | Foundation score ≥ 60/100 (growth, margins, EPS, P/E sanity, debt, FCF) |
| 3. Analyst turn | Analyst feedback turning positive | Analyst Momentum Score > 0 (recent upgrades/PT raises, EPS estimate drift, buy-mix shift, stored target drift) |
| 4. Beginning to rise | The turn has started | Price above 5-day MA and ≥3% off the 21-day low |

Alerts email from `GMAIL_ADDRESS` to `ALERT_TO` (set via GitHub Secrets), with a
7-day per-ticker cooldown (re-alert early only if the composite score jumps 10+).

## Runs

| Run | ET | Singapore (EDT) | Purpose |
|-----|----|-----------------|---------|
| open+1h | 10:30 | 22:30 | Pre-market analyst actions + first-hour price vote |
| midday | 12:45 | 00:45 | Confirmation: did the morning move hold? |
| close-1h | 15:00 | 03:00 | Stocks closing strong before the bell |

Trading days only: `run.py` self-guards using the America/New_York clock and the
NASDAQ calendar (skips holidays; skips close-1h on half-days).

## Usage

```
python3 run.py                    # scheduled mode (self-guards, exits if not a run window)
python3 run.py --force            # run now, label "manual"
python3 run.py --force --no-email # print only
python3 run.py --force --max 100  # dev: first 100 tickers
```

Setup: `cp config.example.py config.py` and fill in the Gmail app password
(or set `GMAIL_ADDRESS` / `GMAIL_APP_PASSWORD` / `ALERT_TO` env vars — that's
what GitHub Actions does via repo secrets).

## Files

- `run.py` — orchestrator: guard, gates, scoring, alert state machine, email
- `radar/universe.py` — S&P 500 list (Wikipedia, 7-day cache)
- `radar/gates.py` — batch price download; dip + rising gates
- `radar/foundation.py` — foundation score (ported from stock-recommender)
- `radar/analyst.py` — Analyst Momentum Score (the turn detector)
- `radar/state.py` — `data/state.json` persistence, cooldown logic
- `radar/guard.py` — NY-clock run windows + NASDAQ calendar
- `radar/emailer.py` — HTML alert email
- `radar/scorecard.py` — grades every alert vs SPY
- `radar/gate_analysis.py` — joins scorecard verdicts against gate inputs to flag what's predictive
- `data/state.json` — per-ticker state, target history (committed by Actions)
- `data/alerts_log.csv` — every alert ever sent (the scorecard's raw data)

## Scorecard & digest

Every alert is graded against SPY from its entry price (`radar/scorecard.py`,
CLI: `python3 -m radar.scorecard`). Verdicts: Working (alpha >= +2%), Flat,
Failed (alpha <= -2%); alerts under 3 days old are "Too fresh". The scorecard
appears in every alert email, and a weekly digest (triggered + watch list +
scorecard) goes out on the Friday close-1h run. Force one with `--digest`.
Thresholds stay human-tuned — the scorecard measures, it doesn't auto-tweak.

## Gate analysis

`radar/gate_analysis.py` (CLI: `python3 -m radar.gate_analysis`) closes the
other half of the loop: it joins the scorecard's verdicts back against the
gate inputs each alert had at fire time (composite, analyst score,
foundation, chg_1m, off_low) to see which of them actually separate winners
from losers. It auto-flags a single date/cluster if it's >20% of the sample
and re-runs the comparison with it excluded, so one bad sector-rotation call
can't masquerade as a broken gate. Same philosophy as the scorecard: it
measures and flags hypotheses, it does not rewrite `gates.py` or `run.py` —
sample sizes are still too small for that. Rerun periodically as
`data/alerts_log.csv` grows.

## Composite conviction score

`0.35 × analyst momentum + 0.30 × foundation + 0.15 × dip quality + 0.20 × rising strength`

The analyst turn is the star; foundation anchors it. Dip quality rewards
deeper entries until they approach collapse territory.

*Automated screening tool, not financial advice.*
