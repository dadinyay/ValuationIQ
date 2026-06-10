"""
DCF (Discounted Cash Flow) valuation engine.
Projects free cash flows, discounts to present value, adds terminal value,
and computes intrinsic value per share with margin of safety.
"""

import numpy as np
from typing import Optional


TERMINAL_GROWTH_DEFAULT = 0.025  # 2.5%


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(value, hi))


def calculate_dcf(
    latest_fcf: float,
    shares_outstanding: float,
    revenue_growth_rate: float,
    wacc: float,
    terminal_growth_rate: float = TERMINAL_GROWTH_DEFAULT,
    projection_years: int = 10,
    cash_and_equivalents: Optional[float] = None,
    total_debt: Optional[float] = None,
    current_price: Optional[float] = None,
) -> dict:
    """
    Run a two-stage DCF model:
      Stage 1 (years 1-5): project FCF at `revenue_growth_rate` (clamped)
      Stage 2 (years 6-10): fade growth toward terminal rate linearly
      Terminal value: Gordon Growth Model
    Returns a dict with intrinsic value, margin of safety, and projections table.
    """

    if latest_fcf is None or latest_fcf <= 0:
        return _insufficient_data("Latest FCF is zero or negative — DCF not meaningful.")

    if shares_outstanding is None or shares_outstanding <= 0:
        return _insufficient_data("Shares outstanding unavailable.")

    # Clamp inputs to sensible ranges
    g1 = clamp(revenue_growth_rate, -0.05, 0.40)   # stage 1 growth
    g2_floor = terminal_growth_rate                  # stage 2 fades to this
    wacc = clamp(wacc, 0.06, 0.25)

    if wacc <= terminal_growth_rate:
        terminal_growth_rate = wacc - 0.01          # ensure convergence

    projections = []
    cumulative_pv = 0.0

    for year in range(1, projection_years + 1):
        # Linear fade from g1 to terminal_growth_rate over years 6-10
        if year <= 5:
            growth = g1
        else:
            fade_fraction = (year - 5) / 5          # 0.2 → 1.0
            growth = g1 + fade_fraction * (g2_floor - g1)

        if year == 1:
            fcf = latest_fcf * (1 + growth)
        else:
            fcf = projections[-1]["fcf"] * (1 + growth)

        discount_factor = 1 / ((1 + wacc) ** year)
        present_value = fcf * discount_factor

        cumulative_pv += present_value
        projections.append(
            {
                "year": year,
                "growth_rate": round(growth * 100, 2),
                "fcf": fcf,
                "fcf_fmt": _fmt(fcf),
                "discount_factor": round(discount_factor, 6),
                "present_value": present_value,
                "present_value_fmt": _fmt(present_value),
                "cumulative_pv_fmt": _fmt(cumulative_pv),
            }
        )

    # Terminal value (Gordon Growth Model)
    terminal_fcf = projections[-1]["fcf"] * (1 + terminal_growth_rate)
    terminal_value = terminal_fcf / (wacc - terminal_growth_rate)
    terminal_pv = terminal_value / ((1 + wacc) ** projection_years)

    total_equity_value = cumulative_pv + terminal_pv

    # Adjust for net debt (enterprise value → equity value)
    net_debt = 0.0
    if total_debt is not None:
        net_debt += total_debt
    if cash_and_equivalents is not None:
        net_debt -= cash_and_equivalents
    # net_debt positive → owe more than we have; subtract from equity value
    equity_value = total_equity_value - net_debt

    intrinsic_value_per_share = equity_value / shares_outstanding

    # Margin of safety
    margin_of_safety = None
    verdict = "UNKNOWN"
    if current_price and current_price > 0 and intrinsic_value_per_share > 0:
        margin_of_safety = (intrinsic_value_per_share - current_price) / intrinsic_value_per_share * 100
        if margin_of_safety > 15:
            verdict = "UNDERVALUED"
        elif margin_of_safety < -15:
            verdict = "OVERVALUED"
        else:
            verdict = "FAIRLY VALUED"

    # PV breakdown
    pv_stage1 = sum(p["present_value"] for p in projections[:5])
    pv_stage2 = sum(p["present_value"] for p in projections[5:])
    tv_pct = (terminal_pv / total_equity_value * 100) if total_equity_value > 0 else None

    return {
        "success": True,
        "intrinsic_value_per_share": round(intrinsic_value_per_share, 2),
        "terminal_value": terminal_value,
        "terminal_value_fmt": _fmt(terminal_value),
        "terminal_pv": terminal_pv,
        "terminal_pv_fmt": _fmt(terminal_pv),
        "terminal_value_pct_of_total": round(tv_pct, 1) if tv_pct else None,
        "total_equity_value": total_equity_value,
        "total_equity_value_fmt": _fmt(total_equity_value),
        "pv_fcf_stage1": pv_stage1,
        "pv_fcf_stage2": pv_stage2,
        "margin_of_safety": round(margin_of_safety, 2) if margin_of_safety is not None else None,
        "verdict": verdict,
        "assumptions": {
            "latest_fcf": latest_fcf,
            "latest_fcf_fmt": _fmt(latest_fcf),
            "revenue_growth_rate": round(g1 * 100, 2),
            "terminal_growth_rate": round(terminal_growth_rate * 100, 2),
            "wacc": round(wacc * 100, 2),
            "projection_years": projection_years,
            "net_debt": net_debt,
            "net_debt_fmt": _fmt(net_debt),
        },
        "projections": projections,
        "shares_outstanding": shares_outstanding,
    }


def _fmt(value: Optional[float]) -> Optional[str]:
    """Format raw dollar value to readable string."""
    if value is None:
        return None
    negative = value < 0
    abs_val = abs(value)
    if abs_val >= 1e12:
        s = f"${abs_val / 1e12:.2f}T"
    elif abs_val >= 1e9:
        s = f"${abs_val / 1e9:.2f}B"
    elif abs_val >= 1e6:
        s = f"${abs_val / 1e6:.2f}M"
    else:
        s = f"${abs_val:,.0f}"
    return f"-{s}" if negative else s


def _insufficient_data(reason: str) -> dict:
    return {
        "success": False,
        "error": reason,
        "intrinsic_value_per_share": None,
        "margin_of_safety": None,
        "verdict": "INSUFFICIENT DATA",
        "projections": [],
    }
