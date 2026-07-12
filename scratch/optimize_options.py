import os, sys, time
import pandas as pd
import numpy as np
import yfinance as yf

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from backend.backtesting.balanced_quality_engine import BalancedQualityEngine
from backend.backtesting.ultra_high_quality_engine import UltraHighQualitySignalEngine
from backend.backtesting.test_with_yfinance import prepare_data_for_backtest
from scratch.test_options_backtest import OptionsBacktestEngine

def main():
    symbol = "NIFTY"
    print(f"Downloading 60 days of 5m data for {symbol} index...")
    ticker = yf.Ticker("^NSEI")
    data = ticker.history(period="60d", interval="5m")
    if data.empty:
        print("Failed to download NIFTY data.")
        return
        
    df = prepare_data_for_backtest(data)
    print(f"Data ready: {len(df)} candles.")
    
    print("\n=======================================================")
    print("      NIFTY OPTIONS PARAMETER OPTIMIZATION SWEEP      ")
    print("=======================================================")
    
    # 1. Balanced Quality Engine signals
    bal_engine = BalancedQualityEngine(df)
    bal_sigs = bal_engine.generate_signals()
    
    # 2. Ultra-High Quality Engine signals
    ultra_engine = UltraHighQualitySignalEngine(df)
    ultra_sigs = ultra_engine.generate_signals()
    
    print(f"Signals found: Balanced Engine: {len(bal_sigs)} | Ultra-High Engine: {len(ultra_sigs)}")
    
    results = []
    
    # We test both engines, different SLs and TPs
    for name, sigs in [("Balanced Engine (65%)", bal_sigs), 
                       ("Ultra-High Engine (70%+)", ultra_sigs)]:
        if not sigs:
            continue
        for sl in [1.5, 2.0, 2.5]:
            for tp in [2.0, 3.0, 4.0, 5.0, 6.0]:
                backtester = OptionsBacktestEngine(initial_capital=100000)
                report = backtester.run_options_backtest(df, "NIFTY", sigs, capital_per_trade=10000, atr_sl=sl, atr_tp=tp)
                results.append({
                    'engine': name,
                    'sl': sl,
                    'tp': tp,
                    'trades': report['total_trades'],
                    'win_rate': report['win_rate'],
                    'pf': report['profit_factor'],
                    'net_profit': report['net_profit'],
                    'net_profit_pct': report['net_profit_pct']
                })
                
    if not results:
        print("No results to show.")
        return
        
    # Sort results by Net Profit Descending
    df_res = pd.DataFrame(results)
    df_res = df_res.sort_values(by='net_profit', ascending=False)
    
    print("\nOPTIMIZED SETTINGS FOR NIFTY OPTIONS:")
    print(df_res.to_string(index=False))

if __name__ == '__main__':
    main()
