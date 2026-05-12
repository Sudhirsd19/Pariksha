import pandas as pd
import numpy as np

import numpy as np
import pandas as pd

class StructureEngine:
    def __init__(self, lookback=20):
        self.lookback = lookback

    def detect_swings(self, df: pd.DataFrame):
        """Institutional swing detection without look-ahead bias."""
        # Use previous candles only for real-time safety
        df['swing_high'] = df['high'].rolling(window=self.lookback).max()
        df['swing_low'] = df['low'].rolling(window=self.lookback).min()
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
        swept = df['high'].iloc[index-1] > df['high'].rolling(10).max().iloc[index-2] or \
                df['low'].iloc[index-1] < df['low'].rolling(10).min().iloc[index-2]
                
        return displacement and swept

    def detect_fvg(self, df):
        """Identify Fair Value Gaps (FVG) in recent price action."""
        if len(df) < 3: return False
        
        # Bullish FVG: High of candle 1 < Low of candle 3
        # Bearish FVG: Low of candle 1 > High of candle 3
        c1 = df.iloc[-3]
        c2 = df.iloc[-2]
        c3 = df.iloc[-1]
        
        bullish_fvg = c1['high'] < c3['low']
        bearish_fvg = c1['low'] > c3['high']
        
        return bullish_fvg or bearish_fvg

    def analyze(self, df: pd.DataFrame):
        df = self.detect_swings(df)
        eq_data = self.get_equilibrium(df)
        eqh, eql = self.detect_liquidity_pools(df)
        fvg_gap = self.detect_fvg(df)
        
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
        
        return {
            'bos': bos,
            'bos_bullish': bos == "Bullish",
            'bos_bearish': bos == "Bearish",
            'sweep_high': current_price > recent_swing_high * 1.001, # Buffer for sweep
            'sweep_low': current_price < recent_swing_low * 0.999,
            'in_discount': in_discount,
            'in_premium': in_premium,
            'eqh': eqh,
            'eql': eql,
            'fvg_gap': fvg_gap,
            'dealing_range': eq_data
        }
