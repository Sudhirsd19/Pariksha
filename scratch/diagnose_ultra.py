import os
import sys
import pandas as pd
import yfinance as yf
from collections import Counter

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from backend.backtesting.ultra_high_quality_engine import UltraHighQualitySignalEngine

def main():
    symbol = "RELIANCE.NS"
    print(f"Downloading 60 days of 5m data for {symbol}...")
    ticker = yf.Ticker(symbol)
    df = ticker.history(period="60d", interval="5m")
    if df.empty:
        print("Failed to download data.")
        return
        
    df = df.reset_index()
    df.rename(columns={
        'Datetime': 'date', 'Open': 'open', 'High': 'high', 'Low': 'low',
        'Close': 'close', 'Volume': 'volume'
    }, inplace=True)
    df['time'] = df['date']
    df['date'] = df['date'].dt.tz_localize(None)
    
    print(f"Loaded {len(df)} candles. Running UltraHighQualitySignalEngine...")
    engine = UltraHighQualitySignalEngine(df)
    signals = engine.generate_signals()
    
    print(f"\nGenerated {len(signals)} signals.")
    
    # Analyze rejected reasons
    rejections = engine.rejected_reasons
    print(f"Total rejection logs: {len(rejections)}")
    
    # Count failed conditions
    failed_conditions = []
    for r in rejections:
        # Format is "BUY rejected at 205: EMA aligned, Volume 2x+"
        if ":" in r:
            failed_parts = r.split(":")[1].strip().split(", ")
            failed_conditions.extend(failed_parts)
            
    counts = Counter(failed_conditions)
    print("\nMost common failed conditions:")
    for cond, count in counts.most_common():
        print(f"  - {cond}: {count} ({count/len(rejections):.1%})")

if __name__ == '__main__':
    main()
