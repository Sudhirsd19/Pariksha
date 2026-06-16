"""
Quick Testing Tool - Simple Strategy with All 5 Improvements
Tests if framework works correctly with simplified logic
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine

def simple_signal_generator(df):
    """
    Simple but effective signal generation:
    - BUY when price breaks above EMA21 on high volume
    - SELL when price breaks below EMA21 on high volume
    - Only trade during allowed hours
    """
    df = df.copy()
    df['signal'] = None
    
    # Calculate indicators
    df['ema21'] = df['close'].ewm(span=21).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['volume_ma'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / (df['volume_ma'] + 1)
    
    # ATR
    tr = np.maximum(
        df['high'] - df['low'],
        np.maximum(
            (df['high'] - df['close'].shift()).abs(),
            (df['low'] - df['close'].shift()).abs()
        )
    )
    df['atr'] = tr.rolling(14).mean()
    
    # RSI
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    df['rsi'] = 100 - (100 / (1 + gain / loss))
    
    # Generate signals
    for i in range(50, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        
        # Skip if not enough data
        if pd.isna(row['ema21']) or pd.isna(row['atr']) or row['atr'] < 0.01:
            continue
        
        # Time filter: 10-11 AM (hour=10) and 2-3 PM (hour=14) IST
        try:
            hour = row['time'].hour
            if hour not in [10, 14]:
                continue
        except:
            continue
        
        # Volume filter: must be > 1.5x MA
        if row['volume_ratio'] < 1.5:
            continue
        
        close = row['close']
        ema21 = row['ema21']
        ema50 = row['ema50']
        prev_close = prev_row['close']
        prev_ema21 = prev_row.get('ema21', ema21)
        
        # ========== BULLISH SIGNAL ==========
        # BUY: Price crosses above EMA21 with volume
        if (prev_close <= prev_ema21 and close > ema21 and
            ema21 > ema50 and  # Uptrend context
            row['rsi'] < 70 and  # Not overbought
            row['volume_ratio'] > 1.5):
            df.at[i, 'signal'] = 'BUY'
        
        # ========== BEARISH SIGNAL ==========
        # SELL: Price crosses below EMA21 with volume
        elif (prev_close >= prev_ema21 and close < ema21 and
              ema21 < ema50 and  # Downtrend context
              row['rsi'] > 30 and  # Not oversold
              row['volume_ratio'] > 1.5):
            df.at[i, 'signal'] = 'SELL'
    
    return df

def create_realistic_data(days=180):
    """Create realistic trending data"""
    np.random.seed(42)
    
    print(f"\n[*] Creating {days}-day realistic price data...")
    
    candles = []
    price = 2450
    trend = 1  # Start with uptrend
    trend_strength = 0
    
    end_date = pd.Timestamp.now(tz='Asia/Kolkata')
    start_date = end_date - timedelta(days=days)
    all_dates = pd.date_range(start=start_date, end=end_date, freq='D', tz='Asia/Kolkata')
    trading_dates = all_dates[all_dates.dayofweek < 5]
    
    for day_idx, day in enumerate(trading_dates):
        # Change trend every 20 days
        if day_idx % 20 == 0 and day_idx > 0:
            trend = -trend
            trend_strength = 0
        
        # Increase trend strength
        trend_strength = min(trend_strength + 0.01, 0.1)
        
        for minute in range(0, 390):  # 9:15 AM - 3:30 PM (390 minutes)
            candle_time = day + pd.Timedelta(hours=9, minutes=15+minute)
            
            if candle_time.hour >= 15 and candle_time.minute >= 31:
                break
            
            # Volume pattern by hour
            hour = candle_time.hour
            if hour == 9 or hour == 10:
                volume_mult = 2.0 + np.random.random()
            elif hour == 11 or hour == 12:
                volume_mult = 0.8 + np.random.random() * 0.5
            elif hour == 13 or hour == 14:
                volume_mult = 1.8 + np.random.random() * 0.4
            else:
                volume_mult = 1.0 + np.random.random() * 0.3
            
            volume = int(100000 * volume_mult + np.random.normal(0, 5000))
            
            # Price movement with trend
            base_change = price * trend * trend_strength * 0.001  # Trend component
            noise = price * np.random.normal(0, 0.008)  # Random noise
            price_change = base_change + noise
            
            new_price = price + price_change
            
            high = max(price, new_price) * (1 + abs(np.random.normal(0, 0.002)))
            low = min(price, new_price) * (1 - abs(np.random.normal(0, 0.002)))
            
            candles.append({
                'time': candle_time,
                'open': price,
                'high': high,
                'low': low,
                'close': new_price,
                'volume': max(30000, volume)
            })
            
            price = new_price
    
    df = pd.DataFrame(candles)
    print(f"    Total candles: {len(df)}")
    print(f"    Price range: {df['close'].min():.2f} to {df['close'].max():.2f}")
    print(f"    Days: {len(trading_dates)}")
    
    return df

def main():
    print("\n" + "="*80)
    print(" RELIANCE 6-MONTH TEST - ALL 5 IMPROVEMENTS ".center(80, "="))
    print("="*80)
    print("\nStrategy: Simple EMA Breakout with 5 Improvements")
    print("  1. 2.5x ATR stops (wider, fewer false exits)")
    print("  2. 1.5x volume filter")
    print("  3. Time restriction (10-11 AM & 2-3 PM IST)")
    print("  4. EMA-based entries")
    print("  5. 2% risk per trade")
    print("="*80)
    
    try:
        # Create data
        df = create_realistic_data(days=180)
        
        # Generate signals
        print("\n[*] Generating simple EMA breakout signals...")
        df = simple_signal_generator(df)
        
        buy_signals = (df['signal'] == 'BUY').sum()
        sell_signals = (df['signal'] == 'SELL').sum()
        total_signals = buy_signals + sell_signals
        
        print(f"[+] Total signals: {total_signals}")
        print(f"    BUY:  {buy_signals}")
        print(f"    SELL: {sell_signals}")
        
        if total_signals == 0:
            print("\n[!] No signals generated. Data might not have enough trends.")
            return
        
        # Run backtest
        print("\n[*] Running backtest with 2.5x ATR stops...")
        engine = AdvancedBacktestEngine(initial_capital=100000, seed=42)
        results = engine.run_backtest(
            df,
            htf_trend="NEUTRAL",
            risk_per_trade=0.02,
            atr_sl=2.5,
            atr_tp=5.0
        )
        
        # Results
        print("\n" + "="*80)
        print(" RESULTS ".center(80, "="))
        print("="*80)
        
        print(f"\nCapital:          Rs. {results['initial_capital']:>12,.0f}")
        print(f"Final Equity:     Rs. {results['final_balance']:>12,.0f}")
        print(f"P&L:              Rs. {results['net_profit']:>12,.0f} ({results['net_profit_pct']:>6.2f}%)")
        
        print(f"\nTrades:           {results['total_trades']:>18}")
        print(f"  Winning:        {results['winning_trades']:>18} ({results['win_rate']:>6.1f}%)")
        print(f"  Losing:         {results['losing_trades']:>18}")
        
        print(f"\nAvg Win:          Rs. {results['avg_win']:>12,.0f}")
        print(f"Avg Loss:         Rs. {results['avg_loss']:>12,.0f}")
        print(f"Profit Factor:    {results['profit_factor']:>18.2f}")
        
        print(f"\nMax Drawdown:     {results['max_drawdown_pct']:>18.2f}%")
        print(f"Sharpe Ratio:     {results['sharpe_ratio']:>18.2f}")
        print(f"Sortino Ratio:    {results['sortino_ratio']:>18.2f}")
        
        print(f"\nExpectancy:       Rs. {results['expectancy']:>12,.0f}")
        
        print("\n" + "="*80)
        print("[*] 5 Active Improvements Working:")
        print("    [+] 2.5x ATR stops (SL distance)")
        print("    [+] 1.5x volume filter (entry quality)")
        print("    [+] Time restriction (10-11 AM & 2-3 PM IST)")
        print("    [+] Trend-based entries (EMA breakouts)")
        print("    [+] 2% risk per trade (position sizing)")
        print("="*80)
        
        # Export
        if results['trades']:
            trades_df = pd.DataFrame(results['trades'])
            export_file = f"reliance_6month_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            trades_df.to_csv(export_file, index=False)
            print(f"\n[+] Trades exported: {export_file}")
        
    except Exception as e:
        print(f"\n[!] Error: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
