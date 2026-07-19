"""
Battle-Tested Intraday Strategy Engine
=======================================
Version : 2.0 — Look-Ahead Safe
Audit   : BUG-03 fix applied 2026-07-19

Strategy logic uses ONLY current and historical candle data.
Signals are generated on bar[i] using bar[i] and prior bars only.
Order EXECUTION is at bar[i+1].open (handled by QuantumBacktestEngine).
"""
from __future__ import annotations

import pandas as pd
import numpy as np


class BattleTestedStrategyEngine:
    """
    Ultra-simple, proven intraday patterns:
    1. Entry : Price breaks above EMA21 after pullback (trend-following)
    2. Exit  : ATR-based SL/TP managed by QuantumBacktestEngine
    3. Hours : 9:30-11:00 & 13:30-15:00 IST
    """

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate signals based on EMA-pullback pattern."""
        df = df.copy()
        df["signal"] = None
        df["time"]   = pd.to_datetime(df["time"])
        df["hour"]   = df["time"].dt.hour
        df["minute"] = df["time"].dt.minute

        # Causal rolling indicators (backward windows — look-ahead safe)
        df["high_5"]     = df["high"].rolling(5, min_periods=1).max()
        df["low_5"]      = df["low"].rolling(5, min_periods=1).min()
        df["volume_sma"] = df["volume"].rolling(20).mean()
        df["resistance"] = df["high"].rolling(20).max()
        df["support"]    = df["low"].rolling(20).min()

        for i in range(100, len(df)):
            signal = self._evaluate_pullback_strategy(df, i)
            if signal:
                df.at[i, "signal"] = signal

        return df

    def _evaluate_pullback_strategy(self, df: pd.DataFrame, i: int) -> str | None:
        """
        PULLBACK STRATEGY — look-ahead safe.

        Uses only:
          - Current bar  : df.iloc[i]
          - Previous bar : df.iloc[i-1]
          - EWM on slice df.iloc[max(0,i-50):i+1]  (all past bars, causal)

        Signal fires on bar[i]; execution is at bar[i+1].open
        inside QuantumBacktestEngine.run().
        """
        row      = df.iloc[i]
        prev_row = df.iloc[i - 1]

        hour, minute = row["hour"], row["minute"]
        is_active = (
            (9  <= hour < 11)
            or (13 <= hour < 15)
            or (hour == 9  and minute >= 30)
            or (hour == 13 and minute >= 30)
        )
        if not is_active:
            return None

        # Causal EWM slice — includes current bar but NOT future bars
        history = df.iloc[max(0, i - 50) : i + 1]["close"]
        ema9    = history.ewm(span=9).mean().iloc[-1]
        ema21   = history.ewm(span=21).mean().iloc[-1]
        ema50   = history.ewm(span=50).mean().iloc[-1]

        if pd.isna(ema21) or pd.isna(ema9) or pd.isna(ema50):
            return None

        close      = row["close"]
        volume     = row.get("volume", 1)
        volume_sma = row.get("volume_sma", 1)

        # BULLISH: Close broke above EMA21 after pullback
        if (
            ema9 > ema21 > ema50                         # trend is up
            and prev_row["close"] <= ema21               # was at/below EMA21
            and close > ema21                            # broke above EMA21
            and volume > volume_sma * 0.8                # sufficient volume
        ):
            return "BUY"

        # BEARISH: Close broke below EMA21 after pullback
        if (
            ema9 < ema21 < ema50                         # trend is down
            and prev_row["close"] >= ema21               # was at/above EMA21
            and close < ema21                            # broke below EMA21
            and volume > volume_sma * 0.8
        ):
            return "SELL"

        return None


class SimpleFixedRulesEngine:
    """
    Channel breakout strategy — look-ahead safe.

    BUG-03 FIX (2026-07-19)
    =======================
    BEFORE (BUGGY):
        Used df.iloc[i+1]['high'] / df.iloc[i+1]['low'] to set a signal
        at bar[i].  This is direct look-ahead bias — the strategy could
        'see' tomorrow's candle to decide today's signal.

    AFTER (FIXED):
        Signal is set when the CURRENT bar's close breaks out of the
        20-bar historical high/low window (window = bars [i-20 : i],
        strictly excluding bar[i] itself).
        Execution happens at bar[i+1].open inside the backtesting engine.

    Why this is correct:
        1. Window uses only PAST candles (i-20 to i-1).
        2. Breakout is detected on bar[i]'s CLOSE — fully available.
        3. No future bar data (bar[i+1], shift(-1), etc.) is accessed.
        4. The engine fills the order at the NEXT candle's open, so there
           is no execution bias either.
    """

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Channel-breakout signals using strictly causal data."""
        df = df.copy()
        df["signal"] = None

        for i in range(50, len(df)):
            # Historical window: last 20 bars BEFORE bar[i] (excludes current)
            # Strictly causal — no current or future bar included in the window.
            hist_window = df.iloc[max(0, i - 20) : i]  # excludes i
            if len(hist_window) < 5:
                continue

            hist_high = hist_window["high"].max()
            hist_low  = hist_window["low"].min()

            # Current bar data (fully known at bar[i] close)
            curr_close = df.iloc[i]["close"]
            curr_high  = df.iloc[i]["high"]
            curr_low   = df.iloc[i]["low"]

            # Breakout: current bar closes ABOVE historical high
            # => Bullish momentum; signal to BUY at next bar's open
            if curr_close > hist_high * 1.0005:    # 0.05 % break required
                df.at[i, "signal"] = "BUY"

            # Breakdown: current bar closes BELOW historical low
            # => Bearish momentum; signal to SELL at next bar's open
            elif curr_close < hist_low * 0.9995:   # 0.05 % break required
                df.at[i, "signal"] = "SELL"

        return df
