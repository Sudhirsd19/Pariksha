"""
70% Win Rate Strategy Testing
Comparison: Standard (55%) vs High Quality (70%+)
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine
from backend.backtesting.optimized_signal_engine import OptimizedSignalEngine
from backend.backtesting.high_winrate_engine import HighWinRateSignalEngine

def create_good_data(days=180):
    """Create realistic data with clear patterns"""
    np.random.seed(42)
    
    candles = []
    price = 2450
    
    end_date = pd.Timestamp.now(tz='Asia/Kolkata')
    start_date = end_date - timedelta(days=days)
    all_dates = pd.date_range(start=start_date, end=end_date, freq='D', tz='Asia/Kolkata')
    trading_dates = all_dates[all_dates.dayofweek < 5]
    
    trend_direction = 1
    trend_strength = 0
    
    for day_idx, day in enumerate(trading_dates):
        # Change trend every 25 days
        if day_idx % 25 == 0 and day_idx > 0:
            trend_direction = -trend_direction
        
        trend_strength = 0.01 + (day_idx % 25) / 25 * 0.01
        
        for minute in range(390):
            candle_time = day + pd.Timedelta(hours=9, minutes=15+minute)
            if candle_time.hour >= 15 and candle_time.minute >= 31:
                break
            
            hour = candle_time.hour
            if hour in [9, 10]:
                vol_mult = 2.0 + np.random.random()
            elif hour in [14, 15]:
                vol_mult = 1.8 + np.random.random() * 0.4
            else:
                vol_mult = 0.9 + np.random.random() * 0.3
            
            vol = int(90000 * vol_mult + np.random.normal(0, 3000))
            
            # Price action
            trend_move = price * trend_direction * trend_strength * 0.0008
            noise = price * np.random.normal(0, 0.006)
            new_price = price + trend_move + noise
            
            high = max(price, new_price) + abs(np.random.normal(0, price*0.001))
            low = min(price, new_price) - abs(np.random.normal(0, price*0.001))
            
            candles.append({
                'time': candle_time,
                'open': price,
                'high': high,
                'low': low,
                'close': new_price,
                'volume': max(25000, vol)
            })
            
            price = new_price
    
    df = pd.DataFrame(candles)
    return df

def test_strategy(name, df, signal_engine, initial_capital=100000):
    """Test a strategy and return results"""
    print(f"\n[*] Testing {name}...")
    
    df = signal_engine.generate_signals(df)
    
    buy_count = (df['signal'] == 'BUY').sum()
    sell_count = (df['signal'] == 'SELL').sum()
    total_count = buy_count + sell_count
    
    print(f"    Signals generated: {total_count} (BUY: {buy_count}, SELL: {sell_count})")
    
    if total_count == 0:
        print(f"    [!] No signals - skipping backtest")
        return None
    
    engine = AdvancedBacktestEngine(initial_capital=initial_capital)
    results = engine.run_backtest(df, atr_sl=2.5, atr_tp=5.0)
    
    return results

def main():
    print("\n" + "="*80)
    print(" COMPARING STRATEGIES: 55% Win Rate vs 70%+ Win Rate ".center(80, "="))
    print("="*80)
    
    # Create data
    print("\n[*] Creating 180-day RELIANCE price data...")
    df = create_good_data(days=180)
    print(f"    Total candles: {len(df)}")
    print(f"    Price range: {df['close'].min():.2f} to {df['close'].max():.2f}")
    
    # Test 1: Standard (55% win rate)
    print("\n" + "-"*80)
    print("STRATEGY 1: Standard (Current) - Optimized Signal Engine")
    print("-"*80)
    print("Characteristics:")
    print("  - 5 improvements active")
    print("  - 2.5x ATR stops")
    print("  - 1.5x volume filter")
    print("  - Time restriction (10-11 AM, 2-3 PM IST)")
    print("  - More signals = more trades")
    print("  - Win rate: ~55%")
    
    standard_engine = OptimizedSignalEngine()
    results_standard = test_strategy(
        "Standard Strategy",
        df.copy(),
        standard_engine
    )
    
    # Test 2: High Win Rate (70%+)
    print("\n" + "-"*80)
    print("STRATEGY 2: High Quality - High Win Rate Engine")
    print("-"*80)
    print("Characteristics:")
    print("  - Only BEST setups")
    print("  - 2x+ volume requirement (stricter)")
    print("  - Strong EMA alignment required")
    print("  - MACD confirmation")
    print("  - RSI in momentum zone")
    print("  - Support/Resistance bounces only")
    print("  - Fewer trades = higher quality")
    print("  - Win rate target: 70%+")
    
    highwr_engine = HighWinRateSignalEngine()
    results_highwr = test_strategy(
        "High Win Rate Strategy",
        df.copy(),
        highwr_engine
    )
    
    # Compare results
    print("\n" + "="*80)
    print(" COMPARISON RESULTS ".center(80, "="))
    print("="*80)
    
    if results_standard is None or results_highwr is None:
        print("\n[!] Cannot compare - one or both strategies generated no signals")
        if results_standard:
            print("\nStrategy 1 results:")
            print_results(results_standard, "STRATEGY 1")
        if results_highwr:
            print("\nStrategy 2 results:")
            print_results(results_highwr, "STRATEGY 2")
        return
    
    # Side by side comparison
    print("\nMetric                      Strategy 1 (55%)      Strategy 2 (70%+)")
    print("-" * 80)
    print(f"Total Trades                {results_standard['total_trades']:>8}            {results_highwr['total_trades']:>8}")
    print(f"Winning Trades              {results_standard['winning_trades']:>8}            {results_highwr['winning_trades']:>8}")
    print(f"Win Rate                    {results_standard['win_rate']:>8.1f}%          {results_highwr['win_rate']:>8.1f}%")
    print(f"Avg Win (Rs.)               {results_standard['avg_win']:>12,.0f}       {results_highwr['avg_win']:>12,.0f}")
    print(f"Avg Loss (Rs.)              {results_standard['avg_loss']:>12,.0f}       {results_highwr['avg_loss']:>12,.0f}")
    print(f"Profit Factor               {results_standard['profit_factor']:>18.2f}         {results_highwr['profit_factor']:>18.2f}")
    print(f"Max Drawdown                {results_standard['max_drawdown_pct']:>18.2f}%        {results_highwr['max_drawdown_pct']:>18.2f}%")
    print(f"Sharpe Ratio                {results_standard['sharpe_ratio']:>18.2f}         {results_highwr['sharpe_ratio']:>18.2f}")
    print(f"Total Return                {results_standard['net_profit_pct']:>18.2f}%        {results_highwr['net_profit_pct']:>18.2f}%")
    print(f"Total P&L (Rs.)             {results_standard['net_profit']:>12,.0f}       {results_highwr['net_profit']:>12,.0f}")
    
    print("\n" + "="*80)
    print(" ANALYSIS ".center(80, "="))
    print("="*80)
    
    # Compare quality metrics
    reduction = (results_standard['total_trades'] - results_highwr['total_trades']) / max(results_standard['total_trades'], 1) * 100
    wr_improvement = results_highwr['win_rate'] - results_standard['win_rate']
    
    print(f"\n[1] Trade Quality Improvement:")
    print(f"    Fewer trades by {reduction:.0f}% (reduced from {results_standard['total_trades']} to {results_highwr['total_trades']})")
    print(f"    Win rate improved by {wr_improvement:.1f}% (from {results_standard['win_rate']:.1f}% to {results_highwr['win_rate']:.1f}%)")
    
    if results_highwr['profit_factor'] > results_standard['profit_factor']:
        print(f"\n[2] Profitability:")
        print(f"    Strategy 2 Profit Factor: {results_highwr['profit_factor']:.2f} vs {results_standard['profit_factor']:.2f}")
        print(f"    Better by: {(results_highwr['profit_factor']/results_standard['profit_factor']-1)*100:.0f}%")
    
    if results_highwr['sharpe_ratio'] > results_standard['sharpe_ratio']:
        print(f"\n[3] Risk-Adjusted Returns:")
        print(f"    Strategy 2 Sharpe: {results_highwr['sharpe_ratio']:.2f} vs {results_standard['sharpe_ratio']:.2f}")
        print(f"    Better risk-adjusted performance")
    
    print(f"\n[4] Verdict:")
    if results_highwr['win_rate'] >= 70:
        print(f"    ✅ Strategy 2 achieves 70%+ win rate target!")
    elif results_highwr['win_rate'] >= 65:
        print(f"    ✅ Strategy 2 achieves {results_highwr['win_rate']:.1f}% (close to 70% target)")
    else:
        print(f"    [*] Strategy 2: {results_highwr['win_rate']:.1f}% win rate")
    
    print(f"\n[5] Recommendation:")
    print(f"    Trade-off: Fewer trades BUT higher quality & higher win rate")
    print(f"    Use Strategy 2 if you want reliability & consistency")
    print(f"    Use Strategy 1 if you want volume & activity")
    
    print("\n" + "="*80)

def print_results(results, title):
    """Print individual results"""
    print(f"\n{title}:")
    print(f"  Win Rate: {results['win_rate']:.1f}%")
    print(f"  Profit Factor: {results['profit_factor']:.2f}")
    print(f"  Return: {results['net_profit_pct']:.2f}%")
    print(f"  Trades: {results['total_trades']}")

if __name__ == "__main__":
    main()
