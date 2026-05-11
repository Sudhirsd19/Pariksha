import pandas as pd

class MomentumEngine:
    def __init__(self):
        pass

    def analyze(self, df: pd.DataFrame):
        last_rsi = df['RSI'].iloc[-1]
        prev_rsi = df['RSI'].iloc[-2]
        
        strength = "Neutral"
        if last_rsi > 60:
            strength = "Strong Bullish"
        elif last_rsi > 50:
            strength = "Bullish"
        elif last_rsi < 40:
            strength = "Strong Bearish"
        elif last_rsi < 50:
            strength = "Bearish"
            
        rising = last_rsi > prev_rsi
        
        return {
            'rsi': last_rsi,
            'strength': strength,
            'rising': rising
        }
