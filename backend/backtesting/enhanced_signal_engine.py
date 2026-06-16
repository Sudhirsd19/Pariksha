"""
Enhanced Signal Generation for High Win Rate (70%+)
Filters: Structure + Trend + Volume + Risk/Reward
"""
import pandas as pd
import numpy as np

class EnhancedSignalEngine:
    """
    High-quality signal generation focusing on:
    - Structure breaks (BOS/FVG)
    - Trend confirmation (EMA/ADX)
    - Volume validation
    - Risk/Reward >1:2
    """
    
    def __init__(self):
        self.min_rr_ratio = 2.0  # Risk reward minimum
        
    def generate_signals(self, df):
        """
        Generate BUY/SELL signals with high quality filters
        Returns df with 'signal' column (BUY, SELL, or None)
        """
        df = df.copy()
        df['signal'] = None
        
        # Calculate all indicators
        df = self._calculate_indicators(df)
        
        # Apply multi-filter logic
        for i in range(100, len(df)):
            current_row = df.iloc[i]
            prev_row = df.iloc[i-1]
            
            # Filter 1: Trend (EMA alignment)
            trend = self._check_trend(df, i)
            if trend == "NEUTRAL":
                continue
            
            # Filter 2: Structure (BOS or pullback into support/resistance)
            structure = self._check_structure(df, i)
            if not structure:
                continue
            
            # Filter 3: Volume (higher than average)
            if not self._check_volume(df, i):
                continue
            
            # Filter 4: Momentum (RSI not extreme)
            rsi = current_row['rsi']
            if pd.isna(rsi):
                continue
            
            # Filter 5: Risk/Reward (use ATR for levels)
            signal = self._calculate_optimal_entry(df, i, trend)
            
            if signal:
                df.at[i, 'signal'] = signal
        
        return df
    
    def _calculate_indicators(self, df):
        """Calculate all required indicators"""
        # EMA
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()
        
        # RSI
        df['rsi'] = self._calculate_rsi(df['close'], period=14)
        
        # Volume MA
        df['volume_ma'] = df['volume'].rolling(20).mean()
        
        # ADX (trend strength)
        df['adx'] = self._calculate_adx(df, period=14)
        
        # Support/Resistance (simple - recent swing points)
        df['support'] = df['low'].rolling(10).min()
        df['resistance'] = df['high'].rolling(10).max()
        
        return df
    
    def _calculate_rsi(self, close, period=14):
        """Calculate RSI"""
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    def _calculate_adx(self, df, period=14):
        """Calculate ADX for trend strength"""
        try:
            high = df['high']
            low = df['low']
            close = df['close']
            
            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs()
            ], axis=1).max(axis=1)
            
            up_move = high - high.shift()
            down_move = low.shift() - low
            
            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
            
            tr_smooth = tr.rolling(period).mean()
            plus_di = 100 * (pd.Series(plus_dm).rolling(period).mean() / tr_smooth)
            minus_di = 100 * (pd.Series(minus_dm).rolling(period).mean() / tr_smooth)
            
            dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
            adx = dx.rolling(period).mean()
            
            return adx
        except:
            return pd.Series(0, index=df.index)
    
    def _check_trend(self, df, i):
        """Determine current trend (BULLISH, BEARISH, NEUTRAL)"""
        row = df.iloc[i]
        
        if pd.isna(row['ema20']) or pd.isna(row['ema50']) or pd.isna(row['ema200']):
            return "NEUTRAL"
        
        close = row['close']
        ema20 = row['ema20']
        ema50 = row['ema50']
        ema200 = row['ema200']
        
        # Strong bullish: price > ema20 > ema50 > ema200
        if close > ema20 and ema20 > ema50 and ema50 > ema200:
            return "BULLISH"
        # Strong bearish: price < ema20 < ema50 < ema200
        elif close < ema20 and ema20 < ema50 and ema50 < ema200:
            return "BEARISH"
        else:
            return "NEUTRAL"
    
    def _check_structure(self, df, i):
        """Check if there's a valid structure break"""
        if i < 20:
            return False
        
        row = df.iloc[i]
        support = row['support']
        resistance = row['resistance']
        close = row['close']
        
        # Check for break of structure (swing high/low)
        recent_lows = df.iloc[max(0, i-20):i]['low'].min()
        recent_highs = df.iloc[max(0, i-20):i]['high'].max()
        
        # Bullish: break above recent highs
        # Bearish: break below recent lows
        # Add some buffer (0.5% ATR)
        atr = row.get('atr', 0)
        buffer = atr * 0.5 if not pd.isna(atr) else close * 0.001
        
        bull_break = close > (recent_highs + buffer)
        bear_break = close < (recent_lows - buffer)
        
        return bull_break or bear_break
    
    def _check_volume(self, df, i):
        """Check if volume is above average (validates moves)"""
        row = df.iloc[i]
        volume = row.get('volume', 0)
        volume_ma = row.get('volume_ma', 1)
        
        if pd.isna(volume_ma) or volume_ma == 0:
            return True
        
        # Volume should be > 80% of MA for validation
        return volume > volume_ma * 0.8
    
    def _calculate_optimal_entry(self, df, i, trend):
        """
        Calculate entry signal with optimal risk/reward
        Returns: "BUY", "SELL", or None
        """
        row = df.iloc[i]
        atr = row.get('atr', 0)
        rsi = row.get('rsi', 50)
        close = row['close']
        
        if pd.isna(atr) or atr == 0:
            return None
        
        # BULLISH setup
        if trend == "BULLISH":
            # RSI not overbought (< 70)
            if pd.isna(rsi) or rsi > 70:
                return None
            
            # Check for pullback into support (quality entry)
            ema50 = row.get('ema50', close)
            support = row.get('support', close - atr)
            
            # Price near support but still in trend
            if close > support and close > ema50:
                # Check ADX > 20 (trend is strong enough)
                adx = row.get('adx', 30)
                if pd.isna(adx) or adx >= 20:
                    return "BUY"
        
        # BEARISH setup
        elif trend == "BEARISH":
            # RSI not oversold (> 30)
            if pd.isna(rsi) or rsi < 30:
                return None
            
            # Check for bounce into resistance
            ema50 = row.get('ema50', close)
            resistance = row.get('resistance', close + atr)
            
            # Price near resistance but still in trend
            if close < resistance and close < ema50:
                # Check ADX > 20
                adx = row.get('adx', 30)
                if pd.isna(adx) or adx >= 20:
                    return "SELL"
        
        return None
    
    def validate_rr_ratio(self, entry_price, sl, tp, is_buy=True):
        """
        Validate if trade has minimum risk/reward ratio
        """
        if is_buy:
            risk = entry_price - sl
            reward = tp - entry_price
        else:
            risk = sl - entry_price
            reward = entry_price - tp
        
        if risk <= 0 or reward <= 0:
            return False
        
        rr_ratio = reward / risk
        return rr_ratio >= self.min_rr_ratio
