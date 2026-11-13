"""Gate analysis -- does the data at alert time actually predict Working vs Failed?

The other half of the feedback loop that scorecard.py started: scorecard grades
each alert vs SPY, this joins those verdicts back against the gate inputs that
were true when the alert fired (composite, analyst_score, foundation, chg_1m,
off_low) to see which of them separate winners from losers.

Like scorecard.py, this measures -- it does not rewrite gates.py or run.py.
Two reasons to keep it human-reviewed for now:

  1. Sample size. Bucketing 40-60 alerts into thirds gives ~15-20 alerts per
     bucket -- enough to spot a hypothesis, not enough to commit to a new
     threshold. Rerun as the log grows; trust a pattern more once each bucket
     clears ~40.
  2. Concentration. A single day/sector cluster (e.g. one bad rotation call
     that fires 15 correlated alerts) can dominate the whole sample and make
     unrelated gates look predictive or anti-predictive by pure confound. This
     script auto-flags the largest single-date cluster and re-runs the field
     comparison with it excluded, so a real signal can be told apart from one
     bad day.

CLI: python3 -m radar.gate_analysis
"""
import csv
import os
import statistics as stats
from collections import Counter

from radar.scorecard import grade_alerts

HERE = os.path.dirname(__file__)
ALERTS_LOG = os.path.join(HERE, "..", "data", "alerts_log.csv")
GATE_FIELDS = ["composite", "analyst_score", "foundation", "chg_1m", "off_low"]
CLUSTER_SHARE_THRESHOLD = 0.20  # flag a single date if it's this much of the sample


def _load_raw():
    if not os.path.exists(ALERTS_LOG):
        return {}
    with open(ALERTS_LOG, newline="") as f:
        return {(r["date"], r["ticker"]): r for r in csv.DictReader(f)}


def build_dataset():
    """Judged alerts (verdict != Too fresh) merged with their gate inputs."""
    raw = _load_raw()
    merged = []
    for g in grade_alerts():
        r = raw.get((g["date"], g["ticker"]))
        if not r:
            continue
        merged.append({**g, **{k: r[k] for k in GATE_FIELDS}, "fresh_turn": r.get("fresh_turn")})
    return [m for m in merged if m["verdict"] != "Too fresh"]


def find_cluster(judged):
    """Largest single date's share of the sample, if it exceeds the threshold."""
    if not judged:
        return None
    counts = Counter(m["date"] for m in judged)
    date, n = counts.most_common(1)[0]
    share = n / len(judged)
    if share < CLUSTER_SHARE_THRESHOLD:
        return None
    sub = [m for m in judged if m["date"] == date]
    return {
        "date": date, "n": n, "share": share,
        "working": sum(1 for m in sub if m["verdict"] == "Working"),
        "flat": sum(1 for m in sub if m["verdict"] == "Flat"),
        "failed": sum(1 for m in sub if m["verdict"] == "Failed"),
    }


def field_spread(judged, fields=GATE_FIELDS):
    """Mean(field | Working) - mean(field | Failed) for each field, plus bucket win rates."""
    out = {}
    for field in fields:
        w = [float(m[field]) for m in judged if m["verdict"] == "Working"]
        fa = [float(m[field]) for m in judged if m["verdict"] == "Failed"]
        if not w or not fa:
            continue
        out[field] = {"working_avg": stats.mean(w), "failed_avg": stats.mean(fa),
                       "spread": stats.mean(w) - stats.mean(fa)}
    return out


def bucket_report(judged, field):
    """Terciles of `field`, with working/failed rate and avg alpha per bucket."""
    vals = sorted(judged, key=lambda m: float(m[field]))
    n = len(vals)
    third = n // 3
    if third == 0:
        return []
    buckets = [("low", vals[:third]), ("mid", vals[third:2 * third]), ("high", vals[2 * third:])]
    rows = []
    for label, b in buckets:
        if not b:
            continue
        rows.append({
            "label": label,
            "lo": min(float(m[field]) for m in b), "hi": max(float(m[field]) for m in b),
            "n": len(b),
            "working_pct": sum(1 for m in b if m["verdict"] == "Working") / len(b) * 100,
            "failed_pct": sum(1 for m in b if m["verdict"] == "Failed") / len(b) * 100,
            "avg_alpha": stats.mean(m["alpha"] for m in b),
        })
    return rows


def repeat_tickers(judged):
    """Tickers alerted 2+ times, with each verdict in date order -- do repeat
    alerts on the same falling name tend to keep failing, or flip?"""
    counts = Counter(m["ticker"] for m in judged)
    out = {}
    for tkr, n in counts.items():
        if n < 2:
            continue
        rows = sorted((m for m in judged if m["ticker"] == tkr), key=lambda m: m["date"])
        out[tkr] = rows
    return out


def _print_summary(label, judged):
    if not judged:
        print(f"{label}: no judged alerts.")
        return
    w = sum(1 for m in judged if m["verdict"] == "Working")
    fl = sum(1 for m in judged if m["verdict"] == "Flat")
    fa = sum(1 for m in judged if m["verdict"] == "Failed")
    print(f"{label}: n={len(judged)}  Working={w} ({w/len(judged)*100:.0f}%)  "
          f"Flat={fl} ({fl/len(judged)*100:.0f}%)  Failed={fa} ({fa/len(judged)*100:.0f}%)  "
          f"avg_alpha={stats.mean(m['alpha'] for m in judged):+.1f}%")


def main():
    judged = build_dataset()
    if len(judged) < 10:
        print(f"Only {len(judged)} judged alerts logged -- too few for a useful read. "
              "Let more data accumulate and rerun.")
        return

    print("=== Overall ===")
    _print_summary("All", judged)

    cluster = find_cluster(judged)
    if cluster:
        print(f"\n=== Concentration flag ===")
        print(f"{cluster['date']} alone is {cluster['n']}/{len(judged)} "
              f"({cluster['share']*100:.0f}%) of the sample -- "
              f"Working={cluster['working']} Flat={cluster['flat']} Failed={cluster['failed']}")
        print("Field patterns below may be confounded by this one day/sector move.")
        excl = [m for m in judged if m["date"] != cluster["date"]]
        _print_summary(f"Excluding {cluster['date']}", excl)
    else:
        excl = judged

    print("\n=== Field spread: mean(Working) - mean(Failed), all data vs cluster excluded ===")
    print(f"{'field':<14}{'spread (all)':>14}{'spread (excl.)':>16}")
    spread_all = field_spread(judged)
    spread_excl = field_spread(excl)
    for field in GATE_FIELDS:
        a = spread_all.get(field, {}).get("spread")
        e = spread_excl.get(field, {}).get("spread")
        a_s = f"{a:+.1f}" if a is not None else "n/a"
        e_s = f"{e:+.1f}" if e is not None else "n/a"
        print(f"{field:<14}{a_s:>14}{e_s:>16}")
    print("A spread near 0 in the excl. column means no real signal in this sample.\n"
          "A spread that survives cluster exclusion is worth watching, not yet acting on.")

    print("\n=== Bucket win-rate by field (cluster excluded) ===")
    for field in GATE_FIELDS:
        rows = bucket_report(excl, field)
        if not rows:
            continue
        print(f"\n{field}:")
        for r in rows:
            print(f"  {r['label']:<5} [{r['lo']:>7.1f}..{r['hi']:>7.1f}] n={r['n']:<3} "
                  f"working={r['working_pct']:>5.1f}% failed={r['failed_pct']:>5.1f}% "
                  f"avg_alpha={r['avg_alpha']:+.1f}%")

    reps = repeat_tickers(judged)
    if reps:
        print("\n=== Repeat tickers (2+ alerts) ===")
        for tkr, rows in sorted(reps.items()):
            trail = ", ".join(f"{r['date']}:{r['verdict']}({r['alpha']:+.1f}%)" for r in rows)
            print(f"  {tkr:<6} {trail}")


if __name__ == "__main__":
    main()
