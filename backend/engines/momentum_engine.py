import pandas as pd

class MomentumEngine:
    def __init__(self):
        pass

    def analyze(self, df: pd.DataFrame):
        # FIX: Guard against missing RSI column or insufficient data
        if df is None or df.empty or 'RSI' not in df.columns or len(df) < 2:
            return {'rsi': 50.0, 'strength': 'Neutral', 'rising': False}

        last_rsi = df['RSI'].iloc[-1]
        prev_rsi = df['RSI'].iloc[-2]

        # FIX: Guard against NaN values (common at start of data)
        if last_rsi != last_rsi:  # NaN check
            return {'rsi': 50.0, 'strength': 'Neutral', 'rising': False}

        strength = "Neutral"
        if last_rsi > 60:
            strength = "Strong Bullish"
        elif last_rsi > 50:
            strength = "Bullish"
        elif last_rsi < 40:
            strength = "Strong Bearish"
        elif last_rsi < 50:
            strength = "Bearish"
        # FIX: RSI exactly 50 stays "Neutral" (was falling through to "Bearish")

        rising = bool(last_rsi > prev_rsi) if prev_rsi == prev_rsi else False

        return {
            'rsi': round(float(last_rsi), 2),
            'strength': strength,
            'rising': rising
        }
