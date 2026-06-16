import os
import sys
import pandas as pd
import yfinance as yf
import datetime

# Setup paths to import backend modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from backend.engines.signal_engine import SignalEngine
from backend.backtesting.backtest_engine import BacktestEngine
from backend.engines.structure_engine import StructureEngine

def fetch_yfinance_historical(symbol="^NSEI", days=30):
    print(f"Fetching historical data for {symbol}...")
    ticker = yf.Ticker(symbol)
    
    # 1 min data is only available for the last 7 days in yfinance
    # 5 min data is available for 60 days
    # For a realistic 30-day backtest, we will use 5m data for signals and 1h for HTF.
    # To simulate the exact signal engine, we need 1m, 5m, 15m, 1h.
    # Due to yfinance limitations, we will use 5m for entry (simulating 1m loop).
    
    df_5m = ticker.history(period=f"{days}d", interval="5m")
    df_15m = ticker.history(period=f"{days}d", interval="15m")
    df_1h = ticker.history(period=f"{days}d", interval="1h")
    
    # Timezone normalization
    for df in [df_5m, df_15m, df_1h]:
        if df.empty: return None, None, None
        if df.index.tz is not None:
            df.index = df.index.tz_convert("Asia/Kolkata")
        else:
            df.index = df.index.tz_localize("Asia/Kolkata")
            
    # Rename columns to lower case to match signal_engine expectations
    for df in [df_5m, df_15m, df_1h]:
        df.rename(columns={'Open':'open', 'High':'high', 'Low':'low', 'Close':'close', 'Volume':'volume'}, inplace=True)
        df.reset_index(inplace=True)
        # Rename Datetime/Date to time
        if 'Datetime' in df.columns:
            df.rename(columns={'Datetime': 'time'}, inplace=True)
        elif 'Date' in df.columns:
            df.rename(columns={'Date': 'time'}, inplace=True)
            
    return df_5m, df_15m, df_1h

def run_historical_backtest(symbol="^NSEI", days=30):
    df_5m, df_15m, df_1h = fetch_yfinance_historical(symbol, days)
    if df_5m is None:
        print("Failed to fetch historical data.")
        return

    engine = BacktestEngine(initial_capital=100000)
    signal_engine = SignalEngine(symbol.replace("^NSEI", "NIFTY"))

    print(f"Starting Backtest on {len(df_5m)} 5-minute candles...")

    open_trade = None

    # Iterate through historical data step by step (windowed)
    for i in range(50, len(df_5m)):
        # Simulate real-time data up to index 'i'
        current_time = df_5m.iloc[i]['time']
        
        # We need historical context for indicators
        window_5m = df_5m.iloc[:i+1].copy()
        
        # Filter HTF data up to current time
        window_15m = df_15m[df_15m['time'] <= current_time].copy()
        window_1h = df_1h[df_1h['time'] <= current_time].copy()
        
        if len(window_1h) < 10 or len(window_15m) < 10:
            continue
            
        current_price = window_5m.iloc[-1]['close']

        # Manage Open Trade
        if open_trade:
            if open_trade['side'] == "BUY":
                if current_price >= open_trade['tp'] or current_price <= open_trade['sl']:
                    engine.execute_trade(open_trade['entry'], current_price, qty=50, side="BUY")
                    open_trade = None
            elif open_trade['side'] == "SELL":
                if current_price <= open_trade['tp'] or current_price >= open_trade['sl']:
                    engine.execute_trade(open_trade['entry'], current_price, qty=50, side="SELL")
                    open_trade = None
            continue # Don't take new trades while one is open

        # We pass window_5m as both 1m and 5m for backtest simulation due to yf limitations
        signal_data = signal_engine.generate_signal(window_5m, window_5m, window_15m, window_1h, symbol="NIFTY", ltp=current_price)
        
        if signal_data and signal_data.get("signal") in ["BUY", "SELL"]:
            side = signal_data["signal"]
            entry = current_price
            sl = signal_data["sl"]
            tp = signal_data["tp"]
            
            open_trade = {
                'side': side,
                'entry': entry,
                'sl': sl,
                'tp': tp,
                'time': current_time
            }

    metrics = engine.get_metrics()
    print("\n--- Backtest Results ---")
    if isinstance(metrics, str):
        print(metrics)
    else:
        for k, v in metrics.items():
            if isinstance(v, float):
                print(f"{k}: {v:.2f}")
            else:
                print(f"{k}: {v}")

if __name__ == "__main__":
    run_historical_backtest("^NSEI", days=25)
