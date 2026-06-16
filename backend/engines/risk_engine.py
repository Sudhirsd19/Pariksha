from backend.risk_management.risk_manager import RiskManager
from backend.config.config import config

class RiskEngine:
    """Risk management engine for trade execution."""
    
    def __init__(self):
        self.risk_manager = RiskManager()
        self.current_risk = 0.0
        self.trade_count = 0
    
    def can_trade(self):
        """Check if trading is allowed based on risk parameters.
        
        Returns:
            tuple: (bool, str) - (allowed, reason)
        """
        # Check daily loss limit
        if self.risk_manager.daily_pnl < -(self.risk_manager.capital * self.risk_manager.max_daily_loss_pct):
            return False, "Daily loss limit reached"
        
        # Check weekly loss limit
        if self.risk_manager.weekly_loss < -(self.risk_manager.capital * self.risk_manager.max_weekly_loss_pct):
            return False, "Weekly loss limit reached"
        
        # Check max drawdown
        if self.risk_manager.capital < self.risk_manager.peak_capital * (1 - self.risk_manager.max_drawdown_pct):
            return False, "Max drawdown limit reached"
        
        # Check consecutive losses
        if self.risk_manager.consecutive_losses >= self.risk_manager.max_consecutive_losses:
            return False, f"Max consecutive losses ({self.risk_manager.max_consecutive_losses}) reached"
        
        # Check max trades per day
        if self.risk_manager.trades_today >= self.risk_manager.max_trades:
            return False, f"Max trades per day ({self.risk_manager.max_trades}) reached"
        
        # Check if in news window
        if self.risk_manager.is_news_window():
            return False, "News event window - trading disabled"
        
        return True, "Ready"
    
    def get_current_risk(self):
        """Get current risk amount for position sizing.
        
        Returns:
            float: Risk amount per trade
        """
        self.current_risk = self.risk_manager.capital * self.risk_manager.risk_per_trade_pct
        return self.current_risk
    
    def update_pnl(self, pnl):
        """Update PnL after trade execution.
        
        Args:
            pnl (float): Profit/Loss amount
        """
        self.risk_manager.daily_pnl += pnl
        self.risk_manager.weekly_loss += pnl if pnl < 0 else 0
        self.risk_manager.capital += pnl
        
        # Update peak capital for drawdown calculation
        if self.risk_manager.capital > self.risk_manager.peak_capital:
            self.risk_manager.peak_capital = self.risk_manager.capital
        
        # Track consecutive losses
        if pnl < 0:
            self.risk_manager.consecutive_losses += 1
        else:
            self.risk_manager.consecutive_losses = 0
        
        self.trade_count += 1
        self.risk_manager.trades_today += 1
    
    def reset_daily_limits(self):
        """Reset daily counters."""
        self.risk_manager.daily_pnl = 0.0
        self.risk_manager.trades_today = 0
        self.risk_manager.consecutive_losses = 0
    
    def reset_weekly_limits(self):
        """Reset weekly counters."""
        self.risk_manager.weekly_loss = 0
        self.reset_daily_limits()
