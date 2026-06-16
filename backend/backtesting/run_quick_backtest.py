from backend.backtesting.run_backtest import run_historical_backtest

if __name__ == '__main__':
    run_historical_backtest('^NSEI', days=3)
