import os
import sys
import pandas as pd
from datetime import datetime

# Add parent directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")

from backend.execution.broker_api import AngelOneBroker
from backend.utils.historical_data import fetch_historical_data
from backend.indicators.technical_indicators import TechnicalIndicators
from backend.signal_engine.signal_engine import SignalEngine
from backend.config.config import config

def test_full_pipeline():
    print("--- QUANTUM INDEX PIPELINE DIAGNOSTIC ---")
    broker = AngelOneBroker()
    
    print("\n1. Testing Login...")
    if not broker.login():
        print("CRITICAL: Login failed. Check your .env credentials.")
        return

    symbols = ["NIFTY", "BANKNIFTY"]
    tokens = {"NIFTY": "99926000", "BANKNIFTY": "99926009"}
    
    signal_engine = SignalEngine()

    for symbol in symbols:
        token = tokens[symbol]
        print(f"\n--- Analyzing {symbol} (Token: {token}) ---")
        
        print("2. Fetching Historical Data (5m)...")
        df_5m = fetch_historical_data(broker.smart_api, token, interval="FIVE_MINUTE")
        
        if df_5m is None or df_5m.empty:
            print(f"FAILED: Could not fetch 5m data for {symbol}")
            continue
        print(f"SUCCESS: Fetched {len(df_5m)} candles.")

        print("3. Fetching other timeframes...")
        df_1m = fetch_historical_data(broker.smart_api, token, interval="ONE_MINUTE")
        df_15m = fetch_historical_data(broker.smart_api, token, interval="FIFTEEN_MINUTE")
        df_1h = fetch_historical_data(broker.smart_api, token, interval="ONE_HOUR")

        if any(df is None for df in [df_1m, df_15m, df_1h]):
            print("FAILED: One or more timeframes missing.")
            continue

        print("4. Calculating Indicators...")
        df_1m = TechnicalIndicators.apply_all(df_1m)
        df_5m = TechnicalIndicators.apply_all(df_5m)
        df_15m = TechnicalIndicators.apply_all(df_15m)
        df_1h = TechnicalIndicators.apply_all(df_1h)
        
        print(f"Latest Close: {df_5m['close'].iloc[-1]}")
        print(f"Latest RSI (5m): {df_5m['RSI'].iloc[-1]:.2f}")
        print(f"Latest EMA20 (5m): {df_5m['EMA_20'].iloc[-1]:.2f}")
        print(f"Latest Supertrend (5m): {df_5m['Supertrend'].iloc[-1]}")

        print("5. Generating Signal...")
        # Mock SessionFilter to return True for test
        from backend.filters.filters import SessionFilter
        original_is_within = SessionFilter.is_within_session
        SessionFilter.is_within_session = lambda: True 
        
        signal = signal_engine.generate_signal(df_1m, df_5m, df_15m, df_1h)
        SessionFilter.is_within_session = original_is_within # Restore

        print(f"SIGNAL RESULT: {signal['signal']}")
        print(f"REASON: {signal.get('reason', 'N/A')}")

    print("\n--- DIAGNOSTIC COMPLETE ---")

if __name__ == "__main__":
    test_full_pipeline()

