import yfinance as yf
import pandas as pd
import numpy as np
from backend.backtesting.optimized_signal_engine import OptimizedSignalEngine

print("=" * 80)
print("DIAGNOSTIC: Why are there 0 signals?")
print("=" * 80)

# Download data
data = yf.download("RELIANCE.NS", period="60d", interval="5m", progress=False)

# Flatten MultiIndex
if isinstance(data.columns, pd.MultiIndex):
    data.columns = [col[0] for col in data.columns]

df = data.reset_index()
df.columns = ['date', 'close', 'high', 'low', 'open', 'volume']
df = df[['date', 'open', 'high', 'low', 'close', 'volume']]

print(f"\n[DATA LOADED] {len(df)} candles")
print(f"  Date range: {df['date'].min()} to {df['date'].max()}")
print(f"  Close price: {df['close'].min():.2f} - {df['close'].max():.2f}")
print(f"  Volume: {df['volume'].min()} - {df['volume'].max()}")

# Initialize engine
engine = OptimizedSignalEngine()

print("\n[*] Testing conditions step-by-step...")

# Test each row
times_ok = 0
volume_ok = 0
ema_ok = 0
macd_ok = 0
rsi_ok = 0
sr_ok = 0
conf_ok = 0
signal_count = 0

for i in range(20, len(df)):
    row = df.iloc[i]
    
    # Test time filter
    if engine._is_allowed_time(row):
        times_ok += 1
    
    # Get indicators
    close_prices = df['close'].iloc[:i+1].values
    
    if len(close_prices) >= 20:
        ema = np.mean(close_prices[-20:])
        ema_ok += 1
    else:
        continue
    
    # Test volume
    if i >= 20:
        vol_ma = df['volume'].iloc[i-20:i].mean()
        if row['volume'] > vol_ma * 1.5:
            volume_ok += 1
    
    # Get signal
    try:
        signal = engine.generate_signal(df, i)
        if signal != "NO_SIGNAL":
            signal_count += 1
            print(f"\n[!] Signal found at index {i}")
            print(f"    Date: {row['date']}")
            print(f"    Close: {row['close']:.2f}")
            print(f"    Signal: {signal}")
    except Exception as e:
        pass

print(f"\n[RESULTS]")
print(f"  ✓ Time-allowed rows: {times_ok}/{len(df)}")
print(f"  ✓ Volume > 1.5x MA: {volume_ok}/{len(df)}")
print(f"  ✓ Total signals: {signal_count}")

# Check time zone
print(f"\n[TIME ZONE CHECK]")
for i in range(0, min(5, len(df))):
    row = df.iloc[i]
    print(f"  {row['date']} -> Hour: {row['date'].hour}, Minute: {row['date'].minute}")
