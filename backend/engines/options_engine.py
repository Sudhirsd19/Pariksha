import numpy as np
from scipy.stats import norm

class OptionsEngine:
    def __init__(self):
        self.risk_free_rate = 0.07 # 7% for Indian market
        self.min_liquidity_threshold = 1000 # Min Open Interest or Volume

    def black_scholes(self, S, K, T, v, r, option_type='call'):
        """Calculate theoretical price and Greeks."""
        if T <= 0: return 0, 0, 0
        
        d1 = (np.log(S / K) + (r + 0.5 * v**2) * T) / (v * np.sqrt(T))
        d2 = d1 - v * np.sqrt(T)
        
        if option_type == 'call':
            price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
            delta = norm.cdf(d1)
        else:
            price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
            delta = norm.cdf(d1) - 1
            
        theta = -(S * norm.pdf(d1) * v / (2 * np.sqrt(T))) - r * K * np.exp(-r * T) * norm.cdf(d2)
        
        return price, delta, theta / 365 # Daily Theta

    def select_best_strike(self, spot_price, option_type, chain_data):
        """
        Institutional Strike Selection:
        - Prefer Delta between 0.45 and 0.55 (ATM/Slightly ITM).
        - Filter by Liquidity (Spread < 2% and OI > threshold).
        """
        best_strike = None
        min_diff = float('inf')
        
        for strike in chain_data:
            # 1. Liquidity Filter
            if strike['spread_pct'] > 0.02 or strike['oi'] < self.min_liquidity_threshold:
                continue
            
            # 2. Delta Alignment (Target 0.5 for ATM)
            # Placeholder: In real-time, you'd calculate Delta for each strike
            delta_dist = abs(strike['delta'] - 0.5) if option_type == 'call' else abs(strike['delta'] + 0.5)
            
            if delta_dist < min_diff:
                min_diff = delta_dist
                best_strike = strike
                
        return best_strike

    def check_iv_crush_risk(self, current_iv, avg_iv, event_upcoming=False):
        """Avoid buying premiums if IV is at a multi-day peak (Pre-Earnings/RBI)."""
        if event_upcoming and current_iv > (avg_iv * 1.5):
            return True # High risk of IV Crush post-event
        return False

    def premium_decay_monitor(self, entry_price, current_theta, hold_time_mins):
        """Exit if Theta decay is eating > 10% of premium without price movement."""
        total_decay = current_theta * (hold_time_mins / 1440)
        if abs(total_decay) > (entry_price * 0.10):
            return True # Force exit due to excessive decay
        return False
