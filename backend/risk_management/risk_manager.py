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
        self.max_trades = config.MAX_TRADES_PER_DAY  # FIX C-3: Was hardcoded 10, config says 5
        self.risk_per_trade_pct = 0.01 # 1%

        # FIX H-3: Removed stale hardcoded May 2026 news events — those dates are past and the check was dead.
        # News events are now loaded dynamically from Firestore at check-time.
        self.news_events = []  # Populated from Firestore: quantum_system/news_events

    def is_news_window(self):
        """Check if we are currently in a high-impact news window."""
        import datetime
        from datetime import timezone, timedelta
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        now = datetime.datetime.now(ist_tz).replace(tzinfo=None)
        
        # FIX H-3: Load news events from Firestore dynamically
        try:
            from backend.config.firebase_config import get_db
            db = get_db()
            if db:
                doc = db.collection("quantum_system").document("news_events").get()
                if doc.exists:
                    data = doc.to_dict()
                    self.news_events = data.get("events", [])
        except Exception:
            pass  # Use existing list if Firestore is unavailable
        
        for event_str in self.news_events:
            try:
                event_time = datetime.datetime.strptime(event_str, "%Y-%m-%d %H:%M")
                diff = abs((now - event_time).total_seconds() / 60)
                if diff <= 30:  # 30 min buffer around event
                    return True
            except ValueError:
                continue
        return False

    def is_restricted_time_window(self):
        import datetime
        from datetime import timezone, timedelta
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        now = datetime.datetime.now(ist_tz)
        # FIX H-4: Was blocking 9:15-9:30 which conflicts with morning killzone (9:15-10:45).
        # Now only blocks the first 5 min (price discovery), allowing killzone to operate from 9:20.
        if now.hour == 9 and 15 <= now.minute < 20:
            return True
        # Block 1:00 PM to 1:30 PM (European market open volatility)
        if now.hour == 13 and 0 <= now.minute < 30:
            return True
        return False

    def check_hard_locks(self, settings=None):
        """Global circuit breaker for the strategy."""
        settings = settings or {}
        if settings.get("use_time_restrictions", True) and self.is_restricted_time_window():
            return False, "Time Lock: Restricted trading window (Opening or Mid-day Lull)."

        if self.is_news_window():
            return False, "News Lock: High-impact event window active."
            
        if self.capital < (self.peak_capital * (1 - self.max_drawdown_pct)):
            return False, "Strategy Stop-Out: Max Drawdown Limit Hit."
        
        if self.daily_loss >= (self.capital * self.max_daily_loss_pct):
            return False, f"Daily Lock: Max Daily Loss Hit (Rs.{self.daily_loss:.2f})."

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
        # FIX C-3: daily_loss was inverted — losses were decreasing it (daily_loss -= negative_pnl = increase)
        # Now losses correctly accumulate as a positive value for comparison against threshold
        if pnl < 0:
            self.daily_loss += abs(pnl)  # Accumulate realized losses as positive total
            self.weekly_loss += abs(pnl)
        self.trades_today += 1
        
        self.capital += pnl
        if self.capital > self.peak_capital:
            self.peak_capital = self.capital
            
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

