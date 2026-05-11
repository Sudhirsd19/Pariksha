from datetime import datetime, time
import pandas as pd
from config.config import config

class SessionFilter:
    @staticmethod
    def is_within_session() -> bool:
        from config.config import config
        
        # Allow trading outside hours ONLY in paper trading mode
        if config.PAPER_TRADING:
            return True
        
        now = datetime.now().time()
        
        # Morning Session: 9:20 AM to 11:30 AM
        s1_start = time(9, 20)
        s1_end = time(11, 30)
        
        # Afternoon Session: 1:45 PM to 3:00 PM
        s2_start = time(13, 45)
        s2_end = time(15, 0)

        if (s1_start <= now <= s1_end) or (s2_start <= now <= s2_end):
            return True
        return False

class VolatilityFilter:
    @staticmethod
    def is_volatile_enough(df: pd.DataFrame, threshold=0.0003) -> bool:
        """Check if ATR is above a certain percentage of price.
        0.0003 = 0.03% of price (~7 points on NIFTY). Safe minimum for 5m candles.
        """
        if df is None or df.empty or 'ATR' not in df.columns:
            return False
            
        last_atr = df['ATR'].iloc[-1]
        last_price = df['close'].iloc[-1]
        
        if last_price == 0:
            return False

        ratio = last_atr / last_price
        is_volatile = ratio > threshold
        if not is_volatile:
            print(f"[VolatilityFilter] BLOCKED: ATR={last_atr:.2f}, Price={last_price:.2f}, Ratio={ratio:.6f} (need >{threshold})")
        return is_volatile
