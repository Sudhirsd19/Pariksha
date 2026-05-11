import sys
import os
import pandas as pd
from datetime import datetime, timedelta

# Add parent dir to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from execution.broker_api import AngelOneBroker
from signal_engine.signal_engine import SignalEngine
from indicators.technical_indicators import TechnicalIndicators
from utils.historical_data import fetch_historical_data
from utils.token_manager import token_manager

def run_backtest():
    broker = AngelOneBroker()
    if not broker.login():
        print("Login Failed")
        return

    symbol = "NIFTY"
    token = token_manager.get_token(symbol)
    exchange = token_manager.get_exchange(symbol)
    
    print(f"Fetching 24h data for {symbol}...")
    import time
    # Fetch all timeframes with delays to avoid rate limits
    df_1m = fetch_historical_data(broker.smart_api, token, "ONE_MINUTE", 1, exchange)
    time.sleep(1)
    df_5m = fetch_historical_data(broker.smart_api, token, "FIVE_MINUTE", 2, exchange)
    time.sleep(1)
    df_15m = fetch_historical_data(broker.smart_api, token, "FIFTEEN_MINUTE", 3, exchange)
    time.sleep(1)
    df_1h = fetch_historical_data(broker.smart_api, token, "ONE_HOUR", 5, exchange)

    if any(df is None or df.empty for df in [df_1m, df_5m, df_15m, df_1h]):
        print("Failed to fetch all data. API Rate limit might be hit.")
        return

    # Apply Indicators
    df_1m = TechnicalIndicators.apply_all(df_1m)
    df_5m = TechnicalIndicators.apply_all(df_5m)
    df_15m = TechnicalIndicators.apply_all(df_15m)
    df_1h = TechnicalIndicators.apply_all(df_1h)

    engine = SignalEngine()
    trades = []
    
    print("Scanning for Ultra-Strict Signals...")
    # Scan the last 100 1-minute candles
    for i in range(len(df_1m) - 100, len(df_1m)):
        sub_1m = df_1m.iloc[:i+1]
        timestamp = sub_1m.iloc[-1]['time']
        
        # Approximate alignment for other TFs (simplified for scratch)
        sub_5m = df_5m[df_5m['time'] <= timestamp]
        sub_15m = df_15m[df_15m['time'] <= timestamp]
        sub_1h = df_1h[df_1h['time'] <= timestamp]
        
        if len(sub_5m) < 20 or len(sub_15m) < 20 or len(sub_1h) < 20:
            continue
            
        signal = engine.generate_signal(sub_1m, sub_5m, sub_15m, sub_1h)
        
        if signal['signal'] != "NO TRADE":
            trades.append({
                "time": timestamp,
                "signal": signal['signal'],
                "price": signal['entry'],
                "reason": signal['reason']
            })

    print("\n" + "="*40)
    print(f"BACKTEST RESULTS (LAST 100 MINS)")
    print("="*40)
    if not trades:
        print("No trades found. Rules were too strict for this price action.")
    else:
        for t in trades:
            print(f"[{t['time']}] {t['signal']} at {t['price']} | {t['reason']}")
    print("="*40)

if __name__ == "__main__":
    run_backtest()
