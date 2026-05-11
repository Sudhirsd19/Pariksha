from datetime import datetime, timedelta

class CooldownEngine:
    def __init__(self, minutes=5):
        self.cooldown_period = timedelta(minutes=minutes)
        self.last_trade_time = None

    def can_trade(self) -> bool:
        if self.last_trade_time is None:
            return True
            
        if datetime.now() - self.last_trade_time > self.cooldown_period:
            return True
            
        return False

    def update_last_trade(self):
        self.last_trade_time = datetime.now()
