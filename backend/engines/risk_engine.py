import datetime

class RiskEngine:
    def __init__(self, initial_capital=10000):
        self.initial_capital = initial_capital
        self.equity = initial_capital
        
        # Risk Limits
        self.max_daily_loss_pct = 0.02  # 2%
        self.max_weekly_loss_pct = 0.05 # 5%
        self.max_monthly_loss_pct = 0.10 # 10%

        # High Impact News Windows (Mock)
        self.news_events = [
            "2026-05-15 10:00",
            "2026-05-20 14:30",
        ]

    def is_news_window(self):
        """Check if we are currently in a high-impact news window."""
        now = datetime.datetime.now()
        for event_str in self.news_events:
            event_time = datetime.datetime.strptime(event_str, "%Y-%m-%d %H:%M")
            diff = abs((now - event_time).total_seconds() / 60)
            if diff <= 30: # 30 min buffer
                return True
        return False
        
        # PnL Tracking
        self.daily_pnl = 0
        self.weekly_pnl = 0
        self.monthly_pnl = 0
        self.consecutive_losses = 0
        
        # Equity Protection
        self.peak_equity = initial_capital
        self.max_drawdown_limit = 0.15 # 15% Max DD stop-out

    def calculate_vol_adjusted_qty(self, entry_price, stop_loss_price, atr):
        """Dynamic position sizing based on ATR volatility and fixed risk."""
        risk_amount = self.get_current_risk_amount()
        sl_points = abs(entry_price - stop_loss_price)
        
        # If SL is too wide relative to ATR, skip or reduce
        if sl_points > (atr * 3):
            return 0 # Volatility too high for this setup
            
        qty = risk_amount / sl_points
        return int(qty)

    def get_current_risk_amount(self):
        """Reduce risk if in a losing streak or near drawdown limit."""
        base_risk = self.equity * 0.01 # 1%
        
        # Adaptive reduction
        if self.consecutive_losses >= 2:
            base_risk *= 0.5
        
        # Hard lock check
        if self.daily_pnl <= -(self.equity * self.max_daily_loss_pct) or \
           self.weekly_pnl <= -(self.equity * self.max_weekly_loss_pct):
            return 0
            
        return base_risk

    def check_hard_locks(self):
        """Global circuit breaker for the strategy."""
        if self.is_news_window():
            return False, "News Lock: High-impact event window active."
            
        if self.equity < (self.peak_equity * (1 - self.max_drawdown_limit)):
            return False, "Strategy Stop-Out: Max Drawdown Limit Hit."
        
        if self.weekly_pnl <= -(self.equity * self.max_weekly_loss_pct):
            return False, "Weekly Lock: Max Weekly Loss Hit."
            
        return True, "Safe"
