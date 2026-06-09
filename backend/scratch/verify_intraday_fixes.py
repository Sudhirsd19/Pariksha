import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import unittest
from unittest.mock import MagicMock, patch, AsyncMock

# Monkey-patch get_db to return None to avoid Firestore hangs
import backend.config.firebase_config
backend.config.firebase_config.get_db = lambda: None

from backend.utils.trade_manager import TradeManager
from backend.risk_management.risk_manager import RiskManager
from backend.engines.cooldown_engine import CooldownEngine
from backend.main import execute_stock_trade, risk_manager

class TestIntradayFixes(unittest.IsolatedAsyncioTestCase):
    def test_trailing_sl_breakeven_buy(self):
        """Verify that BUY stop loss moves to breakeven at 50% target progress (1:1 RR)"""
        tm = TradeManager()
        tm.risk_manager = MagicMock()
        
        # BUY Trade setup: Entry=100, Target=104, SL=98 (1:2 Risk:Reward, risk is 2, target is 4)
        trade = {
            "id": "1",
            "symbol": "SBIN",
            "token": "3045",
            "signal": "BUY",
            "entry": 100.0,
            "sl": 98.0,
            "tp": 104.0,
            "qty": 50,
            "status": "OPEN"
        }
        tm.active_trades = [trade]
        
        # 1. Price is at 101. Profit is 1.0 (50% of risk is not reached yet)
        # Target distance is 4.0. 50% target progress is 2.0 (price 102.0)
        tm.monitor_trades({"3045": 101.0})
        self.assertEqual(tm.active_trades[0]["sl"], 98.0) # SL shouldn't change
        
        # 2. Price is at 102.0 (exactly 50% target progress achieved / 1:1 RR)
        tm.monitor_trades({"3045": 102.0})
        self.assertEqual(tm.active_trades[0]["sl"], 100.0) # SL should be moved to breakeven (entry=100.0)

    def test_trailing_sl_breakeven_sell(self):
        """Verify that SELL stop loss moves to breakeven at 50% target progress (1:1 RR)"""
        tm = TradeManager()
        tm.risk_manager = MagicMock()
        
        # SELL Trade setup: Entry=100, Target=96, SL=102 (1:2 Risk:Reward, risk is 2, target is 4)
        trade = {
            "id": "2",
            "symbol": "SBIN",
            "token": "3045",
            "signal": "SELL",
            "entry": 100.0,
            "sl": 102.0,
            "tp": 96.0,
            "qty": 50,
            "status": "OPEN"
        }
        tm.active_trades = [trade]
        
        # 1. Price is at 99.0. Profit is 1.0 (50% of risk is not reached yet)
        tm.monitor_trades({"3045": 99.0})
        self.assertEqual(tm.active_trades[0]["sl"], 102.0) # SL shouldn't change
        
        # 2. Price is at 98.0 (exactly 50% target progress achieved / 1:1 RR)
        tm.monitor_trades({"3045": 98.0})
        self.assertEqual(tm.active_trades[0]["sl"], 100.0) # SL should be moved to breakeven (entry=100.0)

    @patch('backend.main.broker')
    @patch('backend.main.db_manager')
    async def test_execute_stock_trade_risk_blocking(self, mock_db, mock_broker):
        """Verify that execute_stock_trade blocks manual trades when RiskManager is locked"""
        # Mock settings
        mock_db.get_settings.return_value = {"capital_limit": 10000}
        
        # Force a daily loss lock on global risk_manager
        risk_manager.daily_loss = 5000.0 # High loss
        risk_manager.capital = 100000.0
        risk_manager.max_daily_loss_pct = 0.02 # 2% is 2000.0 limit
        
        # Execute stock trade should return error
        res = await execute_stock_trade("SBIN", "BUY", 10, MagicMock())
        self.assertEqual(res["status"], "error")
        self.assertIn("Blocked by Risk Manager", res["message"])
        
        # Reset daily loss to allow trade
        risk_manager.daily_loss = 0.0
        risk_manager.long_exposure = 0
        
        # Mock stock_analyzer response
        mock_res = {
            "status": "success",
            "symbol": "SBIN",
            "token": "3045",
            "trading_symbol": "SBIN-EQ",
            "ltp": 100.0,
            "score": 80,
            "actionable": True,
            "atr": 1.5
        }
        
        with patch('backend.engines.stock_analyzer.stock_analyzer.analyze_stock', new_callable=AsyncMock) as mock_analyze:
            mock_analyze.return_value = mock_res
            res = await execute_stock_trade("SBIN", "BUY", 10, MagicMock())
            self.assertEqual(res["status"], "success")
            self.assertEqual(risk_manager.long_exposure, 1) # Should correctly increment exposure count

if __name__ == '__main__':
    unittest.main()
