import pandas as pd
import numpy as np

class TechnicalIndicators:
    @staticmethod
    def add_ema(df: pd.DataFrame, length: int) -> pd.DataFrame:
        df[f'EMA_{length}'] = df['close'].ewm(span=length, adjust=False).mean()
        return df

    @staticmethod
    def add_rsi(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
        """Wilder's RSI — matches TradingView / standard charting tools."""
        delta = df['close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        # Wilder's smoothing: EWM with alpha = 1/length, adjust=False
        avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df['RSI'] = 100 - (100 / (1 + rs))
        df['RSI'] = df['RSI'].fillna(50)  # Neutral fallback for initial NaN
        return df

    @staticmethod
    def add_atr(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        df['ATR'] = true_range.rolling(window=length).mean()
        return df

    @staticmethod
    def add_vwap(df: pd.DataFrame) -> pd.DataFrame:
        v = df['volume']
        p = (df['high'] + df['low'] + df['close']) / 3
        df['VWAP'] = (p * v).cumsum() / v.cumsum()
        return df

    @staticmethod
    def add_adx(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
        """Wilder's ADX — proper +DM/-DM directional comparison."""
        up_move   = df['high'] - df['high'].shift(1)
        down_move = df['low'].shift(1) - df['low']

        plus_dm  = pd.Series(np.where((up_move > down_move) & (up_move > 0),   up_move,   0.0), index=df.index)
        minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)

        tr = pd.concat([
            df['high'] - df['low'],
            np.abs(df['high'] - df['close'].shift(1)),
            np.abs(df['low']  - df['close'].shift(1))
        ], axis=1).max(axis=1)

        # Wilder's smoothing
        atr      = tr.ewm(alpha=1/length,       min_periods=length, adjust=False).mean()
        plus_di  = 100 * plus_dm.ewm(alpha=1/length,  min_periods=length, adjust=False).mean() / atr
        minus_di = 100 * minus_dm.ewm(alpha=1/length, min_periods=length, adjust=False).mean() / atr

        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di).replace(0, np.nan)
        df['ADX']      = dx.ewm(alpha=1/length, min_periods=length, adjust=False).mean().fillna(0)
        df['PLUS_DI']  = plus_di.fillna(0)
        df['MINUS_DI'] = minus_di.fillna(0)
        return df

    @staticmethod
    def add_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
        hl2 = (df['high'] + df['low']) / 2
        # Use existing ATR if available, else calculate
        if 'ATR' not in df.columns:
            tr = pd.concat([df['high'] - df['low'], 
                            np.abs(df['high'] - df['close'].shift()), 
                            np.abs(df['low'] - df['close'].shift())], axis=1).max(axis=1)
            atr = tr.rolling(window=period).mean()
        else:
            atr = df['ATR']

        upperband = hl2 + (multiplier * atr)
        lowerband = hl2 - (multiplier * atr)
        
        df['Supertrend'] = True
        df['ST_Upper'] = upperband
        df['ST_Lower'] = lowerband
        
        # This is a simplified Supertrend logic for vectorization
        for i in range(1, len(df)):
            if df['close'].iloc[i] > df['ST_Upper'].iloc[i-1]:
                df.at[df.index[i], 'Supertrend'] = True
            elif df['close'].iloc[i] < df['ST_Lower'].iloc[i-1]:
                df.at[df.index[i], 'Supertrend'] = False
            else:
                df.at[df.index[i], 'Supertrend'] = df['Supertrend'].iloc[i-1]
        
        return df

    @staticmethod
    def add_macd(df: pd.DataFrame, fast=12, slow=26, signal=9) -> pd.DataFrame:
        exp1 = df['close'].ewm(span=fast, adjust=False).mean()
        exp2 = df['close'].ewm(span=slow, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['MACD_Signal'] = df['MACD'].ewm(span=signal, adjust=False).mean()
        df['MACD_Hist'] = df['MACD'] - df['MACD_Signal']
        return df

    @classmethod
    def apply_all(cls, df: pd.DataFrame) -> pd.DataFrame:
        df = cls.add_ema(df, 9)
        df = cls.add_ema(df, 20)
        df = cls.add_ema(df, 50)
        df = cls.add_rsi(df)
        df = cls.add_atr(df)
        df = cls.add_vwap(df)
        df = cls.add_adx(df)
        df = cls.add_macd(df)
        df = cls.add_supertrend(df)
        return df
