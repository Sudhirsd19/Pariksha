import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)) + "/..")

from execution.broker_api import AngelOneBroker
from utils.historical_data import fetch_historical_data
from indicators.technical_indicators import TechnicalIndicators
from engines.trend_engine import TrendEngine
from engines.momentum_engine import MomentumEngine
from engines.structure_engine import StructureEngine
from signal_engine.signal_engine import SignalEngine
from filters.filters import SessionFilter

def deep_diagnostic():
    print("=== DEEP SIGNAL DIAGNOSTIC ===\n")
    broker = AngelOneBroker()
    if not broker.login():
        print("Login FAILED"); return

    # Use FUTURES token for proper data (NFO exchange)
    tokens = {
        "NIFTY": {"token": "66071", "exchange": "NFO", "symbol": "NIFTY26MAY26FUT"},
        "BANKNIFTY": {"token": "66068", "exchange": "NFO", "symbol": "BANKNIFTY26MAY26FUT"},
    }

    trend_engine = TrendEngine()
    momentum_engine = MomentumEngine()

    for name, info in tokens.items():
        token = info['token']
        print(f"\n--- {name} ({info['symbol']}) ---")

        df_1m  = fetch_historical_data(broker.smart_api, token, interval="ONE_MINUTE",     days=2,  exchange="NFO")
        df_5m  = fetch_historical_data(broker.smart_api, token, interval="FIVE_MINUTE",    days=5,  exchange="NFO")
        df_15m = fetch_historical_data(broker.smart_api, token, interval="FIFTEEN_MINUTE", days=10, exchange="NFO")
        df_1h  = fetch_historical_data(broker.smart_api, token, interval="ONE_HOUR",       days=30, exchange="NFO")

        missing = [t for t, d in [("1m", df_1m), ("5m", df_5m), ("15m", df_15m), ("1h", df_1h)] if d is None or d.empty]
        if missing:
            print(f"MISSING DATA for: {missing}"); continue

        df_1m  = TechnicalIndicators.apply_all(df_1m)
        df_5m  = TechnicalIndicators.apply_all(df_5m)
        df_15m = TechnicalIndicators.apply_all(df_15m)
        df_1h  = TechnicalIndicators.apply_all(df_1h)

        # Print detailed values
        for label, df in [("1m", df_1m), ("5m", df_5m), ("15m", df_15m), ("1h", df_1h)]:
            row = df.iloc[-1]
            trend = trend_engine.analyze(df)
            print(f"\n  [{label}] Trend={trend} | Close={row['close']:.2f} | "
                  f"EMA20={row.get('EMA_20', 0):.2f} | EMA50={row.get('EMA_50', 0):.2f} | "
                  f"Supertrend={row.get('Supertrend', '?')} | ADX={row.get('ADX', 0):.2f} | "
                  f"RSI={row.get('RSI', 0):.2f}")

        # Session check
        in_session = SessionFilter.is_within_session()
        print(f"\n  Session Active: {in_session}")
        SessionFilter.is_within_session = lambda: True  # Force open for test

        signal = SignalEngine().generate_signal(df_1m, df_5m, df_15m, df_1h)
        print(f"  SIGNAL: {signal['signal']} | Reason: {signal.get('reason', '')}")
        SessionFilter.is_within_session = lambda: in_session

    print("\n=== DONE ===")

if __name__ == "__main__":
    deep_diagnostic()
