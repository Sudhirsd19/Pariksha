import pandas as pd

class TrendEngine:
    def __init__(self):
        pass

    def analyze(self, df: pd.DataFrame) -> str:
        """
        Analyze trend using a scoring system (2 out of 3 = trend confirmed).
        Returns: 'Bullish', 'Bearish', or 'Neutral'
        """
        if len(df) < 50:
            return "Neutral"

        last_row = df.iloc[-1]
        
        ema20 = last_row.get('EMA_20', 0)
        ema50 = last_row.get('EMA_50', 0)
        st = last_row.get('Supertrend', None)
        adx = last_row.get('ADX', 0)

        # Score-based approach: 2 out of 3 = confirmed trend
        bull_score = 0
        bear_score = 0

        # Factor 1: EMA alignment
        if ema20 > ema50:
            bull_score += 1
        elif ema20 < ema50:
            bear_score += 1

        # Factor 2: Supertrend direction
        if st is True:
            bull_score += 1
        elif st is False:
            bear_score += 1

        # Factor 3: ADX strength (trend exists, not necessarily direction)
        if adx > 15:  # Reduced from 20 to 15 for moderate trends
            # ADX confirms a trend exists; direction from EMA/Supertrend
            if bull_score > bear_score:
                bull_score += 1
            elif bear_score > bull_score:
                bear_score += 1

        # 2 out of 3 = confirmed
        if bull_score >= 2:
            return "Bullish"
        elif bear_score >= 2:
            return "Bearish"
        else:
            return "Neutral"
