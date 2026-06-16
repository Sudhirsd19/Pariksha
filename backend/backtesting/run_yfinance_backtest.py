import asyncio
import os
import sys
import pandas as pd
import yfinance as yf
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine
from backend.backtesting.ultra_high_quality_engine import UltraHighQualitySignalEngine
from backend.backtesting.balanced_quality_engine import BalancedQualityEngine

def fetch_yfinance_data(symbol="RELIANCE.NS", interval="5m", days=60):
    """Fetch historical data using yfinance"""
    print(f"\n[*] Fetching {days} days of {interval} data for {symbol} using yfinance...")
    
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=f"{days}d", interval=interval)
    
    if df.empty:
        return None
        
    df = df.reset_index()
    
    df.rename(columns={
        'Datetime': 'date', # For BalancedQualityEngine
        'Open': 'open',
        'High': 'high',
        'Low': 'low',
        'Close': 'close',
        'Volume': 'volume'
    }, inplace=True)
    
    df['time'] = df['date'] # For AdvancedBacktestEngine
    
    df['date'] = df['date'].dt.tz_localize(None)
    
    print(f"[+] Successfully fetched {len(df)} candles.")
    return df

def main():
    print("\n" + "="*80)
    print(" YFINANCE BACKTEST RUNNER (FREE DATA) ".center(80, "="))
    print("="*80)
    
    df = fetch_yfinance_data(symbol="INFY.NS", interval="5m", days=60)
    
    if df is None or len(df) < 100:
        print("\n[!] Error: Could not fetch sufficient data")
        return
        
    print("\n[*] Select Engine:")
    print("1. Ultra-High-Quality (8 Strict Conditions - Expected lower frequency)")
    print("2. Balanced Quality (6 Conditions - Expected medium frequency)")
    
    # choice = input("Enter your choice (1/2) [Default 1]: ").strip()
    choice = "2"
    
    if choice == '2':
        print("\n[*] Using Balanced Quality Engine...")
        signal_engine = BalancedQualityEngine(df, capital=100000, risk_per_trade=2.0)
    else:
        print("\n[*] Using Ultra-High-Quality Engine...")
        signal_engine = UltraHighQualitySignalEngine(df, capital=100000, risk_per_trade=2.0)
        
    print("\n[*] Step 2: Generating signals...")
    signals = signal_engine.generate_signals()
    
    stats = signal_engine.get_signal_stats()
    print(f"  [+] Generated {stats['total_signals']} total signals")
    print(f"      BUY signals:  {stats['buy_signals']}")
    print(f"      SELL signals: {stats['sell_signals']}")
    
    if stats['total_signals'] == 0:
        print("\n[!] No signals generated on 5-minute data.")
        return
        
    print("\n[*] Step 3: Running backtest (2.5x ATR stops / 5.0x ATR Target)...")
    
    df['signal'] = None
    for s in signals:
        df.at[s['index'], 'signal'] = s['type']
        
    engine = AdvancedBacktestEngine(initial_capital=100000, seed=42)
    
    results = engine.run_backtest(
        df,
        htf_trend="BULLISH",
        risk_per_trade=0.02,
        atr_sl=2.5,
        atr_tp=5.0
    )
    
    print("\n" + "="*80)
    print(" BACKTEST RESULTS ".center(80, "="))
    print("="*80)
    print(f"Win Rate: {results.get('win_rate', 0):.1f}%")
    print(f"Trades: {results.get('total_trades', 0)}")
    print(f"Avg Win: Rs. {results.get('avg_win', 0):.0f}")
    print(f"Avg Loss: Rs. {results.get('avg_loss', 0):.0f}")
    print(f"Profit Factor: {results.get('profit_factor', 0):.2f}")
    print(f"Final Equity: Rs. {results.get('final_equity', 0):.0f}")

if __name__ == "__main__":
    main()
