import os
import sys
import pandas as pd
import yfinance as yf

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from backend.backtesting.balanced_quality_engine import BalancedQualityEngine
from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine
from backend.backtesting.test_with_yfinance import prepare_data_for_backtest

def main():
    symbol = "LT.NS"
    print(f"Downloading 60 days of 5m data for {symbol}...")
    ticker = yf.Ticker(symbol)
    data = ticker.history(period="60d", interval="5m")
    if data.empty:
        print("Failed to download data.")
        return
        
    df = prepare_data_for_backtest(data)
    
    print("\nRunning BalancedQualityEngine...")
    engine = BalancedQualityEngine(df)
    signals = engine.generate_signals()
    
    df['signal'] = None
    for s in signals:
        df.at[s['index'], 'signal'] = s['type']
        
    df['time'] = df['date']
    
    print("\nRunning Backtest on L&T (SL=2.5x, TP=3.0x)...")
    backtest = AdvancedBacktestEngine(initial_capital=100000, seed=42)
    results = backtest.run_backtest(df, htf_trend="BULLISH", risk_per_trade=0.02, atr_sl=2.5, atr_tp=3.0)
    
    print("\nL&T RESULTS:")
    print("-" * 30)
    print(f"Win Rate:      {results['win_rate']:.1f}%")
    print(f"Profit Factor: {results['profit_factor']:.2f}")
    print(f"Net Profit:    Rs. {results['net_profit']:.0f}")
    print(f"Total Trades:  {results['total_trades']}")

if __name__ == '__main__':
    main()
