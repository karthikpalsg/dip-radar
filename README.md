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
- `data/state.json` — per-ticker state, target history (committed by Actions)
- `data/alerts_log.csv` — every alert ever sent (the scorecard's raw data)
- `run_momentum.py`, `radar/momentum_gates.py`, `radar/momentum_universe.py`,
  `radar/momentum_emailer.py` — the momentum scanner, see below. Its own
  `data/momentum_state.json` / `data/momentum_alerts_log.csv` /
  `data/momentum_universe.json`.

## Scorecard & digest

Every alert is graded against SPY from its entry price (`radar/scorecard.py`,
CLI: `python3 -m radar.scorecard`). Verdicts: Working (alpha >= +2%), Flat,
Failed (alpha <= -2%); alerts under 3 days old are "Too fresh". The scorecard
appears in every alert email, and a weekly digest (triggered + watch list +
scorecard) goes out on the Friday close-1h run. Force one with `--digest`.
Thresholds stay human-tuned — the scorecard measures, it doesn't auto-tweak.

## Composite conviction score

`0.35 × analyst momentum + 0.30 × foundation + 0.15 × dip quality + 0.20 × rising strength`

The analyst turn is the star; foundation anchors it. Dip quality rewards
deeper entries until they approach collapse territory.

## Momentum Radar (sibling scanner — breakouts, not dips)

Dip Radar only ever looks for stocks that are *down*. `run_momentum.py` is
the mirror image: it looks for stocks that have already **broken out** —
up 15%+ over the last month and within 10% of their 52-week high — and
still passing the same Foundation and Analyst-turn bar as the dip scanner.
Reuses `radar/foundation.py` and `radar/analyst.py` completely unchanged;
only Gate 1 (`radar/momentum_gates.py`) and the universe are different.

```
python3 run_momentum.py --force --no-email --max 60   # dev: limit universe, print only
python3 run_momentum.py --force                        # full run now, label "manual"
```

**Universe**: the same S&P 500 list, unioned with a small hand-maintained
supplemental list (`data/momentum_universe.json`) for large, liquid names
that show real momentum but aren't S&P 500 constituents — Atlassian
(`TEAM`) is the seed example; add more there as they come up.

**Its own everything else**, kept fully separate from the dip scanner so
neither history contaminates the other:
- `data/momentum_state.json` / `data/momentum_alerts_log.csv`
- `radar/momentum_emailer.py` — same layout as the dip alert email, but
  colors a big monthly gain green instead of red, and flags (⚠️) any
  trigger already up more than 40% in a month as extended/chase-risk
- Scorecard: `python3 -c "from radar.scorecard import grade_alerts, summary_line; print(summary_line(grade_alerts('data/momentum_alerts_log.csv')))"`
  (both `radar/state.py` and `radar/scorecard.py` now take an optional
  `path`/`log_path` argument for this — defaults are unchanged, so the
  dip scanner's own calls are unaffected)

**Composite score**: identical weights and philosophy to the dip
scanner's, with `breakout_quality()` swapped in for `dip_quality()` — it
rewards a healthy 15-40% move, then tapers (not hard-cuts) past 40% as
the move gets more extended and harder to trust as an entry, the same
way `dip_quality()` tapers off past -25%.

**Not yet wired into GitHub Actions** — run it manually until it's earned
a schedule slot next to the dip scanner's. When it is, it should get its
own workflow file (or a mode flag on the existing one) rather than
sharing `dip-radar.yml`, so a failure in one scanner can't silently take
the other down with it.

*Automated screening tool, not financial advice.*
