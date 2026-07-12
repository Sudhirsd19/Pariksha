import os
import sys
import pandas as pd
import yfinance as yf

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from backend.backtesting.ultra_high_quality_engine import UltraHighQualitySignalEngine
from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine
from backend.backtesting.test_with_yfinance import prepare_data_for_backtest

def main():
    symbol = "RELIANCE.NS"
    print(f"Downloading 60 days of 5m data for {symbol}...")
    ticker = yf.Ticker(symbol)
    data = ticker.history(period="60d", interval="5m")
    if data.empty:
        print("Failed to download data.")
        return
        
    df = prepare_data_for_backtest(data)
    
    print("\nRunning UltraHighQualitySignalEngine to generate signals...")
    engine = UltraHighQualitySignalEngine(df)
    signals = engine.generate_signals()
    
    df['signal'] = None
    for s in signals:
        df.at[s['index'], 'signal'] = s['type']
        
    df['time'] = df['date']
    
    print("\nSweeping Take Profit ATR Multiplier for Ultra-High Quality (SL kept at 2.5x ATR):")
    print(f"{'TP Multiplier':<15} | {'Win Rate':<10} | {'Profit Factor':<15} | {'Net Profit':<12} | {'Trades':<8}")
    print("-" * 70)
    
    for tp in [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]:
        backtest = AdvancedBacktestEngine(initial_capital=100000, seed=42)
        results = backtest.run_backtest(df, htf_trend="BULLISH", risk_per_trade=0.02, atr_sl=2.5, atr_tp=tp)
        
        print(f"{tp:<15.1f} | {results['win_rate']:<9.1f}% | {results['profit_factor']:<15.2f} | Rs. {results['net_profit']:<8.0f} | {results['total_trades']:<8}")

if __name__ == '__main__':
    main()
