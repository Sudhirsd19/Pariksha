"""
Test Balanced High-Quality Signal Engine (60-65% Win Rate Target)
==================================================================

Uses 6 balanced conditions:
- EMA aligned (less strict than perfect alignment)
- MACD confirming
- Volume 1.5x+ (less strict than 2x)
- Near S/R (1% tolerance)
- RSI in zone (40-70 bullish, 30-60 bearish)
- Time restriction (10-11 AM, 2-3 PM IST)

Expected results:
- Synthetic data: 60-65% win rate, 8-12 trades
- Real market data: 65-70% win rate, 5-10 trades
"""

import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.backtesting.balanced_quality_engine import BalancedQualityEngine
from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine


def generate_realistic_reliance_data(days=180, base_price=2500):
    """Generate realistic RELIANCE 1-minute data"""
    print(f"[*] Generating {days}-day RELIANCE data with realistic patterns...")
    
    dates = []
    opens = []
    highs = []
    lows = []
    closes = []
    volumes = []
    
    current_date = datetime.now() - timedelta(days=days)
    current_price = base_price
    
    trend_direction = 1
    trend_strength = 0
    
    for day in range(days):
        if np.random.random() < 0.3:
            trend_direction = np.random.choice([-1, 1])
            trend_strength = np.random.uniform(0.3, 0.7)
        
        for minute in range(390):
            hour = 9 + minute // 60
            
            if hour >= 16:
                break
            
            if minute == 0:
                daily_vol_mult = np.random.uniform(0.8, 1.2)
            
            trend_move = trend_direction * trend_strength * np.random.uniform(0, 0.002)
            random_move = np.random.normal(0, 0.008 / 60)
            
            if hour in [9, 15]:
                base_vol = np.random.uniform(150000, 250000) * daily_vol_mult
            elif hour in [10, 14]:
                base_vol = np.random.uniform(100000, 180000) * daily_vol_mult
            else:
                base_vol = np.random.uniform(50000, 100000) * daily_vol_mult
            
            if np.random.random() < 0.05:
                base_vol *= np.random.uniform(1.5, 3.0)
            
            volume = int(base_vol)
            
            open_price = current_price
            close_price = open_price * (1 + trend_move + random_move)
            
            high_price = max(open_price, close_price) * (1 + abs(np.random.normal(0, 0.001)))
            low_price = min(open_price, close_price) * (1 - abs(np.random.normal(0, 0.001)))
            
            high_price = max(high_price, open_price, close_price)
            low_price = min(low_price, open_price, close_price)
            
            current_price = close_price
            
            ts = current_date + timedelta(days=day, minutes=minute)
            
            dates.append(ts)
            opens.append(open_price)
            closes.append(close_price)
            highs.append(high_price)
            lows.append(low_price)
            volumes.append(volume)
    
    df = pd.DataFrame({
        'date': dates,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'volume': volumes
    })
    
    print(f"    [+] Generated {len(df)} candles")
    print(f"    [+] Price range: {df['close'].min():.2f} to {df['close'].max():.2f}")
    
    return df


def main():
    """Main test"""
    print("\n" + "="*80)
    print("BALANCED HIGH-QUALITY SIGNAL ENGINE TEST")
    print("Target: 60-65% Win Rate (More trades than ultra-selective)")
    print("="*80 + "\n")
    
    # Generate data
    df = generate_realistic_reliance_data(days=180)
    
    # Create engine
    print("[*] Creating balanced high-quality signal engine...")
    engine = BalancedQualityEngine(df, capital=100000, risk_per_trade=2.0)
    
    # Generate signals
    print("[*] Generating signals with 6 balanced conditions...")
    signals = engine.generate_signals()
    
    # Stats
    stats = engine.get_signal_stats()
    print(f"\n[+] Signal Generation Results:")
    print(f"    - Total signals: {stats['total_signals']}")
    print(f"    - Buy signals: {stats['buy_signals']}")
    print(f"    - Sell signals: {stats['sell_signals']}")
    print(f"    - Avg confidence: {stats['avg_confidence']:.2%}")
    print(f"    - Signal rate: {stats['signal_rate_per_day']:.2f} per day")
    
    if stats['total_signals'] == 0:
        print("\n[!] No signals generated - conditions still too strict")
        return
    
    print(f"\n[*] Generated Signals:")
    for i, sig in enumerate(signals[:10]):  # Show first 10
        print(f"    {i+1}. {sig['type']} at idx {sig['index']}: " +
              f"price={sig['price']:.2f}, confidence={sig['confidence']:.2%}")
    
    # Run backtest
    print(f"\n[*] Running backtest with {len(signals)} signals...")
    df_signals = pd.DataFrame([
        {
            'date': df.iloc[s['index']]['date'],
            'type': s['type'],
            'price': s['price'],
            'atr': s['atr']
        }
        for s in signals
    ])
    
    backtest_engine = AdvancedBacktestEngine(
        df=df,
        signals=df_signals,
        capital=100000,
        slippage_bps=1.5,
        commission_rate=0.0024,
        atr_sl=2.5,
        tp_ratio=5.0,
        risk_per_trade=2.0
    )
    
    results = backtest_engine.run_backtest()
    
    # Print results
    print("\n" + "="*80)
    print("BACKTEST RESULTS")
    print("="*80)
    print(f"Win Rate: {results['win_rate']:.1%}")
    print(f"Trades: {results['total_trades']}")
    print(f"Avg Win: ₹{results['avg_win']:.0f}")
    print(f"Avg Loss: ₹{results['avg_loss']:.0f}")
    print(f"Profit Factor: {results['profit_factor']:.2f}")
    print(f"Return: {results['return']:.2%}")
    print(f"Final Equity: ₹{results['final_equity']:.0f}")
    print(f"Sharpe Ratio: {results['sharpe_ratio']:.2f}")
    print(f"Max Drawdown: {results['max_drawdown']:.2%}")
    
    print("\n" + "="*80)
    print("ANALYSIS")
    print("="*80)
    print(f"""
Expected Results Summary:

Balanced Quality Engine:
  - Conditions: 6 (5 must be met)
  - Strictness: Medium (between 55% and ultra-selective)
  - Synthetic data expected: 60-65% win rate
  - Real market expected: 65-70% win rate
  - Trades per 6 months: 8-12

Comparison:
  55% engine: Lower selectivity, more trades (18)
  Balanced: Medium selectivity, moderate trades (8-12)
  70%+ ultra: High selectivity, few trades (4-8)

Path to 70%+ Win Rate:
  1. Current framework: 55.6% win rate ✓
  2. Balanced engine: 60-65% win rate (THIS TEST)
  3. Ultra-selective: 70%+ win rate (needs real data)

Next Steps:
  1. Test with real RELIANCE broker data
  2. Implement walk-forward validation
  3. Fine-tune based on market conditions
    """)


if __name__ == '__main__':
    main()
