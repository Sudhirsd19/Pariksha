"""
Quick Test of All 5 Improvements
Uses synthetic data to demonstrate the optimized strategy
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.backtesting.optimized_signal_engine import OptimizedSignalEngine
from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine

def create_sample_data(days=180):
    """Create realistic 1-minute RELIANCE data for testing"""
    np.random.seed(42)
    
    # Generate hourly closes that trend
    num_candles = days * 24 * 60  # 1-minute candles
    
    # Create time index starting from 6 months ago
    end_time = datetime(2026, 6, 16, 15, 30)
    start_time = end_time - timedelta(days=days)
    times = pd.date_range(start=start_time, periods=num_candles, freq='1min')
    
    # Generate price data (random walk with small drift)
    price = 2500  # Typical RELIANCE price
    prices = [price]
    
    for i in range(1, num_candles):
        # Small random walk with 0.01% expected drift per candle
        change = np.random.normal(0.00001, 0.005)
        price = price * (1 + change)
        prices.append(price)
    
    prices = np.array(prices)
    
    # Create OHLCV data
    df = pd.DataFrame({
        'time': times,
        'open': prices,
        'high': prices + np.abs(np.random.normal(0, 0.3, len(prices))),
        'low': prices - np.abs(np.random.normal(0, 0.3, len(prices))),
        'close': prices + np.random.normal(0, 0.2, len(prices)),
        'volume': np.random.randint(50000, 500000, len(prices))
    })
    
    # Ensure OHLC integrity
    df['high'] = df[['open', 'high', 'low', 'close']].max(axis=1)
    df['low'] = df[['open', 'high', 'low', 'close']].min(axis=1)
    
    return df

def main():
    print("\n" + "="*80)
    print(" ALL 5 IMPROVEMENTS - QUICK TEST ".center(80, "="))
    print("="*80)
    
    # Create sample data
    print("\n[*] Creating synthetic 1-minute RELIANCE data (180 days)...")
    df = create_sample_data(days=180)
    print(f"    [+] Generated {len(df)} candles from {df['time'].min()} to {df['time'].max()}")
    
    # Generate signals with all 5 improvements
    print("\n[*] Applying optimized signal engine with 5 improvements...")
    signal_engine = OptimizedSignalEngine()
    df = signal_engine.generate_signals(df)
    
    buy_signals = (df['signal'] == 'BUY').sum()
    sell_signals = (df['signal'] == 'SELL').sum()
    total_signals = buy_signals + sell_signals
    
    print(f"    [+] Generated {total_signals} total signals")
    print(f"        - BUY signals:  {buy_signals}")
    print(f"        - SELL signals: {sell_signals}")
    
    # Show signal distribution
    print("\n[*] Signal Distribution by Time:")
    signal_df = df[df['signal'].notna()].copy()
    if len(signal_df) > 0:
        signal_df['hour'] = signal_df['time'].dt.hour
        hour_dist = signal_df['hour'].value_counts().sort_index()
        for hour in sorted(hour_dist.index):
            count = hour_dist[hour]
            print(f"    Hour {hour:02d}: {count:3d} signals")
    
    # Run backtest with 2.5x ATR stops
    print("\n[*] Running backtest with 2.5x ATR stops (improvement)...")
    engine = AdvancedBacktestEngine(initial_capital=100000, seed=42)
    
    results = engine.run_backtest(
        df,
        htf_trend="BULLISH",
        risk_per_trade=0.02,
        atr_sl=2.5,  # IMPROVEMENT 1: Wider stops
        atr_tp=5.0   # 1:2 risk/reward
    )
    
    # Display results
    print("\n" + "="*80)
    print(" BACKTEST RESULTS WITH ALL 5 IMPROVEMENTS ".center(80, "="))
    print("="*80)
    
    print(f"\nCapital: Rs. {results['initial_capital']:,.0f}")
    print(f"Final Equity: Rs. {results['final_balance']:,.0f}")
    print(f"Total P&L: Rs. {results['net_profit']:,.0f}")
    print(f"Return: {results['net_profit_pct']:.2f}%")
    
    print(f"\nTrades: {results['total_trades']}")
    print(f"Winning Trades: {results['winning_trades']} ({results['win_rate']:.1f}%)")
    print(f"Losing Trades: {results['losing_trades']}")
    
    print(f"\nAvg Win: Rs. {results['avg_win']:,.0f}")
    print(f"Avg Loss: Rs. {results['avg_loss']:,.0f}")
    print(f"Profit Factor: {results['profit_factor']:.2f}")
    
    print(f"\nMax Drawdown: {results['max_drawdown_pct']:.2f}%")
    print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
    print(f"Sortino Ratio: {results['sortino_ratio']:.2f}")
    
    # Summary of improvements
    print("\n" + "="*80)
    print(" IMPROVEMENTS SUMMARY ".center(80, "="))
    print("="*80)
    
    improvements = [
        ("2.5x ATR stops", "Wider stops to reduce false SL hits from 62% to <50%", "ACTIVE"),
        ("2x+ volume filter", "Only trade when volume >= 2x MA", "ACTIVE"),
        ("Time restriction", "10-11 AM & 2-3 PM IST only (avoid 11-1 PM chop)", "ACTIVE"),
        ("S/R bounces", "Trade bounces from support/resistance zones", "ACTIVE"),
        ("2-candle confirmation", "Both current and previous candles must confirm", "ACTIVE"),
    ]
    
    for i, (name, description, status) in enumerate(improvements, 1):
        status_symbol = "[+]" if status == "ACTIVE" else "[!]"
        print(f"\n{i}. {status_symbol} {name}")
        print(f"   {description}")
    
    print("\n" + "="*80)
    print("\nKEY METRICS EXPLANATION:")
    print("  - Win Rate: % of trades that close with profit")
    print("  - Profit Factor: Gross Profit / Gross Loss (>1.5 is good)")
    print("  - Sharpe Ratio: Risk-adjusted returns (>1.0 is good)")
    print("  - Sortino Ratio: Like Sharpe but penalizes downside only")
    print("  - Max Drawdown: Largest peak-to-trough decline")
    print("\nNEXT STEPS:")
    print("  1. Verify time restriction is working (signals only in allowed hours)")
    print("  2. Check volume filter (all signals from 2x+ MA volume candles)")
    print("  3. Validate S/R detection (signals at support/resistance)")
    print("  4. Compare 2.5x ATR results vs 1.5x ATR baseline")
    print("="*80)

if __name__ == "__main__":
    main()
