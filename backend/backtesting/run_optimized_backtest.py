"""
Optimized Backtest Runner v3.0
All 5 improvements implemented:
1. 2.5x ATR stops (wider, fewer false exits)
2. Volume filter (2x+ MA minimum)
3. Time restriction (10-11 AM & 2-3 PM IST)
4. Support/Resistance bounces
5. Confirmation candle requirement
"""
import asyncio
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.execution.broker_api import AngelOneBroker
from backend.utils.token_manager import token_manager
from backend.backtesting.angel_backtest_engine import fetch_long_history
from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine
from backend.backtesting.optimized_signal_engine import OptimizedSignalEngine

async def fetch_minute_data(smart_api, token, interval="ONE_MINUTE", total_days=180, exchange="NSE"):
    """Fetch 1-minute data for backtesting"""
    df_list = []
    end_date = pd.Timestamp.now(tz='Asia/Kolkata')
    chunk_size_days = 7
    remaining_days = total_days
    
    print(f"\n[*] Fetching {total_days} days of {interval} data for token {token}...")
    
    while remaining_days > 0:
        days_to_fetch = min(chunk_size_days, remaining_days)
        start_date = end_date - pd.Timedelta(days=days_to_fetch)
        
        params = {
            "exchange": exchange,
            "symboltoken": token,
            "interval": interval,
            "fromdate": start_date.strftime('%Y-%m-%d %H:%M'),
            "todate": end_date.strftime('%Y-%m-%d %H:%M')
        }
        
        try:
            data = await asyncio.to_thread(smart_api.getCandleData, params)
            if data and data.get('status') and data.get('data'):
                chunk_df = pd.DataFrame(
                    data['data'],
                    columns=['time', 'open', 'high', 'low', 'close', 'volume']
                )
                if not chunk_df.empty:
                    df_list.append(chunk_df)
                    print(f"  [+] {len(chunk_df)} candles from {start_date.date()}")
        except Exception as e:
            print(f"  [!] Failed: {str(e)[:50]}")
            pass
        
        end_date = start_date
        remaining_days -= days_to_fetch
        await asyncio.sleep(0.4)
    
    if not df_list:
        return None
    
    # Merge and clean
    full_df = pd.concat(df_list, ignore_index=True)
    full_df['time'] = pd.to_datetime(full_df['time'])
    full_df.sort_values('time', inplace=True)
    full_df.drop_duplicates(subset=['time'], keep='last', inplace=True)
    full_df.reset_index(drop=True, inplace=True)
    full_df['open'] = pd.to_numeric(full_df['open'], errors='coerce')
    full_df['high'] = pd.to_numeric(full_df['high'], errors='coerce')
    full_df['low'] = pd.to_numeric(full_df['low'], errors='coerce')
    full_df['close'] = pd.to_numeric(full_df['close'], errors='coerce')
    full_df['volume'] = pd.to_numeric(full_df['volume'], errors='coerce')
    full_df.dropna(subset=['open', 'high', 'low', 'close', 'volume'], inplace=True)
    
    print(f"[+] Total: {len(full_df)} candles over {total_days} days")
    return full_df

async def main():
    print("\n" + "="*80)
    print(" OPTIMIZED BACKTEST ENGINE v3.0 ".center(80, "="))
    print("="*80)
    print("\nAll 5 Improvements Implemented:")
    print("  1. 2.5x ATR stops (wider, fewer false exits)")
    print("  2. Volume filter (2x+ MA minimum)")
    print("  3. Time restriction (10-11 AM & 2-3 PM IST only)")
    print("  4. Support/Resistance bounce strategy")
    print("  5. 2-candle confirmation requirement")
    print("="*80)
    
    # Initialize broker
    try:
        broker = AngelOneBroker()
        smart_api = broker.smart_api
        
        # RELIANCE token
        token = 3045
        
        # Fetch data
        print("\n[*] Step 1: Fetching 1-minute RELIANCE data...")
        df = await fetch_minute_data(smart_api, token, interval="ONE_MINUTE", total_days=180)
        
        if df is None or len(df) < 100:
            print("\n[!] Error: Could not fetch sufficient data")
            return
        
        # Generate signals
        print("\n[*] Step 2: Generating optimized signals...")
        signal_engine = OptimizedSignalEngine()
        df = signal_engine.generate_signals(df)
        
        buy_signals = (df['signal'] == 'BUY').sum()
        sell_signals = (df['signal'] == 'SELL').sum()
        total_signals = buy_signals + sell_signals
        
        print(f"  [+] Generated {total_signals} total signals")
        print(f"      BUY signals:  {buy_signals}")
        print(f"      SELL signals: {sell_signals}")
        
        if total_signals == 0:
            print("\n[!] No signals generated. Need to review strategy parameters.")
            print("\nDebug Info:")
            print(f"  - Data shape: {df.shape}")
            print(f"  - Date range: {df['time'].min()} to {df['time'].max()}")
            print(f"  - Avg volume: {df['volume'].mean():.0f}")
            print(f"  - Avg volume_ma: {df['volume_ma'].mean():.0f}")
            print(f"  - Candles with volume > 2x MA: {(df['volume_ratio'] >= 2.0).sum()}")
            return
        
        # Run backtest with optimized parameters
        print("\n[*] Step 3: Running backtest with 2.5x ATR stops...")
        
        engine = AdvancedBacktestEngine(initial_capital=100000, seed=42)
        
        # Use 2.5x ATR for stop loss (the improvement)
        results = engine.run_backtest(
            df,
            htf_trend="BULLISH",
            risk_per_trade=0.02,
            atr_sl=2.5,  # WIDER stops
            atr_tp=5.0   # Correspondingly wider TP for 1:2 risk/reward
        )
        
        # Display results
        print("\n" + "="*80)
        print(" BACKTEST RESULTS ".center(80, "="))
        print("="*80)
        print(f"\nCapital: {results['initial_capital']:,.0f}")
        print(f"Final Equity: {results['final_equity']:,.0f}")
        print(f"Total P&L: Rs. {results['total_pnl']:,.0f}")
        print(f"Return: {results['return_pct']:.2f}%")
        print(f"\nTrades Executed: {results['total_trades']}")
        print(f"Winning Trades: {results['winning_trades']} ({results['win_rate']:.1f}%)")
        print(f"Losing Trades: {results['losing_trades']}")
        print(f"\nAvg Win: Rs. {results['avg_win']:,.0f}")
        print(f"Avg Loss: Rs. {results['avg_loss']:,.0f}")
        print(f"Profit Factor: {results['profit_factor']:.2f}")
        print(f"\nMax Drawdown: {results['max_drawdown_pct']:.2f}%")
        print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
        print(f"Sortino Ratio: {results['sortino_ratio']:.2f}")
        print(f"\nExpectancy per trade: Rs. {results['expectancy']:,.0f}")
        
        # Identify improvements
        print("\n" + "-"*80)
        print("Key Metrics vs Previous Run (1.5x ATR):")
        print("-"*80)
        print(f"[*] ATR multiplier: 1.5x -> 2.5x (wider stops)")
        print(f"    Effect: Should reduce SL hits from 62% to <50%")
        print(f"[*] Volume filter: 2x MA minimum (only high-volume moves)")
        print(f"    Effect: Removes noise, improves signal quality")
        print(f"[*] Time filter: 10-11 AM & 2-3 PM IST only")
        print(f"    Effect: Avoids choppy 11 AM-1 PM slot")
        print(f"[*] S/R bounces: Support/Resistance based entries")
        print(f"    Effect: Enters at high-probability reversal points")
        print(f"[*] Confirmation: 2-candle requirement")
        print(f"    Effect: Reduces false signals, improves entry quality")
        
        # Export trade logs
        if results['trades']:
            trades_df = pd.DataFrame(results['trades'])
            report_file = f"backtest_results_optimized_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            trades_df.to_csv(report_file, index=False)
            print(f"\n[+] Trade log exported to: {report_file}")
        
        print("\n" + "="*80)
        
    except Exception as e:
        print(f"\n[!] Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
