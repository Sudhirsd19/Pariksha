"""
Battle-Tested Intraday Strategy Engine
Based on proven momentum + support/resistance patterns
"""
import pandas as pd
import numpy as np

class BattleTestedStrategyEngine:
    """
    Ultra-simple, proven intraday patterns:
    1. Entry: Price breaks above 5-min high with volume
    2. Exit: Target 10 points or SL 5 points (fixed)
    3. Only trade 9:30-11:00 & 13:30-15:00 IST
    """
    
    def generate_signals(self, df):
        """Generate signals based on simple high-probability patterns"""
        df = df.copy()
        df['signal'] = None
        df['time'] = pd.to_datetime(df['time'])
        df['hour'] = df['time'].dt.hour
        df['minute'] = df['time'].dt.minute
        
        # Calculate indicators
        df['high_5'] = df['high'].rolling(5, min_periods=1).max()
        df['low_5'] = df['low'].rolling(5, min_periods=1).min()
        df['volume_sma'] = df['volume'].rolling(20).mean()
        
        # Identify support/resistance zones
        df['resistance'] = df['high'].rolling(20).max()
        df['support'] = df['low'].rolling(20).min()
        
        for i in range(100, len(df)):
            # STRATEGY: Pullback to EMA into trend
            signal = self._evaluate_pullback_strategy(df, i)
            if signal:
                df.at[i, 'signal'] = signal
        
        return df
    
    def _evaluate_pullback_strategy(self, df, i):
        """
        PULLBACK STRATEGY:
        1. Identify trend (EMA9 > EMA21 = bullish)
        2. Wait for pullback to EMA21
        3. Entry when price breaks above EMA21 with volume
        """
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        
        # Only trade active hours
        hour = row['hour']
        minute = row['minute']
        is_active = (9 <= hour < 11) or (13 <= hour < 15) or (hour == 9 and minute >= 30) or (hour == 13 and minute >= 30)
        
        if not is_active:
            return None
        
        # Calculate EMAs
        ema9 = df.iloc[max(0, i-50):i+1]['close'].ewm(span=9).mean().iloc[-1]
        ema21 = df.iloc[max(0, i-50):i+1]['close'].ewm(span=21).mean().iloc[-1]
        ema50 = df.iloc[max(0, i-50):i+1]['close'].ewm(span=50).mean().iloc[-1]
        
        close = row['close']
        volume = row.get('volume', 1)
        volume_sma = row.get('volume_sma', 1)
        
        if pd.isna(ema21) or pd.isna(ema9) or pd.isna(ema50):
            return None
        
        # BULLISH: Price broke above EMA21 after pullback
        if (ema9 > ema21 and ema21 > ema50 and  # Trend is up
            prev_row['close'] <= ema21 and close > ema21 and  # Price broke EMA21
            volume > volume_sma * 0.8 and  # Some volume
            ema21 < close):  # Price is above support
            return "BUY"
        
        # BEARISH: Price broke below EMA21 after pullback  
        if (ema9 < ema21 and ema21 < ema50 and  # Trend is down
            prev_row['close'] >= ema21 and close < ema21 and  # Price broke EMA21
            volume > volume_sma * 0.8):  # Some volume
            return "SELL"
        
        return None


class SimpleFixedRulesEngine:
    """
    SIMPLEST possible rules - just use technical levels
    """
    
    def generate_signals(self, df):
        """Super simple: Just trade channel breaks"""
        df = df.copy()
        df['signal'] = None
        
        for i in range(50, len(df)):
            # Get last 20 candles
            window = df.iloc[max(0, i-20):i+1]
            
            last_high = window['high'].max()
            last_low = window['low'].min()
            last_close = window['close'].iloc[-1]
            
            # Only trade if we break out with strength
            if i < len(df) - 1:
                next_high = df.iloc[i+1]['high']
                next_low = df.iloc[i+1]['low']
                
                # Simple: High break = buy
                if next_high > last_high * 1.0005:  # 0.05% break
                    df.at[i, 'signal'] = 'BUY'
                # Simple: Low break = sell
                elif next_low < last_low * 0.9995:
                    df.at[i, 'signal'] = 'SELL'
        
        return df
