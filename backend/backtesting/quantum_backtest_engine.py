"""
QuantumIndex Institutional Backtesting Engine v3.0
====================================================
Audit-grade engine implementing all 20 institutional requirements:
  1. Realistic execution (next-candle open fill — no look-ahead bias)
  2. Full NSE charge model (brokerage, STT, exchange, SEBI, GST, stamp)
  3. ATR-based dynamic slippage with volume context
  4. Risk management (per-trade %, daily stop, max positions)
  5. F&O support (futures rollover, weekly options, ATM strike, lot sizing)
  6. Intraday rules (session windows, auto sq-off at 15:10 IST)
  7. Look-ahead bias detection (strict candle indexing)
  8. Data validation (gaps, duplicates, holidays, OHL sanity)
  9. All 18 performance metrics (Sharpe, Sortino, Calmar, MAR, etc.)
 10. Walk-forward & Monte Carlo
 11. Visual reports (equity curve, drawdown, monthly heatmap, distribution)
 12. Full CSV/HTML/Excel output
 13. Parameter grid search + Bayesian (scipy minimize)
 14. Stress testing (crisis scenarios)
 15. Signal audit log (per-candle pass/fail for every filter)
"""

from __future__ import annotations

import os
import csv
import json
import warnings
import traceback
import itertools
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
IST = timezone(timedelta(hours=5, minutes=30))

# NSE Market Sessions (IST)
MARKET_OPEN   = time(9, 15)
ENTRY_CUTOFF  = time(14, 30)   # No new entries after this
SQUAREOFF     = time(15, 10)   # Auto sq-off
MARKET_CLOSE  = time(15, 30)

# NSE/BSE Holidays 2024-2026 (add more as needed)
NSE_HOLIDAYS = {
    date(2024,  1, 22), date(2024,  3, 25), date(2024,  3, 29),
    date(2024,  4, 11), date(2024,  4, 14), date(2024,  4, 17),
    date(2024,  5,  1), date(2024,  6, 17), date(2024,  7, 17),
    date(2024,  8, 15), date(2024, 10,  2), date(2024, 10,  2),
    date(2024, 11,  1), date(2024, 11, 15), date(2024, 12, 25),
    date(2025,  2, 26), date(2025,  3, 14), date(2025,  3, 31),
    date(2025,  4, 10), date(2025,  4, 14), date(2025,  4, 18),
    date(2025,  5,  1), date(2025,  8, 15), date(2025, 10,  2),
    date(2025, 10, 20), date(2025, 11,  5), date(2025, 12, 25),
    date(2026,  1, 26), date(2026,  3, 19), date(2026,  4,  2),
    date(2026,  4,  3), date(2026,  4, 14), date(2026,  5,  1),
    date(2026,  8, 15), date(2026, 10,  2), date(2026, 10, 22),
    date(2026, 11, 25), date(2026, 12, 25),
}

# ── Legacy charge constants (kept for backward-compat; ChargeConfig is canonical) ──
BROKERAGE_PCT   = 0.0003      # 0.03 %
BROKERAGE_CAP   = 20.0        # Rs 20 cap per executed order
STT_INTRA_PCT   = 0.00025     # 0.025 % on sell side (equity intraday)
STT_FUT_PCT     = 0.0001      # 0.01 % on sell (F&O futures)
STT_OPT_BUY_PCT = 0.00125     # 0.125 % on premium buy/sell (options)
STT_OPT_EXP_PCT = 0.00125     # 0.125 % on ITM options at expiry
EXCHANGE_PCT    = 0.0000345   # 0.00345 % (NSE equity) — NOT used for options
EXCHANGE_OPT_PCT = 0.0005    # 0.05 % on options premium (NSE) — BUG-02 FIX
SEBI_PCT        = 0.000001    # 0.0001 % (Rs 1 per Rs 10L)
GST_PCT         = 0.18        # 18 % on (brokerage + exchange + SEBI)
STAMP_BUY_PCT   = 0.00003     # 0.003 % on buy value (equity)
STAMP_FUT_PCT   = 0.00002     # 0.002 % on buy value (F&O)
STAMP_OPT_PCT   = 0.00003     # 0.003 % on buy value (options)


# ══════════════════════════════════════════════════════════════════════════════
# CHARGE CONFIGURATION DATACLASS
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class ChargeConfig:
    """
    Centralized, overridable NSE/BSE charge rate sheet.

    All fields are decimal fractions unless the name ends in '_cap' (Rs).
    Pass a custom instance to ChargeCalculator to override any rate:

        calc = ChargeCalculator(ChargeConfig(brokerage_cap=25.0))
    """
    # Brokerage
    brokerage_pct: float          = 0.0003
    brokerage_cap: float          = 20.0
    # STT — Equity
    stt_eq_intraday_pct: float    = 0.00025
    stt_eq_delivery_pct: float    = 0.001
    # STT — Futures
    stt_fut_pct: float            = 0.0001
    # STT — Options (both legs: buy to open AND sell to close)
    stt_opt_pct: float            = 0.00125
    stt_opt_expiry_itm_pct: float = 0.00125
    # Exchange charges
    exchange_equity_pct: float    = 0.0000345
    exchange_futures_pct: float   = 0.0000210
    exchange_options_pct: float   = 0.0005      # 0.05% on premium — BUG-02 FIX
    # SEBI
    sebi_pct: float               = 0.000001
    # GST
    gst_pct: float                = 0.18
    # Stamp (buy-side only; zero on sell)
    stamp_equity_buy_pct: float   = 0.00003
    stamp_equity_del_pct: float   = 0.00003
    stamp_futures_buy_pct: float  = 0.00002
    stamp_options_buy_pct: float  = 0.00003
    stamp_sell_pct: float         = 0.0


DEFAULT_CHARGE_CONFIG = ChargeConfig()


# ══════════════════════════════════════════════════════════════════════════════
# DATA VALIDATION
# ══════════════════════════════════════════════════════════════════════════════
class DataValidator:
    """Validates and cleans OHLCV data before backtest."""

    def __init__(self, interval_minutes: int = 5):
        self.interval = interval_minutes
        self.issues: List[str] = []

    def validate(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
        """
        Full data validation pipeline. Returns (clean_df, issues_list).
        AUDIT STEP 1 — Data Validation.
        """
        self.issues = []
        df = df.copy()

        # --- Column standardisation ---
        df.columns = [c.lower().strip() for c in df.columns]
        required = {"open", "high", "low", "close"}
        missing = required - set(df.columns)
        if missing:
            self.issues.append(f"CRITICAL: Missing columns {missing}")
            return df, self.issues

        # Ensure timestamp column
        ts_col = next((c for c in ["datetime", "date", "time", "timestamp"]
                       if c in df.columns), None)
        if ts_col and ts_col != "datetime":
            df = df.rename(columns={ts_col: "datetime"})

        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
            df["datetime"] = df["datetime"].dt.tz_convert("Asia/Kolkata")
            df = df.dropna(subset=["datetime"])
            df = df.sort_values("datetime").reset_index(drop=True)

        # --- OHLC sanity ---
        bad_ohl = (df["high"] < df["low"]).sum()
        if bad_ohl:
            self.issues.append(f"OHLC sanity violation: {bad_ohl} rows where high < low")
            df = df[df["high"] >= df["low"]]

        bad_close_h = (df["close"] > df["high"]).sum()
        bad_close_l = (df["close"] < df["low"]).sum()
        if bad_close_h:
            self.issues.append(f"Close > High: {bad_close_h} rows (fixing)")
            df.loc[df["close"] > df["high"], "close"] = df["high"]
        if bad_close_l:
            self.issues.append(f"Close < Low: {bad_close_l} rows (fixing)")
            df.loc[df["close"] < df["low"], "close"] = df["low"]

        bad_open_h = (df["open"] > df["high"]).sum()
        bad_open_l = (df["open"] < df["low"]).sum()
        if bad_open_h:
            self.issues.append(f"Open > High: {bad_open_h} rows (fixing)")
            df.loc[df["open"] > df["high"], "open"] = df["high"]
        if bad_open_l:
            self.issues.append(f"Open < Low: {bad_open_l} rows (fixing)")
            df.loc[df["open"] < df["low"], "open"] = df["low"]

        # --- Zero/negative prices ---
        for col in ["open", "high", "low", "close"]:
            zeros = (df[col] <= 0).sum()
            if zeros:
                self.issues.append(f"Zero/negative prices in '{col}': {zeros} rows removed")
                df = df[df[col] > 0]

        # --- Duplicates ---
        if "datetime" in df.columns:
            dupes = df.duplicated(subset=["datetime"]).sum()
            if dupes:
                self.issues.append(f"Duplicate timestamps: {dupes} removed (keeping last)")
                df = df.drop_duplicates(subset=["datetime"], keep="last")

        # --- Missing candles (gaps) ---
        if "datetime" in df.columns and len(df) > 1:
            expected_delta = timedelta(minutes=self.interval)
            df = df.sort_values("datetime").reset_index(drop=True)
            # Only check within trading hours
            trading_rows = df[
                df["datetime"].dt.weekday < 5
            ].copy()
            if len(trading_rows) > 1:
                diffs = trading_rows["datetime"].diff().dropna()
                large_gaps = diffs[diffs > expected_delta * 3]
                if not large_gaps.empty:
                    self.issues.append(
                        f"Data gaps detected: {len(large_gaps)} gaps "
                        f"(max gap: {large_gaps.max()})"
                    )

        # --- Volume ---
        if "volume" not in df.columns:
            self.issues.append("WARNING: No volume column — slippage model degraded")
            df["volume"] = 0

        zero_vol = (df["volume"] == 0).sum()
        if zero_vol > 0.2 * len(df):
            self.issues.append(
                f"WARNING: {zero_vol}/{len(df)} candles have zero volume"
            )

        # --- Holiday/weekend filter ---
        if "datetime" in df.columns:
            weekend_rows = (df["datetime"].dt.weekday >= 5).sum()
            if weekend_rows:
                self.issues.append(
                    f"Weekend rows present: {weekend_rows} removed"
                )
                df = df[df["datetime"].dt.weekday < 5]
            holiday_rows = df["datetime"].dt.date.isin(NSE_HOLIDAYS).sum()
            if holiday_rows:
                self.issues.append(
                    f"NSE holiday rows present: {holiday_rows} removed"
                )
                df = df[~df["datetime"].dt.date.isin(NSE_HOLIDAYS)]

        df = df.reset_index(drop=True)
        if not self.issues:
            self.issues.append("OK: Data validation passed — no issues found")
        return df, self.issues


# ══════════════════════════════════════════════════════════════════════════════
# CHARGE CALCULATOR  (BUG-02 FIXED — instance-based, configurable, all legs)
# ══════════════════════════════════════════════════════════════════════════════
class ChargeCalculator:
    """
    Precise NSE/BSE charge calculation for all instrument types.

    BUG-02 FIXES applied (2026-07-19):
      1. ChargeCalculator is now instance-based and accepts a ChargeConfig,
         making every rate independently overridable.
      2. options_sell() added — separate charges for closing a long option.
      3. options_round_trip() added — combines entry+exit charges using the
         ACTUAL entry premium and ACTUAL exit premium (not entry for both).
      4. exchange_options_pct now uses 0.05% on premium (was 0.00345% equity).
      5. equity_delivery() added for carry-forward positional trades.

    Usage:
        calc = ChargeCalculator()                         # default NSE rates
        calc = ChargeCalculator(ChargeConfig(brokerage_cap=25.0))  # custom

    AUDIT STEP 7 — Brokerage Validation.
    """

    def __init__(self, config: Optional[ChargeConfig] = None) -> None:
        self.cfg: ChargeConfig = config if config is not None else DEFAULT_CHARGE_CONFIG

    # ── Internal helpers ───────────────────────────────────────────────────────
    def _brokerage_one_leg(self, value: float) -> float:
        """Brokerage for a single leg (capped)."""
        return min(value * self.cfg.brokerage_pct, self.cfg.brokerage_cap)

    def _sebi(self, turnover: float) -> float:
        return turnover * self.cfg.sebi_pct

    def _gst(self, brokerage: float, exchange: float, sebi: float) -> float:
        return (brokerage + exchange + sebi) * self.cfg.gst_pct

    @staticmethod
    def _rd(**kwargs: float) -> Dict[str, float]:
        """Round all values to 4 decimal places."""
        return {k: round(v, 4) for k, v in kwargs.items()}

    # ── EQUITY — INTRADAY (MIS) ───────────────────────────────────────────────
    def equity_intraday(
        self, entry: float, exit_price: float, qty: int
    ) -> Dict[str, float]:
        """
        Equity intraday (MIS) charges.
        STT   : 0.025 % on SELL side only.
        Stamp : 0.003 % on BUY side only.
        """
        buy_val  = entry      * qty
        sell_val = exit_price * qty
        turnover = buy_val + sell_val

        brokerage = self._brokerage_one_leg(buy_val) + self._brokerage_one_leg(sell_val)
        stt       = sell_val  * self.cfg.stt_eq_intraday_pct
        exchange  = turnover  * self.cfg.exchange_equity_pct
        sebi      = self._sebi(turnover)
        gst       = self._gst(brokerage, exchange, sebi)
        stamp     = buy_val   * self.cfg.stamp_equity_buy_pct

        total = brokerage + stt + exchange + sebi + gst + stamp
        return self._rd(
            brokerage=brokerage, stt=stt, exchange=exchange,
            sebi=sebi, gst=gst, stamp=stamp, total=total,
        )

    # ── EQUITY — DELIVERY / CARRY FORWARD (CNC) ───────────────────────────────
    def equity_delivery(
        self, entry: float, exit_price: float, qty: int
    ) -> Dict[str, float]:
        """
        Equity delivery / positional (CNC) charges.
        STT   : 0.1 % on BOTH buy + sell sides.
        Stamp : 0.003 % on BUY side only.
        """
        buy_val  = entry      * qty
        sell_val = exit_price * qty
        turnover = buy_val + sell_val

        brokerage = self._brokerage_one_leg(buy_val) + self._brokerage_one_leg(sell_val)
        stt       = turnover  * self.cfg.stt_eq_delivery_pct   # both sides
        exchange  = turnover  * self.cfg.exchange_equity_pct
        sebi      = self._sebi(turnover)
        gst       = self._gst(brokerage, exchange, sebi)
        stamp     = buy_val   * self.cfg.stamp_equity_del_pct

        total = brokerage + stt + exchange + sebi + gst + stamp
        return self._rd(
            brokerage=brokerage, stt=stt, exchange=exchange,
            sebi=sebi, gst=gst, stamp=stamp, total=total,
        )

    # ── FUTURES ───────────────────────────────────────────────────────────────
    def futures(
        self, entry: float, exit_price: float, qty: int
    ) -> Dict[str, float]:
        """
        F&O Futures charges.
        STT      : 0.01 % on SELL side only.
        Exchange : 0.00210 % on total turnover.
        Stamp    : 0.002 % on BUY notional.
        """
        buy_val  = entry      * qty
        sell_val = exit_price * qty
        turnover = buy_val + sell_val

        brokerage = self._brokerage_one_leg(buy_val) + self._brokerage_one_leg(sell_val)
        stt       = sell_val  * self.cfg.stt_fut_pct
        exchange  = turnover  * self.cfg.exchange_futures_pct
        sebi      = self._sebi(turnover)
        gst       = self._gst(brokerage, exchange, sebi)
        stamp     = buy_val   * self.cfg.stamp_futures_buy_pct

        total = brokerage + stt + exchange + sebi + gst + stamp
        return self._rd(
            brokerage=brokerage, stt=stt, exchange=exchange,
            sebi=sebi, gst=gst, stamp=stamp, total=total,
        )

    # ── OPTIONS — ENTRY: BUY to open a long position ──────────────────────────
    def options_buy(
        self, premium: float, qty: int, is_expiry_itm: bool = False
    ) -> Dict[str, float]:
        """
        Charges for BUYING an option (opening a long position).

        STT      : 0.125 % on BUY premium.                   [stt_opt_pct]
        Exchange : 0.05  % on BUY premium (NSE options rate). [exchange_options_pct]
        Stamp    : 0.003 % on BUY premium.                   [stamp_options_buy_pct]
        Expiry ITM: additional 0.125 % on settlement value if held to expiry.

        Args:
            premium       : Option premium per unit at entry.
            qty           : Number of units (lots x lot_size).
            is_expiry_itm : True if option expires in-the-money.
        """
        buy_val = premium * qty

        brokerage  = self._brokerage_one_leg(buy_val)
        # STT is only charged on option sales/exits in India; normal buy STT is zero.
        stt        = 0.0
        exchange   = buy_val * self.cfg.exchange_options_pct     # 0.05% on premium
        sebi       = self._sebi(buy_val)
        gst        = self._gst(brokerage, exchange, sebi)
        stamp      = buy_val * self.cfg.stamp_options_buy_pct
        expiry_stt = buy_val * self.cfg.stt_opt_expiry_itm_pct if is_expiry_itm else 0.0

        total = brokerage + stt + exchange + sebi + gst + stamp + expiry_stt
        return self._rd(
            brokerage=brokerage,
            stt=stt + expiry_stt,
            exchange=exchange,
            sebi=sebi,
            gst=gst,
            stamp=stamp,
            total=total,
        )

    # ── OPTIONS — EXIT: SELL to close a long position (BUG-02 NEW METHOD) ─────
    def options_sell(self, exit_premium: float, qty: int) -> Dict[str, float]:
        """
        Charges for SELLING an option to CLOSE a long position.

        STT      : 0.125 % on SELL premium.  [stt_opt_pct]
        Exchange : 0.05  % on SELL premium.  [exchange_options_pct]
        Stamp    : ZERO on sell side.         [stamp_sell_pct = 0]
        No expiry STT (sold before expiry).

        Args:
            exit_premium : Option premium per unit at exit (actual exit price).
            qty          : Number of units.
        """
        sell_val = exit_premium * qty

        brokerage = self._brokerage_one_leg(sell_val)
        stt       = sell_val * self.cfg.stt_opt_pct              # on sell premium
        exchange  = sell_val * self.cfg.exchange_options_pct     # 0.05% on premium
        sebi      = self._sebi(sell_val)
        gst       = self._gst(brokerage, exchange, sebi)
        stamp     = sell_val * self.cfg.stamp_sell_pct           # = 0

        total = brokerage + stt + exchange + sebi + gst + stamp
        return self._rd(
            brokerage=brokerage, stt=stt, exchange=exchange,
            sebi=sebi, gst=gst, stamp=stamp, total=total,
        )

    # ── OPTIONS — ROUND TRIP: entry + exit combined (BUG-02 PRIMARY FIX) ──────
    def options_round_trip(
        self,
        entry_premium: float,
        exit_premium: float,
        qty: int,
        is_expiry_itm: bool = False,
    ) -> Dict[str, float]:
        """
        Total round-trip charges for a complete options trade.

        BUG-02 ROOT FIX: Previously _execute_exit() called options_buy() with
        the ENTRY premium for both legs, incorrectly computing exit charges.
        This method receives the ACTUAL entry_premium and ACTUAL exit_premium
        independently and sums both legs correctly.

        Sample (NIFTY CE, entry=200, exit=350, qty=50):
          Entry brokerage : min(200*50*0.0003, 20)  = Rs 3.00
          Entry STT       : 200*50 * 0.00125        = Rs 12.50
          Entry exchange  : 200*50 * 0.0005         = Rs 5.00
          Entry SEBI      : 200*50 * 0.000001       = Rs 0.01
          Entry GST       : (3+5+0.01)*0.18         = Rs 1.44
          Entry stamp     : 200*50 * 0.00003        = Rs 0.30
          Entry total                               = Rs 22.25

          Exit brokerage  : min(350*50*0.0003, 20)  = Rs 5.25  (capped Rs 20)
          Exit STT        : 350*50 * 0.00125        = Rs 21.875
          Exit exchange   : 350*50 * 0.0005         = Rs 8.75
          Exit SEBI       : 350*50 * 0.000001       = Rs 0.0175
          Exit GST        : (5.25+8.75+0.0175)*0.18 = Rs 2.52
          Exit stamp      : 0                       = Rs 0
          Exit total                                = Rs 38.41

          ROUND TRIP TOTAL                          = Rs 60.66

        Args:
            entry_premium : Premium paid at entry.
            exit_premium  : Premium received at exit.
            qty           : Number of units.
            is_expiry_itm : True if held to expiry and ITM.
        """
        entry_ch = self.options_buy(entry_premium, qty, is_expiry_itm=is_expiry_itm)
        exit_ch  = self.options_sell(exit_premium, qty)

        combined: Dict[str, float] = {}
        for key in set(list(entry_ch.keys()) + list(exit_ch.keys())):
            combined[key] = round(entry_ch.get(key, 0.0) + exit_ch.get(key, 0.0), 4)
        combined["total"]       = round(entry_ch["total"] + exit_ch["total"], 4)
        combined["entry_total"] = entry_ch["total"]   # audit trail
        combined["exit_total"]  = exit_ch["total"]    # audit trail
        return combined


# ══════════════════════════════════════════════════════════════════════════════
# SLIPPAGE MODEL
# ══════════════════════════════════════════════════════════════════════════════
class SlippageModel:
    """
    Realistic slippage model based on:
    - Volume (order size relative to candle volume)
    - ATR (volatility proxy)
    - Time of day (opening volatility premium)
    - Instrument type
    AUDIT STEP 6 — Slippage Model.
    """

    def __init__(
        self,
        base_bps: float = 2.0,         # 2 bps = 0.02% base slippage
        vol_impact_factor: float = 0.3, # How much volume ratio multiplies slippage
        opening_premium: float = 2.0,  # Extra multiplier in first 15 min
        configurable_bps: Optional[float] = None,
    ):
        self.base_bps = configurable_bps if configurable_bps is not None else base_bps
        self.vol_impact_factor = vol_impact_factor
        self.opening_premium = opening_premium

    def calculate(
        self,
        price: float,
        qty: int,
        candle_volume: float,
        atr: float,
        bar_time: Optional[datetime] = None,
        is_entry: bool = True,
        instrument: str = "EQUITY",
        spread: Optional[float] = None,
        is_expiry_day: bool = False,
        is_gap_up: bool = False,
        is_gap_down: bool = False,
        iv: Optional[float] = None,
        vix: Optional[float] = None,
    ) -> float:
        """
        Returns per-share slippage amount (₹).
        Slippage is applied as:
          - BUY: effective_price = price + slippage_per_share
          - SELL: effective_price = price - slippage_per_share
        """
        bps = self.base_bps

        # F&O has wider spreads
        if instrument in ("FUTURES", "OPTIONS"):
            bps *= 1.5

        # Volume impact — order size relative to candle volume (both in shares)
        if candle_volume and candle_volume > 0:
            order_value = price * qty
            # Candle volume is in shares; multiply by price to get value
            candle_value = candle_volume * price
            ratio = order_value / candle_value   # fraction of candle turnover we represent
            if ratio > 0.05:    # >5% of candle turnover — large market impact
                bps += self.vol_impact_factor * (ratio / 0.05) * bps
            elif ratio > 0.01:  # 1-5%: moderate impact
                bps += self.vol_impact_factor * 0.5 * bps
        else:
            bps *= 2.0  # No volume data → assume illiquid

        # Opening volatility premium (9:15–9:30 IST)
        if bar_time:
            t = bar_time.time() if hasattr(bar_time, "time") else bar_time
            if time(9, 15) <= t <= time(9, 30):
                bps *= self.opening_premium

        # ATR volatility adjustment
        if atr and atr > 0 and price > 0:
            atr_pct = atr / price * 100    # ATR as % of price
            if atr_pct > 1.5:              # High volatility: more slippage
                bps *= 1.2

        # Dynamic Institutional factors
        if is_expiry_day:
            bps *= 1.2  # Wide spreads on expiry day
        if is_gap_up or is_gap_down:
            bps *= 1.5  # Executing after overnight gap
        if iv and iv > 20.0:
            bps *= (iv / 20.0)  # High IV widening spreads
        if vix and vix > 18.0:
            bps *= (vix / 18.0)

        per_share = price * (bps / 10000.0)
        
        # Spread floor: slippage cannot be less than half the bid-ask spread
        if spread is not None and spread > 0:
            per_share = max(per_share, spread / 2.0)
            
        return per_share


# ══════════════════════════════════════════════════════════════════════════════
# INDICATORS (look-ahead safe — computed on slice ending at current bar)
# ══════════════════════════════════════════════════════════════════════════════
class Indicators:
    """
    All indicators use strictly historical data.
    AUDIT STEP 2 + STEP 4 — Indicator Validation + Look-Ahead Bias.
    """

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def sma(series: pd.Series, period: int) -> pd.Series:
        return series.rolling(period).mean()

    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        h = df["high"]
        l = df["low"]
        c = df["close"].shift(1)
        tr = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
        return tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain  = delta.clip(lower=0)
        loss  = (-delta).clip(lower=0)
        avg_g = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        avg_l = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        rs    = avg_g / avg_l.replace(0, np.nan)
        return 100 - 100 / (1 + rs)

    @staticmethod
    def macd(series: pd.Series, fast=12, slow=26, signal=9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        line     = ema_fast - ema_slow
        sig      = line.ewm(span=signal, adjust=False).mean()
        hist     = line - sig
        return line, sig, hist

    @staticmethod
    def vwap(df: pd.DataFrame) -> pd.Series:
        """VWAP reset per session (intraday only)."""
        typical = (df["high"] + df["low"] + df["close"]) / 3
        vol     = df["volume"].replace(0, np.nan)
        result  = pd.Series(np.nan, index=df.index)
        if "datetime" in df.columns:
            df = df.copy()
            df["_date"] = df["datetime"].dt.date
            for _date, grp in df.groupby("_date"):
                tp = typical.loc[grp.index]
                v  = vol.loc[grp.index]
                vwap_val = (tp * v).cumsum() / v.cumsum()
                result.loc[grp.index] = vwap_val.values
        else:
            result = (typical * vol).cumsum() / vol.cumsum()
        return result

    @staticmethod
    def bollinger(series: pd.Series, period=20, std_dev=2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
        mid   = series.rolling(period).mean()
        std   = series.rolling(period).std()
        upper = mid + std_dev * std
        lower = mid - std_dev * std
        return upper, mid, lower

    @staticmethod
    def adx(df: pd.DataFrame, period: int = 14) -> Tuple[pd.Series, pd.Series, pd.Series]:
        up   = df["high"].diff()
        down = -df["low"].diff()
        pdm  = pd.Series(np.where((up > down) & (up > 0),   up,   0.0), index=df.index)
        ndm  = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
        h, l, c = df["high"], df["low"], df["close"].shift(1)
        tr   = pd.concat([h - l, (h - c).abs(), (l - c).abs()], axis=1).max(axis=1)
        atr_ = tr.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        pdi  = 100 * pdm.ewm(alpha=1/period, min_periods=period, adjust=False).mean() / atr_
        ndi  = 100 * ndm.ewm(alpha=1/period, min_periods=period, adjust=False).mean() / atr_
        dx   = 100 * (pdi - ndi).abs() / (pdi + ndi).replace(0, np.nan)
        adx_ = dx.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
        return adx_.fillna(0), pdi.fillna(0), ndi.fillna(0)

    @staticmethod
    def supertrend(df: pd.DataFrame, period=10, multiplier=3.0) -> pd.Series:
        atr_ = Indicators.atr(df, period)
        hl2  = (df["high"] + df["low"]) / 2
        upper = hl2 + multiplier * atr_
        lower = hl2 - multiplier * atr_
        st    = pd.Series(np.nan, index=df.index)
        trend = pd.Series(True, index=df.index)   # True = bullish
        for i in range(1, len(df)):
            prev_upper = upper.iloc[i-1]
            prev_lower = lower.iloc[i-1]
            curr_upper = upper.iloc[i]
            curr_lower = lower.iloc[i]
            curr_close = df["close"].iloc[i]
            upper.iloc[i] = curr_upper if curr_upper < prev_upper or df["close"].iloc[i-1] > prev_upper else prev_upper
            lower.iloc[i] = curr_lower if curr_lower > prev_lower or df["close"].iloc[i-1] < prev_lower else prev_lower
            if trend.iloc[i-1] and curr_close < lower.iloc[i]:
                trend.iloc[i] = False
            elif not trend.iloc[i-1] and curr_close > upper.iloc[i]:
                trend.iloc[i] = True
            else:
                trend.iloc[i] = trend.iloc[i-1]
            st.iloc[i] = lower.iloc[i] if trend.iloc[i] else upper.iloc[i]
        return trend  # True = price above ST (bullish)

    @staticmethod
    def swing_highs(series: pd.Series, window: int = 5) -> pd.Series:
        """Rolling max — swing high level (no look-ahead)."""
        return series.rolling(window).max()

    @staticmethod
    def swing_lows(series: pd.Series, window: int = 5) -> pd.Series:
        return series.rolling(window).min()

    @staticmethod
    def detect_fvg(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
        """Fair Value Gap: gap between candle[i-2].high and candle[i].low (bullish) or vice versa."""
        bull_fvg = df["low"] > df["high"].shift(2)
        bear_fvg = df["high"] < df["low"].shift(2)
        return bull_fvg.fillna(False), bear_fvg.fillna(False)

    @staticmethod
    def apply_all(df: pd.DataFrame) -> pd.DataFrame:
        """Compute all indicators and attach to df. LOOK-AHEAD SAFE — purely historical."""
        df = df.copy()
        df.columns = [c.lower() for c in df.columns]

        df["ema_9"]     = Indicators.ema(df["close"], 9)
        df["ema_20"]    = Indicators.ema(df["close"], 20)
        df["ema_50"]    = Indicators.ema(df["close"], 50)
        df["sma_200"]   = Indicators.sma(df["close"], 200)
        df["atr_14"]    = Indicators.atr(df, 14)
        df["rsi_14"]    = Indicators.rsi(df["close"], 14)
        df["macd_line"], df["macd_signal"], df["macd_hist"] = Indicators.macd(df["close"])
        df["adx_14"], df["plus_di"], df["minus_di"]         = Indicators.adx(df, 14)
        df["bb_upper"], df["bb_mid"], df["bb_lower"]        = Indicators.bollinger(df["close"])
        df["supertrend"]  = Indicators.supertrend(df)
        df["vwap"]        = Indicators.vwap(df)
        df["swing_high"]  = Indicators.swing_highs(df["high"],  10)
        df["swing_low"]   = Indicators.swing_lows(df["low"],   10)
        df["fvg_bull"], df["fvg_bear"] = Indicators.detect_fvg(df)
        return df


# ══════════════════════════════════════════════════════════════════════════════
# POSITION SIZER
# ══════════════════════════════════════════════════════════════════════════════
class PositionSizer:
    """
    AUDIT STEP 8 + STEP 9 — Risk Management + F&O Validation.
    """

    def __init__(
        self,
        capital: float,
        risk_pct: float = 0.01,       # 1% risk per trade
        max_exposure_pct: float = 0.90, # Max 90% capital in one trade
        lot_size: int = 1,
        instrument: str = "EQUITY",
    ):
        self.capital      = capital
        self.risk_pct     = risk_pct
        self.max_exp      = max_exposure_pct
        self.lot_size     = lot_size
        self.instrument   = instrument

    def size(self, price: float, sl: float) -> Tuple[int, float]:
        """
        Returns (quantity, actual_risk_amount).
        For F&O: quantity is always a multiple of lot_size.
        """
        risk_per_share = abs(price - sl)
        if risk_per_share <= 0:
            return 0, 0.0

        risk_amount = self.capital * self.risk_pct
        raw_qty     = risk_amount / risk_per_share

        if self.instrument in ("FUTURES", "OPTIONS"):
            lots    = max(1, int(raw_qty / self.lot_size))
            qty     = lots * self.lot_size
        else:
            qty = max(1, int(raw_qty))

        # Cap by capital constraint
        max_qty = max(1, int(self.capital * self.max_exp / price))
        qty     = min(qty, max_qty)

        actual_risk = risk_per_share * qty
        return qty, actual_risk


# ══════════════════════════════════════════════════════════════════════════════
# F&O UTILITIES
# ══════════════════════════════════════════════════════════════════════════════
class FnOUtils:
    """
    AUDIT STEP 9 — F&O Validation.
    """

    @staticmethod
    def get_atm_strike(underlying_price: float, instrument: str = "NIFTY") -> int:
        """Round to nearest valid ATM strike."""
        interval = 50 if "NIFTY" in instrument.upper() and "BANK" not in instrument.upper() else 100
        return int(round(underlying_price / interval) * interval)

    @staticmethod
    def next_weekly_expiry(ref_date: date) -> date:
        """Returns the next Thursday (NSE weekly expiry) from ref_date."""
        days_ahead = (3 - ref_date.weekday()) % 7   # 3 = Thursday
        if days_ahead == 0:
            days_ahead = 7
        exp = ref_date + timedelta(days=days_ahead)
        # If that Thursday is a holiday, move to Wednesday
        while exp in NSE_HOLIDAYS:
            exp -= timedelta(days=1)
        return exp

    @staticmethod
    def next_monthly_expiry(ref_date: date) -> date:
        """Returns the last Thursday of the current month, or next month if already passed."""
        import calendar
        y, m = ref_date.year, ref_date.month
        last_day = calendar.monthrange(y, m)[1]
        last_thurs = date(y, m, last_day)
        while last_thurs.weekday() != 3: # 3 = Thursday
            last_thurs -= timedelta(days=1)
        
        if ref_date <= last_thurs:
            while last_thurs in NSE_HOLIDAYS:
                last_thurs -= timedelta(days=1)
            return last_thurs
        else:
            nm = m + 1 if m < 12 else 1
            ny = y if m < 12 else y + 1
            last_day = calendar.monthrange(ny, nm)[1]
            last_thurs = date(ny, nm, last_day)
            while last_thurs.weekday() != 3:
                last_thurs -= timedelta(days=1)
            while last_thurs in NSE_HOLIDAYS:
                last_thurs -= timedelta(days=1)
            return last_thurs

    @staticmethod
    def is_expiry_day(ref_date: date, instrument: str = "NIFTY") -> bool:
        """Check if today is the weekly expiry for the instrument."""
        return FnOUtils.next_weekly_expiry(ref_date - timedelta(days=1)) == ref_date

    @staticmethod
    def calculate_greeks_and_premium(
        underlying: float,
        strike: float,
        days_to_expiry: int,
        iv_pct: float = 15.0,
        option_type: str = "CE",
        r: float = 0.065
    ) -> Dict[str, float]:
        """
        Calculates exact Black-Scholes option premium and all Greeks:
        Delta, Gamma, Theta (daily), Vega, Rho.
        """
        import math
        from statistics import NormalDist
        
        T = days_to_expiry / 365.0
        s = underlying
        k = strike
        v = iv_pct / 100.0
        
        res = {
            "premium": 0.05,
            "delta": 1.0 if option_type == "CE" else -1.0,
            "gamma": 0.0,
            "theta": 0.0,
            "vega": 0.0,
            "rho": 0.0,
            "iv": iv_pct
        }
        
        if days_to_expiry <= 0:
            # Intrinsic value only
            if option_type == "CE":
                res["premium"] = max(0.05, round(underlying - strike, 2))
            else:
                res["premium"] = max(0.05, round(strike - underlying, 2))
            return res
            
        try:
            d1 = (math.log(s / k) + (r + 0.5 * v**2) * T) / (v * math.sqrt(T))
            d2 = d1 - v * math.sqrt(T)
            
            N = NormalDist().cdf
            pdf = NormalDist().pdf
            
            # Premium
            if option_type == "CE":
                premium = s * N(d1) - k * math.exp(-r * T) * N(d2)
                delta = N(d1)
                theta = (- (s * pdf(d1) * v) / (2 * math.sqrt(T)) - r * k * math.exp(-r * T) * N(d2)) / 365.0
                rho = (k * T * math.exp(-r * T) * N(d2)) / 100.0
            else:
                premium = k * math.exp(-r * T) * N(-d2) - s * N(-d1)
                delta = N(d1) - 1.0
                theta = (- (s * pdf(d1) * v) / (2 * math.sqrt(T)) + r * k * math.exp(-r * T) * N(-d2)) / 365.0
                rho = (-k * T * math.exp(-r * T) * N(-d2)) / 100.0
                
            gamma = pdf(d1) / (s * v * math.sqrt(T))
            vega = (s * pdf(d1) * math.sqrt(T)) / 100.0 # for 1% IV change
            
            res["premium"] = max(0.05, round(premium, 2))
            res["delta"] = round(delta, 4)
            res["gamma"] = round(gamma, 6)
            res["theta"] = round(theta, 4)
            res["vega"] = round(vega, 4)
            res["rho"] = round(rho, 4)
        except Exception:
            # Fallback
            if option_type == "CE":
                res["premium"] = max(0.05, round(underlying - strike, 2))
            else:
                res["premium"] = max(0.05, round(strike - underlying, 2))
                
        return res

    @staticmethod
    def solve_iv(
        market_price: float,
        underlying: float,
        strike: float,
        days_to_expiry: int,
        option_type: str = "CE",
        r: float = 0.065
    ) -> float:
        """
        Solves for implied volatility % (e.g. 15.0) given market price using bisection.
        """
        if days_to_expiry <= 0 or market_price <= 0.05:
            return 15.0
            
        low_iv = 0.01  # 1%
        high_iv = 5.0  # 500%
        
        # Bisection search
        for _ in range(50):
            mid_iv = (low_iv + high_iv) / 2.0
            calc = FnOUtils.calculate_greeks_and_premium(underlying, strike, days_to_expiry, mid_iv * 100.0, option_type, r)
            calc_premium = calc["premium"]
            
            if abs(calc_premium - market_price) < 0.01:
                return mid_iv * 100.0
                
            if calc_premium < market_price:
                low_iv = mid_iv
            else:
                high_iv = mid_iv
                
        return (low_iv + high_iv) / 2.0 * 100.0

    @staticmethod
    def estimate_option_premium(
        underlying: float,
        strike: float,
        days_to_expiry: int,
        iv_pct: float = 15.0,   # annualised IV %
        option_type: str = "CE",
    ) -> float:
        """
        Black-Scholes-like premium estimate (simplified, for backtest sizing).
        Returns approximate premium in index points.
        """
        calc = FnOUtils.calculate_greeks_and_premium(underlying, strike, days_to_expiry, iv_pct, option_type)
        return calc["premium"]


# ══════════════════════════════════════════════════════════════════════════════
# PERFORMANCE METRICS
# ══════════════════════════════════════════════════════════════════════════════
class PerformanceMetrics:
    """
    AUDIT STEP 12 — All 18 performance metrics.
    """

    @staticmethod
    def compute(
        trades: List[Dict],
        equity_curve: List[float],
        initial_capital: float,
        periods_per_year: int = 252,  # trading days
    ) -> Dict[str, Any]:
        if not trades:
            return {"message": "No trades to analyse"}

        df = pd.DataFrame(trades)
        net_pnls = df["net_pnl"].values
        gross_profit = df.loc[df["net_pnl"] > 0, "net_pnl"].sum()
        gross_loss   = df.loc[df["net_pnl"] <= 0, "net_pnl"].sum()

        total_trades  = len(df)
        winners       = df[df["net_pnl"] > 0]
        losers        = df[df["net_pnl"] <= 0]
        win_count     = len(winners)
        loss_count    = len(losers)
        win_rate      = win_count / total_trades * 100 if total_trades else 0
        avg_win       = winners["net_pnl"].mean() if win_count else 0
        avg_loss      = abs(losers["net_pnl"].mean()) if loss_count else 0
        largest_win   = winners["net_pnl"].max() if win_count else 0
        largest_loss  = abs(losers["net_pnl"].min()) if loss_count else 0

        # Profit Factor
        pf = gross_profit / abs(gross_loss) if gross_loss != 0 else float("inf")

        # Expectancy
        wr_dec = win_count / total_trades if total_trades else 0
        expectancy = wr_dec * avg_win - (1 - wr_dec) * avg_loss

        # Daily returns for Sharpe / Sortino
        eq = pd.Series(equity_curve)
        daily_ret = eq.pct_change().dropna()

        if len(daily_ret) > 1 and daily_ret.std() > 0:
            sharpe = (daily_ret.mean() / daily_ret.std()) * np.sqrt(periods_per_year)
        else:
            sharpe = 0.0

        neg_ret = daily_ret[daily_ret < 0]
        if len(neg_ret) > 0 and neg_ret.std() > 0:
            sortino = (daily_ret.mean() / neg_ret.std()) * np.sqrt(periods_per_year)
        else:
            sortino = sharpe

        # Max Drawdown (equity-curve based)
        rolling_max = eq.cummax()
        drawdown    = (eq - rolling_max) / rolling_max * 100
        max_dd_pct  = abs(drawdown.min())
        max_dd_abs  = abs((eq - rolling_max).min())

        # Calmar Ratio (annualised return / max drawdown)
        final_bal   = equity_curve[-1] if equity_curve else initial_capital
        net_profit  = final_bal - initial_capital
        total_ret   = net_profit / initial_capital * 100
        # Assume period = calendar days covered
        calmar = total_ret / max_dd_pct if max_dd_pct > 0 else float("inf")

        # MAR (same as Calmar for annual)
        # Recovery Factor
        recovery    = net_profit / max_dd_abs if max_dd_abs > 0 else float("inf")

        # Consecutive win/loss streaks
        win_streak = loss_streak = cur_streak = 0
        for pnl in net_pnls:
            if pnl > 0:
                cur_streak = cur_streak + 1 if cur_streak >= 0 else 1
            else:
                cur_streak = cur_streak - 1 if cur_streak <= 0 else -1
            win_streak  = max(win_streak,  cur_streak)
            loss_streak = max(loss_streak, abs(min(0, cur_streak)))

        # Holding time
        avg_hold = 0
        if "bars_held" in df.columns:
            avg_hold = df["bars_held"].mean()
        elif "entry_time" in df.columns and "exit_time" in df.columns:
            try:
                df["_dur"] = (pd.to_datetime(df["exit_time"]) -
                               pd.to_datetime(df["entry_time"])).dt.total_seconds() / 60
                avg_hold = df["_dur"].mean()
            except Exception:
                pass

        # Rolling Sharpe (20-trade window)
        rolling_sharpe = []
        if len(net_pnls) >= 20:
            for k in range(20, len(net_pnls)):
                window = net_pnls[k-20:k]
                s = np.std(window)
                rolling_sharpe.append(
                    (np.mean(window) / s * np.sqrt(252)) if s > 0 else 0
                )

        return {
            # Trade counts
            "total_trades":      total_trades,
            "winning_trades":    win_count,
            "losing_trades":     loss_count,

            # Win/Loss
            "win_rate":          round(win_rate, 2),
            "loss_rate":         round(100 - win_rate, 2),
            "avg_win":           round(avg_win, 2),
            "avg_loss":          round(avg_loss, 2),
            "largest_win":       round(largest_win, 2),
            "largest_loss":      round(largest_loss, 2),

            # PnL
            "gross_profit":      round(gross_profit, 2),
            "gross_loss":        round(gross_loss, 2),
            "net_profit":        round(net_profit, 2),
            "total_return_pct":  round(total_ret, 2),
            "total_charges":     round(df["charges"].sum() if "charges" in df else 0, 2),

            # Risk Ratios
            "profit_factor":     round(min(pf, 99.0), 3),
            "expectancy":        round(expectancy, 2),
            "sharpe_ratio":      round(sharpe, 3),
            "sortino_ratio":     round(sortino, 3),
            "calmar_ratio":      round(calmar, 3),
            "recovery_factor":   round(recovery, 3),

            # Drawdown
            "max_drawdown_pct":  round(max_dd_pct, 2),
            "max_drawdown_abs":  round(max_dd_abs, 2),

            # Streaks
            "max_win_streak":    win_streak,
            "max_loss_streak":   loss_streak,

            # Timing
            "avg_hold_bars":     round(avg_hold, 1),
            "trade_frequency":   round(total_trades / (len(equity_curve) + 1), 4),

            # Equity
            "initial_capital":   initial_capital,
            "final_capital":     round(final_bal, 2),
            "rolling_sharpe":    rolling_sharpe,
        }

    @staticmethod
    def monthly_returns(trades: List[Dict], initial_capital: float) -> pd.DataFrame:
        """Monthly PnL breakdown for heatmap generation."""
        if not trades:
            return pd.DataFrame()
        df = pd.DataFrame(trades)
        df["exit_dt"] = pd.to_datetime(df["exit_time"], errors="coerce")
        df = df.dropna(subset=["exit_dt"])
        df["year"]  = df["exit_dt"].dt.year
        df["month"] = df["exit_dt"].dt.month
        monthly = df.groupby(["year", "month"])["net_pnl"].sum().reset_index()
        pivot   = monthly.pivot(index="year", columns="month", values="net_pnl").fillna(0)
        pivot.columns = [f"M{c:02d}" for c in pivot.columns]
        return pivot


# ══════════════════════════════════════════════════════════════════════════════
# SIGNAL AUDIT LOG
# ══════════════════════════════════════════════════════════════════════════════
class SignalAuditLog:
    """
    AUDIT STEP 3 — Per-candle signal validation log.
    Records every filter pass/fail for every candle evaluated.
    """

    def __init__(self):
        self.entries: List[Dict] = []

    def record(
        self,
        bar_idx: int,
        bar_time: Any,
        price: float,
        atr: float,
        rsi: float,
        ema9: float,
        ema20: float,
        vwap: float,
        supertrend: bool,
        adx: float,
        macd_hist: float,
        fvg: bool,
        signal_candidate: str,
        filters: Dict[str, bool],
        final_signal: str,
        rejection_reason: str = "",
    ):
        self.entries.append({
            "bar_idx":         bar_idx,
            "datetime":        str(bar_time)[:19] if bar_time else "",
            "price":           round(price, 2),
            "atr":             round(atr, 4),
            "rsi":             round(rsi, 2),
            "ema9":            round(ema9, 2),
            "ema20":           round(ema20, 2),
            "vwap":            round(vwap, 2),
            "supertrend_bull": supertrend,
            "adx":             round(adx, 2),
            "macd_hist":       round(macd_hist, 4),
            "fvg":             fvg,
            "candidate":       signal_candidate,
            **{f"f_{k}": v for k, v in filters.items()},
            "signal":          final_signal,
            "rejection":       rejection_reason,
        })

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.entries)

    def export(self, path: str):
        df = self.to_dataframe()
        df.to_csv(path, index=False)


class Order:
    """
    Represents an institutional order inside the execution queue.
    Supports Market, Limit, Partial Fills, and tracking.
    """
    def __init__(
        self,
        signal: str, # BUY or SELL
        order_type: str, # MARKET or LIMIT
        qty: int,
        limit_price: Optional[float] = None,
        timestamp: Optional[Any] = None,
        option_type: Optional[str] = None,
        strike: Optional[float] = None,
        expiry: Optional[str] = None
    ):
        self.signal = signal
        self.order_type = order_type.upper()
        self.qty = qty
        self.limit_price = limit_price
        self.timestamp = timestamp
        self.option_type = option_type
        self.strike = strike
        self.expiry = expiry
        
        self.status = "PENDING" # PENDING | FILLED | PARTIALLY_FILLED | REJECTED
        self.filled_qty = 0
        self.filled_price = 0.0
        self.rejection_reason = ""


class MarginCalculator:
    """
    Broker-grade margin calculator supporting:
    - SPAN and Exposure margins for short options / futures
    - Premium margin for long options
    - Configurable rules for Zerodha, Angel One, Dhan, Groww
    """
    @staticmethod
    def calculate_required_margin(
        price: float,
        qty: int,
        strike: float,
        instrument: str = "OPTIONS",
        side: str = "BUY", # BUY (long) or SELL (short)
        broker: str = "ZERODHA", # ZERODHA | ANGELONE | DHAN | GROWW
        lot_size: int = 1
    ) -> float:
        if instrument.upper() != "OPTIONS":
            if instrument.upper() == "FUTURES":
                # Futures require SPAN + Exposure (roughly 12% total margin)
                return price * qty * 0.12
            else:
                # Equity cash CNC: 100% margin required
                return price * qty

        if side.upper() == "BUY":
            # Long Option: only premium margin (100% of premium)
            return price * qty
        else:
            # Short Option (Writing/Selling to open): SPAN + Exposure Margin
            # In India, SPAN is usually around 15% and Exposure is 3.5% (index) or 5.0% (stock) of notional value.
            notional = strike * qty
            broker_upper = broker.upper()
            if broker_upper == "ZERODHA":
                span_pct = 0.150
                exposure_pct = 0.035
            elif broker_upper == "ANGELONE":
                span_pct = 0.145
                exposure_pct = 0.035
            elif broker_upper == "DHAN":
                span_pct = 0.140
                exposure_pct = 0.035
            elif broker_upper == "GROWW":
                span_pct = 0.150
                exposure_pct = 0.035
            else:
                span_pct = 0.150
                exposure_pct = 0.035
                
            span_margin = notional * span_pct
            exposure_margin = notional * exposure_pct
            return span_margin + exposure_margin


class ReconciliationEngine:
    """
    Compares backtest trades against live paper trades to generate
    discrepancy statistics (slippage, entry/exit prices, PnL, charges).
    """
    @staticmethod
    def reconcile(
        backtest_trades: List[Dict[str, Any]],
        paper_trades: List[Dict[str, Any]],
        max_time_diff_sec: int = 300
    ) -> Dict[str, Any]:
        matched = []
        unmatched_backtest = []
        unmatched_paper = list(paper_trades)
        
        # Match trades based on entry timestamp closeness
        for bt in backtest_trades:
            bt_entry_time = pd.to_datetime(bt["entry_time"])
            best_match = None
            best_diff = timedelta(seconds=max_time_diff_sec)
            
            for pt in unmatched_paper:
                pt_entry_time = pd.to_datetime(pt["entry_time"])
                diff = abs(bt_entry_time - pt_entry_time)
                if diff <= best_diff:
                    best_diff = diff
                    best_match = pt
            
            if best_match:
                matched.append((bt, best_match))
                unmatched_paper.remove(best_match)
            else:
                unmatched_backtest.append(bt)
                
        # Calculate differences
        pnl_diffs = []
        slippage_diffs = []
        charges_diffs = []
        entry_price_diffs = []
        exit_price_diffs = []
        
        for bt, pt in matched:
            pnl_diffs.append(abs(bt.get("net_pnl", 0) - pt.get("net_pnl", 0)))
            # Slippage diff (entry slip + exit slip)
            bt_slip = bt.get("entry_slip", 0) + bt.get("exit_slip", 0)
            pt_slip = pt.get("entry_slip", 0) + pt.get("exit_slip", 0)
            slippage_diffs.append(abs(bt_slip - pt_slip))
            charges_diffs.append(abs(bt.get("charges", 0) - pt.get("charges", 0)))
            entry_price_diffs.append(abs(bt.get("effective_entry", bt.get("entry", 0)) - pt.get("effective_entry", pt.get("entry", 0))))
            exit_price_diffs.append(abs(bt.get("effective_exit", bt.get("exit", 0)) - pt.get("effective_exit", pt.get("exit", 0))))
            
        return {
            "total_backtest_trades": len(backtest_trades),
            "total_paper_trades": len(paper_trades),
            "matched_trades": len(matched),
            "unmatched_backtest_trades": len(unmatched_backtest),
            "unmatched_paper_trades": len(unmatched_paper),
            "avg_pnl_diff": np.mean(pnl_diffs) if pnl_diffs else 0.0,
            "avg_slippage_diff": np.mean(slippage_diffs) if slippage_diffs else 0.0,
            "avg_charges_diff": np.mean(charges_diffs) if charges_diffs else 0.0,
            "avg_entry_price_diff": np.mean(entry_price_diffs) if entry_price_diffs else 0.0,
            "avg_exit_price_diff": np.mean(exit_price_diffs) if exit_price_diffs else 0.0,
        }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN BACKTEST ENGINE
# ══════════════════════════════════════════════════════════════════════════════
class QuantumBacktestEngine:
    """
    Institutional-grade backtesting engine.

    Key design principles (all audited):
    - Entry is at the OPEN of the NEXT candle after signal fires (no look-ahead)
    - Exit is at SL/TP price or next candle's open if gap-through
    - One position at a time (configurable)
    - All charges calculated precisely
    - Full signal audit trail

    AUDIT STEPS 1-20.
    """

    def __init__(
        self,
        initial_capital:    float = 100_000.0,
        risk_pct:           float = 0.01,
        max_daily_loss_pct: float = 0.03,
        max_positions:      int   = 1,
        max_trades_per_day: int   = 3,
        atr_sl_mult:        float = 2.0,
        atr_tp_mult:        float = 4.0,
        instrument:         str   = "EQUITY",  # EQUITY | FUTURES | OPTIONS
        lot_size:           int   = 1,
        slippage_bps:       float = 2.0,
        interval_minutes:   int   = 5,
        mode:               str   = "INTRADAY",  # INTRADAY | POSITIONAL
        warmup_bars:        int   = 50,
        verbose:            bool  = False,
        symbol:             str   = "NIFTY",
        option_chain_data:  Optional[pd.DataFrame] = None,
        vix_data:           Optional[pd.DataFrame] = None,
        broker:             str   = "ZERODHA",
    ):
        self.initial_capital    = initial_capital
        self.risk_pct           = risk_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_positions      = max_positions
        self.max_trades_per_day = max_trades_per_day
        self.atr_sl_mult        = atr_sl_mult
        self.atr_tp_mult        = atr_tp_mult
        self.instrument         = instrument.upper()
        self.lot_size           = lot_size
        self.interval_minutes   = interval_minutes
        self.mode               = mode.upper()
        self.warmup_bars        = warmup_bars
        self.verbose            = verbose
        self.symbol             = symbol.upper()
        self.option_chain_data  = option_chain_data
        self.vix_data           = vix_data
        self.broker             = broker

        self.slippage_model = SlippageModel(base_bps=slippage_bps)
        self.charge_calc    = ChargeCalculator()
        self.audit_log      = SignalAuditLog()

        # State
        self._reset()

    def _reset(self):
        self.capital       = self.initial_capital
        self.equity_curve  = [self.initial_capital]
        self.trades: List[Dict] = []
        self.open_trades: List[Dict] = []
        self.daily_state: Dict[str, Any] = {}
        self.order_queue: List[Order] = []

    # ── STEP 4: Look-Ahead Bias Detection ─────────────────────────────────────
    def _get_bar(self, df: pd.DataFrame, i: int) -> Optional[pd.Series]:
        """Safe bar accessor — only returns bar at index i."""
        if i < 0 or i >= len(df):
            return None
        return df.iloc[i]

    def _get_history(self, df: pd.DataFrame, i: int) -> pd.DataFrame:
        """
        Returns slice df.iloc[0:i+1] — strictly historical, no future data.
        AUDIT: future candles [i+1:] are NEVER accessed during signal generation.
        """
        return df.iloc[: i + 1]

    # ── STEP 5: Execution Engine ───────────────────────────────────────────────
    def _get_option_data(
        self,
        underlying: float,
        strike: float,
        option_type: str,
        bar_time: Any,
        dte: int,
        iv_fallback: float = 15.0
    ) -> Dict[str, Any]:
        """
        Retrieves option data (premium, bid, ask, volume, open_interest, iv, greeks).
        Attempts lookup in real option chain data if available.
        Falls back to BSM model otherwise.
        """
        # Check if self.option_chain_data is set
        if hasattr(self, "option_chain_data") and self.option_chain_data is not None:
            t_str = str(bar_time)[:19]
            df_opt = self.option_chain_data
            matches = df_opt[
                (df_opt["datetime"].astype(str).str.slice(0, 19) == t_str) &
                (df_opt["strike"] == strike) &
                (df_opt["option_type"] == option_type)
            ]
            if not matches.empty:
                match = matches.iloc[0]
                premium = float(match.get("premium", match.get("close", 0.0)))
                bid = float(match.get("bid", premium * 0.99))
                ask = float(match.get("ask", premium * 1.01))
                vol = float(match.get("volume", 0.0))
                oi = float(match.get("open_interest", 0.0))
                iv = float(match.get("iv", iv_fallback))
                
                delta = match.get("delta", None)
                gamma = match.get("gamma", None)
                theta = match.get("theta", None)
                vega = match.get("vega", None)
                rho = match.get("rho", None)
                
                if delta is None or pd.isna(delta):
                    greeks = FnOUtils.calculate_greeks_and_premium(underlying, strike, dte, iv, option_type)
                    delta = greeks["delta"]
                    gamma = greeks["gamma"]
                    theta = greeks["theta"]
                    vega = greeks["vega"]
                    rho = greeks["rho"]
                    
                return {
                    "source": "REAL",
                    "premium": premium,
                    "bid": bid,
                    "ask": ask,
                    "volume": vol,
                    "open_interest": oi,
                    "iv": iv,
                    "delta": delta,
                    "gamma": gamma,
                    "theta": theta,
                    "vega": vega,
                    "rho": rho
                }
                
        # FALLBACK MODE (Black-Scholes-Merton)
        # Compute dynamic IV Smile/Skew
        spot = underlying
        d = (strike - spot) / spot if spot else 0.0
        skew_coef = -0.1
        smile_coef = 0.5
        vix_val = getattr(self, "vix_data", None)
        if vix_val is not None:
            if isinstance(vix_val, pd.DataFrame):
                t_str = str(bar_time)[:19]
                vix_match = vix_val[vix_val["datetime"].astype(str).str.slice(0, 19) == t_str]
                if not vix_match.empty:
                    base_iv = float(vix_match.iloc[0]["close"])
                else:
                    base_iv = iv_fallback
            else:
                base_iv = float(vix_val)
        else:
            base_iv = iv_fallback
            
        iv = base_iv * (1.0 + skew_coef * d + smile_coef * d**2)
        
        greeks = FnOUtils.calculate_greeks_and_premium(underlying, strike, dte, iv, option_type)
        premium = greeks["premium"]
        
        spread = premium * 0.01 + 0.05 # 1% spread + 1 tick
        bid = max(0.05, premium - spread / 2)
        ask = premium + spread / 2
        
        return {
            "source": "MODEL",
            "premium": premium,
            "bid": bid,
            "ask": ask,
            "volume": 0.0,
            "open_interest": 0.0,
            "iv": iv,
            "delta": greeks["delta"],
            "gamma": greeks["gamma"],
            "theta": greeks["theta"],
            "vega": greeks["vega"],
            "rho": greeks["rho"]
        }

    # ── STEP 5: Execution Engine ───────────────────────────────────────────────
    def _execute_entry(
        self,
        signal: str,
        entry_bar: pd.Series,
        atr: float,
        bar_time: Any,
    ) -> Optional[Dict]:
        """
        Entry execution:
        - Fill at NEXT bar's OPEN price (no look-ahead bias).
        - Apply slippage based on next bar's volume and dynamic factors.
        - Check margin and capital requirements.
        """
        entry_price = float(entry_bar["open"])
        volume      = float(entry_bar.get("volume", 0))

        if self.instrument == "OPTIONS":
            option_type = "CE" if signal == "BUY" else "PE"
            symbol_upper = self.symbol.upper()

            # Select strike interval dynamically
            if "NIFTY" in symbol_upper or "NSEI" in symbol_upper:
                if "BANK" in symbol_upper or "NSEBANK" in symbol_upper:
                    interval = 100
                elif "FIN" in symbol_upper:
                    interval = 50
                else:
                    interval = 50
            else:
                if entry_price < 200:
                    interval = 2.5
                elif entry_price < 500:
                    interval = 5
                elif entry_price < 1000:
                    interval = 10
                elif entry_price < 2000:
                    interval = 20
                else:
                    interval = 50

            strike = int(round(entry_price / interval) * interval)
            ref_date = bar_time.date() if hasattr(bar_time, "date") else bar_time
            is_index = any(idx in symbol_upper for idx in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NSEI", "NSEBANK"])
            expiry_date = FnOUtils.next_weekly_expiry(ref_date) if (is_index and getattr(self, "expiry_type", "WEEKLY") == "WEEKLY") else FnOUtils.next_monthly_expiry(ref_date)
            dte = max(0, (expiry_date - ref_date).days)

            # Query Option Data
            opt_data = self._get_option_data(entry_price, strike, option_type, bar_time, dte)
            premium = opt_data["premium"]
            ask = opt_data["ask"]
            bid = opt_data["bid"]
            spread = ask - bid
            
            # Position sizing
            sl_underlying = entry_price - self.atr_sl_mult * atr if signal == "BUY" else entry_price + self.atr_sl_mult * atr
            greeks_sl = FnOUtils.calculate_greeks_and_premium(
                underlying=sl_underlying,
                strike=strike,
                days_to_expiry=dte,
                iv_pct=opt_data["iv"],
                option_type=option_type
            )
            risk_per_share = ask - greeks_sl["premium"]
            if risk_per_share <= 0:
                risk_per_share = max(0.05, ask * 0.5)

            sizer = PositionSizer(
                capital=self.capital,
                risk_pct=self.risk_pct,
                lot_size=self.lot_size,
                instrument="OPTIONS"
            )
            risk_amount = self.capital * self.risk_pct
            qty = max(self.lot_size, int(risk_amount / risk_per_share / self.lot_size) * self.lot_size)
            max_qty = max(self.lot_size, int(self.capital * sizer.max_exp / ask / self.lot_size) * self.lot_size)
            qty = min(qty, max_qty)

            # Margin Check
            margin_required = MarginCalculator.calculate_required_margin(
                price=ask,
                qty=qty,
                strike=strike,
                instrument="OPTIONS",
                side="BUY",
                broker=self.broker,
                lot_size=self.lot_size
            )
            if margin_required > self.capital:
                if self.verbose:
                    print(f"  [REJECT] Insufficient Margin: Req {margin_required:.2f} > Cap {self.capital:.2f}")
                return None

            # Calculate dynamic slippage
            is_expiry = FnOUtils.is_expiry_day(ref_date, self.symbol)
            
            # Get VIX
            vix_val = None
            if hasattr(self, "vix_data") and self.vix_data is not None:
                if isinstance(self.vix_data, pd.DataFrame):
                    t_str = str(bar_time)[:19]
                    vix_match = self.vix_data[self.vix_data["datetime"].astype(str).str.slice(0, 19) == t_str]
                    if not vix_match.empty:
                        vix_val = float(vix_match.iloc[0]["close"])
                else:
                    vix_val = float(self.vix_data)

            slip = self.slippage_model.calculate(
                price=ask, qty=qty, candle_volume=volume,
                atr=atr * (ask / entry_price),
                bar_time=bar_time, is_entry=True,
                instrument="OPTIONS",
                spread=spread,
                is_expiry_day=is_expiry,
                iv=opt_data["iv"],
                vix=vix_val
            )
            effective_entry = ask + slip

            sl = sl_underlying
            tp = entry_price + self.atr_tp_mult * atr if signal == "BUY" else entry_price - self.atr_tp_mult * atr

            return {
                "signal":           signal,
                "entry_price":      entry_price,
                "effective_entry":  effective_entry,
                "sl":               sl,
                "tp":               tp,
                "qty":              qty,
                "atr":              atr,
                "entry_time":       str(bar_time)[:19] if bar_time else "",
                "entry_slip":       slip,
                "bar_entry_open":   entry_price,
                "entry_premium":    ask, # paid the ask price
                "option_type":      option_type,
                "strike":           strike,
                "expiry":           str(expiry_date),
                "iv":               opt_data["iv"],
                "delta":            opt_data["delta"],
                "gamma":            opt_data["gamma"],
                "theta":            opt_data["theta"],
                "vega":             opt_data["vega"],
                "rho":              opt_data["rho"],
                "required_margin":  margin_required,
                "bid":              bid,
                "ask":              ask,
                "volume":           opt_data["volume"],
                "open_interest":    opt_data["open_interest"],
                "data_source":      opt_data["source"]
            }

        else:
            slip = self.slippage_model.calculate(
                price=entry_price, qty=1, candle_volume=volume,
                atr=atr, bar_time=bar_time, is_entry=True,
                instrument=self.instrument,
            )

            if signal == "BUY":
                sl = entry_price - self.atr_sl_mult * atr
                tp = entry_price + self.atr_tp_mult * atr
                effective_entry = entry_price + slip
            else:
                sl = entry_price + self.atr_sl_mult * atr
                tp = entry_price - self.atr_tp_mult * atr
                effective_entry = entry_price - slip

            sizer = PositionSizer(
                capital=self.capital,
                risk_pct=self.risk_pct,
                lot_size=self.lot_size,
                instrument=self.instrument,
            )
            qty, risk_amt = sizer.size(entry_price, sl)
            if qty <= 0:
                return None

            margin_required = MarginCalculator.calculate_required_margin(
                price=entry_price,
                qty=qty,
                strike=entry_price,
                instrument=self.instrument,
                side="BUY",
                broker=self.broker,
                lot_size=self.lot_size
            )
            if margin_required > self.capital:
                return None

            return {
                "signal":           signal,
                "entry_price":      entry_price,
                "effective_entry":  effective_entry,
                "sl":               sl,
                "tp":               tp,
                "qty":              qty,
                "atr":              atr,
                "entry_time":       str(bar_time)[:19] if bar_time else "",
                "entry_slip":       slip,
                "bar_entry_open":   entry_price,
                "required_margin":  margin_required
            }

    def _execute_exit(
        self,
        trade: Dict,
        current_bar: pd.Series,
        exit_reason: str,
        bar_time: Any,
    ) -> Dict:
        """
        Exit execution with gap-handling:
        - If SL/TP is within candle's H-L range: exit at SL/TP price.
        - If price gaps through SL/TP: exit at the candle's open (gap-fill).
        """
        high  = float(current_bar["high"])
        low   = float(current_bar["low"])
        open_ = float(current_bar["open"])
        vol   = float(current_bar.get("volume", 0))
        atr   = trade["atr"]

        signal = trade["signal"]
        sl     = trade["sl"]
        tp     = trade["tp"]

        # Default exit at close
        exit_price = float(current_bar["close"])

        if "SL" in exit_reason:
            if signal == "BUY":
                exit_price = open_ if open_ < sl else sl
            else:
                exit_price = open_ if open_ > sl else sl
        elif "TP" in exit_reason:
            if signal == "BUY":
                exit_price = open_ if open_ > tp else tp
            else:
                exit_price = open_ if open_ < tp else tp
        elif "SQUAREOFF" in exit_reason or "FORCED" in exit_reason:
            exit_price = open_   # forced close at session open

        if self.instrument == "OPTIONS":
            option_type = trade["option_type"]
            strike = trade["strike"]
            expiry_str = trade["expiry"]
            expiry_date = datetime.strptime(expiry_str, "%Y-%m-%d").date()

            ref_date = bar_time.date() if hasattr(bar_time, "date") else bar_time
            dte_exit = max(0, (expiry_date - ref_date).days)

            # Query Option Data at exit
            opt_data = self._get_option_data(exit_price, strike, option_type, bar_time, dte_exit, iv_fallback=trade.get("iv", 15.0))
            bid = opt_data["bid"]
            ask = opt_data["ask"]
            spread = ask - bid

            # If held to expiry, no slippage at settlement
            if "EXPIRY" in str(exit_reason):
                slip_premium = 0.0
                effective_exit = bid # settlement value
            else:
                is_expiry = FnOUtils.is_expiry_day(ref_date, self.symbol)
                
                # Get VIX
                vix_val = None
                if hasattr(self, "vix_data") and self.vix_data is not None:
                    if isinstance(self.vix_data, pd.DataFrame):
                        t_str = str(bar_time)[:19]
                        vix_match = self.vix_data[self.vix_data["datetime"].astype(str).str.slice(0, 19) == t_str]
                        if not vix_match.empty:
                            vix_val = float(vix_match.iloc[0]["close"])
                    else:
                        vix_val = float(self.vix_data)

                slip_premium = self.slippage_model.calculate(
                    price=bid, qty=trade["qty"], candle_volume=vol,
                    atr=atr * (bid / exit_price) if exit_price > 0 else atr,
                    bar_time=bar_time, is_entry=False,
                    instrument="OPTIONS",
                    spread=spread,
                    is_expiry_day=is_expiry,
                    iv=opt_data["iv"],
                    vix=vix_val
                )
                effective_exit = bid - slip_premium
                
            qty = trade["qty"]
            gross_pnl = (effective_exit - trade["effective_entry"]) * qty
            slip = slip_premium
            
            exit_detail = {
                "exit_premium":     bid, # received bid price
                "exit_iv":          opt_data["iv"],
                "exit_delta":       opt_data["delta"],
                "exit_gamma":       opt_data["gamma"],
                "exit_theta":       opt_data["theta"],
                "exit_vega":        opt_data["vega"],
                "exit_rho":         opt_data["rho"],
            }
        else:
            slip = self.slippage_model.calculate(
                price=exit_price, qty=trade["qty"], candle_volume=vol,
                atr=atr, bar_time=bar_time, is_entry=False,
                instrument=self.instrument,
            )

            if signal == "BUY":
                effective_exit = exit_price - slip
            else:
                effective_exit = exit_price + slip

            qty = trade["qty"]
            if signal == "BUY":
                gross_pnl = (effective_exit - trade["effective_entry"]) * qty
            else:
                gross_pnl = (trade["effective_entry"] - effective_exit) * qty
            exit_detail = {}

        # Charges using actual entry and exit prices
        if self.instrument == "FUTURES":
            charge_detail = self.charge_calc.futures(
                trade["effective_entry"], effective_exit, qty)
        elif self.instrument == "OPTIONS":
            charge_detail = self.charge_calc.options_round_trip(
                entry_premium=trade["effective_entry"],
                exit_premium=effective_exit,
                qty=qty,
                is_expiry_itm=("EXPIRY" in str(exit_reason)),
            )
        elif getattr(self, "mode", "INTRADAY") == "POSITIONAL":
            charge_detail = self.charge_calc.equity_delivery(
                trade["effective_entry"], effective_exit, qty)
        else:
            charge_detail = self.charge_calc.equity_intraday(
                trade["effective_entry"], effective_exit, qty)

        charges   = charge_detail["total"]
        net_pnl   = gross_pnl - charges

        res = {
            "entry_time":      trade["entry_time"],
            "exit_time":       str(bar_time)[:19] if bar_time else "",
            "signal":          trade["signal"],
            "entry":           trade["entry_premium"] if self.instrument == "OPTIONS" else trade["entry_price"],
            "effective_entry": trade["effective_entry"],
            "exit":            effective_exit,
            "effective_exit":  effective_exit,
            "sl":              trade["sl"],
            "tp":              trade["tp"],
            "qty":             qty,
            "atr":             trade["atr"],
            "gross_pnl":       round(gross_pnl, 2),
            "charges":         round(charges, 2),
            "net_pnl":         round(net_pnl, 2),
            "exit_reason":     exit_reason,
            "entry_slip":      trade["entry_slip"],
            "exit_slip":       slip,
            "charge_detail":   charge_detail,
        }
        return res

    # ── STEP 3: Signal Generation (per-candle audit) ───────────────────────────
    def _generate_signal(
        self,
        df: pd.DataFrame,
        i: int,
        bar_time: Any,
    ) -> Tuple[str, Dict[str, bool], str]:
        """
        Signal generation using strictly historical data.
        AUDIT STEP 3: Every filter is explicitly logged.
        AUDIT STEP 4: Only df.iloc[:i+1] is used — no future leakage.

        Returns (signal, filters_dict, rejection_reason)
        """
        bar = df.iloc[i]
        price = float(bar["close"])

        # Safely extract indicators (NaN → default neutral values)
        def safe(col, default=0.0):
            val = bar.get(col, default)
            return default if pd.isna(val) else float(val)

        ema9    = safe("ema_9")
        ema20   = safe("ema_20")
        ema50   = safe("ema_50")
        atr     = safe("atr_14", price * 0.01)
        rsi     = safe("rsi_14", 50.0)
        macd_h  = safe("macd_hist")
        adx     = safe("adx_14")
        vwap    = safe("vwap", price)
        st_bull = bool(bar.get("supertrend", True))
        fvg_b   = bool(bar.get("fvg_bull", False))
        fvg_bear= bool(bar.get("fvg_bear", False))

        # ── BUY conditions ────────────────────────────────────────────────────
        buy_filters = {
            "ema9_above_ema20":  ema9 > ema20,
            "ema20_above_ema50": ema20 > ema50,
            "price_above_vwap":  vwap > 0 and price > vwap,
            "rsi_55_75":         55 <= rsi <= 75,
            "macd_hist_positive": macd_h > 0,
            "supertrend_bull":   st_bull,
            "adx_gt_20":         adx > 20,
            "bullish_fvg":       fvg_b,
        }

        # ── SELL conditions ───────────────────────────────────────────────────
        sell_filters = {
            "ema9_below_ema20":  ema9 < ema20,
            "ema20_below_ema50": ema20 < ema50,
            "price_below_vwap":  vwap > 0 and price < vwap,
            "rsi_25_45":         25 <= rsi <= 45,
            "macd_hist_negative": macd_h < 0,
            "supertrend_bear":   not st_bull,
            "adx_gt_20":         adx > 20,
            "bearish_fvg":       fvg_bear,
        }

        buy_score  = sum(buy_filters.values())
        sell_score = sum(sell_filters.values())

        MIN_FILTERS = 5  # Require 5/8 conditions

        if buy_score >= MIN_FILTERS and buy_score > sell_score:
            return "BUY", buy_filters, ""
        elif sell_score >= MIN_FILTERS and sell_score > buy_score:
            return "SELL", sell_filters, ""

        # Rejection reason
        if buy_score > sell_score:
            failing = [k for k, v in buy_filters.items() if not v]
            reason = f"BUY_WEAK({buy_score}/8): failing={failing[:3]}"
        elif sell_score > buy_score:
            failing = [k for k, v in sell_filters.items() if not v]
            reason = f"SELL_WEAK({sell_score}/8): failing={failing[:3]}"
        else:
            reason = "NEUTRAL: buy_score==sell_score"

        return "NONE", buy_filters if buy_score >= sell_score else sell_filters, reason

    # ── STEP 10: Intraday Rules ────────────────────────────────────────────────
    def _is_entry_allowed(self, bar_time: Optional[datetime], ds: Dict) -> Tuple[bool, str]:
        if bar_time is None:
            return True, ""

        t  = bar_time.time()
        wd = bar_time.weekday()

        if wd >= 5:
            return False, "Weekend"
        if bar_time.date() in NSE_HOLIDAYS:
            return False, "NSE Holiday"

        if self.mode == "INTRADAY":
            if t < MARKET_OPEN:
                return False, "Pre-market"
            # Allow entries only 9:20–14:30 (5-min buffer after open)
            if t < time(9, 20):
                return False, "Opening volatility buffer (9:15-9:20)"
            if t > ENTRY_CUTOFF:
                return False, f"After entry cutoff ({ENTRY_CUTOFF})"

        if ds.get("daily_loss", 0) < -self.initial_capital * self.max_daily_loss_pct:
            return False, f"Daily loss limit hit"
        if ds.get("trades_today", 0) >= self.max_trades_per_day:
            return False, f"Max trades/day ({self.max_trades_per_day}) reached"

        return True, ""

    def _is_auto_squareoff(self, bar_time: Optional[datetime]) -> bool:
        if bar_time is None:
            return False
        if self.mode != "INTRADAY":
            return False
        t = bar_time.time()
        return t >= SQUAREOFF

    # ── Trailing SL ───────────────────────────────────────────────────────────
    def _update_trailing_sl(self, trade: Dict, bar: pd.Series):
        high  = float(bar["high"])
        low   = float(bar["low"])
        entry = trade["effective_entry"]
        sl    = trade["sl"]
        tp    = trade["tp"]
        atr   = trade["atr"]
        signal = trade["signal"]

        if signal == "BUY":
            tp_dist = tp - entry
            best    = high
            profit  = best - entry
            if profit >= tp_dist * 0.5 and sl < entry:
                trade["sl"] = entry                          # break-even
            if profit >= tp_dist * 0.7:
                trail_sl = best - atr * 0.5
                if trail_sl > trade["sl"]:
                    trade["sl"] = round(trail_sl, 2)         # trail
        else:
            tp_dist = entry - tp
            best    = low
            profit  = entry - best
            if profit >= tp_dist * 0.5 and sl > entry:
                trade["sl"] = entry
            if profit >= tp_dist * 0.7:
                trail_sl = best + atr * 0.5
                if trail_sl < trade["sl"]:
                    trade["sl"] = round(trail_sl, 2)

    def _check_exit(
        self, trade: Dict, bar: pd.Series
    ) -> Tuple[bool, str]:
        high  = float(bar["high"])
        low   = float(bar["low"])
        sl    = trade["sl"]
        tp    = trade["tp"]
        signal = trade["signal"]

        if signal == "BUY":
            sl_hit = low  <= sl
            tp_hit = high >= tp
            if tp_hit and sl_hit:
                # Both: prefer TP if SL moved to profit, else SL
                return True, "TP" if trade["sl"] >= trade["effective_entry"] else "SL"
            if tp_hit: return True, "TP"
            if sl_hit: return True, "SL"
        else:
            sl_hit = high >= sl
            tp_hit = low  <= tp
            if tp_hit and sl_hit:
                return True, "TP" if trade["sl"] <= trade["effective_entry"] else "SL"
            if tp_hit: return True, "TP"
            if sl_hit: return True, "SL"

        return False, ""

    # ── MAIN RUN METHOD ────────────────────────────────────────────────────────
    def run(
        self,
        df_raw: pd.DataFrame,
        external_signals: Optional[pd.Series] = None,
    ) -> Dict[str, Any]:
        """
        Full backtest run.

        AUDIT STEP 4 Look-Ahead Bias:
        ─────────────────────────────
        Signal at candle[i] uses df.iloc[:i+1] only.
        Entry fill is at candle[i+1].open (next bar).
        Exit checks use candle[i+1].high/low (no peeking further).

        Parameters
        ----------
        df_raw            : OHLCV DataFrame (raw, unprocessed)
        external_signals  : Optional Series of "BUY"/"SELL"/None indexed same as df_raw.
                            If provided, uses external signals instead of built-in engine.
        """
        self._reset()

        # ── Step 1: Validate Data ─────────────────────────────────────────────
        validator = DataValidator(self.interval_minutes)
        df, data_issues = validator.validate(df_raw)
        if self.verbose:
            for issue in data_issues:
                print(f"  [DataValidator] {issue}")

        if len(df) < self.warmup_bars + 10:
            return {
                "status": "error",
                "error":  f"Insufficient data: {len(df)} bars < warmup ({self.warmup_bars})",
                "data_issues": data_issues,
            }

        # ── Step 2: Compute Indicators (once, on full series — look-ahead safe) ─
        # NOTE: Computing on full series is fine BECAUSE we only READ bar[i]
        # at time i (never bar[i+1..n]).
        df = Indicators.apply_all(df)

    def _process_order_queue(self, next_bar: pd.Series, atr: float, next_bar_time: Any, daily_state: Dict) -> Optional[Dict]:
        """
        Processes pending orders in the queue using next_bar data (execution at next bar).
        Handles market/limit orders, liquidity checks, partial fills, and capital blocks.
        """
        if not self.order_queue:
            return None
            
        order = self.order_queue[0] # peek
        
        # Determine Ask/Bid for option or underlying
        entry_price = float(next_bar["open"])
        if self.instrument == "OPTIONS":
            option_type = "CE" if order.signal == "BUY" else "PE"
            symbol_upper = self.symbol.upper()
            if "NIFTY" in symbol_upper or "NSEI" in symbol_upper:
                interval = 50
            else:
                interval = 20
            strike = int(round(entry_price / interval) * interval)
            ref_date = next_bar_time.date() if hasattr(next_bar_time, "date") else next_bar_time
            is_index = any(idx in symbol_upper for idx in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NSEI", "NSEBANK"])
            expiry_date = FnOUtils.next_weekly_expiry(ref_date) if (is_index and getattr(self, "expiry_type", "WEEKLY") == "WEEKLY") else FnOUtils.next_monthly_expiry(ref_date)
            dte = max(0, (expiry_date - ref_date).days)
            
            opt_data = self._get_option_data(entry_price, strike, option_type, next_bar_time, dte)
            exec_price = opt_data["ask"] if order.signal == "BUY" else opt_data["bid"]
        else:
            exec_price = entry_price
            
        # Limit Order execution check:
        if order.order_type == "LIMIT":
            if order.signal == "BUY" and exec_price > order.limit_price:
                # Ask is higher than limit: skip execution and keep in queue
                return None
            elif order.signal == "SELL" and exec_price < order.limit_price:
                # Bid is lower than limit: skip execution and keep in queue
                return None
                
        # Remove from queue as we are now processing it
        self.order_queue.pop(0)
        
        # Check daily limits and filters
        allowed, block_reason = self._is_entry_allowed(next_bar_time, daily_state)
        if not allowed:
            order.status = "REJECTED"
            order.rejection_reason = block_reason
            return None
            
        # Liquidity Check (NSE options lot size typically 50 or similar)
        # If next_bar volume < 5 lots, reject for lack of liquidity.
        bar_vol = float(next_bar.get("volume", 0))
        min_liq_vol = 5 * self.lot_size
        if self.instrument == "OPTIONS" and bar_vol > 0 and bar_vol < min_liq_vol:
            order.status = "REJECTED"
            order.rejection_reason = "INSUFFICIENT_LIQUIDITY"
            if self.verbose:
                print(f"  [REJECT] Insufficient Liquidity: Vol {bar_vol} < Min {min_liq_vol}")
            return None
            
        # Execute entry
        trade = self._execute_entry(order.signal, next_bar, atr, next_bar_time)
        if trade is None:
            order.status = "REJECTED"
            order.rejection_reason = "EXECUTION_FAILED"
            return None
            
        # Partial Fill check:
        # If order qty > 10% of candle volume, cap it at 10% (partial fill).
        qty = trade["qty"]
        if bar_vol > 0 and qty > 0.1 * bar_vol:
            old_qty = qty
            qty = max(self.lot_size, int((0.1 * bar_vol) / self.lot_size) * self.lot_size)
            trade["qty"] = qty
            order.status = "PARTIALLY_FILLED"
            if self.verbose:
                print(f"  [PARTIAL FILL] Capped qty from {old_qty} to {qty} due to thin candle volume {bar_vol}")
        else:
            order.status = "FILLED"
            
        order.filled_qty = qty
        order.filled_price = trade["effective_entry"]
        
        return trade

    def run(
        self,
        df_raw: pd.DataFrame,
        external_signals: Optional[pd.Series] = None,
    ) -> Dict[str, Any]:
        """
        Full backtest run.

        AUDIT STEP 4 Look-Ahead Bias:
        ─────────────────────────────
        Signal at candle[i] uses df.iloc[:i+1] only.
        Entry fill is at candle[i+1].open (next bar).
        Exit checks use candle[i+1].high/low (no peeking further).

        Parameters
        ----------
        df_raw            : OHLCV DataFrame (raw, unprocessed)
        external_signals  : Optional Series of "BUY"/"SELL"/None indexed same as df_raw.
                            If provided, uses external signals instead of built-in engine.
        """
        self._reset()

        # ── Step 1: Validate Data ─────────────────────────────────────────────
        validator = DataValidator(self.interval_minutes)
        df, data_issues = validator.validate(df_raw)
        if self.verbose:
            for issue in data_issues:
                print(f"  [DataValidator] {issue}")

        if len(df) < self.warmup_bars + 10:
            return {
                "status": "error",
                "error":  f"Insufficient data: {len(df)} bars < warmup ({self.warmup_bars})",
                "data_issues": data_issues,
            }

        # ── Step 2: Compute Indicators (once, on full series — look-ahead safe) ─
        # NOTE: Computing on full series is fine BECAUSE we only READ bar[i]
        # at time i (never bar[i+1..n]).
        df = Indicators.apply_all(df)

        # ── Main simulation loop ───────────────────────────────────────────────
        last_date   = None
        daily_state = {"daily_loss": 0.0, "trades_today": 0}
        bar_entry   = None   # bar index where entry signal fired (fill next bar)
        open_trade  = None

        for i in range(self.warmup_bars, len(df) - 1):
            bar      = self._get_bar(df, i)
            next_bar = self._get_bar(df, i + 1)
            if bar is None or next_bar is None:
                continue

            # Resolve timestamp
            bar_time = bar.get("datetime")
            if pd.isna(bar_time) if isinstance(bar_time, float) else False:
                bar_time = None
            next_bar_time = next_bar.get("datetime")

            # ── Reset daily counters ──────────────────────────────────────────
            current_date = bar_time.date() if bar_time else None
            if current_date != last_date:
                daily_state = {"daily_loss": 0.0, "trades_today": 0}
                last_date = current_date
                # Clear queue of stale intraday orders on a new day
                self.order_queue = []

            # ── A. Manage open trade ──────────────────────────────────────────
            if open_trade is not None:
                # Check auto sq-off (use CURRENT bar time, not next)
                if self._is_auto_squareoff(bar_time):
                    record = self._execute_exit(
                        open_trade, next_bar, "SQUAREOFF", next_bar_time)
                    record["bars_held"] = i - open_trade.get("_bar_idx", i)
                    self.trades.append(record)
                    daily_state["daily_loss"] += record["net_pnl"]
                    self.capital += record["net_pnl"]
                    self.equity_curve.append(round(self.capital, 2))
                    open_trade = None
                    if self.verbose:
                        print(f"  [SQOFF] {record['exit_time']} | PnL={record['net_pnl']:.2f}")
                    continue

                # ── BUG-01 FIX: Check exit FIRST, update trailing SL only if still open ──
                hit, reason = self._check_exit(open_trade, bar)
                if hit:
                    record = self._execute_exit(
                        open_trade, bar, reason, bar_time)
                    record["bars_held"] = i - open_trade.get("_bar_idx", i)
                    self.trades.append(record)
                    daily_state["daily_loss"] += record["net_pnl"]
                    self.capital += record["net_pnl"]
                    self.equity_curve.append(round(self.capital, 2))
                    if self.verbose:
                        print(f"  [{reason}] {record['exit_time']} | PnL={record['net_pnl']:.2f}")
                    open_trade = None
                else:
                    # Trade still open — safe to advance trailing stop for next candle
                    self._update_trailing_sl(open_trade, bar)
                continue   # No new entries while a position is open

            # ── B. Queue execution (next candle open fill) ───────────────────
            # Process any queued orders using next_bar (which has open price at i+1)
            atr = float(bar.get("atr_14", float(bar["close"]) * 0.01))
            if pd.isna(atr) or atr <= 0:
                atr = float(bar["close"]) * 0.01
                
            if open_trade is None and self.order_queue:
                trade = self._process_order_queue(next_bar, atr, next_bar_time, daily_state)
                if trade is not None:
                    trade["_bar_idx"] = i + 1
                    open_trade = trade
                    daily_state["trades_today"] += 1
                    if self.verbose:
                        print(
                            f"  [ENTRY via Queue] {trade['signal']} @ {trade['effective_entry']:.2f} "
                            f"SL={trade['sl']:.2f} TP={trade['tp']:.2f} "
                            f"Qty={trade['qty']} | {next_bar_time}"
                        )
                    continue

            # ── C. Signal generation ──────────────────────────────────────────
            if external_signals is not None:
                sig_val = external_signals.iloc[i] if i < len(external_signals) else None
                signal  = sig_val if sig_val in ("BUY", "SELL") else "NONE"
                filters = {}
                rejection = "" if signal != "NONE" else "External signal: NONE"
            else:
                signal, filters, rejection = self._generate_signal(df, i, bar_time)

            # Audit log
            self.audit_log.record(
                bar_idx=i, bar_time=bar_time, price=float(bar["close"]),
                atr=atr, rsi=float(bar.get("rsi_14", 50) or 50),
                ema9=float(bar.get("ema_9", 0) or 0), ema20=float(bar.get("ema_20", 0) or 0),
                vwap=float(bar.get("vwap", 0) or 0), supertrend=bool(bar.get("supertrend", True)),
                adx=float(bar.get("adx_14", 0) or 0), macd_hist=float(bar.get("macd_hist", 0) or 0),
                fvg=bool(bar.get("fvg_bull", False)) or bool(bar.get("fvg_bear", False)),
                signal_candidate=signal, filters=filters,
                final_signal=signal, rejection_reason=rejection,
            )

            if signal == "NONE":
                continue

            # ── D. Queue new order if allowed ─────────────────────────────────
            allowed, block_reason = self._is_entry_allowed(bar_time, daily_state)
            if not allowed:
                self.audit_log.entries[-1]["signal"] = "BLOCKED"
                self.audit_log.entries[-1]["rejection"] = block_reason
                continue

            order = Order(
                signal=signal,
                order_type="MARKET",
                qty=0,
                timestamp=next_bar_time
            )
            self.order_queue.append(order)

        # ── Force-close any remaining trade at last bar ───────────────────────
        if open_trade is not None:
            last_bar  = df.iloc[-1]
            bar_time_ = last_bar.get("datetime")
            record = self._execute_exit(open_trade, last_bar, "FORCED_CLOSE", bar_time_)
            record["bars_held"] = len(df) - 1 - open_trade.get("_bar_idx", len(df) - 1)
            self.trades.append(record)
            self.capital += record["net_pnl"]
            self.equity_curve.append(round(self.capital, 2))

        # ── Compute metrics ───────────────────────────────────────────────────
        metrics = PerformanceMetrics.compute(
            self.trades, self.equity_curve, self.initial_capital
        )
        monthly = PerformanceMetrics.monthly_returns(self.trades, self.initial_capital)

        return {
            "status":       "success",
            "data_issues":  data_issues,
            "metrics":      metrics,
            "equity_curve": self.equity_curve,
            "trades":       self.trades,
            "monthly_pnl":  monthly.to_dict() if not monthly.empty else {},
            "audit_log_size": len(self.audit_log.entries),
            "config": {
                "instrument":      self.instrument,
                "mode":            self.mode,
                "risk_pct":        self.risk_pct,
                "atr_sl_mult":     self.atr_sl_mult,
                "atr_tp_mult":     self.atr_tp_mult,
                "lot_size":        self.lot_size,
                "max_daily_loss":  self.max_daily_loss_pct,
                "initial_capital": self.initial_capital,
            },
        }


# ══════════════════════════════════════════════════════════════════════════════
# WALK-FORWARD OPTIMIZER
# ══════════════════════════════════════════════════════════════════════════════
class WalkForwardOptimizer:
    """
    AUDIT STEP 15 — Walk-Forward Testing.
    Prevents look-ahead in parameter selection.

    Strategy:
    - Split data into N folds
    - For each fold: train on in-sample window, validate on OOS window
    - Never use OOS data during optimisation
    - Computes Walk Forward Efficiency (WFE) and Stability Scores.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        n_folds: int = 5,
        train_ratio: float = 0.7,
        initial_capital: float = 100_000.0,
    ):
        self.df              = df
        self.n_folds         = n_folds
        self.train_ratio     = train_ratio
        self.initial_capital = initial_capital
        self.results: List[Dict] = []

    def optimize(
        self,
        param_grid: Dict[str, List],
        metric: str = "sharpe_ratio",
    ) -> Dict[str, Any]:
        """
        Grid-search + walk-forward.
        """
        n = len(self.df)
        fold_size    = n // self.n_folds
        keys         = list(param_grid.keys())
        combinations = list(itertools.product(*[param_grid[k] for k in keys]))
        fold_results = []

        print(f"\n[WalkForward] {self.n_folds} folds, {len(combinations)} param combos each")
        print(f"[WalkForward] Metric: {metric}")

        for fold in range(self.n_folds):
            fold_start = fold * fold_size
            fold_end   = fold_start + fold_size
            train_end  = fold_start + int(fold_size * self.train_ratio)

            train_df = self.df.iloc[fold_start: train_end].reset_index(drop=True)
            test_df  = self.df.iloc[train_end:  fold_end].reset_index(drop=True)

            if len(train_df) < 100 or len(test_df) < 20:
                continue

            # Find best params on train
            best_metric = -np.inf
            best_params = combinations[0]

            for combo in combinations:
                params = dict(zip(keys, combo))
                try:
                    engine = QuantumBacktestEngine(
                        initial_capital=self.initial_capital,
                        **params,
                        mode="INTRADAY",
                        verbose=False,
                    )
                    result = engine.run(train_df)
                    if result["status"] != "success":
                        continue
                    m = result["metrics"].get(metric, -999)
                    if isinstance(m, (int, float)) and m > best_metric:
                        best_metric = m
                        best_params = combo
                except Exception:
                    pass

            # Validate best params on OOS test set
            oos_params = dict(zip(keys, best_params))
            try:
                oos_engine = QuantumBacktestEngine(
                    initial_capital=self.initial_capital,
                    **oos_params,
                    mode="INTRADAY",
                    verbose=False,
                )
                oos_result = oos_engine.run(test_df)
                oos_m = oos_result["metrics"] if oos_result["status"] == "success" else {}
            except Exception as e:
                oos_m = {"error": str(e)}

            # WFE Calculation: OOS metric / IS metric
            oos_metric_val = oos_m.get(metric, 0)
            wfe = oos_metric_val / best_metric if best_metric != 0 else 0.0

            fold_results.append({
                "fold":          fold,
                "train_bars":    len(train_df),
                "oos_bars":      len(test_df),
                "best_params":   oos_params,
                "train_metric":  best_metric,
                "oos_metric":    oos_metric_val,
                "oos_sharpe":    oos_m.get("sharpe_ratio", 0),
                "oos_win_rate":  oos_m.get("win_rate", 0),
                "oos_net_pnl":   oos_m.get("net_profit", 0),
                "oos_max_dd":    oos_m.get("max_drawdown_pct", 0),
                "oos_trades":    oos_m.get("total_trades", 0),
                "wfe":           wfe,
            })
            print(f"  Fold {fold+1}: train_{metric}={best_metric:.3f} "
                  f"| OOS_sharpe={oos_m.get('sharpe_ratio', 0):.3f} "
                  f"| WFE={wfe:.2f}")

        # Aggregate OOS performance
        fold_df = pd.DataFrame(fold_results)
        if fold_df.empty:
            return {"status": "error", "error": "No valid folds"}

        # Most common best params across folds
        param_df = pd.DataFrame([r["best_params"] for r in fold_results])
        most_common_params = {}
        for col in param_df.columns:
            most_common_params[col] = param_df[col].mode().iloc[0]

        # Stability Score: max(0, 1 - std(OOS PnL) / mean(OOS PnL)) if mean > 0
        oos_pnls = fold_df["oos_net_pnl"]
        mean_pnl = oos_pnls.mean()
        std_pnl = oos_pnls.std()
        stability_score = max(0.0, 1.0 - (std_pnl / mean_pnl)) if mean_pnl > 0 else 0.0

        self.results = fold_results
        return {
            "status":           "success",
            "best_params":      most_common_params,
            "fold_results":     fold_results,
            "oos_avg_sharpe":   fold_df["oos_sharpe"].mean(),
            "oos_avg_win_rate":  fold_df["oos_win_rate"].mean(),
            "oos_avg_net_pnl":  fold_df["oos_net_pnl"].mean(),
            "oos_consistency":  fold_df["oos_sharpe"].std(),
            "oos_avg_wfe":      fold_df["wfe"].mean(),
            "stability_score":  stability_score,
            "profitable_folds": (fold_df["oos_net_pnl"] > 0).sum(),
            "total_folds":      len(fold_df),
        }


# ══════════════════════════════════════════════════════════════════════════════
# MONTE CARLO SIMULATION
# ══════════════════════════════════════════════════════════════════════════════
class MonteCarloSimulator:
    """
    AUDIT STEP 16 — Monte Carlo Analysis.
    Supports random trades, spreads, slippage, execution delays, and volatility.
    """

    def __init__(self, trades: List[Dict], initial_capital: float, n_simulations: int = 5000):
        self.trades          = trades
        self.initial_capital = initial_capital
        self.n_sims          = n_simulations

    def run(self, seed: int = 42) -> Dict[str, Any]:
        if not self.trades:
            return {"error": "No trades to simulate"}

        rng      = np.random.default_rng(seed)
        net_pnls = np.array([t["net_pnl"] for t in self.trades])
        n        = len(net_pnls)

        final_balances = []
        max_drawdowns  = []
        sharpes        = []

        for _ in range(self.n_sims):
            # 1. Resample trades (random sequence)
            seq = rng.choice(net_pnls, size=n, replace=True)
            
            # 2. Random slippage variation (±50%)
            slippage_mult = rng.uniform(0.5, 1.5, size=n)
            
            # 3. Random spread widening (reducing PnL by an additional spread cost)
            spread_mult = rng.uniform(1.0, 2.0, size=n)
            
            # 4. Random execution delay / volatility shock (extra slippage/drag)
            delay_drag = rng.exponential(scale=0.05, size=n)
            
            # Adjust resampled net pnls dynamically
            adjusted_pnls = seq * slippage_mult - (spread_mult - 1.0) * 2.0 - delay_drag * 5.0

            eq = self.initial_capital + np.cumsum(adjusted_pnls)
            eq = np.insert(eq, 0, self.initial_capital)

            final_balances.append(eq[-1])
            rolling_max = np.maximum.accumulate(eq)
            dd = (eq - rolling_max) / rolling_max * 100
            max_drawdowns.append(abs(dd.min()))

            ret = pd.Series(eq).pct_change().dropna()
            sharpes.append(
                (ret.mean() / ret.std() * np.sqrt(252)) if ret.std() > 0 else 0
            )

        fb = np.array(final_balances)
        dd = np.array(max_drawdowns)
        sh = np.array(sharpes)

        return {
            "n_simulations":     self.n_sims,
            "median_final":      round(np.median(fb), 2),
            "mean_final":        round(np.mean(fb), 2),
            "p5_final":          round(np.percentile(fb, 5), 2),
            "p25_final":         round(np.percentile(fb, 25), 2),
            "p75_final":         round(np.percentile(fb, 75), 2),
            "p95_final":         round(np.percentile(fb, 95), 2),
            "prob_profit":       round((fb > self.initial_capital).mean() * 100, 1),
            "prob_loss_gt_20pct": round((fb < self.initial_capital * 0.8).mean() * 100, 1),
            "median_max_dd":     round(np.median(dd), 2),
            "p95_max_dd":        round(np.percentile(dd, 95), 2),
            "median_sharpe":     round(np.median(sh), 3),
            "p5_sharpe":         round(np.percentile(sh, 5), 3),
        }


# ══════════════════════════════════════════════════════════════════════════════
# STRESS TESTER
# ══════════════════════════════════════════════════════════════════════════════
class StressTester:
    """
    AUDIT STEP 17 — Stress Testing on crisis/event scenarios.
    """

    SCENARIOS = {
        "COVID_CRASH":      {"date_range": ("2020-02-14", "2020-03-24"), "label": "COVID Crash"},
        "BUDGET_DAY":       {"volatility_mult": 3.0,  "label": "Budget Day volatility"},
        "HIGH_VIX":         {"vix_threshold": 25.0,   "label": "High VIX (>25)"},
        "GAP_UP":           {"gap_pct": 1.5,          "label": "Gap-Up >1.5%"},
        "GAP_DOWN":         {"gap_pct": -1.5,         "label": "Gap-Down <-1.5%"},
        "LOW_LIQUIDITY":    {"volume_mult": 0.2,      "label": "Low Liquidity (20% volume)"},
        "EXPIRY_DAY":       {"is_expiry": True,       "label": "Weekly Expiry Day"},
        "MONTHLY_EXPIRY":   {"is_monthly": True,      "label": "Monthly Expiry Day"},
        "CIRCUIT_BREAKER":  {"circuit": True,         "label": "Market Circuit Breaker"},
        "FLASH_CRASH":      {"drop_pct": -5.0,        "label": "Flash Crash (-5% in 5min)"},
    }

    def __init__(self, engine: QuantumBacktestEngine):
        self.engine = engine

    def run_all(self, df: pd.DataFrame) -> Dict[str, Any]:
        results = {}
        base    = self.engine.run(df)
        results["BASE"] = base.get("metrics", {})

        # Gap stress
        for scenario, gap_pct in [("GAP_UP", 1.5), ("GAP_DOWN", -1.5)]:
            df_stress = df.copy()
            df_stress["open"] = df_stress["open"] * (1 + gap_pct / 100)
            df_stress["high"] = df_stress[["high", "open"]].max(axis=1)
            df_stress["low"]  = df_stress[["low", "open"]].min(axis=1)
            eng = deepcopy(self.engine)
            eng._reset()
            r = eng.run(df_stress)
            results[scenario] = r.get("metrics", {})

        # Low liquidity
        df_low_vol = df.copy()
        df_low_vol["volume"] = df_low_vol["volume"] * 0.2
        eng = deepcopy(self.engine)
        eng._reset()
        r = eng.run(df_low_vol)
        results["LOW_LIQUIDITY"] = r.get("metrics", {})

        # High volatility (widen H-L by 3x)
        df_hvol = df.copy()
        mid = (df_hvol["high"] + df_hvol["low"]) / 2
        half_range = (df_hvol["high"] - df_hvol["low"]) / 2
        df_hvol["high"] = mid + half_range * 3
        df_hvol["low"]  = (mid - half_range * 3).clip(lower=0.01)
        eng = deepcopy(self.engine)
        eng._reset()
        r = eng.run(df_hvol)
        results["HIGH_VOLATILITY"] = r.get("metrics", {})

        return results


# ══════════════════════════════════════════════════════════════════════════════
# REPORT GENERATOR
# ══════════════════════════════════════════════════════════════════════════════
class ReportGenerator:
    """
    AUDIT STEP 13 + 19 — Visual Report + Output Files.
    Generates CSV trade log, HTML summary, and equity chart (matplotlib).
    """

    def __init__(self, output_dir: str = "backend/backtesting/reports"):
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def save_trade_log(self, trades: List[Dict], symbol: str = "") -> str:
        path = os.path.join(self.output_dir, f"trade_log_{symbol}_{self.timestamp}.csv")
        if not trades:
            return path
        df = pd.DataFrame(trades)
        # Flatten charge_detail dict into columns
        if "charge_detail" in df.columns:
            charge_df = pd.DataFrame(df["charge_detail"].tolist())
            charge_df.columns = [f"charge_{c}" for c in charge_df.columns]
            df = pd.concat([df.drop(columns=["charge_detail"]), charge_df], axis=1)
        df.to_csv(path, index=False)
        return path

    def save_audit_log(self, audit_log: SignalAuditLog, symbol: str = "") -> str:
        path = os.path.join(self.output_dir, f"signal_audit_{symbol}_{self.timestamp}.csv")
        audit_log.export(path)
        return path

    def save_equity_curve(self, equity_curve: List[float], trades: List[Dict],
                          symbol: str = "") -> str:
        path = os.path.join(self.output_dir, f"equity_curve_{symbol}_{self.timestamp}.csv")
        df   = pd.DataFrame({"idx": range(len(equity_curve)), "balance": equity_curve})
        df.to_csv(path, index=False)
        return path

    def save_metrics_json(self, metrics: Dict, config: Dict, symbol: str = "") -> str:
        path = os.path.join(self.output_dir, f"metrics_{symbol}_{self.timestamp}.json")
        with open(path, "w") as f:
            json.dump({**metrics, "config": config}, f, indent=2, default=str)
        return path

    def save_html_report(
        self,
        metrics: Dict,
        trades: List[Dict],
        equity_curve: List[float],
        monthly_pnl: Dict,
        mc_results: Optional[Dict],
        stress_results: Optional[Dict],
        symbol: str,
        data_issues: List[str],
    ) -> str:
        """Generate a self-contained HTML report."""
        path = os.path.join(self.output_dir, f"report_{symbol}_{self.timestamp}.html")

        def fmt(v, decimals=2):
            if isinstance(v, float):
                return f"{v:,.{decimals}f}"
            return str(v)

        # Metrics table rows
        key_metrics = [
            ("Total Trades",      metrics.get("total_trades", 0),         ""),
            ("Win Rate",          f"{metrics.get('win_rate', 0):.1f}%",    ""),
            ("Profit Factor",     fmt(metrics.get("profit_factor", 0)),    ""),
            ("Net Profit",        f"₹{fmt(metrics.get('net_profit', 0))}", ""),
            ("Total Return",      f"{fmt(metrics.get('total_return_pct', 0))}%", ""),
            ("Max Drawdown",      f"{fmt(metrics.get('max_drawdown_pct', 0))}%", ""),
            ("Sharpe Ratio",      fmt(metrics.get("sharpe_ratio", 0)),     ""),
            ("Sortino Ratio",     fmt(metrics.get("sortino_ratio", 0)),    ""),
            ("Calmar Ratio",      fmt(metrics.get("calmar_ratio", 0)),     ""),
            ("Expectancy",        f"₹{fmt(metrics.get('expectancy', 0))}", ""),
            ("Avg Win",           f"₹{fmt(metrics.get('avg_win', 0))}",    ""),
            ("Avg Loss",          f"₹{fmt(metrics.get('avg_loss', 0))}",   ""),
            ("Largest Win",       f"₹{fmt(metrics.get('largest_win', 0))}",""),
            ("Largest Loss",      f"₹{fmt(metrics.get('largest_loss', 0))}",""),
            ("Max Win Streak",    metrics.get("max_win_streak", 0),        ""),
            ("Max Loss Streak",   metrics.get("max_loss_streak", 0),       ""),
            ("Total Charges",     f"₹{fmt(metrics.get('total_charges', 0))}",""),
            ("Final Capital",     f"₹{fmt(metrics.get('final_capital', 0))}",""),
        ]

        metric_rows = "\n".join(
            f'<tr><td>{k}</td><td><b>{v}</b></td></tr>' for k, v, *_ in key_metrics
        )

        # Trade log table (last 50)
        trade_rows = ""
        for t in trades[-50:]:
            pnl_color = "#27ae60" if t.get("net_pnl", 0) > 0 else "#e74c3c"
            trade_rows += (
                f"<tr>"
                f"<td>{t.get('entry_time','')}</td>"
                f"<td>{t.get('signal','')}</td>"
                f"<td>₹{t.get('entry', 0):.2f}</td>"
                f"<td>₹{t.get('exit', 0):.2f}</td>"
                f"<td>₹{t.get('sl', 0):.2f}</td>"
                f"<td>₹{t.get('tp', 0):.2f}</td>"
                f"<td>{t.get('qty', 0)}</td>"
                f"<td style='color:{pnl_color}'>₹{t.get('net_pnl', 0):.2f}</td>"
                f"<td>{t.get('exit_reason','')}</td>"
                f"</tr>"
            )

        # Equity curve JS data
        eq_data = json.dumps(equity_curve[-500:])

        # Data issues
        issues_html = "".join(
            f'<li style="color:{"red" if "CRITICAL" in i else "orange" if "WARNING" in i else "green"}">{i}</li>'
            for i in data_issues
        )

        # Monte Carlo section
        mc_html = ""
        if mc_results and "error" not in mc_results:
            mc_html = f"""
            <h2>Monte Carlo Analysis ({mc_results['n_simulations']} simulations)</h2>
            <table>
            <tr><td>Median Final Balance</td><td><b>₹{mc_results['median_final']:,.2f}</b></td></tr>
            <tr><td>P5 (5th percentile)</td><td>₹{mc_results['p5_final']:,.2f}</td></tr>
            <tr><td>P95 (95th percentile)</td><td>₹{mc_results['p95_final']:,.2f}</td></tr>
            <tr><td>Probability of Profit</td><td><b>{mc_results['prob_profit']}%</b></td></tr>
            <tr><td>Prob Loss &gt;20%</td><td>{mc_results['prob_loss_gt_20pct']}%</td></tr>
            <tr><td>Median Max Drawdown</td><td>{mc_results['median_max_dd']:.2f}%</td></tr>
            <tr><td>P95 Max Drawdown</td><td>{mc_results['p95_max_dd']:.2f}%</td></tr>
            </table>
            """

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>QuantumIndex Backtest — {symbol}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  body {{font-family:'Segoe UI',sans-serif;background:#0f1117;color:#e0e0e0;margin:0;padding:20px}}
  h1{{color:#00d4ff;border-bottom:2px solid #00d4ff;padding-bottom:8px}}
  h2{{color:#7c83fd;margin-top:30px}}
  table{{border-collapse:collapse;width:100%;margin:10px 0}}
  th{{background:#1e2130;color:#7c83fd;padding:8px 12px;text-align:left;border:1px solid #2a2d3e}}
  td{{padding:7px 12px;border:1px solid #2a2d3e;font-size:13px}}
  tr:nth-child(even){{background:#161a28}}
  canvas{{background:#1e2130;border-radius:8px;margin:10px 0}}
  .badge{{display:inline-block;padding:4px 10px;border-radius:12px;font-size:12px;font-weight:bold}}
  .green{{background:#1a3a2a;color:#27ae60}}
  .red{{background:#3a1a1a;color:#e74c3c}}
  ul{{list-style:none;padding:0}}
  li{{padding:3px 0}}
</style>
</head>
<body>
<h1>📊 QuantumIndex Backtest Report — {symbol}</h1>
<p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')} | Engine v3.0</p>

<h2>Data Validation</h2>
<ul>{issues_html}</ul>

<h2>Performance Metrics</h2>
<table>
<tr><th>Metric</th><th>Value</th></tr>
{metric_rows}
</table>

<h2>Equity Curve</h2>
<canvas id="eq" height="100"></canvas>
<script>
new Chart(document.getElementById('eq'), {{
  type:'line',
  data:{{
    labels:{json.dumps(list(range(len(json.loads(eq_data)))))},
    datasets:[{{
      label:'Portfolio Balance',
      data:{eq_data},
      borderColor:'#00d4ff',
      backgroundColor:'rgba(0,212,255,0.07)',
      borderWidth:1.5,
      pointRadius:0,
      fill:true,
    }}]
  }},
  options:{{
    responsive:true,
    plugins:{{legend:{{labels:{{color:'#e0e0e0'}}}}}},
    scales:{{
      x:{{display:false}},
      y:{{ticks:{{color:'#e0e0e0'}},grid:{{color:'#2a2d3e'}}}}
    }}
  }}
}});
</script>

{mc_html}

<h2>Trade Log (Last 50)</h2>
<table>
<tr><th>Entry Time</th><th>Signal</th><th>Entry</th><th>Exit</th>
<th>SL</th><th>TP</th><th>Qty</th><th>Net PnL</th><th>Reason</th></tr>
{trade_rows}
</table>

</body></html>"""

        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        return path


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC RUNNER — called from FastAPI endpoint
# ══════════════════════════════════════════════════════════════════════════════
def run_quantum_backtest(
    symbol:          str   = "NIFTY",
    days:            int   = 90,
    initial_capital: float = 100_000.0,
    instrument:      str   = "EQUITY",
    mode:            str   = "INTRADAY",
    risk_pct:        float = 0.01,
    atr_sl_mult:     float = 2.0,
    atr_tp_mult:     float = 4.0,
    lot_size:        int   = 1,
    slippage_bps:    float = 2.0,
    min_score:       int   = 60,
    run_monte_carlo: bool  = True,
    run_walk_fwd:    bool  = False,
    verbose:         bool  = False,
    df_override:     Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Single-entry-point for running the complete institutional backtest.
    Fetches data via yfinance if df_override is None.
    """
    # ── Fetch Data ─────────────────────────────────────────────────────────────
    if df_override is not None:
        df_raw = df_override
    else:
        try:
            import yfinance as yf
            ticker = f"{symbol.upper().replace('-EQ','').replace('.NS','')}.NS"
            df_raw = yf.download(ticker, period=f"{days}d", interval="5m",
                                 progress=False, auto_adjust=True)
            if df_raw is None or df_raw.empty:
                return {"status": "error", "error": f"No data for {symbol}"}
            df_raw.columns = [str(c[0]).lower() if isinstance(c, tuple) else str(c).lower()
                              for c in df_raw.columns]
            df_raw = df_raw.reset_index()
            if "datetime" in df_raw.columns:
                pass
            elif "date" in df_raw.columns:
                df_raw = df_raw.rename(columns={"date": "datetime"})
            elif "index" in df_raw.columns:
                df_raw = df_raw.rename(columns={"index": "datetime"})
        except Exception as e:
            return {"status": "error", "error": f"Data fetch failed: {e}"}

    # ── Create Engine ──────────────────────────────────────────────────────────
    engine = QuantumBacktestEngine(
        initial_capital    = initial_capital,
        risk_pct           = risk_pct,
        max_daily_loss_pct = 0.03,
        max_positions      = 1,
        max_trades_per_day = 5,
        atr_sl_mult        = atr_sl_mult,
        atr_tp_mult        = atr_tp_mult,
        instrument         = instrument,
        lot_size           = lot_size,
        slippage_bps       = slippage_bps,
        interval_minutes   = 5,
        mode               = mode,
        verbose            = verbose,
        symbol             = symbol,
    )

    # ── Run Backtest ───────────────────────────────────────────────────────────
    result = engine.run(df_raw)
    if result["status"] != "success":
        return result

    metrics      = result["metrics"]
    trades       = result["trades"]
    equity_curve = result["equity_curve"]
    data_issues  = result["data_issues"]

    # ── Monte Carlo ────────────────────────────────────────────────────────────
    mc_results = None
    if run_monte_carlo and trades:
        mc = MonteCarloSimulator(trades, initial_capital, n_simulations=1000)
        mc_results = mc.run()

    # ── Walk-Forward ───────────────────────────────────────────────────────────
    wf_results = None
    if run_walk_fwd and len(df_raw) > 500:
        validator = DataValidator(5)
        df_clean, _ = validator.validate(df_raw)
        df_clean = Indicators.apply_all(df_clean)
        wfo = WalkForwardOptimizer(df_clean, n_folds=5, initial_capital=initial_capital)
        wf_results = wfo.optimize(
            param_grid={
                "atr_sl_mult": [1.5, 2.0, 2.5],
                "atr_tp_mult": [3.0, 4.0, 5.0],
                "risk_pct":    [0.01, 0.015, 0.02],
            }
        )

    # ── Reports ────────────────────────────────────────────────────────────────
    rg = ReportGenerator()
    trade_log_path = rg.save_trade_log(trades, symbol)
    audit_log_path = rg.save_audit_log(engine.audit_log, symbol)
    html_path      = rg.save_html_report(
        metrics       = metrics,
        trades        = trades,
        equity_curve  = equity_curve,
        monthly_pnl   = result.get("monthly_pnl", {}),
        mc_results    = mc_results,
        stress_results= None,
        symbol        = symbol,
        data_issues   = data_issues,
    )
    metrics_path = rg.save_metrics_json(metrics, result["config"], symbol)

    # ── Final Return ───────────────────────────────────────────────────────────
    return {
        "status":       "success",
        "symbol":       symbol,
        "days":         days,
        "metrics":      metrics,
        "equity_curve": equity_curve[:500],   # cap for API payload
        "trades":       trades[-100:],
        "data_issues":  data_issues,
        "monte_carlo":  mc_results,
        "walk_forward": wf_results,
        "reports": {
            "trade_log":   trade_log_path,
            "audit_log":   audit_log_path,
            "html_report": html_path,
            "metrics_json":metrics_path,
        },
        "config":       result["config"],
    }


# ══════════════════════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    symbol = sys.argv[1] if len(sys.argv) > 1 else "RELIANCE"
    days   = int(sys.argv[2]) if len(sys.argv) > 2 else 60

    print(f"\n{'='*70}")
    print(f"  QuantumIndex Institutional Backtest — {symbol} ({days}d)")
    print(f"{'='*70}\n")

    result = run_quantum_backtest(
        symbol          = symbol,
        days            = days,
        initial_capital = 100_000.0,
        instrument      = "EQUITY",
        mode            = "INTRADAY",
        risk_pct        = 0.01,
        atr_sl_mult     = 2.0,
        atr_tp_mult     = 4.0,
        slippage_bps    = 2.0,
        run_monte_carlo = True,
        run_walk_fwd    = False,
        verbose         = True,
    )

    if result["status"] == "error":
        print(f"\n[ERROR] {result['error']}")
        sys.exit(1)

    m = result["metrics"]
    print(f"\n{'='*70}")
    print("  PERFORMANCE SUMMARY")
    print(f"{'='*70}")
    print(f"  Trades:         {m['total_trades']:>6}  |  Win Rate:    {m['win_rate']:.1f}%")
    print(f"  Net Profit:  ₹{m['net_profit']:>10,.2f}  |  Return:      {m['total_return_pct']:.2f}%")
    print(f"  Profit Factor:  {m['profit_factor']:>6.3f}  |  Expectancy: ₹{m['expectancy']:.2f}")
    print(f"  Sharpe:         {m['sharpe_ratio']:>6.3f}  |  Sortino:     {m['sortino_ratio']:.3f}")
    print(f"  Calmar:         {m['calmar_ratio']:>6.3f}  |  Max DD:      {m['max_drawdown_pct']:.2f}%")
    print(f"  Avg Win:     ₹{m['avg_win']:>10,.2f}  |  Avg Loss:   ₹{m['avg_loss']:.2f}")
    print(f"  Largest Win: ₹{m['largest_win']:>10,.2f}  |  Largest Loss:₹{m['largest_loss']:.2f}")
    print(f"  Win Streak:     {m['max_win_streak']:>6}  |  Loss Streak: {m['max_loss_streak']}")
    print(f"  Total Charges: ₹{m['total_charges']:>9,.2f}  |  Final Cap:  ₹{m['final_capital']:,.2f}")

    if result.get("monte_carlo"):
        mc = result["monte_carlo"]
        print(f"\n{'='*70}")
        print("  MONTE CARLO (1000 simulations)")
        print(f"{'='*70}")
        print(f"  Median Final:    ₹{mc['median_final']:>10,.2f}")
        print(f"  P5 / P95:        ₹{mc['p5_final']:>10,.2f}  /  ₹{mc['p95_final']:,.2f}")
        print(f"  Prob of Profit:  {mc['prob_profit']:>6.1f}%")
        print(f"  Prob Loss >20%:  {mc['prob_loss_gt_20pct']:>6.1f}%")
        print(f"  Median Max DD:   {mc['median_max_dd']:>6.2f}%  |  P95 Max DD: {mc['p95_max_dd']:.2f}%")

    print(f"\n  Data Issues:")
    for issue in result.get("data_issues", []):
        print(f"    {issue}")

    print(f"\n  Reports saved:")
    for k, v in result.get("reports", {}).items():
        print(f"    {k}: {v}")

    print(f"\n{'='*70}\n")
