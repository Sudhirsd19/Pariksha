Backtesting helper scripts

Usage:

Run a quick historical backtest:

```bash
python -m backend.backtesting.run_backtest --symbol "^NSEI" --days 7
```

Run the parameter sweep (generates per-run metrics and trades CSVs):

```bash
python -m backend.backtesting.param_sweep --symbol "^NSEI" --days 7 --out ./backtest_outputs
```

Notes:
- Scripts use `yfinance` for historical intraday data. yfinance limits 1m data to ~7 days.
- For reproducible, high-quality backtests, provide local CSV or vendor data and adapt `fetch_yfinance_historical()`.
- Trade logs and metrics are written to the `--out` directory.
