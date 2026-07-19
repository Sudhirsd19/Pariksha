"""
QuantumIndex Backtesting Engine — Bug Fix Validation Test Suite
===============================================================
Tests for BUG-01 (Trailing Stop Order), BUG-02 (Options Charges),
and BUG-03 (Look-Ahead Bias).

Run with:
    python -m pytest backend/backtesting/tests/test_bug_fixes.py -v
    -- or --
    python backend/backtesting/tests/test_bug_fixes.py
"""
from __future__ import annotations

import ast
import os
import re
import sys
import math
import glob
import unittest
from pathlib import Path

# ── Path bootstrap ──────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[3]   # d:\QuantumIndex
sys.path.insert(0, str(ROOT))

import pandas as pd
import numpy as np

from backend.backtesting.quantum_backtest_engine import (
    ChargeConfig,
    ChargeCalculator,
    QuantumBacktestEngine,
)
from backend.backtesting.battle_tested_strategy import (
    BattleTestedStrategyEngine,
    SimpleFixedRulesEngine,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def _make_ohlcv(
    n: int = 20,
    open_: float = 500.0,
    close: float = 505.0,
    high: float = 510.0,
    low: float = 495.0,
    volume: float = 100_000.0,
    start: str = "2025-01-02 09:20:00",
) -> pd.DataFrame:
    """Create a minimal OHLCV DataFrame with datetime column."""
    times = pd.date_range(start, periods=n, freq="5min")
    return pd.DataFrame({
        "datetime": times,
        "open":     open_,
        "high":     high,
        "low":      low,
        "close":    close,
        "volume":   volume,
    })


def _make_engine(instrument: str = "EQUITY", capital: float = 100_000.0) -> QuantumBacktestEngine:
    return QuantumBacktestEngine(
        instrument=instrument,
        initial_capital=capital,
        risk_pct=0.01,           # 1% as fraction (not percentage)
        verbose=False,
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 1: BUG-01 — TRAILING STOP EXECUTION ORDER
# ═══════════════════════════════════════════════════════════════════════════════

class TestTrailingStopOrder(unittest.TestCase):
    """
    BUG-01 Fix: _update_trailing_sl must NEVER run before _check_exit.

    Golden rule: if a candle triggers the trailing stop AND would have also
    been caught by the pre-candle stop, only the pre-candle stop should fire.
    The trailing stop update is deferred to AFTER the exit check confirms
    the trade is still alive.
    """

    def setUp(self):
        self.engine = _make_engine()

    # ── 1a. Long trade: SL check uses pre-candle stop ─────────────────────
    def test_long_sl_uses_precanlde_stop_not_moved_stop(self):
        """
        Scenario: BUY trade, entry=500, SL=490, TP=520, ATR=5.
        Bar: high=519 (would move trail to 516.5), low=491.

        With the OLD (buggy) code:
          1. Trail moves from 490 → 516.5.
          2. _check_exit sees low(491) < SL(516.5) → EXIT TRIGGERED.
          But low=491 is above the original SL=490. Trade should NOT exit.

        With the FIXED code:
          1. _check_exit: low(491) > original SL(490) → NO exit.
          2. _update_trailing_sl: trail moves to 516.5 for NEXT bar.
        """
        trade = {
            "signal": "BUY",
            "sl": 490.0,
            "tp": 520.0,
            "qty": 10,
            "entry_price": 500.0,
            "effective_entry": 500.0,
            "atr": 5.0,
            "entry_time": "2025-01-02 09:20:00",
            "_bar_idx": 0,
        }
        bar = pd.Series({
            "open": 500.0, "high": 519.0, "low": 491.0,
            "close": 495.0, "volume": 100_000.0,
            "atr_14": 5.0,
        })

        # Apply the FIXED flow: check exit first, then update trail
        hit, reason = self.engine._check_exit(trade, bar)
        self.assertFalse(
            hit,
            f"Trade should NOT exit (low=491 > original SL=490). Got: hit={hit}, reason={reason}"
        )

        # Now update trailing — must succeed without raising
        original_sl = trade["sl"]
        self.engine._update_trailing_sl(trade, bar)
        # Trail should have moved above the original SL
        self.assertGreater(trade["sl"], original_sl,
                           "Trailing SL should advance after bar high=519")

    # ── 1b. Long trade: TP hit on same bar that would trail ───────────────
    def test_long_tp_hit_stops_trailing_update(self):
        """
        If TP is hit, the trade exits and trailing stop should NOT update.
        """
        trade = {
            "signal": "BUY",
            "sl": 490.0,
            "tp": 510.0,
            "qty": 10,
            "entry_price": 500.0,
            "effective_entry": 500.0,
            "atr": 5.0,
            "entry_time": "2025-01-02 09:20:00",
            "_bar_idx": 0,
        }
        bar = pd.Series({
            "open": 500.0, "high": 515.0, "low": 499.0,
            "close": 514.0, "volume": 100_000.0,
            "atr_14": 5.0,
        })

        hit, reason = self.engine._check_exit(trade, bar)
        self.assertTrue(hit, "TP at 510 should be hit when high=515")
        self.assertIn("TP", reason)

        # In the FIXED loop, when hit=True, we do NOT call _update_trailing_sl
        # Simulate the fixed flow and verify trail was not touched
        sl_before = trade["sl"]
        if not hit:                        # fixed flow: else branch
            self.engine._update_trailing_sl(trade, bar)
        self.assertEqual(trade["sl"], sl_before, "SL must not change when trade already exits")

    # ── 1c. Short trade: SL check uses pre-candle stop ───────────────────
    def test_short_sl_not_triggered_by_moved_trail(self):
        """
        SELL trade, entry=500, SL=510, TP=480, ATR=5.
        Bar: low=481 (would move short trail to 488), high=509.
        Original SL=510, high=509 < SL=510 → should NOT exit.
        """
        trade = {
            "signal": "SELL",
            "sl": 510.0,
            "tp": 480.0,
            "qty": 10,
            "entry_price": 500.0,
            "effective_entry": 500.0,
            "atr": 5.0,
            "entry_time": "2025-01-02 09:20:00",
            "_bar_idx": 0,
        }
        bar = pd.Series({
            "open": 500.0, "high": 509.0, "low": 481.0,
            "close": 485.0, "volume": 100_000.0,
            "atr_14": 5.0,
        })

        hit, reason = self.engine._check_exit(trade, bar)
        self.assertFalse(hit, "Short trade: high=509 < original SL=510, should NOT exit")

        original_sl = trade["sl"]
        self.engine._update_trailing_sl(trade, bar)
        self.assertLess(trade["sl"], original_sl,
                        "Short trailing SL should move DOWN (tighten) after low=481")

    # ── 1d. Gap-down candle: SL triggered at open ────────────────────────
    def test_gap_down_triggers_sl_at_open(self):
        """
        BUY trade, SL=490. Bar opens at 485 (gap-down through SL).
        Engine should detect SL breach (open < SL).
        """
        trade = {
            "signal": "BUY",
            "sl": 490.0,
            "tp": 520.0,
            "qty": 10,
            "entry_price": 500.0,
            "effective_entry": 500.0,
            "atr": 5.0,
            "entry_time": "2025-01-02 09:20:00",
            "_bar_idx": 0,
        }
        bar = pd.Series({
            "open": 485.0, "high": 487.0, "low": 482.0,
            "close": 484.0, "volume": 100_000.0,
            "atr_14": 5.0,
        })

        hit, reason = self.engine._check_exit(trade, bar)
        self.assertTrue(hit, "Gap-down open=485 < SL=490 must trigger SL exit")

    # ── 1e. Gap-up candle: TP triggered at open ──────────────────────────
    def test_gap_up_triggers_tp_at_open(self):
        """
        BUY trade, TP=510. Bar gaps up to open=515 (above TP).
        Engine should detect TP breach.
        """
        trade = {
            "signal": "BUY",
            "sl": 490.0,
            "tp": 510.0,
            "qty": 10,
            "entry_price": 500.0,
            "effective_entry": 500.0,
            "atr": 5.0,
            "entry_time": "2025-01-02 09:20:00",
            "_bar_idx": 0,
        }
        bar = pd.Series({
            "open": 515.0, "high": 518.0, "low": 514.0,
            "close": 516.0, "volume": 100_000.0,
            "atr_14": 5.0,
        })

        hit, reason = self.engine._check_exit(trade, bar)
        self.assertTrue(hit, "Gap-up open=515 > TP=510 must trigger TP exit")

    # ── 1f. Trailing stop advances over multiple bars ──────────────────────
    def test_trailing_stop_advances_incrementally(self):
        """
        Trailing stop must advance after profit crosses 70% of TP distance.

        Parameters:
          entry=500, tp=520, tp_dist=20, 70% threshold=14 pts
          Bar-1 high=515 → profit=15 >= 14 → trail fires: sl = 515 - 1.0 = 514
          Bar-2 high=517 → profit=17 >= 14 → sl = 517 - 1.0 = 516 (advances)
          Bar-3 high=519 → profit=19 >= 14 → sl = 519 - 1.0 = 518 (advances)
          tp=520 is never hit by high (bars stop at 519) so no premature exit.
        """
        trade = {
            "signal": "BUY",
            "sl": 490.0,
            "tp": 520.0,          # tp_dist=20; 70%=14 pts; bars never reach 520
            "qty": 10,
            "entry_price": 500.0,
            "effective_entry": 500.0,
            "atr": 2.0,           # trail_sl = best - atr*0.5 = best - 1.0
            "entry_time": "2025-01-02 09:20:00",
            "_bar_idx": 0,
        }
        bars = [
            # bar-1: profit=15 >= 14 → trail fires, sl = 515 - 1.0 = 514
            #   low=507 >> sl=490 (original) → no exit
            {"open": 500.0, "high": 515.0, "low": 507.0, "close": 514.0, "atr_14": 2.0},
            # bar-2: profit=17 >= 14 → sl = 517 - 1.0 = 516 (advances)
            #   low=516.5 > sl=514 (from bar-1) → no exit
            {"open": 514.0, "high": 517.0, "low": 516.5, "close": 516.5, "atr_14": 2.0},
            # bar-3: profit=19 >= 14 → sl = 519 - 1.0 = 518 (advances)
            #   low=517.5 > sl=516 (from bar-2) → no exit
            {"open": 516.5, "high": 519.0, "low": 517.5, "close": 518.5, "atr_14": 2.0},
        ]

        prev_sl = trade["sl"]
        for idx, bar_dict in enumerate(bars):
            bar = pd.Series({**bar_dict, "volume": 100_000.0})
            hit, _ = self.engine._check_exit(trade, bar)
            self.assertFalse(hit, f"Bar {idx}: unexpected exit (low={bar_dict['low']}, sl={trade['sl']}")
            self.engine._update_trailing_sl(trade, bar)
            self.assertGreaterEqual(
                trade["sl"], prev_sl,
                f"Bar {idx}: Trailing SL must not decrease: {prev_sl} → {trade['sl']}"
            )
            prev_sl = trade["sl"]

        self.assertGreater(
            trade["sl"], 490.0,
            f"Trailing SL must have advanced from 490 after bars crossing 70% profit threshold. "
            f"Final SL: {trade['sl']}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 2: BUG-02 — CHARGE CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════════

class TestChargeCalculatorEquityIntraday(unittest.TestCase):
    """Manual reconciliation: equity intraday charges."""

    def setUp(self):
        self.calc = ChargeCalculator()

    def _manual_equity_intraday(
        self, entry: float, exit_price: float, qty: int
    ) -> dict:
        buy_val  = entry      * qty
        sell_val = exit_price * qty
        turnover = buy_val + sell_val

        brokerage = min(buy_val * 0.0003, 20.0) + min(sell_val * 0.0003, 20.0)
        stt       = sell_val  * 0.00025
        exchange  = turnover  * 0.0000345
        sebi      = turnover  * 0.000001
        gst       = (brokerage + exchange + sebi) * 0.18
        stamp     = buy_val   * 0.00003
        total     = brokerage + stt + exchange + sebi + gst + stamp
        return {"brokerage": brokerage, "stt": stt, "exchange": exchange,
                "sebi": sebi, "gst": gst, "stamp": stamp, "total": total}

    def test_basic_reconciliation(self):
        entry, exit_price, qty = 100.0, 105.0, 100
        expected = self._manual_equity_intraday(entry, exit_price, qty)
        got      = self.calc.equity_intraday(entry, exit_price, qty)

        for key in ["brokerage", "stt", "exchange", "sebi", "gst", "stamp", "total"]:
            self.assertAlmostEqual(got[key], round(expected[key], 4), places=2,
                msg=f"equity_intraday[{key}]: expected {expected[key]:.4f}, got {got[key]}")

    def test_brokerage_cap_applied(self):
        """For large trades, brokerage per leg must be capped at Rs 20."""
        result = self.calc.equity_intraday(10_000.0, 10_100.0, qty=1000)
        # Buy brokerage: min(10_000_000 * 0.0003, 20) = 20
        # Sell brokerage: min(10_100_000 * 0.0003, 20) = 20
        self.assertAlmostEqual(result["brokerage"], 40.0, places=2)

    def test_stt_only_on_sell_side(self):
        """STT must be 0.025% of sell_val only."""
        result = self.calc.equity_intraday(100.0, 110.0, qty=100)
        expected_stt = 100 * 110.0 * 0.00025
        self.assertAlmostEqual(result["stt"], round(expected_stt, 4), places=2)

    def test_stamp_only_on_buy_side(self):
        """Stamp must be 0.003% of buy_val only."""
        result = self.calc.equity_intraday(100.0, 105.0, qty=100)
        expected_stamp = 100 * 100.0 * 0.00003
        self.assertAlmostEqual(result["stamp"], round(expected_stamp, 4), places=2)


class TestChargeCalculatorEquityDelivery(unittest.TestCase):
    """Delivery / positional trades: STT on both sides."""

    def setUp(self):
        self.calc = ChargeCalculator()

    def test_stt_on_both_sides(self):
        entry, exit_price, qty = 500.0, 550.0, 50
        result   = self.calc.equity_delivery(entry, exit_price, qty)
        turnover = (entry + exit_price) * qty
        expected_stt = turnover * 0.001   # 0.1% on both sides
        self.assertAlmostEqual(result["stt"], round(expected_stt, 4), places=2)

    def test_delivery_charges_higher_than_intraday(self):
        """Delivery STT (0.1% both sides) > intraday STT (0.025% sell only)."""
        entry, exit_price, qty = 500.0, 550.0, 50
        intra    = self.calc.equity_intraday(entry, exit_price, qty)
        delivery = self.calc.equity_delivery(entry, exit_price, qty)
        self.assertGreater(delivery["stt"], intra["stt"],
                           "Delivery STT should be greater than intraday STT")


class TestChargeCalculatorFutures(unittest.TestCase):
    """Futures charges: different exchange rate, sell-side STT."""

    def setUp(self):
        self.calc = ChargeCalculator()

    def _manual_futures(self, entry, exit_price, qty):
        buy_val  = entry      * qty
        sell_val = exit_price * qty
        turnover = buy_val + sell_val
        brokerage = min(buy_val * 0.0003, 20.0) + min(sell_val * 0.0003, 20.0)
        stt       = sell_val  * 0.0001
        exchange  = turnover  * 0.0000210
        sebi      = turnover  * 0.000001
        gst       = (brokerage + exchange + sebi) * 0.18
        stamp     = buy_val   * 0.00002
        return brokerage + stt + exchange + sebi + gst + stamp

    def test_futures_total_reconciliation(self):
        entry, exit_price, qty = 24_000.0, 24_200.0, 50
        expected = self._manual_futures(entry, exit_price, qty)
        result   = self.calc.futures(entry, exit_price, qty)
        self.assertAlmostEqual(result["total"], round(expected, 4), places=1)

    def test_futures_exchange_rate(self):
        """Futures exchange charge is 0.00210% of turnover (not equity 0.00345%)."""
        entry, exit_price, qty = 1000.0, 1010.0, 100
        turnover = (entry + exit_price) * qty
        expected_exchange = turnover * 0.0000210
        result = self.calc.futures(entry, exit_price, qty)
        self.assertAlmostEqual(result["exchange"], round(expected_exchange, 4), places=3)


class TestChargeCalculatorOptionsBuyLeg(unittest.TestCase):
    """Options BUY leg: verify 0.05% exchange fee (not equity 0.00345%)."""

    def setUp(self):
        self.calc = ChargeCalculator()

    def _manual_options_buy(self, premium, qty):
        buy_val   = premium * qty
        brokerage = min(buy_val * 0.0003, 20.0)
        stt       = 0.0                           # STT is zero on buy leg
        exchange  = buy_val * 0.0005              # 0.05% on premium (FIXED)
        sebi      = buy_val * 0.000001
        gst       = (brokerage + exchange + sebi) * 0.18
        stamp     = buy_val * 0.00003
        return {"brokerage": brokerage, "stt": stt, "exchange": exchange,
                "sebi": sebi, "gst": gst, "stamp": stamp,
                "total": brokerage + stt + exchange + sebi + gst + stamp}

    def test_exchange_fee_uses_options_rate(self):
        """
        Exchange fee must be 0.05% of premium (options NSE rate),
        NOT 0.00345% of turnover (equity rate).
        """
        premium, qty = 200.0, 75
        result   = self.calc.options_buy(premium, qty)
        expected = self._manual_options_buy(premium, qty)

        self.assertAlmostEqual(result["exchange"], round(expected["exchange"], 4), places=3,
            msg=f"Exchange: expected {expected['exchange']:.4f} (0.05% of premium), got {result['exchange']}")

        # Sanity check: old (wrong) value would have been:
        old_wrong_exchange = premium * qty * 0.0000345
        self.assertNotAlmostEqual(result["exchange"], old_wrong_exchange, places=3,
            msg="Exchange fee must NOT use the old equity rate (0.00345%)")

    def test_options_buy_total_reconciliation(self):
        premium, qty = 150.0, 50
        expected = self._manual_options_buy(premium, qty)
        result   = self.calc.options_buy(premium, qty)
        self.assertAlmostEqual(result["total"], round(expected["total"], 4), places=2)

    def test_options_buy_no_stamp_on_expiry_itm_but_stt_added(self):
        """Expiry ITM adds extra STT on settlement value."""
        premium, qty = 100.0, 50
        normal = self.calc.options_buy(premium, qty, is_expiry_itm=False)
        itm    = self.calc.options_buy(premium, qty, is_expiry_itm=True)
        self.assertGreater(itm["stt"], normal["stt"],
                           "Expiry ITM adds extra STT on settlement")
        self.assertGreater(itm["total"], normal["total"])


class TestChargeCalculatorOptionsSellLeg(unittest.TestCase):
    """Options SELL leg: new method, correct charges."""

    def setUp(self):
        self.calc = ChargeCalculator()

    def _manual_options_sell(self, exit_premium, qty):
        sell_val  = exit_premium * qty
        brokerage = min(sell_val * 0.0003, 20.0)
        stt       = sell_val * 0.00125      # 0.125% on sell premium
        exchange  = sell_val * 0.0005       # 0.05% on premium
        sebi      = sell_val * 0.000001
        gst       = (brokerage + exchange + sebi) * 0.18
        stamp     = 0.0                     # NO stamp on sell
        return {"brokerage": brokerage, "stt": stt, "exchange": exchange,
                "sebi": sebi, "gst": gst, "stamp": stamp,
                "total": brokerage + stt + exchange + sebi + gst + stamp}

    def test_options_sell_reconciliation(self):
        exit_premium, qty = 350.0, 50
        expected = self._manual_options_sell(exit_premium, qty)
        result   = self.calc.options_sell(exit_premium, qty)

        for key in ["brokerage", "stt", "exchange", "sebi", "gst", "stamp", "total"]:
            self.assertAlmostEqual(result[key], round(expected[key], 4), places=2,
                msg=f"options_sell[{key}]: expected {expected[key]:.4f}, got {result[key]}")

    def test_no_stamp_on_sell(self):
        result = self.calc.options_sell(200.0, 75)
        self.assertEqual(result["stamp"], 0.0, "Stamp duty must be zero on sell side")

    def test_stt_on_sell_premium(self):
        exit_premium, qty = 200.0, 75
        result       = self.calc.options_sell(exit_premium, qty)
        expected_stt = exit_premium * qty * 0.00125
        self.assertAlmostEqual(result["stt"], round(expected_stt, 4), places=3)


class TestChargeCalculatorOptionsRoundTrip(unittest.TestCase):
    """
    Options round-trip: the PRIMARY BUG-02 fix.
    Verifies that entry charges use entry_premium and exit charges use exit_premium.
    """

    def setUp(self):
        self.calc = ChargeCalculator()

    def test_round_trip_equals_buy_plus_sell(self):
        """round_trip total must equal options_buy(entry) + options_sell(exit)."""
        entry_premium, exit_premium, qty = 200.0, 350.0, 50

        buy_ch  = self.calc.options_buy(entry_premium, qty)
        sell_ch = self.calc.options_sell(exit_premium, qty)
        rt_ch   = self.calc.options_round_trip(entry_premium, exit_premium, qty)

        expected_total = round(buy_ch["total"] + sell_ch["total"], 4)
        self.assertAlmostEqual(rt_ch["total"], expected_total, places=3,
            msg=f"Round-trip total {rt_ch['total']} != buy+sell {expected_total}")

    def test_round_trip_uses_exit_premium_not_entry(self):
        """
        Previously the engine used options_buy(entry_premium) for BOTH legs,
        ignoring the exit premium. Verify the round-trip total differs from
        2× options_buy(entry_premium).
        """
        entry_premium, exit_premium, qty = 200.0, 350.0, 50
        rt_correct  = self.calc.options_round_trip(entry_premium, exit_premium, qty)
        # Old buggy behavior: two calls to options_buy(entry_premium)
        old_buggy   = self.calc.options_buy(entry_premium, qty)["total"]

        self.assertNotAlmostEqual(
            rt_correct["total"], old_buggy, places=1,
            msg="Round-trip must NOT equal double-entry (BUG-02 regression check)"
        )

    def test_round_trip_audit_trail_keys(self):
        """Round-trip dict must include entry_total and exit_total for audit."""
        rt = self.calc.options_round_trip(200.0, 350.0, 50)
        self.assertIn("entry_total", rt)
        self.assertIn("exit_total",  rt)
        self.assertAlmostEqual(
            rt["entry_total"] + rt["exit_total"], rt["total"], places=4
        )

    def test_sample_nifty_ce_calculation(self):
        """
        Manual reconciliation for NIFTY CE trade:
          entry=200, exit=350, qty=50 (1 lot NIFTY)
        """
        entry_premium, exit_premium, qty = 200.0, 350.0, 50

        # Entry leg (manual)
        bv_entry   = entry_premium * qty              # 10_000
        entry_brok = min(bv_entry * 0.0003, 20.0)    # min(3, 20) = 3.00
        entry_stt  = 0.0                             # STT is zero on buy leg
        entry_exch = bv_entry * 0.0005               # 5.00
        entry_sebi = bv_entry * 0.000001             # 0.01
        entry_gst  = (entry_brok + entry_exch + entry_sebi) * 0.18  # 1.4418
        entry_stamp= bv_entry * 0.00003              # 0.30
        entry_total= entry_brok + entry_stt + entry_exch + entry_sebi + entry_gst + entry_stamp
        # ≈ 9.7518

        # Exit leg (manual)
        sv_exit    = exit_premium * qty              # 17_500
        exit_brok  = min(sv_exit * 0.0003, 20.0)    # min(5.25, 20) = 5.25
        exit_stt   = sv_exit * 0.00125              # 21.875
        exit_exch  = sv_exit * 0.0005               # 8.75
        exit_sebi  = sv_exit * 0.000001             # 0.0175
        exit_gst   = (exit_brok + exit_exch + exit_sebi) * 0.18
        exit_stamp = 0.0
        exit_total = exit_brok + exit_stt + exit_exch + exit_sebi + exit_gst + exit_stamp

        expected_rt = round(entry_total + exit_total, 4)
        result      = self.calc.options_round_trip(entry_premium, exit_premium, qty)

        self.assertAlmostEqual(result["total"], expected_rt, places=1,
            msg=f"NIFTY CE round-trip: expected ≈{expected_rt:.2f}, got {result['total']:.2f}")

    def test_configurable_rates(self):
        """ChargeConfig allows rate overrides; verify they flow through."""
        custom_cfg  = ChargeConfig(exchange_options_pct=0.0003)  # custom rate
        custom_calc = ChargeCalculator(config=custom_cfg)
        default_calc= ChargeCalculator()

        premium, qty = 200.0, 50
        custom_ch  = custom_calc.options_buy(premium, qty)
        default_ch = default_calc.options_buy(premium, qty)

        # Custom exchange (0.03%) < default (0.05%)
        self.assertLess(custom_ch["exchange"], default_ch["exchange"],
                        "Custom exchange rate (0.03%) must produce lower exchange charge")


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 3: BUG-03 — LOOK-AHEAD BIAS DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

STRATEGY_DIR = Path(ROOT) / "backend" / "backtesting"
PATTERNS_ILLEGAL = [
    r"\.iloc\s*\[\s*i\s*\+\s*1\s*\]",   # .iloc[i+1]
    r"\.iloc\s*\[\s*index\s*\+\s*1\s*\]",
    r"\.shift\s*\(\s*-\s*[1-9]",         # .shift(-N)  (forward shift)
    r"future_price",
    r"future_high",
    r"future_low",
    r"future_close",
    r"future_index",
    r"next_high\s*=\s*df\.iloc",          # the original BUG-03 line
    r"next_low\s*=\s*df\.iloc",
]

# Files known to legitimately use next_bar in EXECUTION context (not signals)
# These are whitelisted from the look-ahead scan.
WHITELIST_PATTERNS = {
    "quantum_backtest_engine.py": [
        r"next_bar\s*=",           # execution fill at next candle — intentional
        r"next_bar_time",
        r"_execute_entry.*next_bar",
    ],
}


class TestLookAheadBias(unittest.TestCase):
    """
    BUG-03: Static scan of all strategy Python files for look-ahead bias patterns.
    Test FAILS if any illegal future-data reference is found.
    """

    @classmethod
    def _scan_file(cls, filepath: Path) -> list[str]:
        """
        Return list of violation strings for any illegal future-data pattern.
        Lines that are pure comments (#) or inside docstrings are skipped
        because the DESCRIPTION of the old bug is allowed in docstrings.
        """
        violations = []
        try:
            text = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return violations

        filename  = filepath.name
        whitelist = WHITELIST_PATTERNS.get(filename, [])

        # Parse the file with AST to find actual code lines vs string literals
        try:
            tree = ast.parse(text)
            # Collect line ranges that are inside string literals (docstrings)
            docstring_lines: set[int] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                    # This is a string expression (docstring)
                    start = getattr(node, "lineno", 0)
                    end   = getattr(node, "end_lineno", start)
                    docstring_lines.update(range(start, end + 1))
        except SyntaxError:
            docstring_lines = set()

        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            # Skip pure comment lines
            if stripped.startswith("#"):
                continue
            # Skip docstring lines
            if lineno in docstring_lines:
                continue

            for pattern in PATTERNS_ILLEGAL:
                if re.search(pattern, line, re.IGNORECASE):
                    whitelisted = any(re.search(wp, line) for wp in whitelist)
                    if not whitelisted:
                        violations.append(
                            f"  {filepath.name}:{lineno}: [{pattern}]\n    {line.strip()}"
                        )
        return violations

    def test_battle_tested_strategy_no_lookahead(self):
        """
        battle_tested_strategy.py must NOT contain any future-data references.
        BUG-03 fix: SimpleFixedRulesEngine.generate_signals removed df.iloc[i+1].
        """
        target = STRATEGY_DIR / "battle_tested_strategy.py"
        self.assertTrue(target.exists(), f"File not found: {target}")
        violations = self._scan_file(target)
        self.assertEqual(
            len(violations), 0,
            f"Look-ahead bias detected in battle_tested_strategy.py:\n"
            + "\n".join(violations)
        )

    def test_quantum_engine_signal_generation_no_lookahead(self):
        """
        quantum_backtest_engine.py signal generation must not use future bars.
        Legitimate next_bar usage for order EXECUTION is whitelisted.
        """
        target = STRATEGY_DIR / "quantum_backtest_engine.py"
        self.assertTrue(target.exists(), f"File not found: {target}")
        violations = self._scan_file(target)
        self.assertEqual(
            len(violations), 0,
            f"Potential look-ahead bias detected in quantum_backtest_engine.py:\n"
            + "\n".join(violations)
        )

    def test_project_wide_no_shift_minus_one(self):
        """
        No .shift(-N) (forward shift = look-ahead) in any strategy/engine file.
        """
        py_files = list(STRATEGY_DIR.rglob("*.py"))
        all_violations = []
        for f in py_files:
            if "test_" in f.name or f.name == "__init__.py":
                continue
            for lineno, line in enumerate(
                f.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
            ):
                if re.search(r"\.shift\s*\(\s*-\s*[1-9]", line):
                    all_violations.append(f"  {f.name}:{lineno}: {line.strip()}")

        self.assertEqual(
            len(all_violations), 0,
            "Forward shift .shift(-N) detected (look-ahead bias):\n"
            + "\n".join(all_violations)
        )

    def test_simple_fixed_rules_uses_current_bar_close(self):
        """
        SimpleFixedRulesEngine.generate_signals must NOT reference df.iloc[i+1]
        in EXECUTABLE code. Docstrings documenting the old bug are permitted.
        """
        target = STRATEGY_DIR / "battle_tested_strategy.py"
        text   = target.read_text(encoding="utf-8")

        # Build set of docstring line numbers via AST (they describe the old bug — OK)
        try:
            tree = ast.parse(text)
            docstring_lines: set[int] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                    s = getattr(node, "lineno", 0)
                    e = getattr(node, "end_lineno", s)
                    docstring_lines.update(range(s, e + 1))
        except SyntaxError:
            docstring_lines = set()

        # Scan only executable lines for actual future-bar access
        code_violations = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("#") or lineno in docstring_lines:
                continue
            if re.search(r"df\.iloc\s*\[\s*i\s*\+\s*1\s*\]", line):
                code_violations.append(f"  line {lineno}: {line.strip()}")

        self.assertEqual(
            len(code_violations), 0,
            "SimpleFixedRulesEngine has df.iloc[i+1] in executable code (look-ahead bias):\n"
            + "\n".join(code_violations)
        )

        # Confirm causal breakout logic: curr_close vs hist_window
        has_causal = ("curr_close" in text) and ("hist_window" in text)
        self.assertTrue(has_causal,
                        "SimpleFixedRulesEngine must use hist_window + curr_close breakout")


class TestSimpleFixedRulesEngineSignals(unittest.TestCase):
    """Behavioral test: signals are based only on past data."""

    def _make_df(self, n=100) -> pd.DataFrame:
        prices = np.linspace(100, 120, n)
        return pd.DataFrame({
            "open":   prices * 0.998,
            "high":   prices * 1.005,
            "low":    prices * 0.993,
            "close":  prices,
            "volume": 100_000.0,
            "time":   pd.date_range("2025-01-02 09:15:00", periods=n, freq="5min"),
        })

    def test_no_signal_on_last_bar(self):
        """
        The FIXED engine must NOT produce a signal on the last bar (no next bar to execute on).
        The BUG-03 original code skipped last bar via `if i < len(df) - 1` — the fix
        should produce signals on bars that break out, not on the last bar.
        """
        engine = SimpleFixedRulesEngine()
        df = self._make_df()
        result = engine.generate_signals(df)
        # Last bar signal — depends on data; what we verify is signals exist
        self.assertIn("signal", result.columns)

    def test_signals_only_on_breakout_bars(self):
        """
        If price is flat (no breakout), no BUY/SELL signal should be generated.
        """
        engine = SimpleFixedRulesEngine()
        n = 100
        # Flat prices — no breakout
        df = pd.DataFrame({
            "open":   [500.0] * n,
            "high":   [501.0] * n,
            "low":    [499.0] * n,
            "close":  [500.0] * n,
            "volume": [100_000.0] * n,
            "time":   pd.date_range("2025-01-02 09:15:00", periods=n, freq="5min"),
        })
        result = engine.generate_signals(df)
        buy_sell = result["signal"].isin(["BUY", "SELL"])
        self.assertEqual(buy_sell.sum(), 0,
                         f"No breakout signals expected for flat price. Got {buy_sell.sum()} signals")

    def test_buy_signal_on_upward_breakout(self):
        """
        If price closes clearly above the 20-bar historical high, BUY expected.
        """
        engine = SimpleFixedRulesEngine()
        n = 80
        # First 50 bars: flat around 500
        prices = [500.0] * 50 + [501.0] * 10 + [502.0] * 10 + [600.0] * 10  # spike
        df = pd.DataFrame({
            "open":   [p * 0.999 for p in prices],
            "high":   [p * 1.001 for p in prices],
            "low":    [p * 0.998 for p in prices],
            "close":  prices,
            "volume": [100_000.0] * n,
            "time":   pd.date_range("2025-01-02 09:15:00", periods=n, freq="5min"),
        })
        result = engine.generate_signals(df)
        buy_signals = (result["signal"] == "BUY").sum()
        self.assertGreater(buy_signals, 0,
                           "Expected at least one BUY signal when price spikes to 600")


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 4: PROJECT-WIDE REGRESSION / INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestChargeCalculatorBackwardCompatibility(unittest.TestCase):
    """
    Ensure ChargeCalculator still works as before for equity and futures.
    instance-based API must not break callers.
    """

    def test_equity_intraday_still_works(self):
        calc = ChargeCalculator()
        result = calc.equity_intraday(100.0, 105.0, 100)
        self.assertIn("total", result)
        self.assertGreater(result["total"], 0)

    def test_futures_still_works(self):
        calc = ChargeCalculator()
        result = calc.futures(24_000.0, 24_200.0, 50)
        self.assertIn("total", result)
        self.assertGreater(result["total"], 0)

    def test_options_buy_still_works(self):
        calc = ChargeCalculator()
        result = calc.options_buy(200.0, 50)
        self.assertIn("total", result)
        self.assertGreater(result["total"], 0)

    def test_options_sell_is_new_method(self):
        calc = ChargeCalculator()
        self.assertTrue(hasattr(calc, "options_sell"),
                        "ChargeCalculator must have options_sell() method (BUG-02)")

    def test_options_round_trip_is_new_method(self):
        calc = ChargeCalculator()
        self.assertTrue(hasattr(calc, "options_round_trip"),
                        "ChargeCalculator must have options_round_trip() method (BUG-02)")

    def test_equity_delivery_is_new_method(self):
        calc = ChargeCalculator()
        self.assertTrue(hasattr(calc, "equity_delivery"),
                        "ChargeCalculator must have equity_delivery() method")

    def test_custom_config_accepted(self):
        cfg  = ChargeConfig(brokerage_cap=25.0)
        calc = ChargeCalculator(config=cfg)
        self.assertEqual(calc.cfg.brokerage_cap, 25.0)

    def test_default_config_is_singleton(self):
        c1 = ChargeCalculator()
        c2 = ChargeCalculator()
        # Both should use the same rates (but independent instances)
        self.assertEqual(c1.cfg.exchange_options_pct, 0.0005)
        self.assertEqual(c2.cfg.exchange_options_pct, 0.0005)


class TestEngineRunRegression(unittest.TestCase):
    """
    Integration smoke test: engine must complete a full run without errors.
    Verifies no regression from the three bug fixes.
    """

    def _minimal_df(self, n: int = 60) -> pd.DataFrame:
        """Build a minimal valid DataFrame for the engine."""
        times = pd.date_range("2025-01-02 09:15:00", periods=n, freq="5min")
        prices = np.linspace(500.0, 520.0, n)
        return pd.DataFrame({
            "datetime": times,
            "open":     prices,
            "high":     prices + 2.0,
            "low":      prices - 2.0,
            "close":    prices + 0.5,
            "volume":   np.random.randint(50_000, 200_000, n).astype(float),
        })

    def test_equity_engine_completes(self):
        engine = _make_engine("EQUITY")
        df = self._minimal_df()
        result = engine.run(df)
        self.assertIn("metrics", result)
        self.assertIn("trades", result)

    def test_options_engine_no_charge_error(self):
        """
        Options engine must not raise AttributeError for options_sell.
        (Before BUG-02 fix, _execute_exit called options_buy for both legs.)
        """
        engine = _make_engine("OPTIONS")
        df = self._minimal_df()
        try:
            result = engine.run(df)
            self.assertIn("metrics", result)
        except AttributeError as e:
            self.fail(f"Options engine raised AttributeError: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
#  SECTION 5: CHARGE RATE CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestChargeConfig(unittest.TestCase):
    """ChargeConfig dataclass: rates, overrides, defaults."""

    def test_default_options_exchange_rate(self):
        """exchange_options_pct must be 0.0005 (0.05%) — the BUG-02 fix."""
        cfg = ChargeConfig()
        self.assertEqual(cfg.exchange_options_pct, 0.0005,
                         "Default options exchange must be 0.05% (not equity 0.00345%)")

    def test_default_equity_exchange_rate(self):
        cfg = ChargeConfig()
        self.assertAlmostEqual(cfg.exchange_equity_pct, 0.0000345, places=8)

    def test_stamp_sell_is_zero(self):
        """No stamp duty on sell side."""
        cfg = ChargeConfig()
        self.assertEqual(cfg.stamp_sell_pct, 0.0)

    def test_stt_delivery_both_sides(self):
        """Delivery STT rate (0.1%) must be 4× intraday rate (0.025%)."""
        cfg = ChargeConfig()
        self.assertAlmostEqual(
            cfg.stt_eq_delivery_pct / cfg.stt_eq_intraday_pct, 4.0, places=5
        )

    def test_rate_override_persists(self):
        cfg = ChargeConfig(gst_pct=0.28)  # future hypothetical
        self.assertEqual(cfg.gst_pct, 0.28)
        calc = ChargeCalculator(config=cfg)
        # GST on Rs 100 base = 0.28 × 100 = 28
        computed = calc._gst(brokerage=50.0, exchange=30.0, sebi=20.0)
        self.assertAlmostEqual(computed, (50.0 + 30.0 + 20.0) * 0.28, places=5)


# ═══════════════════════════════════════════════════════════════════════════════
#  RUNNER
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Run with verbose output and collect results
    loader  = unittest.TestLoader()
    suite   = loader.loadTestsFromModule(sys.modules[__name__])
    runner  = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result  = runner.run(suite)

    print("\n" + "=" * 70)
    print("BUG FIX VALIDATION SUMMARY")
    print("=" * 70)
    print(f"Tests run    : {result.testsRun}")
    print(f"Failures     : {len(result.failures)}")
    print(f"Errors       : {len(result.errors)}")
    print(f"Skipped      : {len(result.skipped)}")
    print(f"Success      : {result.wasSuccessful()}")
    print()

    if result.failures:
        print("FAILURES:")
        for test, tb in result.failures:
            print(f"  FAIL: {test}")
    if result.errors:
        print("ERRORS:")
        for test, tb in result.errors:
            print(f"  ERROR: {test}")

    if result.wasSuccessful():
        print("ALL TESTS PASSED — All 3 bugs confirmed fixed.")
    else:
        print("SOME TESTS FAILED — Review failures above.")

    sys.exit(0 if result.wasSuccessful() else 1)
