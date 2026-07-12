import numpy as np
import pandas as pd

class StructureEngine:
    def __init__(self, lookback=20):
        self.lookback = lookback

    def detect_swings(self, df: pd.DataFrame):
        """Institutional swing detection without look-ahead bias."""
        df = df.copy()  # FIX: prevent mutation of caller's DataFrame
        df['swing_high'] = df['high'].rolling(window=self.lookback).max()
        df['swing_low']  = df['low'].rolling(window=self.lookback).min()
        return df

    def get_equilibrium(self, df):
        """Identify Premium and Discount zones based on the current dealing range."""
        recent_high = df['high'].rolling(50).max().iloc[-1]
        recent_low = df['low'].rolling(50).min().iloc[-1]
        mid = (recent_high + recent_low) / 2
        return {"premium": recent_high, "discount": recent_low, "eq": mid}

    def detect_liquidity_pools(self, df):
        """Identify Equal Highs (EQH) and Equal Lows (EQL) - Liquidity Targets."""
        # Check if recent highs are within 0.05% of each other
        highs = df['high'].iloc[-10:].values
        lows = df['low'].iloc[-10:].values
        
        eqh = any(abs(highs[i] - highs[j]) < (highs[i] * 0.0005) for i in range(len(highs)) for j in range(i+1, len(highs)))
        eql = any(abs(lows[i] - lows[j]) < (lows[i] * 0.0005) for i in range(len(lows)) for j in range(i+1, len(lows)))
        
        return eqh, eql

    def validate_order_block(self, df, index):
        """Validate if a candle is a true Institutional Order Block (OB).
        Must have: 1. Swept liquidity, 2. Created Displacement, 3. Left FVG.
        """
        if index < 5: return False
        
        # Displacement check (Body > 1.5x avg)
        body = abs(df['close'].iloc[index] - df['open'].iloc[index])
        avg_body = abs(df['close'] - df['open']).rolling(10).mean().iloc[index]
        displacement = body > (avg_body * 1.5)
        
        # Check if previous candle swept a swing
        # Use index-3 as the rolling base so the sweep candle (index-1) is NOT in the window
        swept = df['high'].iloc[index-1] > df['high'].rolling(10).max().iloc[index-3] or \
                df['low'].iloc[index-1] < df['low'].rolling(10).min().iloc[index-3]
                
        return displacement and swept

    def detect_fvg(self, df):
        """Identify Fair Value Gaps (FVG) in recent price action.
        Returns a dict with direction-aware flags so callers can match bias."""
        if len(df) < 3:
            return {'bullish_fvg': False, 'bearish_fvg': False, 'fvg_gap': False}

        c1 = df.iloc[-3]
        # c2 = df.iloc[-2]  # middle candle (not used in gap detection)
        c3 = df.iloc[-1]

        bullish_fvg = c1['high'] < c3['low']   # gap above c1's high
        bearish_fvg = c1['low']  > c3['high']  # gap below c1's low

        return {
            'bullish_fvg': bool(bullish_fvg),
            'bearish_fvg': bool(bearish_fvg),
            'fvg_gap':     bool(bullish_fvg or bearish_fvg),
        }

    def detect_choch(self, df: pd.DataFrame):
        """Detect Change of Character (CHoCH).

        In a downtrend (consecutive lower lows), a break ABOVE a recent swing
        high signals Bullish CHoCH.  In an uptrend (consecutive higher highs),
        a break BELOW a recent swing low signals Bearish CHoCH.

        Requires at least 3 swing points to confirm prior trend direction.
        Uses only data available up to the current candle (no look-ahead).
        """
        default = {'choch_bullish': False, 'choch_bearish': False, 'choch_level': 0.0}
        if df is None or len(df) < self.lookback + 5:
            return default

        swung = self.detect_swings(df)
        highs = swung['swing_high'].dropna().unique()
        lows = swung['swing_low'].dropna().unique()

        if len(highs) < 3 or len(lows) < 3:
            return default

        current_price = df['close'].iloc[-1]

        # --- Downtrend → Bullish CHoCH ---
        # Check at least 3 consecutive lower lows
        recent_lows = lows[-3:]
        downtrend = all(recent_lows[i] > recent_lows[i + 1] for i in range(len(recent_lows) - 1))
        bullish_choch = False
        choch_level = 0.0
        if downtrend:
            recent_swing_high = highs[-1]
            if current_price > recent_swing_high:
                bullish_choch = True
                choch_level = float(recent_swing_high)

        # --- Uptrend → Bearish CHoCH ---
        recent_highs = highs[-3:]
        uptrend = all(recent_highs[i] < recent_highs[i + 1] for i in range(len(recent_highs) - 1))
        bearish_choch = False
        if uptrend:
            recent_swing_low = lows[-1]
            if current_price < recent_swing_low:
                bearish_choch = True
                choch_level = float(recent_swing_low)

        return {
            'choch_bullish': bullish_choch,
            'choch_bearish': bearish_choch,
            'choch_level': choch_level,
        }

    def detect_mss(self, df: pd.DataFrame):
        """Detect Market Structure Shift (MSS).

        MSS = CHoCH + BOS confirmation in the new direction.
        First detects CHoCH, then verifies BOS follows in the same direction
        (i.e. price broke the prior structure level *and* continues).
        """
        default = {'mss_bullish': False, 'mss_bearish': False}
        if df is None or len(df) < self.lookback + 5:
            return default

        choch = self.detect_choch(df)

        # Need swing data for BOS confirmation
        swung = self.detect_swings(df)
        current_price = df['close'].iloc[-1]
        recent_swing_high = swung['swing_high'].iloc[-2]
        recent_swing_low = swung['swing_low'].iloc[-2]

        bos_bullish = current_price > recent_swing_high
        bos_bearish = current_price < recent_swing_low

        return {
            'mss_bullish': choch['choch_bullish'] and bos_bullish,
            'mss_bearish': choch['choch_bearish'] and bos_bearish,
        }

    def detect_breakout(self, df: pd.DataFrame, lookback: int = 20):
        """Detect momentum breakout of N-bar high / low.

        Conditions:
        - Price *closes* outside the lookback range (not just a wick).
        - Current candle body > 1.5× average body (momentum confirmation).
        """
        default = {'breakout_bullish': False, 'breakout_bearish': False, 'breakout_level': 0.0}
        if df is None or len(df) < lookback + 2:
            return default

        current = df.iloc[-1]
        body = abs(current['close'] - current['open'])
        avg_body = abs(df['close'] - df['open']).rolling(lookback).mean().iloc[-2]

        if avg_body != avg_body or avg_body == 0:  # NaN / zero guard
            return default

        has_momentum = body > (avg_body * 1.5)

        # N-bar high/low EXCLUDING the current candle
        n_bar_high = df['high'].iloc[-(lookback + 1):-1].max()
        n_bar_low = df['low'].iloc[-(lookback + 1):-1].min()

        bullish = has_momentum and current['close'] > n_bar_high
        bearish = has_momentum and current['close'] < n_bar_low

        level = 0.0
        if bullish:
            level = float(n_bar_high)
        elif bearish:
            level = float(n_bar_low)

        return {
            'breakout_bullish': bool(bullish),
            'breakout_bearish': bool(bearish),
            'breakout_level': level,
        }

    def detect_fake_breakout(self, df: pd.DataFrame, lookback: int = 20):
        """Detect fake breakout / liquidity trap.

        A candle breaks outside the N-bar range but:
        - Wick > body (rejection)
        - Close returns inside the range
        Checks the last 2 candles to catch traps that resolve on the next bar.
        """
        default = {'fake_breakout_up': False, 'fake_breakout_down': False}
        if df is None or len(df) < lookback + 3:
            return default

        n_bar_high = df['high'].iloc[-(lookback + 3):-2].max()
        n_bar_low = df['low'].iloc[-(lookback + 3):-2].min()

        fake_up = False
        fake_down = False

        # Scan the last 2 candles for trap patterns
        for offset in (-2, -1):
            candle = df.iloc[offset]
            body = abs(candle['close'] - candle['open'])
            upper_wick = candle['high'] - max(candle['close'], candle['open'])
            lower_wick = min(candle['close'], candle['open']) - candle['low']

            # Fake breakout UP: wick pierced above range, but closed inside
            if candle['high'] > n_bar_high and candle['close'] <= n_bar_high:
                if upper_wick > body:
                    fake_up = True

            # Fake breakout DOWN: wick pierced below range, but closed inside
            if candle['low'] < n_bar_low and candle['close'] >= n_bar_low:
                if lower_wick > body:
                    fake_down = True

        return {
            'fake_breakout_up': fake_up,
            'fake_breakout_down': fake_down,
        }

    def detect_pullback(self, df: pd.DataFrame):
        """Detect pullback / retest of a broken structure level.

        After BOS, price retraces towards the broken swing level (within 0.3%
        tolerance) while still respecting the new trend direction.
        """
        default = {'pullback_to_support': False, 'pullback_to_resistance': False, 'retest_level': 0.0}
        if df is None or len(df) < self.lookback + 5:
            return default

        swung = self.detect_swings(df)
        current_price = df['close'].iloc[-1]
        tolerance = 0.003  # 0.3 %

        # Use the second-to-last swing values (the "broken" level)
        recent_swing_high = swung['swing_high'].iloc[-2]
        recent_swing_low = swung['swing_low'].iloc[-2]

        # Check for prior BOS in the last few candles (not the very last candle)
        prior_close = df['close'].iloc[-3]
        bos_bullish_prior = prior_close > recent_swing_high
        bos_bearish_prior = prior_close < recent_swing_low

        pullback_support = False
        pullback_resistance = False
        retest_level = 0.0

        if bos_bullish_prior:
            # After bullish BOS, price retraces DOWN toward the broken high
            # and the current price is near that level (support retest)
            if abs(current_price - recent_swing_high) / recent_swing_high < tolerance:
                if current_price >= recent_swing_high:  # still above → trend intact
                    pullback_support = True
                    retest_level = float(recent_swing_high)

        if bos_bearish_prior:
            # After bearish BOS, price retraces UP toward the broken low
            if abs(current_price - recent_swing_low) / recent_swing_low < tolerance:
                if current_price <= recent_swing_low:  # still below → trend intact
                    pullback_resistance = True
                    retest_level = float(recent_swing_low)

        return {
            'pullback_to_support': pullback_support,
            'pullback_to_resistance': pullback_resistance,
            'retest_level': retest_level,
        }

    def analyze(self, df: pd.DataFrame):
        """Run full structure analysis — all SMC checks in one call."""
        df = self.detect_swings(df)
        eq_data = self.get_equilibrium(df)
        eqh, eql = self.detect_liquidity_pools(df)
        fvg_result = self.detect_fvg(df)   # now returns a dict
        
        current_price = df['close'].iloc[-1]
        in_discount = current_price < eq_data['eq']
        in_premium = current_price > eq_data['eq']
        
        # Simple BOS Detection
        bos = "None"
        recent_swing_high = df['swing_high'].iloc[-2]
        recent_swing_low = df['swing_low'].iloc[-2]
        
        if current_price > recent_swing_high:
            bos = "Bullish"
        elif current_price < recent_swing_low:
            bos = "Bearish"
        
        current_high = df['high'].iloc[-1]
        current_low = df['low'].iloc[-1]
        
        sweep_high = current_high > recent_swing_high and current_price <= recent_swing_high
        sweep_low = current_low < recent_swing_low and current_price >= recent_swing_low

        # --- New SMC detections ---
        choch_result = self.detect_choch(df)
        mss_result = self.detect_mss(df)
        breakout_result = self.detect_breakout(df)
        fake_breakout_result = self.detect_fake_breakout(df)
        pullback_result = self.detect_pullback(df)
        
        result = {
            # Existing keys (preserved)
            'bos': bos,
            'bos_bullish': bos == "Bullish",
            'bos_bearish': bos == "Bearish",
            'sweep_high': sweep_high,
            'sweep_low': sweep_low,
            'in_discount': in_discount,
            'in_premium': in_premium,
            'eqh': eqh,
            'eql': eql,
            'fvg_gap':     fvg_result['fvg_gap'],      # backward-compat key
            'bullish_fvg': fvg_result['bullish_fvg'],  # new directional keys
            'bearish_fvg': fvg_result['bearish_fvg'],
            'dealing_range': eq_data,
        }

        # Merge new SMC results
        result.update(choch_result)
        result.update(mss_result)
        result.update(breakout_result)
        result.update(fake_breakout_result)
        result.update(pullback_result)

        return result
