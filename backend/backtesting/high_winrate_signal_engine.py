"""
High-Win-Rate Signal Engine (70%+ target)
Ultra-selective signals with strict filters
"""
import pandas as pd
import numpy as np

class HighWinRateSignalEngine:
    """
    Ultra-selective signal generation optimized for 70%+ win rate
    Key: Fewer but higher quality signals
    """
    
    def __init__(self):
        self.atr_period = 14
        
    def generate_signals(self, df):
        """
        Generate only the highest quality signals
        Focus on breakouts with volume and trend confirmation
        """
        df = df.copy()
        df['signal'] = None
        
        # Calculate indicators
        df = self._calculate_indicators(df)
        
        # Generate signals with strict filters
        for i in range(100, len(df)):
            signal = self._evaluate_signal(df, i)
            if signal:
                df.at[i, 'signal'] = signal
        
        return df
    
    def _calculate_indicators(self, df):
        """Calculate necessary indicators"""
        # EMAs for trend
        df['ema20'] = df['close'].ewm(span=20).mean()
        df['ema50'] = df['close'].ewm(span=50).mean()
        
        # ATR for volatility
        tr = self._true_range(df)
        df['atr'] = tr.rolling(self.atr_period).mean()
        
        # RSI for momentum
        df['rsi'] = self._calculate_rsi(df['close'], 14)
        
        # Volume analysis
        df['volume_sma'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / (df['volume_sma'] + 1)
        
        # Price range
        df['high_20'] = df['high'].rolling(20).max()
        df['low_20'] = df['low'].rolling(20).min()
        
        return df
    
    def _true_range(self, df):
        """Calculate True Range"""
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        return pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    
    def _calculate_rsi(self, close, period=14):
        """Calculate RSI"""
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def _evaluate_signal(self, df, i):
        """
        Generate signal only when ALL conditions are met
        """
        row = df.iloc[i]
        prev_row = df.iloc[i-1] if i > 0 else None
        
        # Check indicators exist
        if pd.isna(row.get('ema20')) or pd.isna(row.get('atr')):
            return None
        
        close = row['close']
        ema20 = row['ema20']
        ema50 = row['ema50']
        atr = row['atr']
        rsi = row.get('rsi', 50)
        volume_ratio = row.get('volume_ratio', 0.5)
        
        # === BULLISH SIGNAL ===
        # Criteria: Price > both EMAs, EMA20 > EMA50, RSI 40-70, Volume > 100% MA
        if (close > ema20 and ema20 > ema50 and 
            40 < rsi < 70 and volume_ratio > 1.0):
            
            # Additional: Check price just broke above EMA20
            if prev_row is not None:
                prev_close = prev_row['close']
                if prev_close <= ema20 and close > ema20:
                    return "BUY"
            
            # Or: Price is retesting EMA20 from above (pullback entry)
            if row['low'] <= ema20 and close > ema20:
                return "BUY"
        
        # === BEARISH SIGNAL ===
        # Criteria: Price < both EMAs, EMA20 < EMA50, RSI 30-60, Volume > 100% MA
        if (close < ema20 and ema20 < ema50 and 
            30 < rsi < 60 and volume_ratio > 1.0):
            
            # Additional: Check price just broke below EMA20
            if prev_row is not None:
                prev_close = prev_row['close']
                if prev_close >= ema20 and close < ema20:
                    return "SELL"
            
            # Or: Price is retesting EMA20 from below
            if row['high'] >= ema20 and close < ema20:
                return "SELL"
        
        return None



class ImprovedSignalMatcher:
    """
    Matches the actual signal generation in the backtest
    For use in the advanced backtest engine
    """
    
    def __init__(self, df):
        self.df = df.copy()
        self.engine = HighWinRateSignalEngine()
        
    def get_signals(self):
        """Returns DataFrame with 'signal' column populated"""
        return self.engine.generate_signals(self.df)
