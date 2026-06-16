import os
import argparse
from datetime import datetime
from backend.backtesting.run_backtest import fetch_yfinance_historical
from backend.backtesting.backtest_engine import BacktestEngine
from backend.engines.signal_engine import SignalEngine


def run_param_sweep(symbol, days, out_dir, atr_sl_list, atr_tp_list, qty_list):
    os.makedirs(out_dir, exist_ok=True)

    df_5m, df_15m, df_1h = fetch_yfinance_historical(symbol, days)
    if df_5m is None:
        print("Failed to fetch historical data.")
        return

    print(f"Running parameter sweep for {symbol} on {len(df_5m)} 5m candles")

    results = []
    run_id = 0
    for atr_sl in atr_sl_list:
        for atr_tp in atr_tp_list:
            for qty in qty_list:
                run_id += 1
                engine = BacktestEngine(initial_capital=100000)
                signal_engine = SignalEngine()

                # Inject ATR multipliers into signal engine by monkey patching for this run
                # (simpler than changing core API) — we pass via kwargs in generate_signal
                trades_folder = os.path.join(out_dir, f"run_{run_id}")
                os.makedirs(trades_folder, exist_ok=True)

                open_trade = None

                for i in range(50, len(df_5m)):
                    current_time = df_5m.iloc[i]['time']
                    window_5m = df_5m.iloc[:i+1].copy()
                    window_15m = df_15m[df_15m['time'] <= current_time].copy()
                    window_1h = df_1h[df_1h['time'] <= current_time].copy()

                    if len(window_1h) < 10 or len(window_15m) < 10:
                        continue

                    current_price = window_5m.iloc[-1]['close']

                    if open_trade:
                        if open_trade['side'] == "BUY":
                            if current_price >= open_trade['tp'] or current_price <= open_trade['sl']:
                                engine.execute_trade(open_trade['entry'], current_price, qty=qty, side="BUY")
                                open_trade = None
                        elif open_trade['side'] == "SELL":
                            if current_price <= open_trade['tp'] or current_price >= open_trade['sl']:
                                engine.execute_trade(open_trade['entry'], current_price, qty=qty, side="SELL")
                                open_trade = None
                        continue

                    # Use backtest_override to be permissive
                    signal_data = signal_engine.generate_signal(window_5m, window_5m, window_15m, window_1h, symbol=symbol, ltp=current_price, backtest_override=True)

                    if signal_data and signal_data.get("signal") in ["BUY", "SELL"]:
                        side = signal_data["signal"]
                        entry = current_price
                        # Apply ATR multipliers to compute SL/TP locally
                        atr = signal_data.get('atr', 30.0)
                        sl = entry - (atr * atr_sl) if side == 'BUY' else entry + (atr * atr_sl)
                        tp = entry + (atr * atr_tp) if side == 'BUY' else entry - (atr * atr_tp)

                        open_trade = {
                            'side': side,
                            'entry': entry,
                            'sl': sl,
                            'tp': tp,
                            'time': current_time
                        }

                metrics = engine.get_metrics()
                run_name = f"run_{run_id}_sl{atr_sl}_tp{atr_tp}_q{qty}"
                metrics_file = os.path.join(trades_folder, f"{run_name}_metrics.csv")
                trades_file = os.path.join(trades_folder, f"{run_name}_trades.csv")
                engine.export_metrics_csv(metrics_file)
                engine.export_trades_csv(trades_file)

                print(f"Completed {run_name}")
                results.append({
                    'run': run_name,
                    'metrics_file': metrics_file,
                    'trades_file': trades_file,
                })

    # Summary
    summary_file = os.path.join(out_dir, f"summary_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv")
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write('run,metrics_file,trades_file\n')
        for r in results:
            f.write(f"{r['run']},{r['metrics_file']},{r['trades_file']}\n")

    print(f"Parameter sweep complete. Summary: {summary_file}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Parameter sweep for backtests')
    parser.add_argument('--symbol', default='^NSEI')
    parser.add_argument('--days', type=int, default=7)
    parser.add_argument('--out', default='backtest_runs')
    args = parser.parse_args()

    run_param_sweep(args.symbol, args.days, args.out, atr_sl_list=[1.0, 1.5], atr_tp_list=[2.0, 3.0], qty_list=[25, 50])
