import os
import sys
import pandas as pd
import yfinance as yf

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from backend.backtesting.ultra_high_quality_engine import UltraHighQualitySignalEngine
from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine
from backend.backtesting.test_with_yfinance import prepare_data_for_backtest

def main():
    symbol = "RELIANCE.NS"
    print(f"Downloading 60 days of 5m data for {symbol}...")
    ticker = yf.Ticker(symbol)
    data = ticker.history(period="60d", interval="5m")
    if data.empty:
        print("Failed to download data.")
        return
        
    df = prepare_data_for_backtest(data)
    
    print("\nRunning UltraHighQualitySignalEngine...")
    engine = UltraHighQualitySignalEngine(df)
    signals = engine.generate_signals()
    
    print(f"Generated {len(signals)} signals.")
    
    df['signal'] = None
    for s in signals:
        df.at[s['index'], 'signal'] = s['type']
        
    df['time'] = df['date']
    
    print("\nRunning Backtest...")
    backtest = AdvancedBacktestEngine(initial_capital=100000, seed=42)
    results = backtest.run_backtest(df, htf_trend="BULLISH", risk_per_trade=0.02, atr_sl=2.5, atr_tp=5.0)
    
    trades = results['trades']
    print(f"\nExecuted {len(trades)} trades:")
    
    df_trades = pd.DataFrame(trades)
    if not df_trades.empty:
        pd.set_option('display.max_columns', None)
        pd.set_option('display.width', 1000)
        print(df_trades[['entry_time', 'exit_time', 'type', 'entry_price_effective', 'exit_price_effective', 'exit_reason', 'gross_pnl', 'entry_commission', 'exit_commission', 'net_pnl']])
    else:
        print("No trades executed.")

if __name__ == '__main__':
    main()
