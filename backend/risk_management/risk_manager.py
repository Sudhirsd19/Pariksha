from backend.config.config import config

class RiskManager:
    def __init__(self, initial_capital=10000):
        self.capital = initial_capital
        self.peak_capital = initial_capital
        self.daily_loss = 0
        self.weekly_loss = 0
        self.consecutive_losses = 0
        self.max_consecutive_losses = 3
        
        # Exposure Management
        self.long_exposure = 0
        self.short_exposure = 0
        self.max_directional_exposure = 3 # Max 3 trades in one direction
        
        # INSTITUTIONAL LIMITS
        self.max_daily_loss_pct = 0.02 # 2%
        self.max_weekly_loss_pct = 0.05 # 5%
        self.max_drawdown_pct = 0.10 # 10%
        self.trades_today = 0
        self.max_trades = 10 
        self.risk_per_trade_pct = 0.01 # 1%

        # High Impact News Windows (Mock)
        self.news_events = [
            "2026-05-15 10:00",
            "2026-05-20 14:30",
        ]

    def is_news_window(self):
        """Check if we are currently in a high-impact news window."""
        import datetime
        now = datetime.datetime.now()
        for event_str in self.news_events:
            event_time = datetime.datetime.strptime(event_str, "%Y-%m-%d %H:%M")
            diff = abs((now - event_time).total_seconds() / 60)
            if diff <= 30: # 30 min buffer
                return True
        return False

    def check_hard_locks(self):
        """Global circuit breaker for the strategy."""
        if self.is_news_window():
            return False, "News Lock: High-impact event window active."
            
        if self.capital < (self.peak_capital * (1 - self.max_drawdown_pct)):
            return False, "Strategy Stop-Out: Max Drawdown Limit Hit."
        
        if self.daily_loss >= (self.capital * self.max_daily_loss_pct):
            return False, f"Daily Lock: Max Daily Loss Hit (₹{self.daily_loss:.2f})."

        if self.weekly_loss >= (self.capital * self.max_weekly_loss_pct):
            return False, "Weekly Lock: Max Weekly Loss Hit."
            
        return True, "Safe"

    def can_trade(self, side=None) -> bool:
        can_trade_global, reason = self.check_hard_locks()
        if not can_trade_global:
            print(f"[RiskManager] BLOCKED: {reason}")
            return False
        if self.trades_today >= self.max_trades:
            print(f"[RiskManager] STOPPED: Max daily trades reached ({self.trades_today}/{self.max_trades})")
            return False
        if self.consecutive_losses >= self.max_consecutive_losses:
            print(f"[RiskManager] STOPPED: Consecutive loss limit hit ({self.consecutive_losses})")
            return False
            
        # Directional Exposure Check
        if side == "BUY" and self.long_exposure >= self.max_directional_exposure:
            print(f"[RiskManager] BLOCKED: Max Long exposure reached")
            return False
        if side == "SELL" and self.short_exposure >= self.max_directional_exposure:
            print(f"[RiskManager] BLOCKED: Max Short exposure reached")
            return False
            
        return True

    def calculate_position_size(self, entry, sl, symbol="NIFTY"):
        risk_per_share = abs(entry - sl)
        if risk_per_share == 0:
            return 0

        # Use dynamic risk_per_trade_pct if set from Firebase, else fallback to config
        risk_pct = getattr(self, 'risk_per_trade_pct', config.RISK_PER_TRADE)
        total_risk = self.capital * risk_pct
        
        raw_quantity = int(total_risk / risk_per_share)
        
        # Get correct lot size from token_manager (2026: Nifty=65, BankNifty=30)
        from backend.utils.token_manager import token_manager
        lot_size = token_manager.get_lotsize(symbol)
        
        # Round down to nearest lot
        lots = raw_quantity // lot_size
        if lots < 1: lots = 1 # Minimum 1 lot
        
        return lots * lot_size

    def update_pnl(self, pnl, side=None):
        """Updates daily trackers and exposure."""
        self.daily_loss -= pnl 
        self.trades_today += 1
        
        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        # Decrement exposure when trade closes
        if side == "BUY": self.long_exposure = max(0, self.long_exposure - 1)
        if side == "SELL": self.short_exposure = max(0, self.short_exposure - 1)

    def record_entry(self, side):
        if side == "BUY": self.long_exposure += 1
        if side == "SELL": self.short_exposure += 1

    def reset_daily(self):
        self.daily_loss = 0
        self.trades_today = 0
        self.consecutive_losses = 0
        self.long_exposure = 0
        self.short_exposure = 0

