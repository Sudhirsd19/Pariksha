"""
Optimized Backtest with Real RELIANCE 6-Month Data
All 5 improvements active:
1. 2.5x ATR stops
2. 1.5x+ volume filter
3. 10-11 AM & 2-3 PM IST time restriction
4. Support/Resistance bounces
5. 2-candle confirmation
"""
import asyncio
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.execution.broker_api import AngelOneBroker
from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine
from backend.backtesting.optimized_signal_engine import OptimizedSignalEngine

async def fetch_reliance_data(smart_api, token, days_back=180):
    """Fetch RELIANCE 1-minute data for specified days"""
    print(f"\n[*] Fetching {days_back} days of 1-minute RELIANCE data...")
    
    df_list = []
    end_date = pd.Timestamp.now(tz='Asia/Kolkata')
    chunk_size = 7  # Fetch 7 days at a time
    remaining_days = days_back
    
    while remaining_days > 0:
        days_to_fetch = min(chunk_size, remaining_days)
        start_date = end_date - pd.Timedelta(days=days_to_fetch)
        
        params = {
            "exchange": "NSE",
            "symboltoken": token,
            "interval": "ONE_MINUTE",
            "fromdate": start_date.strftime('%Y-%m-%d %H:%M'),
            "todate": end_date.strftime('%Y-%m-%d %H:%M')
        }
        
        try:
            print(f"  [*] Fetching {start_date.date()} to {end_date.date()}...", end=" ")
            data = await asyncio.to_thread(smart_api.getCandleData, params)
            
            if data and data.get('status') and data.get('data'):
                chunk_df = pd.DataFrame(
                    data['data'],
                    columns=['time', 'open', 'high', 'low', 'close', 'volume']
                )
                if not chunk_df.empty:
                    df_list.append(chunk_df)
                    print(f"[+] {len(chunk_df)} candles")
                else:
                    print(f"[!] No data")
            else:
                print(f"[!] API error: {data}")
        except Exception as e:
            print(f"[!] Error: {str(e)[:50]}")
        
        end_date = start_date - pd.Timedelta(minutes=1)
        remaining_days -= days_to_fetch
        await asyncio.sleep(0.5)
    
    if not df_list:
        print("\n[!] No data fetched!")
        return None
    
    print(f"\n[+] Consolidating data...")
    full_df = pd.concat(df_list, ignore_index=True)
    full_df['time'] = pd.to_datetime(full_df['time'])
    full_df.sort_values('time', inplace=True)
    full_df.drop_duplicates(subset=['time'], keep='last', inplace=True)
    full_df.reset_index(drop=True, inplace=True)
    
    # Ensure numeric columns
    for col in ['open', 'high', 'low', 'close', 'volume']:
        full_df[col] = pd.to_numeric(full_df[col], errors='coerce')
    
    full_df.dropna(subset=['open', 'high', 'low', 'close', 'volume'], inplace=True)
    
    print(f"[+] Total {len(full_df)} 1-minute candles from {full_df['time'].min()} to {full_df['time'].max()}")
    return full_df

def analyze_signals(df):
    """Analyze signal distribution"""
    if 'signal' not in df.columns:
        return
    
    signal_df = df[df['signal'].notna()].copy()
    if len(signal_df) == 0:
        print("\n[!] No signals generated")
        return
    
    # By hour
    signal_df['hour'] = signal_df['time'].dt.hour
    hour_dist = signal_df.groupby('hour').size()
    
    # By signal type
    buy_signals = (signal_df['signal'] == 'BUY').sum()
    sell_signals = (signal_df['signal'] == 'SELL').sum()
    
    print(f"\n[*] Signal Analysis:")
    print(f"    Total signals: {len(signal_df)}")
    print(f"    BUY signals:  {buy_signals}")
    print(f"    SELL signals: {sell_signals}")
    print(f"\n    By hour (IST):")
    for hour in sorted(hour_dist.index):
        count = hour_dist[hour]
        is_allowed = " [ALLOWED]" if hour in [10, 14] else " (blocked)"
        print(f"      Hour {hour:2d}: {count:4d} signals{is_allowed}")

def print_results(results):
    """Pretty print backtest results"""
    print("\n" + "="*80)
    print(" BACKTEST RESULTS - WITH ALL 5 IMPROVEMENTS ".center(80, "="))
    print("="*80)
    
    print(f"\nCapital:              Rs. {results['initial_capital']:>12,.0f}")
    print(f"Final Equity:         Rs. {results['final_balance']:>12,.0f}")
    print(f"Total P&L:            Rs. {results['net_profit']:>12,.0f}")
    print(f"Return:               {results['net_profit_pct']:>16.2f}%")
    
    print(f"\nTotal Trades:         {results['total_trades']:>18}")
    print(f"Winning Trades:       {results['winning_trades']:>18} ({results['win_rate']:>6.1f}%)")
    print(f"Losing Trades:        {results['losing_trades']:>18}")
    
    print(f"\nAvg Win:              Rs. {results['avg_win']:>12,.0f}")
    print(f"Avg Loss:             Rs. {results['avg_loss']:>12,.0f}")
    print(f"Profit Factor:        {results['profit_factor']:>18.2f}")
    
    print(f"\nMax Drawdown:         {results['max_drawdown_pct']:>18.2f}%")
    print(f"Sharpe Ratio:         {results['sharpe_ratio']:>18.2f}")
    print(f"Sortino Ratio:        {results['sortino_ratio']:>18.2f}")
    print(f"\nExpectancy per trade: Rs. {results['expectancy']:>12,.0f}")
    
    print(f"\nTotal Commission:     Rs. {results['total_commission']:>12,.0f}")
    print(f"Gross Profit:         Rs. {results['gross_profit']:>12,.0f}")
    print(f"Gross Loss:           Rs. {results['gross_loss']:>12,.0f}")
    
    print("\n" + "="*80)
    
    # Interpretation
    if results['win_rate'] >= 50:
        wr_text = "EXCELLENT"
    elif results['win_rate'] >= 40:
        wr_text = "GOOD"
    elif results['win_rate'] >= 35:
        wr_text = "ACCEPTABLE"
    else:
        wr_text = "NEEDS IMPROVEMENT"
    
    if results['profit_factor'] >= 2.0:
        pf_text = "EXCELLENT"
    elif results['profit_factor'] >= 1.5:
        pf_text = "GOOD"
    elif results['profit_factor'] >= 1.0:
        pf_text = "BREAKEVEN"
    else:
        pf_text = "LOSING"
    
    if results['sharpe_ratio'] >= 1.0:
        sr_text = "EXCELLENT"
    elif results['sharpe_ratio'] >= 0.5:
        sr_text = "GOOD"
    else:
        sr_text = "NEEDS IMPROVEMENT"
    
    print(f"\n[*] Interpretation:")
    print(f"    Win Rate ({results['win_rate']:.1f}%):        {wr_text}")
    print(f"    Profit Factor ({results['profit_factor']:.2f}):   {pf_text}")
    print(f"    Sharpe Ratio ({results['sharpe_ratio']:.2f}):     {sr_text}")
    print(f"\n[*] 5 Active Improvements:")
    print(f"    [+] 2.5x ATR stops (wider, fewer false exits)")
    print(f"    [+] 1.5x volume filter (only high-volume candles)")
    print(f"    [+] Time restriction (10-11 AM & 2-3 PM IST only)")
    print(f"    [+] Support/Resistance bounces (mean reversion)")
    print(f"    [+] 2-candle confirmation (reduces false signals)")

async def main():
    print("\n" + "="*80)
    print(" RELIANCE 6-MONTH BACKTEST - ALL 5 IMPROVEMENTS ".center(80, "="))
    print("="*80)
    print("\nActive Improvements:")
    print("  1. 2.5x ATR stops (wider, fewer false exits)")
    print("  2. 1.5x volume filter (only trade high-volume moves)")
    print("  3. Time restriction (10-11 AM & 2-3 PM IST only)")
    print("  4. Support/Resistance bounces (high-probability entries)")
    print("  5. 2-candle confirmation (reduces noise)")
    print("="*80)
    
    try:
        # Initialize broker
        broker = AngelOneBroker()
        smart_api = broker.smart_api
        
        # RELIANCE token
        token = 3045
        
        # Fetch data
        df = await fetch_reliance_data(smart_api, token, days_back=180)
        
        if df is None or len(df) < 500:
            print("\n[!] Insufficient data. Need at least 500 candles for proper backtest.")
            return
        
        # Generate signals
        print("\n[*] Generating signals with all 5 improvements...")
        signal_engine = OptimizedSignalEngine()
        df = signal_engine.generate_signals(df)
        
        # Analyze signals
        analyze_signals(df)
        
        # Run backtest
        print("\n[*] Running backtest with 2.5x ATR stops...")
        engine = AdvancedBacktestEngine(initial_capital=100000, seed=42)
        results = engine.run_backtest(
            df,
            htf_trend="BULLISH",
            risk_per_trade=0.02,  # 2% risk per trade
            atr_sl=2.5,           # WIDER stops
            atr_tp=5.0            # 1:2 risk/reward
        )
        
        # Display results
        print_results(results)
        
        # Export trade log
        if results['trades']:
            trades_df = pd.DataFrame(results['trades'])
            export_file = f"reliance_6month_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            trades_df.to_csv(export_file, index=False)
            print(f"\n[+] Trade log exported to: {export_file}")
            print(f"    Total trades: {len(trades_df)}")
        
        print("\n" + "="*80)
        
    except Exception as e:
        print(f"\n[!] Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
