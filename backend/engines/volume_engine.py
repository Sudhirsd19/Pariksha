import pandas as pd

class VolumeEngine:
    def __init__(self, spike_multiplier=2.0):
        self.spike_multiplier = spike_multiplier

    def analyze(self, df: pd.DataFrame):
        last_row = df.iloc[-1]
        avg_volume = df['volume'].rolling(window=20).mean().iloc[-1]
        
        is_spike = last_row['volume'] > (avg_volume * self.spike_multiplier)
        above_vwap = last_row['close'] > last_row.get('VWAP', last_row['close'])
        
        strength = "Strong" if is_spike else "Weak"
        bias = "Bullish" if above_vwap else "Bearish"
        
        return {
            'volume_spike': is_spike,
            'strength': strength,
            'bias': bias,
            'vwap_status': 'Above' if above_vwap else 'Below'
        }
