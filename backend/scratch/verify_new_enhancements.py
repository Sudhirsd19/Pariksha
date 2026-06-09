import sys
import os
import unittest
import pandas as pd
import numpy as np
import datetime
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# Mock firebase configuration to avoid hanging
import backend.config.firebase_config
backend.config.firebase_config.get_db = lambda: None

from backend.risk_management.risk_manager import RiskManager
from backend.engines.signal_engine import SignalEngine
from backend.engines.stock_analyzer import StockAnalyzer
from backend.utils.token_manager import token_manager

class TestNewIntradayEnhancements(unittest.TestCase):
    def test_daily_profit_cap_lock(self):
        """Verify that RiskManager locks trading when daily profit cap is exceeded."""
        rm = RiskManager(initial_capital=100000)
        rm.daily_pnl = 3500.0  # Rs. 3500 profit (3.5% of 100,000)
        
        # 1. 4% cap check (profit 3.5% should be SAFE)
        can_trade, reason = rm.check_hard_locks({"daily_profit_cap_pct": 0.04})
        self.assertTrue(can_trade)
        self.assertEqual(reason, "Safe")
        
        # 2. 3% cap check (profit 3.5% should be BLOCKED)
        can_trade, reason = rm.check_hard_locks({"daily_profit_cap_pct": 0.03})
        self.assertFalse(can_trade)
        self.assertIn("Daily Profit Cap Lock", reason)

    def test_equity_position_sizing(self):
        """Verify that position sizing does not round to index lot sizes for Equities."""
        rm = RiskManager(initial_capital=100000)
        rm.risk_per_trade_pct = 0.01  # 1% risk = Rs. 1000
        
        # For NIFTY (Index), standard lot size applies (e.g. 25 or 50 or dynamically resolved like 65)
        # Risk per index unit = Rs. 10. Qty = 1000 / 10 = 100 units
        lot_size = token_manager.get_lotsize("NIFTY")
        qty_idx = rm.calculate_position_size(24000.0, 23990.0, symbol="NIFTY")
        self.assertEqual(qty_idx % lot_size, 0)
        
        # For SBIN (Equity), lot size should be 1 (cash segment)
        # Entry = 800, SL = 790 (risk is Rs. 10). Qty = 1000 / 10 = 100 shares (exactly)
        qty_eq = rm.calculate_position_size(800.0, 790.0, symbol="SBIN-EQ")
        self.assertEqual(qty_eq, 100)

    def test_adx_trend_filtering(self):
        """Verify ADX indicator calculation logic under SignalEngine."""
        engine = SignalEngine()
        
        # Build mock dataframe with high trend
        times = [f"2026-06-09 09:{i:02d}" for i in range(15, 60, 5)]
        closes = [100.0 + i * 2.0 for i in range(len(times))] # strongly trending up
        highs = [c + 1.0 for c in closes]
        lows = [c - 1.0 for c in closes]
        opens = [c - 2.0 for c in closes]
        
        df = pd.DataFrame({
            "time": times,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1000] * len(times)
        })
        
        adx_val = engine.calculate_adx(df, period=5)
        self.assertIsNotNone(adx_val)
        self.assertTrue(isinstance(adx_val, float))

    def test_token_manager_expiry_rollover(self):
        """Verify that TokenManager rolls over to next weekly option on Expiry Day."""
        # Set up mock options_index in token_manager
        today = datetime.date.today()
        next_week = today + datetime.timedelta(days=7)
        
        token_manager.options_index = {
            "NIFTY": {
                "CE": {
                    24000: [
                        {"token": "1001", "symbol": "NIFTY_TODAY", "lotsize": 25, "expiry": today},
                        {"token": "1002", "symbol": "NIFTY_NEXT_WEEK", "lotsize": 25, "expiry": next_week}
                    ]
                }
            }
        }
        
        # 1. On expiry day (or if force_next_weekly=True), it should return next week's contract (token "1002")
        contract = token_manager.get_atm_option("NIFTY", 24010.0, "CE")
        self.assertIsNotNone(contract)
        self.assertEqual(contract["token"], "1002")
        self.assertEqual(contract["symbol"], "NIFTY_NEXT_WEEK")

if __name__ == "__main__":
    unittest.main()
