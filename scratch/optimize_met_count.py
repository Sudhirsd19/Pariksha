import os
import sys
import pandas as pd
import yfinance as yf

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from backend.backtesting.balanced_quality_engine import BalancedQualityEngine
from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine
from backend.backtesting.test_with_yfinance import prepare_data_for_backtest

class DynamicBalancedQualityEngine(BalancedQualityEngine):
    def __init__(self, df, min_conditions=5):
        self.min_conditions = min_conditions
        super().__init__(df)
        
    def _evaluate_bullish_signal(self, idx):
        res = super()._evaluate_bullish_signal(idx)
        if res and res['conditions_met'] < self.min_conditions:
            return None
        return res
        
    def _evaluate_bearish_signal(self, idx):
        res = super()._evaluate_bearish_signal(idx)
        if res and res['conditions_met'] < self.min_conditions:
            return None
        return res

def main():
    symbol = "RELIANCE.NS"
    print(f"Downloading 60 days of 5m data for {symbol}...")
    ticker = yf.Ticker(symbol)
    data = ticker.history(period="60d", interval="5m")
    if data.empty:
        print("Failed to download data.")
        return
        
    df = prepare_data_for_backtest(data)
    
    print("\nSweeping Minimum Conditions Met for BalancedQualityEngine (SL=2.5x, TP=3.0x):")
    print(f"{'Min Conditions':<15} | {'Win Rate':<10} | {'Profit Factor':<15} | {'Net Profit':<12} | {'Trades':<8}")
    print("-" * 70)
    
    for min_cond in [4, 5, 6]:
        # Custom evaluation logic by subclassing
        engine = DynamicBalancedQualityEngine(df, min_conditions=min_cond)
        signals = engine.generate_signals()
        
        df_run = df.copy()
        df_run['signal'] = None
        for s in signals:
            df_run.at[s['index'], 'signal'] = s['type']
            
        df_run['time'] = df_run['date']
        
        backtest = AdvancedBacktestEngine(initial_capital=100000, seed=42)
        results = backtest.run_backtest(df_run, htf_trend="BULLISH", risk_per_trade=0.02, atr_sl=2.5, atr_tp=3.0)
        
        print(f"{min_cond:<15d} | {results['win_rate']:<9.1f}% | {results['profit_factor']:<15.2f} | Rs. {results['net_profit']:<8.0f} | {results['total_trades']:<8}")

if __name__ == '__main__':
    main()
