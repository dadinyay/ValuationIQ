"""
ValuationIQ — Flask backend
Serves DCF valuation and quote data for any stock ticker via yfinance.
"""

import os
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

from services.financials import get_financial_data
from services.dcf import calculate_dcf

load_dotenv()

app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app)


# ── Static frontend ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ── API: Full DCF valuation ────────────────────────────────────────────────────

@app.route("/api/valuation/<ticker>", methods=["GET"])
def valuation(ticker: str):
    """
    Full DCF valuation for a ticker.
    Optional query params to override DCF assumptions:
      ?growth=0.12&wacc=0.09&terminal=0.025&years=10
    """
    ticker = ticker.strip().upper()
    if not ticker or not ticker.replace(".", "").replace("-", "").isalnum():
        return jsonify({"error": "Invalid ticker symbol."}), 400

    try:
        fin = get_financial_data(ticker)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 502
    except Exception as e:
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500

    # Allow caller to override DCF assumptions via query string
    try:
        growth = float(request.args.get("growth", fin["revenue_growth_rate"] or 0.08))
        wacc = float(request.args.get("wacc", fin["wacc"] or 0.10))
        terminal = float(request.args.get("terminal", 0.025))
        years = int(request.args.get("years", 10))
    except (TypeError, ValueError):
        return jsonify({"error": "Invalid query parameters."}), 400

    dcf = calculate_dcf(
        latest_fcf=fin["latest_fcf"],
        shares_outstanding=fin["shares_outstanding"],
        revenue_growth_rate=growth,
        wacc=wacc,
        terminal_growth_rate=terminal,
        projection_years=years,
        cash_and_equivalents=fin["cash_and_equivalents"],
        total_debt=fin["total_debt"],
        current_price=fin["current_price"],
    )

    # Analyst vs DCF comparison
    analyst_verdict = None
    if (
        dcf.get("intrinsic_value_per_share")
        and fin.get("analyst_target")
        and fin["analyst_target"] > 0
    ):
        iv = dcf["intrinsic_value_per_share"]
        at = fin["analyst_target"]
        diff_pct = (iv - at) / at * 100
        if diff_pct > 10:
            analyst_verdict = "MORE_BULLISH"
        elif diff_pct < -10:
            analyst_verdict = "MORE_BEARISH"
        else:
            analyst_verdict = "AGREE"

    return jsonify(
        {
            "ticker": ticker,
            "financials": fin,
            "dcf": dcf,
            "analyst_comparison": {
                "analyst_target": fin.get("analyst_target"),
                "analyst_low": fin.get("analyst_low"),
                "analyst_high": fin.get("analyst_high"),
                "dcf_intrinsic": dcf.get("intrinsic_value_per_share"),
                "verdict": analyst_verdict,
            },
        }
    )


# ── API: Quick quote ───────────────────────────────────────────────────────────

@app.route("/api/quote/<ticker>", methods=["GET"])
def quote(ticker: str):
    """Return current price and key metrics only (faster, no full DCF)."""
    ticker = ticker.strip().upper()
    if not ticker:
        return jsonify({"error": "Ticker is required."}), 400

    try:
        fin = get_financial_data(ticker)
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify(
        {
            "ticker": fin["ticker"],
            "company_name": fin["company_name"],
            "current_price": fin["current_price"],
            "price_change": fin["price_change"],
            "price_change_pct": fin["price_change_pct"],
            "market_cap": fin["market_cap"],
            "market_cap_fmt": fin["market_cap_fmt"],
            "week_52_high": fin["week_52_high"],
            "week_52_low": fin["week_52_low"],
            "pe_ratio": fin["pe_ratio"],
            "eps": fin["eps"],
            "beta": fin["beta"],
        }
    )


# ── Health check ───────────────────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "ValuationIQ"})


# ── Run ────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "true").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
