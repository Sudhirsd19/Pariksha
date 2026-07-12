import os, sys
import pandas as pd
import yfinance as yf

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from backend.backtesting.balanced_quality_engine import BalancedQualityEngine
from backend.backtesting.ultra_high_quality_engine import UltraHighQualitySignalEngine
from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine
from backend.backtesting.test_with_yfinance import prepare_data_for_backtest

def run_backtest_verbose(df, engine_class, name, tp_mult=5.0):
    print(f"\n{'='*70}")
    print(f"  {name} (TP: {tp_mult}x ATR)")
    print(f"{'='*70}")
    engine = engine_class(df)
    signals = engine.generate_signals()
    print(f"  Signals generated: {len(signals)}")
    
    df_run = df.copy()
    df_run['signal'] = None
    for s in signals:
        df_run.at[s['index'], 'signal'] = s['type']
    df_run['time'] = df_run['date']
    
    backtest = AdvancedBacktestEngine(initial_capital=100000, seed=42)
    results = backtest.run_backtest(df_run, htf_trend="BULLISH", risk_per_trade=0.02, atr_sl=2.5, atr_tp=tp_mult)
    
    print(f"\n  --- Summary ---")
    print(f"  Win Rate:      {results['win_rate']:.1f}%")
    print(f"  Total Trades:  {results['total_trades']}")
    print(f"  Profit Factor: {results['profit_factor']:.2f}")
    print(f"  Net Return:    Rs. {results['net_profit']:.0f} ({results['net_profit_pct']:.2f}%)")
    
    if backtest.trades:
        print(f"\n  --- Trade-by-Trade Details ---")
        for i, t in enumerate(backtest.trades):
            pnl_icon = "WIN" if t['net_pnl'] > 0 else ("BE" if abs(t['net_pnl']) < 5 else "LOSS")
            print(f"  #{i+1}: {t['type']} | Entry: {t['entry_price']:.2f} -> Exit: {t['exit_price']:.2f} | "
                  f"SL: {t['sl']:.2f} | TP: {t['tp']:.2f} | "
                  f"PnL: Rs.{t['net_pnl']:.0f} [{pnl_icon}] | {t['exit_reason']}")
    
    return results

def main():
    symbol = "IRCON.NS"
    print(f"Downloading 60 days of 5m data for {symbol}...")
    ticker = yf.Ticker(symbol)
    data = ticker.history(period="60d", interval="5m")
    if data.empty:
        print("Failed to download data.")
        return
    
    df = prepare_data_for_backtest(data)
    print(f"Data: {len(df)} candles | {df.iloc[0]['date']} to {df.iloc[-1]['date']}")
    
    run_backtest_verbose(df, BalancedQualityEngine, "Balanced Quality Engine (Baseline)", tp_mult=5.0)
    run_backtest_verbose(df, BalancedQualityEngine, "Balanced Quality Engine (Optimized)", tp_mult=3.0)
    run_backtest_verbose(df, UltraHighQualitySignalEngine, "Ultra-High Quality Engine (Baseline)", tp_mult=5.0)
    run_backtest_verbose(df, UltraHighQualitySignalEngine, "Ultra-High Quality Engine (Optimized)", tp_mult=2.0)

if __name__ == '__main__':
    main()
