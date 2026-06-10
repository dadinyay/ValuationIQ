# ValuationIQ — Professional DCF Stock Valuation

A Bloomberg-style Discounted Cash Flow valuation engine built with Python/Flask and live market data from Yahoo Finance.

## Quick Start

```bash
cd ValuationIQ
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000 in your browser.

## Features

- Live financial data via yfinance (no API key required)
- Two-stage DCF model (high growth → terminal fade)
- WACC calculated from beta, debt structure, and market data
- Adjustable assumptions with instant recalculation
- Analyst consensus comparison
- 10-year FCF projection table

## Test Tickers

AAPL, MSFT, GOOGL, JPM, BAC, TSLA, AMZN, NVDA

## Project Structure

```
ValuationIQ/
├── app.py                  Flask backend + API routes
├── services/
│   ├── financials.py       yfinance data fetching
│   └── dcf.py              DCF calculation engine
├── static/
│   └── index.html          Bloomberg-style frontend
├── requirements.txt
└── .env.example
```

## API Endpoints

- `GET /api/valuation/<ticker>` — Full DCF valuation
  - Query params: `?growth=0.12&wacc=0.09&terminal=0.025`
- `GET /api/quote/<ticker>` — Quick price and stats
- `GET /api/health` — Health check
