import time
import pandas as pd

class ExecutionEngine:
    def __init__(self):
        self.entry_time = None
        self.max_hold_time_mins = 25
        self.trailing_sl = None
        self.partial_booked = False
        self.peak_pnl_pct = 0.0

    def check_fvg_retest(self, current_price, fvgs, side):
        """Wait for price to retrace into the FVG zone for entry."""
        if not fvgs: return False
        
        last_fvg = fvgs[-1]
        if side == "BUY" and last_fvg['type'] == "BULLISH":
            return current_price <= last_fvg['top'] and current_price >= last_fvg['bottom']
        elif side == "SELL" and last_fvg['type'] == "BEARISH":
            return current_price >= last_fvg['bottom'] and current_price <= last_fvg['top']
            
        return False

    def check_time_exit(self):
        """Exit if no momentum within defined hold time."""
        if not self.entry_time: return False
        
        elapsed = (time.time() - self.entry_time) / 60
        if elapsed > self.max_hold_time_mins:
            return True
        return False

    def check_partial_profit(self, current_price, entry_price, side) -> bool:
        """Check if PnL is >= 1% to trigger partial profit booking (50% position)."""
        if not entry_price or entry_price <= 0:
            return False
            
        pnl_pct = (current_price - entry_price) / entry_price * 100
        if side == "SELL":
            pnl_pct = -pnl_pct
            
        self.peak_pnl_pct = max(self.peak_pnl_pct, pnl_pct)
        
        if pnl_pct >= 1.0 and not self.partial_booked:
            self.partial_booked = True
            return True
        return False

    def check_score_decay_exit(self, current_score, entry_score) -> bool:
        """Exit if signal strength drops >50% of entry score (reversal guard)."""
        if entry_score and entry_score > 0:
            if current_score < (entry_score * 0.5):
                return True
        return False

    def update_trailing_sl(self, current_price, atr, side, phase):
        """Dynamic ATR-based trailing stop with tighter trail in good profit."""
        if self.peak_pnl_pct > 1.0:
            mult = 1.0  # Lock in gains when in deep profit (>1%)
        else:
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
        self.partial_booked = False
        self.peak_pnl_pct = 0.0
