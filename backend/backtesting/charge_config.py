"""
NSE/BSE Charge Configuration -- Centralized Rate Sheet
=======================================================
Version : 2.0
Effective: July 2026
Sources  : NSE circulars, SEBI guidelines, AngelOne rate card

All rates are expressed as decimal fractions (not percentages).
Override any rate by instantiating ChargeConfig with keyword args
and passing it to ChargeCalculator:

    cfg  = ChargeConfig(brokerage_cap=25.0, exchange_options_pct=0.0003)
    calc = ChargeCalculator(config=cfg)
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChargeConfig:
    """
    Centralized, fully configurable NSE/BSE charge rate sheet.
    All fields are decimal fractions unless the name ends in _cap (Rs).
    """

    # Brokerage ----------------------------------------------------------------
    brokerage_pct: float          = 0.0003
    brokerage_cap: float          = 20.0       # Rs 20 cap per executed order

    # STT -- Equity ------------------------------------------------------------
    stt_eq_intraday_pct: float    = 0.00025    # 0.025% on SELL side only (MIS)
    stt_eq_delivery_pct: float    = 0.001      # 0.100% on BOTH sides (CNC)

    # STT -- Futures -----------------------------------------------------------
    stt_fut_pct: float            = 0.0001     # 0.010% on SELL notional

    # STT -- Options -----------------------------------------------------------
    # Charged on the SELL side: both option writers and buyers closing long
    stt_opt_pct: float            = 0.00125    # 0.125% on SELL premium
    # Extra STT at expiry for ITM options (on intrinsic/settlement value)
    stt_opt_expiry_itm_pct: float = 0.00125    # 0.125% on settlement value

    # Exchange charges (NSE) ---------------------------------------------------
    exchange_equity_pct: float    = 0.0000345  # 0.00345% on equity turnover
    exchange_futures_pct: float   = 0.0000210  # 0.00210% on futures turnover
    # CRITICAL BUG-02 FIX: options uses PREMIUM value, not notional turnover.
    # NSE rate: 0.05% of option premium (was incorrectly 0.00345% equity rate).
    exchange_options_pct: float   = 0.0005     # 0.050% on PREMIUM value

    # SEBI charges -------------------------------------------------------------
    sebi_pct: float               = 0.000001   # Rs 1 per Rs 10L turnover

    # GST ----------------------------------------------------------------------
    gst_pct: float                = 0.18       # 18% on (brokerage + exchange + SEBI)

    # Stamp duty (BUY side only -- ZERO on sell side) --------------------------
    stamp_equity_buy_pct: float   = 0.00003    # 0.003% on buy value (intraday)
    stamp_equity_del_pct: float   = 0.00003    # 0.003% on buy value (delivery)
    stamp_futures_buy_pct: float  = 0.00002    # 0.002% on buy notional
    stamp_options_buy_pct: float  = 0.00003    # 0.003% on buy premium
    stamp_sell_pct: float         = 0.0        # No stamp duty on sell side


# Module-level default singleton -- import and use directly when no override needed
DEFAULT_CHARGE_CONFIG: ChargeConfig = ChargeConfig()
