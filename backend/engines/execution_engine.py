import time
import pandas as pd

class ExecutionEngine:
    def __init__(self):
        self.entry_time = None
        self.max_hold_time_mins = 25
        self.trailing_sl = None

    def check_fvg_retest(self, current_price, fvgs, side):
        """Wait for price to retrace into the FVG zone for entry."""
        if not fvgs: return False
        
        last_fvg = fvgs[-1]
        if side == "BUY" and last_fvg['type'] == "BULLISH":
            # Entry when price touches the top of Bullish FVG
            return current_price <= last_fvg['top'] and current_price >= last_fvg['bottom']
        elif side == "SELL" and last_fvg['type'] == "BEARISH":
            # Entry when price touches the bottom of Bearish FVG
            return current_price >= last_fvg['bottom'] and current_price <= last_fvg['top']
            
        return False

    def check_time_exit(self):
        """Exit if no momentum within defined hold time."""
        if not self.entry_time: return False
        
        elapsed = (time.time() - self.entry_time) / 60
        if elapsed > self.max_hold_time_mins:
            return True # Exit trade
        return False

    def update_trailing_sl(self, current_price, atr, side, phase):
        """Dynamic ATR-based trailing stop."""
        mult = 1.5 if phase == "EXPANSION" else 2.5 # Tight trail during expansion
        
        if side == "BUY":
            new_sl = current_price - (atr * mult)
            if self.trailing_sl is None or new_sl > self.trailing_sl:
                self.trailing_sl = new_sl
        else:
            new_sl = current_price + (atr * mult)
            if self.trailing_sl is None or new_sl < self.trailing_sl:
                self.trailing_sl = new_sl
                
        return self.trailing_sl

    def reset(self):
        self.entry_time = None
        self.trailing_sl = None
