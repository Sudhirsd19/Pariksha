import pandas as pd
import numpy as np

class SignalEngine:
    def __init__(self):
        self.min_score = 6

    def detect_market_phase(self, df):
        """Classify market phase: Trending, Expansion, Consolidation."""
        atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
        atr_avg = atr.rolling(50).mean().iloc[-1]
        current_atr = atr.iloc[-1]
        
        # Consolidation check: Narrow ATR + overlapping candles
        if current_atr < (atr_avg * 0.7):
            return "CONSOLIDATION"
        
        # Trending vs Expansion
        # Expansion is sudden move, Trending is sustained
        sma20 = df['close'].rolling(20).mean().iloc[-1]
        sma50 = df['close'].rolling(50).mean().iloc[-1]
        
        if abs(df['close'].iloc[-1] - sma20) > (current_atr * 2):
            return "EXPANSION"
        elif (df['close'].iloc[-1] > sma20 > sma50) or (df['close'].iloc[-1] < sma20 < sma50):
            return "TRENDING"
        
        return "NEUTRAL"

    def get_daily_bias(self, current_price, daily_open, pdh, pdl):
        """Calculate Daily Bias based on Open, PDH, and PDL."""
        bias = "NEUTRAL"
        if current_price > daily_open and current_price > pdh:
            bias = "BULLISH"
        elif current_price < daily_open and current_price < pdl:
            bias = "BEARISH"
        return bias

    def evaluate(self, htf_df, mtf_df, structure_data, daily_data, session_info):
        """Evaluate full confluence with advanced filters."""
        last_close = mtf_df['close'].iloc[-1]
        phase = self.detect_market_phase(mtf_df)
        
        # Daily Bias Alignment
        bias = self.get_daily_bias(
            last_close, 
            daily_data['open'], 
            daily_data['pdh'], 
            daily_data['pdl']
        )
        
        # Score Calculation
        score = 0
        if bias == "BULLISH" and structure_data['bos_bullish']: score += 3
        if bias == "BEARISH" and structure_data['bos_bearish']: score += 3
        if structure_data['sweep_high'] or structure_data['sweep_low']: score += 2
        if phase in ["TRENDING", "EXPANSION"]: score += 2
        if session_info['is_valid']: score += 1
        
        # Volume Validation
        vol_avg = mtf_df['volume'].rolling(20).mean().iloc[-1]
        if mtf_df['volume'].iloc[-1] > (vol_avg * 1.5): score += 2
        
        side = None
        if score >= self.min_score and phase != "CONSOLIDATION":
            if bias == "BULLISH" and structure_data['bos_bullish']: side = "BUY"
            elif bias == "BEARISH" and structure_data['bos_bearish']: side = "SELL"
            
        return {
            'side': side,
            'score': score,
            'phase': phase,
            'bias': bias,
            'fvg_ready': len(structure_data['fvgs']) > 0
        }
