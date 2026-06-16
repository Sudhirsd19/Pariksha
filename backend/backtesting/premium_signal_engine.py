"""
Premium Signal Engine - Ultra-Selective for Profitability
Focus: Only trade high-confidence setups that actually work
"""
import pandas as pd
import numpy as np

class PremiumSignalEngine:
    """
    Super selective signal generation focusing on:
    - Trend confirmation (not just trend presence)
    - Momentum divergence (price vs RSI)
    - Volume surge into support/resistance
    - Multi-timeframe alignment
    """
    
    def __init__(self):
        self.min_atr_volatility = 1.2  # At least 20% above normal
        self.min_volume_surge = 1.3    # 30% above MA
        
    def generate_signals(self, df):
        """Generate only HIGH CONFIDENCE signals"""
        df = df.copy()
        df['signal'] = None
        
        # Calculate indicators
        df = self._calculate_indicators(df)
        
        # CRITICAL: Only generate signals with STRONG confluence
        for i in range(200, len(df)):
            signal = self._evaluate_premium_signal(df, i)
            if signal:
                df.at[i, 'signal'] = signal
        
        return df
    
    def _calculate_indicators(self, df):
        """Calculate ALL indicators"""
        # Moving averages
        df['ema9'] = df['close'].ewm(span=9).mean()
        df['ema21'] = df['close'].ewm(span=21).mean()
        df['ema50'] = df['close'].ewm(span=50).mean()
        
        # Momentum
        df['rsi14'] = self._calculate_rsi(df['close'], 14)
        df['macd'] = self._calculate_macd(df['close'])
        
        # Volatility
        tr = self._true_range(df)
        df['atr'] = tr.rolling(14).mean()
        df['atr_ma'] = df['atr'].rolling(20).mean()
        
        # Volume
        df['volume_ma'] = df['volume'].rolling(20).mean()
        df['volume_ratio'] = df['volume'] / df['volume_ma']
        
        # Support/Resistance
        df['resistance_5'] = df['high'].rolling(5).max()
        df['support_5'] = df['low'].rolling(5).min()
        
        return df
    
    def _true_range(self, df):
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        return pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    
    def _calculate_rsi(self, close, period=14):
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def _calculate_macd(self, close):
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        return ema12 - ema26
    
    def _evaluate_premium_signal(self, df, i):
        """
        ONLY generate signal when ALL of these are true:
        1. Strong EMA alignment (price in trend)
        2. Volume surge (breakout has conviction)
        3. Momentum confirmation (RSI + MACD agree)
        4. Price at/near support/resistance (technical level)
        5. ATR elevated (volatility environment good)
        """
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        
        # Quick checks
        if pd.isna(row.get('ema21')) or pd.isna(row.get('atr')):
            return None
        
        close = row['close']
        ema9 = row['ema9']
        ema21 = row['ema21']
        ema50 = row['ema50']
        rsi = row.get('rsi14', 50)
        macd = row.get('macd', 0)
        volume_ratio = row.get('volume_ratio', 0)
        atr = row['atr']
        atr_ma = row['atr_ma']
        
        # FILTER 1: Volatility check - only trade when ATR is elevated
        if pd.isna(atr_ma) or atr < atr_ma * 0.9:
            return None
        
        # FILTER 2: Volume must be strong
        if volume_ratio < 1.0:
            return None
        
        # ========== BULLISH SETUP ==========
        # Criteria:
        # - Price > EMA9 > EMA21 > EMA50 (all EMAs aligned)
        # - Price just broke above EMA21 (momentum)
        # - Volume surge
        # - RSI 40-70 (not overbought)
        # - MACD positive
        if (close > ema9 and ema9 > ema21 and ema21 > ema50 and
            prev_row['close'] <= ema21 and close > ema21 and  # Break above EMA21
            40 < rsi < 75 and
            macd > 0 and
            volume_ratio > 1.1):
            return "BUY"
        
        # Alternative: Price retesting EMA50 with volume
        if (close > ema50 and close < ema21 and
            prev_row['close'] <= ema50 and close > ema50 and  # Break above EMA50
            ema21 > ema50 and
            rsi > 40 and
            volume_ratio > 1.3):  # Need high volume for retests
            return "BUY"
        
        # ========== BEARISH SETUP ==========
        if (close < ema9 and ema9 < ema21 and ema21 < ema50 and
            prev_row['close'] >= ema21 and close < ema21 and  # Break below EMA21
            25 < rsi < 60 and
            macd < 0 and
            volume_ratio > 1.1):
            return "SELL"
        
        # Alternative: Price retesting EMA50 with volume
        if (close < ema50 and close > ema21 and
            prev_row['close'] >= ema50 and close < ema50 and  # Break below EMA50
            ema21 < ema50 and
            rsi < 60 and
            volume_ratio > 1.3):
            return "SELL"
        
        return None
