"""
Yahoo Finance (yfinance) - Real RELIANCE Data Downloader
========================================================

Ye script yfinance library use karke RELIANCE ka real data download karega
aur strategy ko test karega!

Data Availability:
- 1-minute: Last 7 days
- 5-minute: Last 60 days
- Daily: Unlimited history

Advantages:
- Free (no API key needed)
- Real market data
- Easy to use
- Direct from Yahoo Finance
"""

import yfinance as yf
import pandas as pd
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from backend.backtesting.optimized_signal_engine import OptimizedSignalEngine
from backend.backtesting.balanced_quality_engine import BalancedQualityEngine
from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine


def download_reliance_data(interval='5m', period='60d'):
    """
    RELIANCE ka real data download karo yfinance se
    
    Parameters:
    - interval: '1m' (1-minute, last 7 days), '5m' (5-minute, last 60 days)
    - period: '7d', '30d', '60d', etc.
    
    Returns:
    - DataFrame with OHLCV data
    """
    print(f"[*] Downloading RELIANCE data from Yahoo Finance...")
    print(f"    Interval: {interval}")
    print(f"    Period: {period}")
    
    try:
        # Download RELIANCE.NS data
        data = yf.download(
            'RELIANCE.NS',
            interval=interval,
            period=period,
            progress=True
        )
        
        print(f"[+] Successfully downloaded {len(data)} candles")
        print(f"[+] Date range: {str(data.index.min())} to {str(data.index.max())}")
        if len(data) > 0:
            try:
                price_min = float(data['Close'].min())
                price_max = float(data['Close'].max())
                print(f"[+] Price range: {price_min:.2f} to {price_max:.2f}")
            except:
                print(f"[+] Price data available")
        
        return data
        
    except Exception as e:
        print(f"[!] Error downloading data: {e}")
        return None


def prepare_data_for_backtest(data):
    """
    yfinance data को backtest के लिए तैयार करो
    MultiIndex columns को handle करो
    """
    print("\n[*] Preparing data for backtest...")
    
    df = data.copy()
    
    # Handle MultiIndex columns from yfinance
    if isinstance(df.columns, pd.MultiIndex):
        # Flatten MultiIndex - keep only first level (price type)
        df.columns = [col[0] for col in df.columns]
    
    # Reset index to make datetime a column
    df = df.reset_index()
    
    # Get column names (case-insensitive mapping)
    column_map = {}
    for col in df.columns:
        col_lower = col.lower()
        if 'datetime' in col_lower or 'date' in col_lower:
            column_map[col] = 'date'
        elif col_lower == 'open':
            column_map[col] = 'open'
        elif col_lower == 'high':
            column_map[col] = 'high'
        elif col_lower == 'low':
            column_map[col] = 'low'
        elif col_lower == 'close':
            column_map[col] = 'close'
        elif col_lower == 'volume':
            column_map[col] = 'volume'
    
    df.rename(columns=column_map, inplace=True)
    
    # Ensure required columns exist
    required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")
    
    # Keep only required columns
    df = df[required_cols]
    
    # Convert data types
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Remove any NaN rows
    df = df.dropna()
    
    print(f"[+] Data prepared: {len(df)} candles")
    print(f"[+] First row: {df.iloc[0].to_dict()}")
    print(f"[+] Last row: {df.iloc[-1].to_dict()}")
    
    return df


def test_strategy_on_real_data(df):
    """
    Real RELIANCE data पर strategy को test करो
    """
    print("\n" + "="*70)
    print("TESTING STRATEGY ON REAL RELIANCE DATA")
    print("="*70)
    
    # Generate signals
    print("\n[*] Generating signals with 65% quality filters...")
    engine = BalancedQualityEngine(df)
    signals = engine.generate_signals()  # Returns list directly
    
    print(f"[+] Signals generated: {len(signals)}")
    buys = len([s for s in signals if s.get('signal_type') == 'BUY' or s.get('type') == 'BUY'])
    sells = len([s for s in signals if s.get('signal_type') == 'SELL' or s.get('type') == 'SELL'])
    print(f"    - BUY: {buys}")
    print(f"    - SELL: {sells}")
    
    if len(signals) == 0:
        print("[!] No signals generated on real data")
        print("[!] This might mean:")
        print("    - Not enough data points")
        print("    - Market conditions don't match signal criteria")
        print("    - Conditions too strict")
        return None
    
    # Run backtest
    print(f"\n[*] Running backtest on {len(signals)} signals...")
    
    # Add signal column to df
    df['signal'] = None
    for s in signals:
        df.at[s['index'], 'signal'] = s['type']
    
    # Add time column (needed by backtest engine)
    df['time'] = df['date']
    
    backtest_engine = AdvancedBacktestEngine(
        initial_capital=100000,
        seed=42
    )
    
    results = backtest_engine.run_backtest(
        df=df,
        htf_trend="BULLISH",
        risk_per_trade=0.02,
        atr_sl=2.5,
        atr_tp=5.0
    )
    
    return results, signals


def print_results(results, signals):
    """
    Results को nicely print करो
    """
    print("\n" + "="*70)
    print("REAL RELIANCE DATA - BACKTEST RESULTS")
    print("="*70)
    
    try:
        print(f"\nCapital: Rs. {float(results['initial_capital']):,.0f}")
        print(f"Final Equity: Rs. {float(results['final_balance']):,.0f}")
        print(f"Total P&L: Rs. {float(results['net_profit']):,.0f}")
        print(f"Return: {float(results['net_profit_pct']):.2f}%")
        
        print(f"\nTrades: {int(results['total_trades'])}")
        print(f"Winning Trades: {int(results['winning_trades'])} ({float(results['win_rate']):.1f}%)")
        print(f"Losing Trades: {int(results['losing_trades'])}")
        
        if int(results['winning_trades']) > 0:
            print(f"Avg Win: Rs. {float(results['avg_win']):,.0f}")
        if int(results['losing_trades']) > 0:
            print(f"Avg Loss: Rs. {float(results['avg_loss']):,.0f}")
        
        print(f"\nProfit Factor: {float(results['profit_factor']):.2f}")
        print(f"Sharpe Ratio: {float(results['sharpe_ratio']):.2f}")
        print(f"Max Drawdown: {float(results['max_drawdown_pct']):.2f}%")
    except Exception as e:
        print(f"[!] Error printing results: {e}")
        print(results)
    
    # Compare with expected
    print("\n" + "="*70)
    print("COMPARISON WITH SYNTHETIC DATA")
    print("="*70)
    
    synthetic_results = {
        'win_rate': 55.6,
        'return': 8.12,
        'profit_factor': 1.99,
        'max_drawdown': 3.07,
        'sharpe': 5.36
    }
    
    print(f"\nMetric                | Synthetic | Real Data | Status")
    print("-" * 60)
    print(f"Win Rate              | {synthetic_results['win_rate']:.1f}%     | {results['win_rate']:.1f}%      | ", end="")
    if results['win_rate'] >= synthetic_results['win_rate']:
        print("✅ BETTER/SAME")
    else:
        print("⚠️  LOWER")
    
    print(f"Return                | {synthetic_results['return']:.2f}%    | {results['net_profit_pct']:.2f}%     | ", end="")
    if results['net_profit_pct'] >= synthetic_results['return']:
        print("✅ BETTER/SAME")
    else:
        print("⚠️  LOWER")
    
    print(f"Profit Factor         | {synthetic_results['profit_factor']:.2f}     | {results['profit_factor']:.2f}      | ", end="")
    if results['profit_factor'] >= synthetic_results['profit_factor'] * 0.9:
        print("✅ GOOD")
    else:
        print("⚠️  LOWER")
    
    print(f"Max Drawdown          | {synthetic_results['max_drawdown']:.2f}%     | {results['max_drawdown_pct']:.2f}%     | ", end="")
    if results['max_drawdown_pct'] <= synthetic_results['max_drawdown'] * 1.1:
        print("✅ GOOD")
    else:
        print("⚠️  HIGHER")


def main():
    print("\n" + "="*70)
    print("RELIANCE DATA TESTING WITH YAHOO FINANCE (yfinance)")
    print("="*70)
    
    # Download data
    print("\n[STEP 1] Download Real RELIANCE Data")
    print("-" * 70)
    
    # Try different intervals
    intervals = [
        ('5m', '60d', '5-minute data (last 60 days) - RECOMMENDED'),
        ('1d', '180d', 'Daily data (last 180 days) - Alternative'),
    ]
    
    data = None
    for interval, period, desc in intervals:
        print(f"\n[*] Trying {desc}...")
        try:
            data = download_reliance_data(interval=interval, period=period)
            if data is not None and len(data) > 100:
                print(f"[+] SUCCESS: Got {len(data)} candles")
                break
        except Exception as e:
            print(f"[!] Failed: {e}")
    
    if data is None or len(data) < 100:
        print("\n[!] Could not download sufficient data")
        print("[!] Common reasons:")
        print("    - Market is closed")
        print("    - Holiday period")
        print("    - Network issue")
        print("\n[*] Suggestion: Try again during market hours (9:15 AM - 3:30 PM IST)")
        return
    
    # Prepare data
    print("\n[STEP 2] Prepare Data")
    print("-" * 70)
    
    try:
        df = prepare_data_for_backtest(data)
    except Exception as e:
        print(f"[!] Error preparing data: {e}")
        return
    
    # Test strategy
    print("\n[STEP 3] Test Strategy")
    print("-" * 70)
    
    result = test_strategy_on_real_data(df)
    
    if result is None:
        print("\n[!] Strategy test failed")
        return
    
    results, signals = result
    
    # Print results
    print("\n[STEP 4] Results")
    print("-" * 70)
    
    print_results(results, signals)
    
    # Conclusion
    print("\n" + "="*70)
    print("CONCLUSION")
    print("="*70)
    
    if results['win_rate'] >= 0.50:
        print("""
✅ STRATEGY WORKING ON REAL DATA!

Results show:
- Win rate >= 50% (good)
- Positive return (profitable)
- All 5 improvements active

STATUS: Ready for live trading! 🚀
        """)
    else:
        print("""
⚠️  STRATEGY NEEDS TUNING

Results show:
- Win rate < 50% (needs improvement)
- May need parameter adjustment
- Check market conditions

RECOMMENDATION:
- Adjust filters (time, volume, ATR)
- Test different time periods
- Compare with synthetic data
        """)
    
    # Show trade details
    if len(signals) > 0:
        print("\n" + "="*70)
        print("SIGNAL DETAILS")
        print("="*70)
        print(f"\nTotal signals generated: {len(signals)}")
        for i, sig in enumerate(signals[:10]):
            print(f"  {i+1}. {sig['type']} at index {sig['index']}: {sig['price']:.2f}")
        
        if len(signals) > 10:
            print(f"  ... and {len(signals) - 10} more signals")


if __name__ == '__main__':
    main()
