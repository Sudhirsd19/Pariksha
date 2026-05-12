import pandas as pd

class CorrelationEngine:
    def __init__(self):
        self.min_correlation = 0.7

    def check_index_alignment(self, nifty_df, banknifty_df):
        """Check if Nifty and BankNifty are moving in sync to avoid divergence traps."""
        if nifty_df.empty or banknifty_df.empty:
            return True # Default to True if data is missing

        # Calculate returns over last 5 candles
        nifty_ret = nifty_df['close'].pct_change(5).iloc[-1]
        banknifty_ret = banknifty_df['close'].pct_change(5).iloc[-1]

        # If one is strongly bullish and other is bearish, it's a divergence
        if (nifty_ret > 0.001 and banknifty_ret < -0.001) or \
           (nifty_ret < -0.001 and banknifty_ret > 0.001):
            return False # Divergence detected

        return True # Aligned
