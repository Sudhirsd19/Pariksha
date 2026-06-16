import yfinance as yf
import pandas as pd

print("Downloading RELIANCE data...")
data = yf.download("RELIANCE.NS", period="60d", interval="5m", progress=False)

print(f"\nData type: {type(data)}")
print(f"Data shape: {data.shape}")
print(f"Index type: {type(data.index)}")
print(f"Columns type: {type(data.columns)}")
print(f"Columns: {data.columns}")
print(f"Columns list: {list(data.columns)}")

print("\nFirst 5 rows:")
print(data.head())

print("\nData info:")
print(data.info())

print("\nReset index:")
df = data.reset_index()
print(f"After reset - Columns: {list(df.columns)}")
print(f"After reset - Column types: {[type(c) for c in df.columns]}")
print(df.head())
