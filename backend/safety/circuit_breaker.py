import logging

class CircuitBreaker:
    def __init__(self):
        self.mode = "NORMAL" # NORMAL, SAFE, RISK_OFF, HARD_STOP
        self.fail_count = 0
        self.max_fails = 3
        self.latency_threshold_ms = 500

    def check_market_conditions(self, vix, spread_pct, slippage_avg):
        """Monitor for dangerous market regimes."""
        if vix > 30 or spread_pct > 0.05: # High VIX or Abnormal Spread
            self.trigger_safe_mode("Extreme Volatility / Spread Widening")
        
        if slippage_avg > 0.02: # 2% Slippage is unacceptable
            self.trigger_safe_mode("Excessive Slippage Spike")

    def check_system_health(self, latency, api_success):
        """Monitor technical stability."""
        if not api_success:
            self.fail_count += 1
        else:
            self.fail_count = 0

        if self.fail_count >= self.max_fails:
            self.trigger_hard_stop("Repeated API Failures")
        
        if latency > self.latency_threshold_ms:
            self.trigger_safe_mode("High Latency Spike")

    def trigger_safe_mode(self, reason):
        if self.mode != "HARD_STOP":
            self.mode = "SAFE"
            logging.warning(f"CIRCUIT BREAKER: Entering SAFE MODE. Reason: {reason}")

    def trigger_hard_stop(self, reason):
        self.mode = "HARD_STOP"
        logging.critical(f"CIRCUIT BREAKER: TRIGGERING HARD STOP! Reason: {reason}")
        # Call global liquidation logic here

    def can_enter_trade(self):
        return self.mode == "NORMAL"
