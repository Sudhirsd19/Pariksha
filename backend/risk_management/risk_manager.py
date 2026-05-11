from config.config import config

class RiskManager:
    def __init__(self, initial_capital=10000):
        self.capital = initial_capital
        self.daily_loss = 0
        self.consecutive_losses = 0
        self.max_consecutive_losses = 3
        
        # Exposure Management
        self.long_exposure = 0
        self.short_exposure = 0
        self.max_directional_exposure = 3 # Max 3 trades in one direction
        
        # INSTITUTIONAL LIMITS (₹10,000 CAPITAL)
        self.max_daily_loss = 5000 # Increased for testing
        self.max_loss_per_trade = 1000 
        self.trades_today = 0
        self.max_trades = 10 # Increased to 10 for better testing coverage
        self.risk_per_trade_pct = 0.01 # 1%

    def can_trade(self, side=None) -> bool:
        if self.daily_loss >= self.max_daily_loss:
            print(f"[RiskManager] STOPPED: Daily loss limit hit (₹{self.daily_loss:.2f})")
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
        from utils.token_manager import token_manager
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
