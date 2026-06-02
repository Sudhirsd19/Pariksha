import pandas as pd

class VolumeEngine:
    def __init__(self, spike_multiplier=2.0):
        self.spike_multiplier = spike_multiplier

    def analyze(self, df: pd.DataFrame):
        if df is None or df.empty or len(df) < 2:
            return {'volume_spike': False, 'strength': 'Weak', 'bias': 'Neutral', 'vwap_status': 'Unknown'}

        last_row = df.iloc[-1]

        # FIX: Guard against NaN from rolling mean on short DataFrames
        avg_volume = df['volume'].rolling(window=min(20, len(df))).mean().iloc[-1]
        if avg_volume != avg_volume or avg_volume == 0:  # NaN check
            is_spike = False
        else:
            is_spike = last_row['volume'] > (avg_volume * self.spike_multiplier)

        # FIX: If VWAP column is missing, use neutral status instead of
        # falling back to close > close which always returns False (Below)
        if 'VWAP' in df.columns and last_row['VWAP'] > 0:
            above_vwap = last_row['close'] > last_row['VWAP']
            vwap_status = 'Above' if above_vwap else 'Below'
        else:
            above_vwap = None
            vwap_status = 'Unknown'  # FIX: Was silently returning 'Below' when VWAP missing

        strength = "Strong" if is_spike else "Weak"
        bias = "Bullish" if above_vwap else ("Bearish" if above_vwap is not None else "Neutral")

        return {
            'volume_spike': is_spike,
            'strength': strength,
            'bias': bias,
            'vwap_status': vwap_status
        }
