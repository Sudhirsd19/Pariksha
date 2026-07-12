import pandas as pd
import numpy as np

class CandlestickEngine:
    """Candlestick pattern recognition for trade confirmation."""

    def detect_engulfing(self, df: pd.DataFrame):
        """Detect bullish and bearish engulfing patterns on the last 2 candles with volume weighting."""
        default = {'bullish_engulfing': False, 'bearish_engulfing': False, 'engulfing_strength': 0.0}
        if df is None or len(df) < 2:
            return default

        prev = df.iloc[-2]
        curr = df.iloc[-1]

        prev_open, prev_close = prev['open'], prev['close']
        curr_open, curr_close = curr['open'], curr['close']

        prev_red = prev_close < prev_open
        prev_green = prev_close > prev_open
        curr_red = curr_close < curr_open
        curr_green = curr_close > curr_open

        bullish = (
            prev_red and curr_green and
            curr_close > prev_open and
            curr_open <= prev_close
        )

        bearish = (
            prev_green and curr_red and
            curr_close < prev_open and
            curr_open >= prev_close
        )

        strength = 0.0
        if bullish or bearish:
            prev_body = abs(prev_close - prev_open)
            curr_body = abs(curr_close - curr_open)
            prev_volume = prev.get('volume', 1)
            curr_volume = curr.get('volume', 1)
            if prev_volume <= 0: prev_volume = 1
            if prev_body <= 0: prev_body = 0.01

            volume_ratio = min(3.0, curr_volume / prev_volume)
            body_ratio = min(3.0, curr_body / prev_body)
            strength = min(1.0, (volume_ratio * 0.6 + body_ratio * 0.4) / 3.0)

        return {
            'bullish_engulfing': bool(bullish),
            'bearish_engulfing': bool(bearish),
            'engulfing_strength': float(strength)
        }

    def detect_doji(self, df: pd.DataFrame):
        """Detect doji candle (body < 10% of the total high-low range)."""
        default = {'doji': False, 'doji_type': 'none'}
        if df is None or len(df) < 1:
            return default

        candle = df.iloc[-1]
        body = abs(candle['close'] - candle['open'])
        total_range = candle['high'] - candle['low']

        if total_range == 0:
            return default

        is_doji = body < (total_range * 0.10)

        doji_type = 'none'
        if is_doji:
            upper_wick = candle['high'] - max(candle['close'], candle['open'])
            lower_wick = min(candle['close'], candle['open']) - candle['low']

            if upper_wick > (total_range * 0.6):
                doji_type = 'gravestone'   # Bearish at top
            elif lower_wick > (total_range * 0.6):
                doji_type = 'dragonfly'    # Bullish at bottom
            else:
                doji_type = 'standard'

        return {
            'doji': bool(is_doji),
            'doji_type': doji_type,
        }

    def detect_hammer(self, df: pd.DataFrame):
        """Detect hammer / inverted hammer candles."""
        default = {'hammer': False, 'inverted_hammer': False}
        if df is None or len(df) < 1:
            return default

        candle = df.iloc[-1]
        body = abs(candle['close'] - candle['open'])
        upper_wick = candle['high'] - max(candle['close'], candle['open'])
        lower_wick = min(candle['close'], candle['open']) - candle['low']
        total_range = candle['high'] - candle['low']

        if total_range == 0 or body == 0:
            return default

        hammer = lower_wick >= (2 * body) and upper_wick < body
        inverted = upper_wick >= (2 * body) and lower_wick < body

        return {
            'hammer': bool(hammer),
            'inverted_hammer': bool(inverted),
        }

    def detect_morning_star(self, df: pd.DataFrame):
        """Detect morning star pattern (3-candle bullish reversal)."""
        default = {'morning_star': False}
        if df is None or len(df) < 3:
            return default

        c1 = df.iloc[-3]
        c2 = df.iloc[-2]
        c3 = df.iloc[-1]

        # Calculate average body size for threshold
        bodies = abs(df['close'] - df['open'])
        avg_body = bodies.rolling(min(10, len(df))).mean().iloc[-1]
        if pd.isna(avg_body) or avg_body <= 0:
            avg_body = bodies.mean()

        c1_body = abs(c1['close'] - c1['open'])
        c2_body = abs(c2['close'] - c2['open'])
        c3_body = abs(c3['close'] - c3['open'])

        c1_red = c1['close'] < c1['open']
        c3_green = c3['close'] > c3['open']

        # Morning Star conditions
        is_morning_star = (
            c1_red and c3_green and
            c1_body > (avg_body * 1.2) and  # Candle 1: Large red
            c2_body < (avg_body * 0.5) and  # Candle 2: Small body / indecision
            c3_body > (avg_body * 0.8) and  # Candle 3: Significant green
            c3['close'] > ((c1['open'] + c1['close']) / 2)  # Closes above midpoint of C1
        )

        return {'morning_star': bool(is_morning_star)}

    def detect_evening_star(self, df: pd.DataFrame):
        """Detect evening star pattern (3-candle bearish reversal)."""
        default = {'evening_star': False}
        if df is None or len(df) < 3:
            return default

        c1 = df.iloc[-3]
        c2 = df.iloc[-2]
        c3 = df.iloc[-1]

        bodies = abs(df['close'] - df['open'])
        avg_body = bodies.rolling(min(10, len(df))).mean().iloc[-1]
        if pd.isna(avg_body) or avg_body <= 0:
            avg_body = bodies.mean()

        c1_body = abs(c1['close'] - c1['open'])
        c2_body = abs(c2['close'] - c2['open'])
        c3_body = abs(c3['close'] - c3['open'])

        c1_green = c1['close'] > c1['open']
        c3_red = c3['close'] < c3['open']

        is_evening_star = (
            c1_green and c3_red and
            c1_body > (avg_body * 1.2) and  # Candle 1: Large green
            c2_body < (avg_body * 0.5) and  # Candle 2: Small body
            c3_body > (avg_body * 0.8) and  # Candle 3: Large red
            c3['close'] < ((c1['open'] + c1['close']) / 2)  # Closes below midpoint of C1
        )

        return {'evening_star': bool(is_evening_star)}

    def analyze(self, df: pd.DataFrame):
        """Run all candlestick pattern checks."""
        result = {}
        result.update(self.detect_engulfing(df))
        result.update(self.detect_doji(df))
        result.update(self.detect_hammer(df))
        result.update(self.detect_morning_star(df))
        result.update(self.detect_evening_star(df))
        return result

candlestick_engine = CandlestickEngine()
