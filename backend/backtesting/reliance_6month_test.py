"""
RELIANCE 6-Month Backtest with Realistic Synthetic Data
All 5 improvements tested
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine
from backend.backtesting.optimized_signal_engine import OptimizedSignalEngine

def create_realistic_reliance_data(days=180):
    """
    Create realistic 1-minute RELIANCE price data based on actual behavior:
    - Trading hours: 9:15 AM - 3:30 PM IST
    - Average volatility: 1-2% per day
    - Volume patterns: Morning surge, midday, afternoon
    """
    print("\n[*] Creating realistic RELIANCE 6-month data...")
    
    np.random.seed(42)
    
    # Create trading days (excluding weekends and holidays)
    end_date = pd.Timestamp.now(tz='Asia/Kolkata')
    start_date = end_date - timedelta(days=days)
    
    all_dates = pd.date_range(start=start_date, end=end_date, freq='D', tz='Asia/Kolkata')
    # Remove weekends (Mon=0, Sun=6)
    trading_dates = all_dates[all_dates.dayofweek < 5]
    
    print(f"    Trading days: {len(trading_dates)}")
    
    candles = []
    price = 2450  # Typical RELIANCE price
    
    for day_idx, day in enumerate(trading_dates):
        # 1-minute candles from 9:15 AM to 3:30 PM (390 minutes)
        for minute in range(0, 390):  # 9:15 AM + 390 minutes = 3:45 PM
            candle_time = day + pd.Timedelta(hours=9, minutes=15+minute)
            
            # Skip if outside trading hours (9:15 AM - 3:30 PM)
            if candle_time.hour >= 15 and candle_time.minute >= 31:
                break
            
            # Volume patterns
            hour = candle_time.hour
            if hour == 9 or hour == 10:
                # Morning opening surge
                volume_mult = 1.8 + np.random.random() * 0.4
            elif hour == 11 or hour == 12:
                # Midday chop
                volume_mult = 0.8 + np.random.random() * 0.4
            elif hour == 13 or hour == 14:
                # Afternoon momentum
                volume_mult = 1.5 + np.random.random() * 0.3
            else:
                # Regular
                volume_mult = 1.0 + np.random.random() * 0.3
            
            base_volume = 80000 * volume_mult
            volume = int(base_volume + np.random.normal(0, 5000))
            
            # Price movement
            daily_drift = 0.0001 * (np.random.random() - 0.5)  # ±0.005% per day drift
            intraday_volatility = 0.008  # 0.8% per minute volatility
            
            price_change = price * (daily_drift + np.random.normal(0, intraday_volatility))
            new_price = price + price_change
            
            # Create OHLC (high and low around close)
            high = max(price, new_price) + abs(np.random.normal(0, new_price * 0.002))
            low = min(price, new_price) - abs(np.random.normal(0, new_price * 0.002))
            
            candles.append({
                'time': candle_time,
                'open': price,
                'high': high,
                'low': low,
                'close': new_price,
                'volume': max(10000, volume)  # Min volume
            })
            
            price = new_price
    
    df = pd.DataFrame(candles)
    print(f"    Total candles: {len(df)}")
    print(f"    Date range: {df['time'].min()} to {df['time'].max()}")
    print(f"    Price range: {df['close'].min():.2f} to {df['close'].max():.2f}")
    
    return df

def analyze_signals(df):
    """Analyze signal distribution"""
    if 'signal' not in df.columns:
        return
    
    signal_df = df[df['signal'].notna()].copy()
    if len(signal_df) == 0:
        print("\n[!] No signals generated")
        return
    
    signal_df['hour'] = signal_df['time'].dt.hour
    hour_dist = signal_df.groupby('hour').size()
    
    buy_signals = (signal_df['signal'] == 'BUY').sum()
    sell_signals = (signal_df['signal'] == 'SELL').sum()
    
    print(f"\n[*] Signal Analysis:")
    print(f"    Total signals: {len(signal_df)}")
    print(f"    BUY signals:  {buy_signals}")
    print(f"    SELL signals: {sell_signals}")
    print(f"\n    By hour (IST):")
    for hour in range(9, 16):
        count = hour_dist.get(hour, 0)
        is_allowed = " [ALLOWED]" if hour in [10, 14] else " (blocked)"
        if count > 0 or hour in [10, 14]:
            print(f"      Hour {hour:2d}: {count:4d} signals{is_allowed}")

def print_results(results):
    """Pretty print backtest results"""
    print("\n" + "="*80)
    print(" BACKTEST RESULTS - RELIANCE 6-MONTH (WITH ALL 5 IMPROVEMENTS) ".center(80, "="))
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
    print("[*] 5 Active Improvements:")
    print("    [+] 2.5x ATR stops (wider, fewer false exits)")
    print("    [+] 1.5x volume filter (only high-volume candles)")
    print("    [+] Time restriction (10-11 AM & 2-3 PM IST only)")
    print("    [+] Support/Resistance bounces (mean reversion)")
    print("    [+] 2-candle confirmation (reduces false signals)")
    print("="*80)
    
    # Assessment
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
    
    print(f"\n[*] Performance Assessment:")
    print(f"    Win Rate ({results['win_rate']:.1f}%):        {wr_text}")
    print(f"    Profit Factor ({results['profit_factor']:.2f}):   {pf_text}")
    print(f"\n[*] Next Steps:")
    if results['profit_factor'] < 1.0:
        print(f"    - Strategy is currently unprofitable")
        print(f"    - Need to improve entry signal quality")
        print(f"    - Consider additional filters or parameters")
    else:
        print(f"    - Strategy shows promise!")
        print(f"    - Optimize parameters with walk-forward testing")
        print(f"    - Test on live market with small capital")

def main():
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
        # Create realistic data
        df = create_realistic_reliance_data(days=180)
        
        # Generate signals
        print("\n[*] Generating signals with all 5 improvements...")
        signal_engine = OptimizedSignalEngine()
        df = signal_engine.generate_signals(df)
        
        # Analyze signals
        analyze_signals(df)
        
        # Run backtest
        print("\n[*] Running backtest with 2.5x ATR stops, 2% risk per trade...")
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
        
        # Export trades if any
        if results['trades']:
            trades_df = pd.DataFrame(results['trades'])
            export_file = f"reliance_6month_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            trades_df.to_csv(export_file, index=False)
            print(f"\n[+] Trade log exported: {export_file}")
        
    except Exception as e:
        print(f"\n[!] Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
