import asyncio
import os
import sys
import pandas as pd
import yfinance as yf
import warnings
warnings.filterwarnings('ignore')

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine
from backend.backtesting.optimized_signal_engine import OptimizedSignalEngine
from backend.backtesting.balanced_quality_engine import BalancedQualityEngine
from backend.backtesting.ultra_high_quality_engine import UltraHighQualitySignalEngine

def fetch_yfinance_data(symbol="RELIANCE.NS", interval="5m", days=60):
    print(f"\n[*] Fetching {days} days of {interval} data for {symbol} using yfinance...")
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=f"{days}d", interval=interval)
    if df.empty: return None
    df = df.reset_index()
    df.rename(columns={
        'Datetime': 'date', 'Open': 'open', 'High': 'high', 'Low': 'low',
        'Close': 'close', 'Volume': 'volume'
    }, inplace=True)
    df['time'] = df['date']
    df['date'] = df['date'].dt.tz_localize(None)
    return df

def run_engine(engine_class, engine_name, df_original):
    df = df_original.copy()
    print(f"\n" + "-"*60)
    print(f" TESTING: {engine_name} ".center(60, "-"))
    
    # 1. Generate Signals
    if engine_name == "Optimized Engine (Base - 55%)":
        signal_engine = engine_class()
        signals = signal_engine.generate_signals(df)
    else:
        signal_engine = engine_class(df, capital=100000, risk_per_trade=2.0)
        signals = signal_engine.generate_signals()
        
    if isinstance(signals, pd.DataFrame):
        df_res = signals
        buy_signals = len(df_res[df_res['signal'] == 'BUY'])
        sell_signals = len(df_res[df_res['signal'] == 'SELL'])
        total_signals = buy_signals + sell_signals
    else:
        total_signals = len(signals)
        buy_signals = sum(1 for s in signals if s['type'] == 'BUY')
        sell_signals = sum(1 for s in signals if s['type'] == 'SELL')
        df_res = df.copy()
        df_res['signal'] = None
        for s in signals:
            df_res.at[s['index'], 'signal'] = s['type']
            
    print(f"Generated {total_signals} signals (BUY: {buy_signals}, SELL: {sell_signals})")
    
    if total_signals == 0:
        print("[!] No signals generated.")
        return None
        
    engine = AdvancedBacktestEngine(initial_capital=100000, seed=42)
    results = engine.run_backtest(df_res, htf_trend="BULLISH", risk_per_trade=0.02, atr_sl=2.5, atr_tp=5.0)
    
    print(f"Win Rate:      {results.get('win_rate', 0):.1f}%")
    print(f"Total Trades:  {results.get('total_trades', 0)}")
    print(f"Profit Factor: {results.get('profit_factor', 0):.2f}")
    
    return {
        'name': engine_name,
        'win_rate': results.get('win_rate', 0),
        'trades': results.get('total_trades', 0),
        'profit_factor': results.get('profit_factor', 0)
    }

def main():
    symbol = "RELIANCE.NS"
    print("="*80)
    print(f" ENGINE COMPARISON RUNNER for {symbol} ".center(80, "="))
    print("="*80)
    
    df = fetch_yfinance_data(symbol=symbol, interval="5m", days=60)
    if df is None: return
    
    engines = [
        (OptimizedSignalEngine, "Optimized Engine (Base - 55%)"),
        (BalancedQualityEngine, "Balanced Quality Engine (Medium - 65%)"),
        (UltraHighQualitySignalEngine, "Ultra-High Quality Engine (Strict - 70%+)")
    ]
    
    summary = []
    for cls, name in engines:
        res = run_engine(cls, name, df)
        if res:
            summary.append(res)
            
    print("\n" + "="*80)
    print(" FINAL COMPARISON SUMMARY ".center(80, "="))
    print("="*80)
    print(f"{'Engine Name':<40} | {'Win Rate':<10} | {'Trades':<8} | {'Profit Factor':<10}")
    print("-" * 80)
    for s in summary:
        print(f"{s['name']:<40} | {s['win_rate']:.1f}%      | {s['trades']:<8} | {s['profit_factor']:.2f}")

if __name__ == '__main__':
    main()
