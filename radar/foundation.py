"""Gate 2 — Foundation score (0-100): is the business itself sound?

Ported from stock-recommender's fundamentals scorer, minus analyst-target
upside (that belongs to the analyst gate, not business quality).
Components: revenue growth 25, gross margin 15, EPS positive 15,
forward-vs-trailing P/E 20, debt 10, free cash flow 15.
"""

FOUNDATION_THRESHOLD = 60


def foundation_score(info):
    """Takes a yfinance .info dict. Returns (score 0-100, detail string)."""
    try:
        revenue_growth = (info.get("revenueGrowth") or 0) * 100
        gross_margin = (info.get("grossMargins") or 0) * 100
        trailing_eps = info.get("trailingEps") or 0
        forward_pe = info.get("forwardPE") or 0
        trailing_pe = info.get("trailingPE") or 0
        debt_to_equity = info.get("debtToEquity")
        fcf = info.get("freeCashflow")

        growth_pts = max(0.0, min(25.0, revenue_growth * 2.5))  # 10%+ growth = full marks
        margin_pts = max(0.0, min(15.0, gross_margin * 0.25))   # 60%+ margin = full marks
        eps_pts = 15.0 if trailing_eps > 0 else 0.0

        pe_note = ""
        if forward_pe > 0 and trailing_pe > 0:
            if forward_pe < 8 and forward_pe < trailing_pe * 0.5:
                pe_pts = 5.0  # cyclical trap: market pricing peak earnings
                pe_note = "fwd P/E deep-discount (peak-cycle risk)"
            elif forward_pe < trailing_pe * 0.75 and revenue_growth > 0:
                pe_pts = 20.0  # earnings growing into the valuation
            elif forward_pe < trailing_pe:
                pe_pts = 13.0
            else:
                pe_pts = 5.0
        else:
            pe_pts = 8.0  # neutral when either P/E is missing/negative

        if debt_to_equity is None:
            debt_pts = 5.0
        elif debt_to_equity < 100:
            debt_pts = 10.0
        elif debt_to_equity < 200:
            debt_pts = 5.0
        else:
            debt_pts = 0.0

        if fcf is None:
            fcf_pts = 7.0
        else:
            fcf_pts = 15.0 if fcf > 0 else 0.0

        score = min(100.0, growth_pts + margin_pts + eps_pts + pe_pts + debt_pts + fcf_pts)
        detail = (f"Rev growth {revenue_growth:+.0f}% | margin {gross_margin:.0f}% | "
                  f"EPS {'+' if trailing_eps > 0 else '-'} | debt/eq "
                  f"{debt_to_equity:.0f}" if debt_to_equity is not None else
                  f"Rev growth {revenue_growth:+.0f}% | margin {gross_margin:.0f}% | "
                  f"EPS {'+' if trailing_eps > 0 else '-'} | debt n/a")
        if pe_note:
            detail += f" | {pe_note}"
        return round(score, 1), detail
    except Exception:
        return 0.0, "Fundamentals unavailable"
