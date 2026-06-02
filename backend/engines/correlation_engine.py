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

    def check_heavyweight_alignment(self, symbol, index_df, heavyweight_df):
        """
        Check if the Index and its Heavyweight component are aligned.
        For NIFTY -> Reliance
        For BANKNIFTY -> HDFC Bank
        """
        if index_df is None or heavyweight_df is None:
            return False
        if index_df.empty or heavyweight_df.empty:
            return False

        index_ret = index_df['close'].pct_change(1).iloc[-1]
        heavyweight_ret = heavyweight_df['close'].pct_change(1).iloc[-1]

        if index_ret != index_ret or heavyweight_ret != heavyweight_ret:
            return True

        # If Index is pumping but Heavyweight is dumping => Fake Breakout (Trap)
        if (index_ret > 0.001 and heavyweight_ret < -0.0005) or \
           (index_ret < -0.001 and heavyweight_ret > 0.0005):
            print(f"[CorrelationGuard] TRAP AVOIDED: {symbol} diverging from its Heavyweight.")
            return False

        return True
