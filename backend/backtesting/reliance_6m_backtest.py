import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.backtesting.backtest_engine import BacktestEngine
from backend.engines.signal_engine import SignalEngine

def run_reliance_intraday_backtest():
    """
    Run 6-month intraday backtest on RELIANCE data using yfinance.
    """
    print("=" * 70)
    print("RELIANCE 6-MONTH INTRADAY BACKTEST")
    print("=" * 70)
    
    # Fetch 6 months of 5m data for RELIANCE
    symbol = "RELIANCE.BO"  # NSE symbol
    print(f"\nFetching {symbol} 5-minute data (last 6 months)...")
    
    ticker = yf.Ticker(symbol)
    df_5m = ticker.history(period="6mo", interval="5m")
    df_15m = ticker.history(period="6mo", interval="15m")
    df_1h = ticker.history(period="6mo", interval="1h")
    
    if df_5m.empty or df_15m.empty or df_1h.empty:
        print("Failed to fetch data from yfinance.")
        return
    
    # Normalize timezones
    for df in [df_5m, df_15m, df_1h]:
        if df.index.tz is not None:
            df.index = df.index.tz_convert("Asia/Kolkata")
        else:
            df.index = df.index.tz_localize("Asia/Kolkata")
    
    # Rename columns
    for df in [df_5m, df_15m, df_1h]:
        df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}, inplace=True)
        df.reset_index(inplace=True)
        if 'Datetime' in df.columns:
            df.rename(columns={'Datetime': 'time'}, inplace=True)
        elif 'Date' in df.columns:
            df.rename(columns={'Date': 'time'}, inplace=True)
    
    print(f"Fetched {len(df_5m)} 5m candles, {len(df_15m)} 15m candles, {len(df_1h)} 1h candles.")
    
    # Initialize engines
    engine = BacktestEngine(initial_capital=100000)
    signal_engine = SignalEngine()
    
    print(f"\nStarting simulation on {len(df_5m)} candles...")
    
    open_trade = None
    trades_count = 0
    
    # Warmup period
    for i in range(100, len(df_5m)):
        current_time = df_5m.iloc[i]['time']
        
        # Get window data
        window_5m = df_5m.iloc[:i+1].copy()
        window_15m = df_15m[df_15m['time'] <= current_time].copy()
        window_1h = df_1h[df_1h['time'] <= current_time].copy()
        
        if len(window_1h) < 10 or len(window_15m) < 10:
            continue
        
        current_price = window_5m.iloc[-1]['close']
        
        # Manage open trade
        if open_trade:
            if open_trade['side'] == "BUY":
                if current_price >= open_trade['tp'] or current_price <= open_trade['sl']:
                    engine.execute_trade(open_trade['entry'], current_price, qty=50, side="BUY")
                    print(f"  [CLOSED] BUY trade closed at {current_price:.2f} | Entry: {open_trade['entry']:.2f}")
                    open_trade = None
                    continue
            elif open_trade['side'] == "SELL":
                if current_price <= open_trade['tp'] or current_price >= open_trade['sl']:
                    engine.execute_trade(open_trade['entry'], current_price, qty=50, side="SELL")
                    print(f"  [CLOSED] SELL trade closed at {current_price:.2f} | Entry: {open_trade['entry']:.2f}")
                    open_trade = None
                    continue
            continue
        
        # Generate signal (with backtest override enabled)
        signal_data = signal_engine.generate_signal(window_5m, window_5m, window_15m, window_1h, symbol="RELIANCE", ltp=current_price, backtest_override=True)
        
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
            trades_count += 1
            print(f"[{trades_count}] {side} signal at {current_price:.2f} | SL: {sl:.2f}, TP: {tp:.2f}")
    
    # Print metrics
    metrics = engine.get_metrics()
    print("\n" + "=" * 70)
    print("BACKTEST RESULTS")
    print("=" * 70)
    
    if isinstance(metrics, str):
        print(metrics)
    else:
        for k, v in metrics.items():
            if isinstance(v, float):
                print(f"{k:.<40} {v:>15.2f}")
            else:
                print(f"{k:.<40} {v:>15}")
    
    print("=" * 70)
    
    return metrics, engine

if __name__ == "__main__":
    metrics, engine = run_reliance_intraday_backtest()
