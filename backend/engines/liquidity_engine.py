import pandas as pd

class LiquidityEngine:
    def __init__(self, tolerance=0.0005):
        self.tolerance = tolerance

    def detect_liquidity_zones(self, df: pd.DataFrame):
        """Detect Equal Highs and Equal Lows"""
        highs = df['high'].values
        lows = df['low'].values
        
        eq_highs = []
        eq_lows = []
        
        for i in range(len(highs)-1):
            for j in range(i+1, min(i+20, len(highs))):
                if abs(highs[i] - highs[j]) / highs[i] < self.tolerance:
                    eq_highs.append(highs[i])
                if abs(lows[i] - lows[j]) / lows[i] < self.tolerance:
                    eq_lows.append(lows[i])
                    
        return list(set(eq_highs)), list(set(eq_lows))

    def detect_sweeps(self, df: pd.DataFrame, eq_highs, eq_lows):
        """Detect price sweeping above eq highs or below eq lows and reversing"""
        last_high = df['high'].iloc[-1]
        last_low = df['low'].iloc[-1]
        last_close = df['close'].iloc[-1]
        
        sweep_signal = None
        
        for h in eq_highs:
            if last_high > h and last_close < h:
                sweep_signal = "Bearish Sweep"
                break
        
        if not sweep_signal:
            for l in eq_lows:
                if last_low < l and last_close > l:
                    sweep_signal = "Bullish Sweep"
                    break
                    
        return sweep_signal

    def analyze(self, df: pd.DataFrame):
        eq_h, eq_l = self.detect_liquidity_zones(df)
        sweep = self.detect_sweeps(df, eq_h, eq_l)
        return {
            'eq_highs': eq_h,
            'eq_lows': eq_l,
            'sweep': sweep
        }
