import pandas as pd

class RegimeEngine:
    def __init__(self, adx_threshold=20):
        self.adx_threshold = adx_threshold

    def analyze(self, df: pd.DataFrame):
        """
        Identify if market is Trending or Sideways.
        """
        if 'ADX' not in df.columns or 'ATR' not in df.columns:
            return {"regime": "Unknown", "trending": False}
            
        last_row = df.iloc[-1]
        adx = last_row['ADX']
        atr = last_row['ATR']
        
        # Calculate ATR Moving Average to see if volatility is expanding
        atr_ma = df['ATR'].rolling(window=20).mean().iloc[-1]
        
        is_trending = adx > self.adx_threshold or atr > atr_ma
        
        return {
            "adx": adx,
            "atr": atr,
            "trending": is_trending,
            "regime": "Trending" if is_trending else "Sideways/Choppy"
        }
