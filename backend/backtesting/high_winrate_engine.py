"""
High Win Rate Signal Engine (70%+ Win Rate)
Balanced approach: Quality over Quantity
"""
import pandas as pd
import numpy as np

class HighWinRateSignalEngine:
    """
    Strategy for 70%+ win rate:
    - Trade only strongest setups
    - Reduce total trades
    - Increase quality/probability of each trade
    """
    
    def __init__(self):
        self.atr_multiplier_sl = 2.5
        self.allowed_hours = [(10, 11), (14, 15)]
        
    def generate_signals(self, df):
        """Generate high-quality signals targeting 70%+ win rate"""
        df = df.copy()
        df['signal'] = None
        
        df = self._calculate_indicators(df)
        
        for i in range(100, len(df)):
            signal = self._evaluate_high_quality_signal(df, i)
            if signal:
                df.at[i, 'signal'] = signal
        
        return df
    
    def _calculate_indicators(self, df):
        """Calculate indicators"""
        # EMAs
        df['ema9'] = df['close'].ewm(span=9).mean()
        df['ema21'] = df['close'].ewm(span=21).mean()
        df['ema50'] = df['close'].ewm(span=50).mean()
        
        # RSI
        df['rsi'] = self._calc_rsi(df['close'], 14)
        
        # MACD
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['macd'] = ema12 - ema26
        df['macd_sig'] = df['macd'].ewm(span=9).mean()
        df['macd_hist'] = df['macd'] - df['macd_sig']
        
        # ATR
        tr = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift()),
                abs(df['low'] - df['close'].shift())
            )
        )
        df['atr'] = tr.rolling(14).mean()
        
        # Volume
        df['vol_ma'] = df['volume'].rolling(20).mean()
        df['vol_ratio'] = df['volume'] / (df['vol_ma'] + 1)
        
        # S/R
        df['support'] = df['low'].rolling(10).min()
        df['resistance'] = df['high'].rolling(10).max()
        
        return df
    
    def _evaluate_high_quality_signal(self, df, i):
        """Evaluate HIGH QUALITY signals only"""
        row = df.iloc[i]
        prev = df.iloc[i-1]
        
        if pd.isna(row['ema21']):
            return None
        
        # TIME FILTER
        try:
            if row['time'].hour not in [10, 14]:
                return None
        except:
            pass
        
        # VOLUME FILTER (2x MA)
        if row['vol_ratio'] < 2.0:
            return None
        
        close = row['close']
        ema9 = row['ema9']
        ema21 = row['ema21']
        ema50 = row['ema50']
        rsi = row['rsi']
        macd_h = row['macd_hist']
        support = row['support']
        resistance = row['resistance']
        
        # ============ BULLISH HIGH-QUALITY SETUP ============
        # Signal 1: Strong uptrend + momentum
        if (ema9 > ema21 > ema50 and
            close > ema21 and
            rsi > 45 and rsi < 75 and  # In momentum, not overbought
            macd_h > 0 and
            macd_h > prev['macd_hist'] and  # Increasing
            row['vol_ratio'] >= 2.0 and  # High volume
            close > row['open']):  # Bullish candle
            return "BUY"
        
        # Signal 2: Bounce from support with strong volume
        if (close > support and
            abs(close - support) / (support + 0.01) * 100 < 0.8 and  # Near support
            close > ema21 and
            rsi > 35 and rsi < 70 and
            macd_h > 0 and
            row['vol_ratio'] >= 2.0 and
            close > row['open'] and
            prev['close'] > prev['open']):  # Both candles bullish
            return "BUY"
        
        # Signal 3: EMA breakout
        if (prev['close'] <= ema21 and
            close > ema21 and
            ema21 > ema50 and
            rsi > 40 and rsi < 75 and
            macd_h > 0 and
            row['vol_ratio'] >= 2.0):
            return "BUY"
        
        # ============ BEARISH HIGH-QUALITY SETUP ============
        # Signal 1: Strong downtrend + momentum
        if (ema9 < ema21 < ema50 and
            close < ema21 and
            rsi < 55 and rsi > 25 and  # In momentum, not oversold
            macd_h < 0 and
            macd_h < prev['macd_hist'] and  # Decreasing
            row['vol_ratio'] >= 2.0 and
            close < row['open']):  # Bearish candle
            return "SELL"
        
        # Signal 2: Bounce from resistance
        if (close < resistance and
            abs(resistance - close) / (close + 0.01) * 100 < 0.8 and
            close < ema21 and
            rsi < 65 and rsi > 30 and
            macd_h < 0 and
            row['vol_ratio'] >= 2.0 and
            close < row['open'] and
            prev['close'] < prev['open']):  # Both candles bearish
            return "SELL"
        
        # Signal 3: EMA breakout
        if (prev['close'] >= ema21 and
            close < ema21 and
            ema21 < ema50 and
            rsi < 60 and rsi > 25 and
            macd_h < 0 and
            row['vol_ratio'] >= 2.0):
            return "SELL"
        
        return None
    
    def _calc_rsi(self, close, period=14):
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
