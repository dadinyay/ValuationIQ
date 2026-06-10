from curl_cffi.requests import Session as CurlSession
import yfinance as yf
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

session = CurlSession(verify=False, impersonate='chrome')
t = yf.Ticker('AAPL', session=session)

print("=== CASHFLOW ===")
cf = t.cashflow
print("Columns:", list(cf.columns) if not cf.empty else "EMPTY")
print("Index:", list(cf.index)[:15] if not cf.empty else "EMPTY")
if not cf.empty:
    col = list(cf.columns)[0]
    for row in ['Operating Cash Flow', 'Capital Expenditure', 'Free Cash Flow']:
        s = cf.get(row, pd.Series())
        print(f"{row}: {s.get(col)}")

print("\n=== INCOME STMT ===")
inc = t.financials
print("Columns:", list(inc.columns) if not inc.empty else "EMPTY")
if not inc.empty:
    col = list(inc.columns)[0]
    for row in ['Total Revenue', 'Net Income']:
        s = inc.get(row, pd.Series())
        print(f"{row}: {s.get(col)}")

print("\n=== INFO (key fields) ===")
info = t.info
for k in ['currentPrice', 'marketCap', 'sharesOutstanding', 'beta', 'revenueGrowth']:
    print(f"{k}: {info.get(k)}")
