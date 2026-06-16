import sys
import os
import asyncio
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.execution.broker_api import AngelOneBroker
broker = AngelOneBroker()
from backend.utils.token_manager import token_manager
from backend.backtesting.angel_backtest_engine import fetch_long_history
from backend.engines.signal_engine import SignalEngine
from backend.engines.structure_engine import StructureEngine

async def debug_signals():
    broker.login()
    token = token_manager.get_stock_info("RELIANCE")["token"]
    
    df = await fetch_long_history(broker.smart_api, token, interval="FIVE_MINUTE", total_days=5, exchange="NSE")
    if df is None or df.empty:
        print("No data")
        return
        
    signal_engine = SignalEngine()
    
    print(f"Loaded {len(df)} candles.")
    
    for i in range(100, len(df)):
        current_df = df.iloc[max(0, i - 300) : i+1].copy()
        current_row = current_df.iloc[-1]
        current_price = float(current_row['close'])
        
        current_df.set_index('time', inplace=True)
        df_15m = current_df.resample('15min').agg({'open':'first', 'high':'max', 'low':'min', 'close':'last', 'volume':'sum'}).dropna().reset_index()
        df_1h = current_df.resample('1h').agg({'open':'first', 'high':'max', 'low':'min', 'close':'last', 'volume':'sum'}).dropna().reset_index()
        current_df.reset_index(inplace=True)
        
        signal = signal_engine.generate_signal(
            current_df, current_df, df_15m, df_1h, 
            symbol="RELIANCE", ltp=current_price, backtest_override=True
        )
        
        if signal.get('score', 0) > 0:
            print(f"Time: {current_row['time']} | Score: {signal.get('score')} | Bias: {signal.get('bias')} | Phase: {signal.get('phase')} | Side: {signal.get('side')}")

if __name__ == '__main__':
    asyncio.run(debug_signals())
