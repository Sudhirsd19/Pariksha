import pandas as pd
import time

class OIEngine:
    def __init__(self):
        # We will cache the Open Interest data here
        self.options_chain = {}
        self.last_update_time = 0

    def fetch_options_chain(self, symbol, smart_api):
        """
        Placeholder for fetching live options chain data from Angel One.
        Real implementation requires a data pipeline or a third-party source
        (like Sensibull/Opstra API) as retail broker APIs limit OI fetches.
        """
        # TODO: Implement real-time fetch logic using smart_api.getOptionChain()
        pass

    def calculate_pcr(self, symbol):
        """
        Calculate Put-Call Ratio (PCR).
        PCR > 1.0 => Bullish
        PCR < 0.8 => Bearish
        """
        if symbol not in self.options_chain:
            return 1.0  # Neutral fallback

        chain_data = self.options_chain[symbol]
        total_ce_oi = sum([strike['ce_oi'] for strike in chain_data])
        total_pe_oi = sum([strike['pe_oi'] for strike in chain_data])

        if total_ce_oi == 0:
            return 1.0
        
        pcr = total_pe_oi / total_ce_oi
        return round(pcr, 2)

    def calculate_max_pain(self, symbol):
        """
        Calculate the Max Pain strike price (where options buyers lose maximum money).
        Institutional sellers tend to push the expiry price towards Max Pain.
        """
        if symbol not in self.options_chain:
            return 0.0
        
        # TODO: Implement Max pain logic by iterating over strikes and calculating total intrinsic value
        return 0.0

    def is_oi_supportive(self, symbol, side):
        """
        Checks if the Open Interest supports the trade direction.
        Used as a final filter before placing a trade.
        """
        pcr = self.calculate_pcr(symbol)
        
        if side == "BUY":
            # If we want to go Long, PCR should ideally be > 0.85
            if pcr < 0.8:
                print(f"[OIEngine] TRAP ALERT: Rejecting BUY on {symbol}. PCR is too low ({pcr}). Call writers dominate.")
                return False
        elif side == "SELL":
            # If we want to go Short, PCR should ideally be < 1.15
            if pcr > 1.2:
                print(f"[OIEngine] TRAP ALERT: Rejecting SELL on {symbol}. PCR is too high ({pcr}). Put writers dominate.")
                return False
                
        return True

oi_engine = OIEngine()
