import pandas as pd

class CorrelationEngine:
    def __init__(self):
        self.min_correlation = 0.7

    def check_index_alignment(self, nifty_df, banknifty_df):
        """Check if Nifty and BankNifty are moving in sync to avoid divergence traps."""
        if nifty_df is None or banknifty_df is None:
            return False  # FIX: Missing data = block trade (was: return True = allow)

        if nifty_df.empty or banknifty_df.empty:
            return False  # FIX: Same — empty data should block, not pass

        # FIX: Use pct_change(1) instead of pct_change(5)
        # pct_change(5) on a 5-row DataFrame returns NaN for all rows
        # pct_change(1) gives valid return for last candle
        nifty_ret = nifty_df['close'].pct_change(1).iloc[-1]
        banknifty_ret = banknifty_df['close'].pct_change(1).iloc[-1]

        # Guard against NaN values
        if nifty_ret != nifty_ret or banknifty_ret != banknifty_ret:
            return True  # NaN means insufficient history — allow trade

        # If one is strongly bullish and other is bearish, it's a divergence
        if (nifty_ret > 0.001 and banknifty_ret < -0.001) or \
           (nifty_ret < -0.001 and banknifty_ret > 0.001):
            return False  # Divergence detected

        return True  # Aligned
