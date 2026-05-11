import pandas as pd
import numpy as np

class TechnicalIndicators:
    @staticmethod
    def add_ema(df: pd.DataFrame, length: int) -> pd.DataFrame:
        df[f'EMA_{length}'] = df['close'].ewm(span=length, adjust=False).mean()
        return df

    @staticmethod
    def add_rsi(df: pd.DataFrame, length: int = 14) -> pd.DataFrame:
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=length).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=length).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
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
        plus_dm = df['high'].diff()
        minus_dm = df['low'].diff()
        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm > 0] = 0
        
        tr = pd.concat([df['high'] - df['low'], 
                        np.abs(df['high'] - df['close'].shift()), 
                        np.abs(df['low'] - df['close'].shift())], axis=1).max(axis=1)
        atr = tr.rolling(window=length).mean()
        
        plus_di = 100 * (plus_dm.rolling(window=length).mean() / atr)
        minus_di = 100 * (np.abs(minus_dm).rolling(window=length).mean() / atr)
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        df['ADX'] = dx.rolling(window=length).mean()
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

    @classmethod
    def apply_all(cls, df: pd.DataFrame) -> pd.DataFrame:
        df = cls.add_ema(df, 20)
        df = cls.add_ema(df, 50)
        df = cls.add_rsi(df)
        df = cls.add_atr(df)
        df = cls.add_vwap(df)
        df = cls.add_adx(df)
        df = cls.add_supertrend(df)
        return df
