"""
Test original strategy with improved backtest engine
"""
import asyncio
import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.execution.broker_api import AngelOneBroker
from backend.utils.token_manager import token_manager
from backend.backtesting.angel_backtest_engine import fetch_long_history, AngelBacktestEngine as OriginalEngine
from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine

async def main():
    print("="*80)
    print("COMPARING: Original Strategy with Original vs Improved Backtest")
    print("="*80)
    
    broker = AngelOneBroker()
    broker.login()
    
    token = token_manager.get_stock_info('RELIANCE')['token']
    df = await fetch_long_history(broker.smart_api, token, 'FIVE_MINUTE', 180)
    
    if df is None:
        print("Failed to fetch data")
        return
    
    print(f"\nFetched {len(df)} candles\n")
    
    # Test 1: Original engine (simple backtest)
    print("1. ORIGINAL ENGINE (5-min data, simple costs):")
    print("-" * 80)
    orig_engine = OriginalEngine(initial_capital=100000)
    orig_report = orig_engine.run_backtest(df, htf_trend="BULLISH", risk_per_trade=0.02)
    
    print(f"Final Balance: Rs. {orig_report['final_balance']:,.0f}")
    print(f"Net Profit: Rs. {orig_report['net_profit']:,.0f}")
    print(f"Win Rate: {orig_report['win_rate']:.1f}%")
    print(f"Total Trades: {orig_report['total_trades']}")
    
    # Test 2: Same strategy, improved engine (realistic costs)
    print(f"\n2. IMPROVED ENGINE (5-min data, realistic costs):")
    print("-" * 80)
    
    # Add signal column from original
    for i in range(len(df)):
        if i not in orig_engine.trades:
            df.at[i, 'signal'] = None
    
    adv_engine = AdvancedBacktestEngine(initial_capital=100000)
    adv_report = adv_engine.run_backtest(df, risk_per_trade=0.02, atr_sl=1.5, atr_tp=3.0)
    
    print(f"Final Balance: Rs. {adv_report['final_balance']:,.0f}")
    print(f"Net Profit: Rs. {adv_report['net_profit']:,.0f}")
    print(f"Win Rate: {adv_report['win_rate']:.1f}%")
    print(f"Total Trades: {adv_report['total_trades']}")
    print(f"Commission Paid: Rs. {adv_report['total_commission']:,.0f}")
    
    print(f"\n3. KEY INSIGHT:")
    print("-" * 80)
    diff = orig_report['net_profit'] - adv_report['net_profit']
    print(f"Difference: Rs. {abs(diff):,.0f}")
    print(f"This is the cost of REALISTIC slippage + commission")
    print(f"Original assumed no friction costs!")

asyncio.run(main())
