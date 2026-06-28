import yfinance as yf
import pandas as pd

# Wilder's RMA function
def rma(x, n):
    y = x.ewm(alpha=1/n, adjust=False).mean()
    return y

# ADX / DI function
def adx_di(df, n=14):
    df['TR'] = pd.concat([
        (df['High'] - df['Low']),
        (df['High'] - df['Close'].shift()).abs(),
        (df['Low'] - df['Close'].shift()).abs()
    ], axis=1).max(axis=1)

    df['+DM'] = df['High'].diff().clip(lower=0)
    df['-DM'] = (-df['Low'].diff()).clip(lower=0)
    df.loc[df['+DM'] < df['-DM'], '+DM'] = 0
    df.loc[df['-DM'] < df['+DM'], '-DM'] = 0

    df['TR_rma'] = rma(df['TR'], n)
    df['+DM_rma'] = rma(df['+DM'], n)
    df['-DM_rma'] = rma(df['-DM'], n)

    df['+DI'] = 100 * df['+DM_rma'] / df['TR_rma']
    df['-DI'] = 100 * df['-DM_rma'] / df['TR_rma']
    df['DX'] = (100 * (df['+DI'] - df['-DI']).abs() /
                (df['+DI'] + df['-DI']))

    df['ADX'] = rma(df['DX'], n)
    return df

print("Fetching AAPL 6mo 1d data...")
df = yf.download("AAPL", period="6mo", interval="1d")
df = adx_di(df, 14)

# Use .iloc[-1] with .at[] to ensure scalar values
adx = round(df['ADX'].iloc[-1], 2)
dip = round(df['+DI'].iloc[-1], 2)
dim = round(df['-DI'].iloc[-1], 2)

print("\nLatest ADX/DI values (Yahoo Finance ADX 14,14):")
print(f"ADX : {adx:.2f}")
print(f"+DI : {dip:.2f}")
print(f"-DI : {dim:.2f}")

print("\nLast 10 rows:")
print(df[['ADX', '+DI', '-DI']].tail(10).round(2))
