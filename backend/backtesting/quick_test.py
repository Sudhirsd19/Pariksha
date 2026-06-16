"""
Quick test of advanced backtest engine with simple signals
"""
import asyncio
import os
import sys
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.execution.broker_api import AngelOneBroker
from backend.utils.token_manager import token_manager
from backend.backtesting.angel_backtest_engine import fetch_long_history
from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine
from backend.backtesting.test_signal_engine import TestSignalEngine

async def main():
    print("Quick Test: Advanced Backtest with Simple Signals\n")
    
    broker = AngelOneBroker()
    broker.login()
    
    token = token_manager.get_stock_info('RELIANCE')['token']
    df = await fetch_long_history(broker.smart_api, token, 'FIVE_MINUTE', 30)
    
    if df is None:
        print("Failed to fetch data")
        return
    
    print(f"Fetched {len(df)} candles\n")
    
    # Generate test signals
    signal_engine = TestSignalEngine()
    df = signal_engine.generate_signals(df)
    
    signal_count = (df['signal'].notna()).sum()
    print(f"Generated {signal_count} test signals")
    print(df[df['signal'].notna()][['time', 'close', 'signal']].head())
    
    # Run backtest
    print("\nRunning backtest...")
    engine = AdvancedBacktestEngine(initial_capital=100000)
    report = engine.run_backtest(df, risk_per_trade=0.02, atr_sl=1.5, atr_tp=3.0)
    
    print(f"\nInitial:     Rs. {report['initial_capital']:,.0f}")
    print(f"Final:       Rs. {report['final_balance']:,.0f}")
    print(f"Net Profit:  Rs. {report['net_profit']:,.0f}")
    print(f"Total Trades: {report['total_trades']}")
    print(f"Win Rate:    {report['win_rate']:.1f}%")
    print(f"Sharpe:      {report['sharpe_ratio']:.2f}")

asyncio.run(main())
