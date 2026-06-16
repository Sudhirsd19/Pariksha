"""
Advanced Backtest Runner v2.0
- Fetches 1-minute data (or 5-minute fallback)
- Generates high-quality signals
- Optimizes parameters
- Runs walk-forward validation
- Exports detailed reports
"""
import asyncio
import os
import sys
import pandas as pd
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.execution.broker_api import AngelOneBroker
from backend.utils.token_manager import token_manager
from backend.backtesting.angel_backtest_engine import fetch_long_history
from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine
from backend.backtesting.param_optimizer import ParameterOptimizer
from backend.backtesting.premium_signal_engine import PremiumSignalEngine

async def fetch_minute_data(smart_api, token, interval="ONE_MINUTE", total_days=180, exchange="NSE"):
    """
    Fetch 1-minute data (with fallback to 5-minute)
    """
    df_list = []
    end_date = pd.Timestamp.now(tz='Asia/Kolkata')
    chunk_size_days = 7  # Smaller chunks for 1-minute data
    remaining_days = total_days
    
    print(f"\nAttempting to fetch {total_days} days of {interval} data for token {token}...")
    
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
                chunk_df = pd.DataFrame(data['data'], columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                if not chunk_df.empty:
                    df_list.append(chunk_df)
                    print(f"  [+] Fetched {len(chunk_df)} candles from {start_date.date()}")
        except Exception as e:
            print(f"  ! Could not fetch {interval} data from {start_date.date()}: {str(e)[:50]}")
            pass
        
        end_date = start_date
        remaining_days -= days_to_fetch
        await asyncio.sleep(0.4)
    
    if not df_list:
        return None
    
    # Concatenate and clean
    full_df = pd.concat(df_list, ignore_index=True)
    full_df['time'] = pd.to_datetime(full_df['time'])
    full_df.sort_values('time', inplace=True)
    full_df.drop_duplicates(subset=['time'], keep='last', inplace=True)
    full_df.reset_index(drop=True, inplace=True)
    
    print(f"[+] Successfully fetched {len(full_df)} {interval} candles over {total_days} days")
    return full_df

async def main():
    print("\n" + "="*80)
    print(" ADVANCED INTRADAY BACKTESTER v2.0 ".center(80, "="))
    print("="*80)
    print("Improvements:")
    print("  1. Realistic slippage & commission modeling")
    print("  2. Risk management (position-sizing, stop-loss, daily loss limit)")
    print("  3. 1-minute data for better execution accuracy")
    print("  4. Parameter optimization + walk-forward validation")
    print("  5. Advanced metrics (Sharpe, Sortino, Profit Factor, Expectancy)")
    print("="*80 + "\n")
    
    # Initialize broker
    broker = AngelOneBroker()
    
    try:
        broker.login()
        if not broker.session:
            print("[!] Failed to establish Angel One session")
            return
        print("[+] Logged into Angel One successfully\n")
    except Exception as e:
        print(f"[!] Login failed: {e}")
        return
    
    # Fetch data
    symbol = "RELIANCE"
    stock_info = token_manager.get_stock_info(symbol)
    if not stock_info:
        print(f"[!] Could not find token for {symbol}")
        return
    
    token = stock_info["token"]
    print(f"Fetching data for {symbol} (Token: {token})...\n")
    
    # Try 1-minute first, fallback to 5-minute
    df = await fetch_minute_data(broker.smart_api, token, interval="ONE_MINUTE", total_days=180)
    
    if df is None or len(df) < 1000:
        print("\n[*] Insufficient 1-minute data, falling back to 5-minute...")
        df = await fetch_long_history(broker.smart_api, token, interval="FIVE_MINUTE", total_days=180)
    
    if df is None or df.empty:
        print("[!] Failed to fetch historical data")
        return
    
    # Generate signals with PREMIUM engine - ultra-selective for profitability
    print("\n" + "="*80)
    print("GENERATING PREMIUM SIGNALS (Ultra-Selective for 70%+ Win Rate)")
    print("="*80)
    signal_engine = PremiumSignalEngine()
    df = signal_engine.generate_signals(df)
    signal_count = (df['signal'].notna()).sum()
    print(f"[+] Generated {signal_count} signals from {len(df)} candles")
    print(f"    Signal density: {signal_count/len(df)*100:.2f}%\n")
    
    # Parameter optimization
    print("="*80)
    print("PARAMETER OPTIMIZATION (Profitability Focus)")
    print("="*80)
    
    optimizer = ParameterOptimizer(df, train_ratio=0.7)
    results_df = optimizer.optimize_parameters(
        risk_per_trade_values=[0.01, 0.015],
        atr_sl_values=[2.0, 2.5],
        atr_tp_values=[4.0, 5.0]
    )
    
    # Get best parameters
    best_result = results_df.iloc[0]
    best_params = {
        'risk_pct': best_result['risk_pct'],
        'atr_sl': best_result['atr_sl'],
        'atr_tp': best_result['atr_tp']
    }
    
    print(f"\n[+] Best parameters (Sharpe-optimized):")
    print(f"  Risk per trade: {best_result['risk_pct']:.1f}%")
    print(f"  Stop Loss: {best_result['atr_sl']}x ATR")
    print(f"  Take Profit: {best_result['atr_tp']}x ATR")
    print(f"  Train Sharpe: {best_result['train_sharpe']:.2f}")
    print(f"  Train Win Rate: {best_result['train_win_rate']:.1f}%")
    print(f"  Train Trades: {int(best_result['total_trades'])}\n")
    
    # Walk-forward validation
    wf_results = optimizer.walk_forward_test(best_params, window_size=500)
    
    # Final test on full data
    print("\n" + "="*80)
    print("FINAL BACKTEST (FULL DATA WITH BEST PARAMETERS)")
    print("="*80)
    
    engine = AdvancedBacktestEngine(initial_capital=100000, seed=42)
    final_report = engine.run_backtest(
        df,
        risk_per_trade=best_params['risk_pct'] / 100,
        atr_sl=best_params['atr_sl'],
        atr_tp=best_params['atr_tp']
    )
    
    # Print final report
    print("\n" + "="*80)
    print("FINAL BACKTEST REPORT")
    print("="*80)
    print(f"\nCapital:")
    print(f"  Initial:      Rs. {final_report['initial_capital']:>12,.0f}")
    print(f"  Final:        Rs. {final_report['final_balance']:>12,.0f}")
    print(f"  Net Profit:   Rs. {final_report['net_profit']:>12,.0f} ({final_report['net_profit_pct']:>6.2f}%)")
    
    print(f"\nTrades:")
    print(f"  Total:        {final_report['total_trades']:>12d}")
    print(f"  Winning:      {final_report['winning_trades']:>12d}")
    print(f"  Losing:       {final_report['losing_trades']:>12d}")
    print(f"  Win Rate:     {final_report['win_rate']:>12.1f}%")
    
    print(f"\nPnL Analysis:")
    print(f"  Avg Win:      Rs. {final_report['avg_win']:>12,.0f}")
    print(f"  Avg Loss:     Rs. {final_report['avg_loss']:>12,.0f}")
    print(f"  Profit Factor: {final_report['profit_factor']:>15.2f}x")
    print(f"  Expectancy:   Rs. {final_report['expectancy']:>12,.0f}")
    
    print(f"\nRisk Metrics:")
    print(f"  Max Drawdown: {final_report['max_drawdown_pct']:>12.2f}%")
    print(f"  Recovery Fac: {final_report['recovery_factor']:>15.2f}x")
    print(f"  Longest Win:  {final_report['longest_win_streak']:>12d}")
    print(f"  Longest Loss: {final_report['longest_loss_streak']:>12d}")
    
    print(f"\nRisk-Adjusted Returns:")
    print(f"  Sharpe Ratio: {final_report['sharpe_ratio']:>15.2f}")
    print(f"  Sortino Ratio: {final_report['sortino_ratio']:>14.2f}")
    
    print(f"\nCosts:")
    print(f"  Total Commission: Rs. {final_report['total_commission']:>8,.0f}")
    
    print("\n" + "="*80)
    
    # Export results
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_dir = "backend/backtesting/reports"
    os.makedirs(export_dir, exist_ok=True)
    
    # Export trade log
    trade_log_path = f"{export_dir}/trade_log_{timestamp}.csv"
    engine.export_trade_log(trade_log_path)
    print(f"\n[+] Trade log exported: {trade_log_path}")
    
    # Export parameter results
    param_results_path = f"{export_dir}/param_optimization_{timestamp}.csv"
    results_df.to_csv(param_results_path, index=False)
    print(f"[+] Parameter optimization results: {param_results_path}")
    
    # Export walk-forward results
    wf_results_path = f"{export_dir}/walk_forward_{timestamp}.csv"
    wf_results.to_csv(wf_results_path, index=False)
    print(f"[+] Walk-forward validation results: {wf_results_path}")
    
    # Summary
    print("\n" + "="*80)
    print("BACKTEST SUMMARY")
    print("="*80)
    
    if final_report['win_rate'] >= 70:
        print(f"\n[SUCCESS] TARGET ACHIEVED! Win rate: {final_report['win_rate']:.1f}% (>=70%)")
    else:
        improvement_needed = 70 - final_report['win_rate']
        print(f"\n[*] Win rate: {final_report['win_rate']:.1f}% (need +{improvement_needed:.1f}% for 70%)")
        print("Recommendations for improvement:")
        print(f"  • Tighten entry filters (current: {signal_count} signals)")
        print(f"  • Increase Stop Loss to {best_params['atr_sl']+0.5}x ATR (less false SLs)")
        print(f"  • Reduce position size ({best_params['risk_pct']:.1f}% → {best_params['risk_pct']-0.5:.1f}%)")
        print(f"  • Add trend strength filter (only trade when ADX > 25)")
    
    print(f"\nProfit Factor: {final_report['profit_factor']:.2f}x (target: >1.5x)")
    print(f"Sharpe Ratio: {final_report['sharpe_ratio']:.2f} (target: >1.0)")
    print(f"Recovery Factor: {final_report['recovery_factor']:.2f}x (target: >2.0x)")
    
    print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    asyncio.run(main())
