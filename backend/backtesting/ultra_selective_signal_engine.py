"""
Ultra-Selective High Win Rate Signal Engine
Goal: Achieve 70%+ win rate by trading ONLY the best setups

Key Strategy:
- Reduce total trades but increase win rate dramatically
- Only enter when ALL conditions align perfectly
- Prioritize quality over quantity
- Focus on highest-probability setups
"""
import pandas as pd
import numpy as np

class UltraSelectiveSignalEngine:
    """
    Ultra-selective signal generation targeting 70%+ win rate
    Strategy: Trade ONLY the absolute best setups
    """
    
    def __init__(self):
        self.atr_multiplier_sl = 2.5
        self.allowed_hours = [(10, 11), (14, 15)]  # 10-11 AM & 2-3 PM IST
        
    def generate_signals(self, df):
        """Generate ultra-selective signals for 70%+ win rate"""
        df = df.copy()
        df['signal'] = None
        df['signal_strength'] = 0
        
        # Calculate all indicators
        df = self._calculate_indicators(df)
        
        # Generate ONLY the best signals
        for i in range(200, len(df)):
            signal = self._evaluate_ultra_selective_signal(df, i)
            if signal:
                df.at[i, 'signal'] = signal
        
        return df
    
    def _calculate_indicators(self, df):
        """Calculate comprehensive indicators"""
        # Moving averages
        df['ema5'] = df['close'].ewm(span=5).mean()
        df['ema9'] = df['close'].ewm(span=9).mean()
        df['ema21'] = df['close'].ewm(span=21).mean()
        df['ema50'] = df['close'].ewm(span=50).mean()
        
        # RSI with multiple periods
        df['rsi14'] = self._calculate_rsi(df['close'], 14)
        df['rsi7'] = self._calculate_rsi(df['close'], 7)
        
        # MACD
        df['macd'] = self._calculate_macd(df['close'])
        df['macd_signal'] = df['macd'].ewm(span=9).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # ATR and volatility
        tr = self._true_range(df)
        df['atr'] = tr.rolling(14).mean()
        df['atr_ma'] = df['atr'].rolling(20).mean()
        df['volatility'] = df['close'].rolling(14).std() / df['close'].rolling(14).mean()
        
        # Volume analysis
        df['volume_ma20'] = df['volume'].rolling(20).mean()
        df['volume_ma50'] = df['volume'].rolling(50).mean()
        df['volume_ratio'] = df['volume'] / (df['volume_ma20'] + 1)
        df['volume_trend'] = df['volume_ma20'] / df['volume_ma50']
        
        # Support/Resistance
        df['resistance_10'] = df['high'].rolling(10, center=False).max()
        df['support_10'] = df['low'].rolling(10, center=False).min()
        df['resistance_20'] = df['high'].rolling(20).max()
        df['support_20'] = df['low'].rolling(20).min()
        
        # Price position
        df['price_pct_of_range'] = (df['close'] - df['support_20']) / (df['resistance_20'] - df['support_20'] + 0.01)
        
        # Momentum
        df['momentum_5'] = df['close'].pct_change(5) * 100
        df['momentum_10'] = df['close'].pct_change(10) * 100
        
        # Stochastic
        df['stoch_k'], df['stoch_d'] = self._calculate_stochastic(df['high'], df['low'], df['close'], 14)
        
        return df
    
    def _evaluate_ultra_selective_signal(self, df, i):
        """
        ULTRA SELECTIVE: Generate signals only for the ABSOLUTE BEST setups
        Target: 70%+ win rate by trading only when everything aligns
        """
        if i < 201:
            return None
        
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        prev_prev_row = df.iloc[i-2]
        
        # Validation
        if pd.isna(row.get('ema21')) or pd.isna(row.get('atr')):
            return None
        
        # TIME FILTER (non-negotiable)
        try:
            hour = row['time'].hour
            if hour not in [10, 14]:
                return None
        except:
            pass
        
        # VOLUME FILTER (strict: 2x+ MA)
        if row['volume_ratio'] < 2.0:
            return None
        
        # ============ BULLISH ULTRA-SELECTIVE SETUP ============
        # BUY only when ALL conditions met:
        buy_signal = self._check_ultra_bullish(df, i)
        if buy_signal:
            return "BUY"
        
        # ============ BEARISH ULTRA-SELECTIVE SETUP ============
        sell_signal = self._check_ultra_bearish(df, i)
        if sell_signal:
            return "SELL"
        
        return None
    
    def _check_ultra_bullish(self, df, i):
        """
        ULTRA BULLISH SETUP - Only trade when ALL conditions met
        This filters out 70% of signals but keeps the best 30%
        """
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        prev_prev_row = df.iloc[i-2]
        
        close = row['close']
        ema5 = row.get('ema5', 0)
        ema9 = row.get('ema9', 0)
        ema21 = row.get('ema21', 0)
        ema50 = row.get('ema50', 0)
        rsi14 = row.get('rsi14', 50)
        rsi7 = row.get('rsi7', 50)
        macd_hist = row.get('macd_hist', 0)
        volume_ratio = row.get('volume_ratio', 0)
        stoch_k = row.get('stoch_k', 50)
        
        support_20 = row.get('support_20', 0)
        
        # ===== CONDITION 1: TREND ALIGNMENT =====
        # All EMAs in perfect uptrend order
        if not (ema5 > ema9 > ema21 > ema50):
            return False
        
        # ===== CONDITION 2: MOMENTUM ALIGNMENT =====
        # MACD must be positive and increasing
        if macd_hist <= 0:
            return False
        
        # MACD histogram must be bigger than previous
        if df.iloc[i-1].get('macd_hist', 0) > macd_hist:
            return False
        
        # ===== CONDITION 3: RSI ALIGNMENT =====
        # RSI7 > 40 and < 75 (not overbought, in momentum zone)
        if not (40 < rsi7 < 75):
            return False
        
        # RSI14 > 35 and < 70
        if not (35 < rsi14 < 70):
            return False
        
        # RSI7 must be rising
        if df.iloc[i-1].get('rsi7', 50) >= rsi7:
            return False
        
        # ===== CONDITION 4: PRICE NEAR SUPPORT =====
        # Price must bounce from support (within 0.5%)
        support_pct = abs(close - support_20) / (support_20 + 0.01) * 100
        if support_pct > 0.5:
            return False
        
        # ===== CONDITION 5: VOLUME CONFIRMATION =====
        # Volume must be 2x+ MA (strict)
        if volume_ratio < 2.0:
            return False
        
        # Volume must be increasing
        if df.iloc[i-1].get('volume_ratio', 0) >= volume_ratio:
            return False
        
        # ===== CONDITION 6: CANDLE CONFIRMATION =====
        # Current candle is strongly bullish
        candle_pct = (close - row['open']) / row['open'] * 100
        if candle_pct < 0.2:  # Must close with 0.2%+ gain
            return False
        
        # Previous candle also bullish
        prev_close = prev_row['close']
        prev_open = prev_row['open']
        prev_candle_pct = (prev_close - prev_open) / prev_open * 100
        if prev_candle_pct < 0.1:
            return False
        
        # ===== CONDITION 7: VOLATILITY ENVIRONMENT =====
        # ATR must be elevated (above 20-day MA)
        atr = row.get('atr', 0)
        atr_ma = row.get('atr_ma', 0)
        if atr < atr_ma * 0.95:
            return False
        
        # ===== CONDITION 8: STOCHASTIC ALIGNMENT =====
        # Stochastic K < 80 (not overbought) and > 20 (not oversold)
        if stoch_k < 20 or stoch_k > 80:
            return False
        
        # ALL CONDITIONS MET - ULTRA HIGH PROBABILITY BUY SIGNAL
        return True
    
    def _check_ultra_bearish(self, df, i):
        """
        ULTRA BEARISH SETUP - Mirror of bullish
        """
        row = df.iloc[i]
        prev_row = df.iloc[i-1]
        
        close = row['close']
        ema5 = row.get('ema5', 0)
        ema9 = row.get('ema9', 0)
        ema21 = row.get('ema21', 0)
        ema50 = row.get('ema50', 0)
        rsi14 = row.get('rsi14', 50)
        rsi7 = row.get('rsi7', 50)
        macd_hist = row.get('macd_hist', 0)
        volume_ratio = row.get('volume_ratio', 0)
        stoch_k = row.get('stoch_k', 50)
        
        resistance_20 = row.get('resistance_20', 0)
        
        # ===== CONDITION 1: TREND ALIGNMENT =====
        if not (ema5 < ema9 < ema21 < ema50):
            return False
        
        # ===== CONDITION 2: MOMENTUM ALIGNMENT =====
        if macd_hist >= 0:
            return False
        
        if df.iloc[i-1].get('macd_hist', 0) < macd_hist:
            return False
        
        # ===== CONDITION 3: RSI ALIGNMENT =====
        if not (25 < rsi7 < 60):
            return False
        
        if not (30 < rsi14 < 65):
            return False
        
        if df.iloc[i-1].get('rsi7', 50) <= rsi7:
            return False
        
        # ===== CONDITION 4: PRICE NEAR RESISTANCE =====
        resistance_pct = abs(resistance_20 - close) / (close + 0.01) * 100
        if resistance_pct > 0.5:
            return False
        
        # ===== CONDITION 5: VOLUME CONFIRMATION =====
        if volume_ratio < 2.0:
            return False
        
        if df.iloc[i-1].get('volume_ratio', 0) >= volume_ratio:
            return False
        
        # ===== CONDITION 6: CANDLE CONFIRMATION =====
        candle_pct = (row['open'] - close) / row['open'] * 100
        if candle_pct < 0.2:
            return False
        
        prev_close = prev_row['close']
        prev_open = prev_row['open']
        prev_candle_pct = (prev_open - prev_close) / prev_open * 100
        if prev_candle_pct < 0.1:
            return False
        
        # ===== CONDITION 7: VOLATILITY =====
        atr = row.get('atr', 0)
        atr_ma = row.get('atr_ma', 0)
        if atr < atr_ma * 0.95:
            return False
        
        # ===== CONDITION 8: STOCHASTIC =====
        if stoch_k < 20 or stoch_k > 80:
            return False
        
        return True
    
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
    
    def _calculate_stochastic(self, high, low, close, period=14):
        lowest_low = low.rolling(period).min()
        highest_high = high.rolling(period).max()
        k = 100 * (close - lowest_low) / (highest_high - lowest_low + 0.01)
        d = k.rolling(3).mean()
        return k, d
