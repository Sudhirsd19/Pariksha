import asyncio
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.execution.broker_api import AngelOneBroker
from backend.utils.token_manager import token_manager
from backend.backtesting.angel_backtest_engine import fetch_long_history, AngelBacktestEngine

async def main():
    print("--- 6-Month Angel One Backtester ---")
    broker = AngelOneBroker()
    
    # 1. Login to Broker
    try:
        broker.login()
        if not broker.session:
            print("Failed to establish Angel One session.")
            return
        print("Logged into Angel One successfully.")
    except Exception as e:
        print(f"Login failed: {e}")
        return
        
    symbol = "RELIANCE"
    stock_info = token_manager.get_stock_info(symbol)
    if not stock_info:
        print(f"Could not find token for {symbol}")
        return
        
    token = stock_info["token"]
    
    # 2. Fetch 180 days of 5-Minute Data
    print(f"\nInitiating historical data fetch for {symbol} (Token: {token})...")
    df = await fetch_long_history(broker.smart_api, token, interval="FIVE_MINUTE", total_days=180, exchange="NSE")
    
    if df is None or df.empty:
        print("Failed to fetch historical data.")
        return
        
    # 3. Run Simulation
    engine = AngelBacktestEngine(initial_capital=100000)
    print("\nStarting simulation...")
    
    # We pass 'BULLISH' as default HTF trend, but in reality we could use the StructureEngine 
    # to calculate dynamic HTF trend using daily data.
    report = engine.run_backtest(df, htf_trend="BULLISH", risk_per_trade=0.02)
    
    # 4. Print Report
    print("\n==============================")
    print("   BACKTEST PERFORMANCE REPORT")
    print("==============================")
    print(f"Initial Capital:  Rs. {report['initial_capital']:,.2f}")
    print(f"Final Balance:    Rs. {report['final_balance']:,.2f}")
    print(f"Net Profit:       Rs. {report['net_profit']:,.2f}")
    print(f"Total Trades:     {report['total_trades']}")
    print(f"Win Rate:         {report['win_rate']:.1f}%")
    print(f"Max Drawdown:     {report['max_drawdown_pct']:.2f}%")
    print(f"Gross Profit:     Rs. {report['gross_profit']:,.2f}")
    print(f"Gross Loss:       Rs. {report['gross_loss']:,.2f}")
    print("==============================\n")
    
if __name__ == "__main__":
    asyncio.run(main())
