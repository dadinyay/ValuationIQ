"""
Financial data fetching service using yfinance.
Pulls live market data, income statement, balance sheet, and cash flow data.
"""

import yfinance as yf
import numpy as np
import pandas as pd
from typing import Optional
from curl_cffi.requests import Session as CurlSession

# Windows systems often lack the root CA bundle that curl_cffi needs.
# Provide a shared session with SSL verification disabled for yfinance requests.
_YF_SESSION = CurlSession(verify=False, impersonate="chrome")


def safe_get(value, default=None):
    """Return value if it's a valid number, else default."""
    if value is None:
        return default
    try:
        v = float(value)
        if np.isnan(v) or np.isinf(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def format_large_number(value: Optional[float]) -> Optional[str]:
    """Format a large number into B/M/K suffix notation."""
    if value is None:
        return None
    abs_val = abs(value)
    if abs_val >= 1e12:
        return f"${value / 1e12:.2f}T"
    elif abs_val >= 1e9:
        return f"${value / 1e9:.2f}B"
    elif abs_val >= 1e6:
        return f"${value / 1e6:.2f}M"
    elif abs_val >= 1e3:
        return f"${value / 1e3:.2f}K"
    return f"${value:.2f}"


def calculate_growth_rate(values: list) -> Optional[float]:
    """Calculate CAGR from a list of annual values (oldest to newest)."""
    clean = [v for v in values if v is not None and v > 0]
    if len(clean) < 2:
        return None
    years = len(clean) - 1
    if clean[0] == 0:
        return None
    cagr = (clean[-1] / clean[0]) ** (1 / years) - 1
    return round(cagr, 4)


def get_financial_data(ticker: str) -> dict:
    """
    Fetch comprehensive financial data for a given ticker symbol.
    Returns a structured dictionary of all financial metrics needed for DCF.
    """
    try:
        stock = yf.Ticker(ticker.upper(), session=_YF_SESSION)
        info = stock.info

        # Validate ticker
        if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
            # Try a secondary check
            hist = stock.history(period="5d")
            if hist.empty:
                raise ValueError(f"No data found for ticker '{ticker}'")

        # ── Current price ──────────────────────────────────────────────────────
        current_price = safe_get(
            info.get("currentPrice") or info.get("regularMarketPrice")
        )
        prev_close = safe_get(info.get("previousClose") or info.get("regularMarketPreviousClose"))
        price_change = None
        price_change_pct = None
        if current_price is not None and prev_close is not None:
            price_change = round(current_price - prev_close, 4)
            price_change_pct = round((price_change / prev_close) * 100, 4)

        # ── Income statement ────────────────────────────────────────────────────
        try:
            income_stmt = stock.financials  # annual, columns newest-first
        except Exception:
            income_stmt = pd.DataFrame()

        def df_row(df: pd.DataFrame, *row_names: str) -> pd.Series:
            """Return the first matching row from a DataFrame by index label."""
            for name in row_names:
                if name in df.index:
                    return df.loc[name]
            return pd.Series(dtype=float)

        revenues = []
        net_incomes = []
        if not income_stmt.empty:
            rev_row = df_row(income_stmt, "Total Revenue")
            ni_row  = df_row(income_stmt, "Net Income")
            for col in list(income_stmt.columns)[:3]:
                revenues.append(safe_get(rev_row.get(col)))
                net_incomes.append(safe_get(ni_row.get(col)))
            revenues.reverse()
            net_incomes.reverse()

        # ── Cash flow statement ─────────────────────────────────────────────────
        try:
            cashflow = stock.cashflow
        except Exception:
            cashflow = pd.DataFrame()

        fcf_list = []
        operating_cf_list = []
        capex_list = []
        if not cashflow.empty:
            fcf_row  = df_row(cashflow, "Free Cash Flow")
            ocf_row  = df_row(cashflow, "Operating Cash Flow", "Cash Flow From Continuing Operating Activities")
            capex_row= df_row(cashflow, "Capital Expenditure")
            for col in list(cashflow.columns)[:3]:
                # Prefer pre-calculated FCF row; fall back to OCF - CapEx
                fcf_direct = safe_get(fcf_row.get(col))
                ocf = safe_get(ocf_row.get(col))
                capex_raw = safe_get(capex_row.get(col))
                capex_val = abs(capex_raw) if capex_raw is not None else None
                if fcf_direct is not None:
                    fcf = fcf_direct
                elif ocf is not None and capex_val is not None:
                    fcf = ocf - capex_val
                else:
                    fcf = None
                fcf_list.append(fcf)
                operating_cf_list.append(ocf)
                capex_list.append(capex_val)
            fcf_list.reverse()
            operating_cf_list.reverse()
            capex_list.reverse()

        # ── Balance sheet ───────────────────────────────────────────────────────
        try:
            balance = stock.balance_sheet
        except Exception:
            balance = pd.DataFrame()

        total_debt = None
        total_equity = None
        cash_and_equivalents = None
        if not balance.empty:
            col = list(balance.columns)[0]
            debt_row  = df_row(balance, "Total Debt", "Long Term Debt")
            eq_row    = df_row(balance, "Stockholders Equity", "Common Stock Equity")
            cash_row  = df_row(
                balance,
                "Cash And Cash Equivalents",
                "Cash Cash Equivalents And Short Term Investments",
                "Cash And Short Term Investments",
            )
            total_debt          = safe_get(debt_row.get(col))
            total_equity        = safe_get(eq_row.get(col))
            cash_and_equivalents= safe_get(cash_row.get(col))

        # ── Growth rates ────────────────────────────────────────────────────────
        revenue_growth_rate = calculate_growth_rate(revenues)
        fcf_growth_rate = calculate_growth_rate(fcf_list)

        # Fallback: use info fields for growth
        if revenue_growth_rate is None:
            rg = safe_get(info.get("revenueGrowth"))
            revenue_growth_rate = rg if rg is not None else 0.08

        # ── Key metrics from info ───────────────────────────────────────────────
        shares_outstanding = safe_get(
            info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
        )
        market_cap = safe_get(info.get("marketCap"))
        eps = safe_get(info.get("trailingEps") or info.get("epsTrailingTwelveMonths"))
        pe_ratio = safe_get(info.get("trailingPE") or info.get("forwardPE"))
        beta = safe_get(info.get("beta"))
        week_52_high = safe_get(info.get("fiftyTwoWeekHigh"))
        week_52_low = safe_get(info.get("fiftyTwoWeekLow"))
        analyst_target = safe_get(info.get("targetMeanPrice"))
        analyst_low = safe_get(info.get("targetLowPrice"))
        analyst_high = safe_get(info.get("targetHighPrice"))
        profit_margin = safe_get(info.get("profitMargins"))
        roe = safe_get(info.get("returnOnEquity"))
        debt_to_equity = safe_get(info.get("debtToEquity"))
        if debt_to_equity is not None:
            debt_to_equity = debt_to_equity / 100  # yfinance returns as %, normalize

        # ── WACC components ─────────────────────────────────────────────────────
        # Cost of equity via CAPM: Rf + beta*(Rm - Rf)
        risk_free_rate = 0.0425  # ~10yr US Treasury as of mid-2024
        equity_risk_premium = 0.055
        beta_val = beta if (beta is not None and 0.1 < beta < 5) else 1.0
        cost_of_equity = risk_free_rate + beta_val * equity_risk_premium

        # Cost of debt
        interest_expense = None
        if not income_stmt.empty:
            col = list(income_stmt.columns)[0]
            ie_row = df_row(income_stmt, "Interest Expense", "Interest Expense Non Operating")
            interest_expense = safe_get(ie_row.get(col))
            if interest_expense is not None:
                interest_expense = abs(interest_expense)

        tax_rate = 0.21  # US corporate tax rate
        if total_debt and total_debt > 0 and interest_expense and interest_expense > 0:
            cost_of_debt_pretax = interest_expense / total_debt
            cost_of_debt = cost_of_debt_pretax * (1 - tax_rate)
        else:
            cost_of_debt = 0.04 * (1 - tax_rate)

        # WACC weights
        equity_value = market_cap or (
            (current_price * shares_outstanding) if current_price and shares_outstanding else None
        )
        if equity_value and total_debt:
            total_capital = equity_value + total_debt
            weight_equity = equity_value / total_capital
            weight_debt = total_debt / total_capital
        else:
            weight_equity = 0.8
            weight_debt = 0.2

        wacc = weight_equity * cost_of_equity + weight_debt * cost_of_debt
        wacc = max(0.06, min(wacc, 0.20))  # clamp to reasonable bounds

        # ── Latest FCF for DCF seed ─────────────────────────────────────────────
        latest_fcf = next((f for f in reversed(fcf_list) if f is not None), None)
        if latest_fcf is None:
            # Fallback: use operating cash flow
            latest_fcf = next((f for f in reversed(operating_cf_list) if f is not None), None)

        # Per-share FCF
        fcf_per_share = None
        if latest_fcf is not None and shares_outstanding and shares_outstanding > 0:
            fcf_per_share = latest_fcf / shares_outstanding

        # ── Revenue trailing twelve months ──────────────────────────────────────
        ttm_revenue = safe_get(info.get("totalRevenue"))
        if ttm_revenue is None and revenues:
            ttm_revenue = revenues[-1]

        return {
            # Identity
            "ticker": ticker.upper(),
            "company_name": info.get("longName") or info.get("shortName") or ticker.upper(),
            "exchange": info.get("exchange") or info.get("fullExchangeName", ""),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "currency": info.get("currency", "USD"),

            # Price
            "current_price": current_price,
            "prev_close": prev_close,
            "price_change": price_change,
            "price_change_pct": price_change_pct,
            "week_52_high": week_52_high,
            "week_52_low": week_52_low,

            # Market data
            "market_cap": market_cap,
            "market_cap_fmt": format_large_number(market_cap),
            "shares_outstanding": shares_outstanding,
            "eps": eps,
            "pe_ratio": pe_ratio,
            "beta": beta,

            # Margins & ratios
            "profit_margin": profit_margin,
            "roe": roe,
            "debt_to_equity": debt_to_equity,

            # Analyst
            "analyst_target": analyst_target,
            "analyst_low": analyst_low,
            "analyst_high": analyst_high,

            # Financials — arrays (oldest to newest, up to 3 years)
            "revenues": revenues,
            "revenues_fmt": [format_large_number(r) for r in revenues],
            "net_incomes": net_incomes,
            "net_incomes_fmt": [format_large_number(n) for n in net_incomes],
            "fcf_list": fcf_list,
            "fcf_list_fmt": [format_large_number(f) for f in fcf_list],
            "operating_cf_list": operating_cf_list,

            # Growth
            "revenue_growth_rate": revenue_growth_rate,
            "fcf_growth_rate": fcf_growth_rate,
            "ttm_revenue": ttm_revenue,
            "ttm_revenue_fmt": format_large_number(ttm_revenue),

            # DCF inputs
            "latest_fcf": latest_fcf,
            "latest_fcf_fmt": format_large_number(latest_fcf),
            "fcf_per_share": fcf_per_share,
            "wacc": round(wacc, 4),
            "cost_of_equity": round(cost_of_equity, 4),
            "cost_of_debt": round(cost_of_debt, 4),
            "beta_used": round(beta_val, 4),
            "total_debt": total_debt,
            "total_debt_fmt": format_large_number(total_debt),
            "cash_and_equivalents": cash_and_equivalents,
            "cash_fmt": format_large_number(cash_and_equivalents),
        }

    except ValueError:
        raise
    except Exception as e:
        raise RuntimeError(f"Failed to fetch data for '{ticker}': {str(e)}")
