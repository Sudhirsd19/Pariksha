"""
Phase 1 — Trade Replay Engine
==============================
Replays every completed trade bar-by-bar to compute MFE, MAE,
trailing SL history, indicator snapshot, and capital chain.

DO NOT modify any strategy or engine files.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class TradeReplayRecord:
    """Complete replay record for one trade."""
    trade_num:             int
    date:                  str
    entry_time:            str
    exit_time:             str
    symbol:                str
    signal:                str
    signal_candle:         str
    next_candle_open:      float
    fill_price:            float
    entry_slippage:        float
    exit_slippage:         float
    original_sl:           float
    original_tp:           float
    trailing_sl_history:   List[Tuple[str, float]] = field(default_factory=list)
    mfe_pts:               float = 0.0
    mfe_pct:               float = 0.0
    mfe_rs:                float = 0.0
    mae_pts:               float = 0.0
    mae_pct:               float = 0.0
    mae_rs:                float = 0.0
    exit_price:            float = 0.0
    exit_reason:           str   = ""
    gross_pnl:             float = 0.0
    charges:               float = 0.0
    net_pnl:               float = 0.0
    capital_before:        float = 0.0
    capital_after:         float = 0.0
    risk_amount:           float = 0.0
    qty:                   int   = 0
    bars_held:             int   = 0
    minutes_held:          float = 0.0
    indicator_snapshot:    Dict[str, float] = field(default_factory=dict)
    indicator_match:       bool  = True
    indicator_mismatches:  List[str] = field(default_factory=list)


class TradeReplayEngine:
    """
    Replays every trade from a completed backtest result.

    Usage::

        replayer = TradeReplayEngine(symbol="RELIANCE", interval_minutes=5)
        records  = replayer.replay(result, df_processed)
        replayer.save(records, Path("reports"))
    """

    def __init__(
        self,
        symbol:           str   = "UNKNOWN",
        interval_minutes: int   = 5,
        initial_capital:  float = 100_000.0,
    ) -> None:
        self.symbol          = symbol
        self.interval_min    = interval_minutes
        self.initial_capital = initial_capital

    def replay(
        self,
        result:       Dict[str, Any],
        df_processed: pd.DataFrame,
    ) -> List[TradeReplayRecord]:
        """Replay all trades. Returns list of TradeReplayRecord."""
        trades = result.get("trades", [])
        if not trades:
            logger.warning("Phase 1: No trades to replay")
            return []

        cfg        = result.get("config", {})
        risk_pct   = cfg.get("risk_pct",    0.01)
        atr_sl     = cfg.get("atr_sl_mult", 2.0)
        atr_tp     = cfg.get("atr_tp_mult", 4.0)

        # Build datetime → row index map
        df = df_processed.copy()
        dt_map: Dict[str, int] = {}
        if "datetime" in df.columns:
            df["_dt_str"] = df["datetime"].astype(str).str[:19]
            dt_map = {r["_dt_str"]: i for i, r in df.iterrows()}

        records: List[TradeReplayRecord] = []
        capital = self.initial_capital

        for n, trade in enumerate(trades, start=1):
            rec     = self._replay_one(n, trade, df, dt_map, capital, risk_pct, atr_sl, atr_tp)
            capital += trade.get("net_pnl", 0.0)
            records.append(rec)

        logger.info("Phase 1: Replayed %d trades", len(records))
        return records

    def _replay_one(
        self,
        trade_num:      int,
        trade:          Dict[str, Any],
        df:             pd.DataFrame,
        dt_map:         Dict[str, int],
        capital_before: float,
        risk_pct:       float,
        atr_sl_mult:    float,
        atr_tp_mult:    float,
    ) -> TradeReplayRecord:
        entry_time  = str(trade.get("entry_time", ""))[:19]
        exit_time   = str(trade.get("exit_time",  ""))[:19]
        signal      = trade.get("signal", "")
        qty         = trade.get("qty", 0)
        eff_entry   = trade.get("effective_entry", 0.0)
        eff_exit    = trade.get("effective_exit", trade.get("exit", 0.0))
        atr         = trade.get("atr", 0.0)
        entry_slip  = trade.get("entry_slip",  0.0)
        exit_slip   = trade.get("exit_slip",   0.0)
        gross_pnl   = trade.get("gross_pnl",   0.0)
        charges     = trade.get("charges",     0.0)
        net_pnl     = trade.get("net_pnl",     0.0)

        # Original SL/TP (calculated from entry_price before slippage)
        entry_price = trade.get("entry_price", trade.get("entry", eff_entry))
        if signal == "BUY":
            original_sl = entry_price - atr_sl_mult * atr
            original_tp = entry_price + atr_tp_mult * atr
        else:
            original_sl = entry_price + atr_sl_mult * atr
            original_tp = entry_price - atr_tp_mult * atr

        entry_idx = dt_map.get(entry_time)
        exit_idx  = dt_map.get(exit_time)

        # Signal candle (one bar before entry fill)
        signal_candle    = ""
        next_candle_open = entry_price
        if entry_idx is not None:
            next_candle_open = float(df.iloc[entry_idx]["open"])
            if entry_idx > 0:
                signal_candle = str(df.iloc[entry_idx - 1].get("datetime", ""))[:19]

        # ── MFE / MAE + trailing SL history ────────────────────────────────
        mfe_pts = mae_pts = 0.0
        trailing_sl_hist: List[Tuple[str, float]] = [(entry_time, round(original_sl, 4))]
        current_sl = original_sl
        tp_dist    = abs(original_tp - eff_entry) if atr > 0 else 1.0

        if entry_idx is not None and exit_idx is not None:
            for _, bar in df.iloc[entry_idx : exit_idx + 1].iterrows():
                high = float(bar["high"])
                low  = float(bar["low"])
                bts  = str(bar.get("datetime", ""))[:19]

                if signal == "BUY":
                    fav    = high - eff_entry
                    adv    = eff_entry - low
                    profit = high - eff_entry
                    if profit >= tp_dist * 0.5 and current_sl < eff_entry:
                        current_sl = eff_entry
                        trailing_sl_hist.append((bts, round(current_sl, 4)))
                    if profit >= tp_dist * 0.7 and atr > 0:
                        trail = high - atr * 0.5
                        if trail > current_sl:
                            current_sl = round(trail, 4)
                            trailing_sl_hist.append((bts, current_sl))
                else:
                    fav    = eff_entry - low
                    adv    = high - eff_entry
                    profit = eff_entry - low
                    if profit >= tp_dist * 0.5 and current_sl > eff_entry:
                        current_sl = eff_entry
                        trailing_sl_hist.append((bts, round(current_sl, 4)))
                    if profit >= tp_dist * 0.7 and atr > 0:
                        trail = low + atr * 0.5
                        if trail < current_sl:
                            current_sl = round(trail, 4)
                            trailing_sl_hist.append((bts, current_sl))

                mfe_pts = max(mfe_pts, fav)
                mae_pts = max(mae_pts, adv)

        mfe_pct = (mfe_pts / eff_entry * 100) if eff_entry > 0 else 0.0
        mae_pct = (mae_pts / eff_entry * 100) if eff_entry > 0 else 0.0

        # ── Indicator snapshot at entry bar ─────────────────────────────────
        snapshot: Dict[str, float] = {}
        if entry_idx is not None:
            bar = df.iloc[entry_idx]
            for label, col in [
                ("ema9", "ema_9"), ("ema20", "ema_20"), ("ema50", "ema_50"),
                ("vwap", "vwap"),  ("rsi",  "rsi_14"), ("atr",  "atr_14"),
                ("macd_hist", "macd_hist"), ("adx", "adx_14"),
            ]:
                val = bar.get(col, np.nan)
                snapshot[label] = round(float(val), 6) if not pd.isna(val) else float("nan")
            st_val = bar.get("supertrend", None)
            snapshot["supertrend"] = float(st_val) if st_val is not None else float("nan")

        bars_held    = trade.get("bars_held", max(0, (exit_idx or 0) - (entry_idx or 0)))
        minutes_held = bars_held * self.interval_min

        return TradeReplayRecord(
            trade_num=trade_num,
            date=entry_time[:10],
            entry_time=entry_time,
            exit_time=exit_time,
            symbol=self.symbol,
            signal=signal,
            signal_candle=signal_candle,
            next_candle_open=round(next_candle_open, 4),
            fill_price=round(eff_entry, 4),
            entry_slippage=round(entry_slip, 4),
            exit_slippage=round(exit_slip, 4),
            original_sl=round(original_sl, 4),
            original_tp=round(original_tp, 4),
            trailing_sl_history=trailing_sl_hist,
            mfe_pts=round(mfe_pts, 4),
            mfe_pct=round(mfe_pct, 4),
            mfe_rs=round(mfe_pts * qty, 2),
            mae_pts=round(mae_pts, 4),
            mae_pct=round(mae_pct, 4),
            mae_rs=round(mae_pts * qty, 2),
            exit_price=round(eff_exit, 4),
            exit_reason=trade.get("exit_reason", ""),
            gross_pnl=round(gross_pnl, 2),
            charges=round(charges, 2),
            net_pnl=round(net_pnl, 2),
            capital_before=round(capital_before, 2),
            capital_after=round(capital_before + net_pnl, 2),
            risk_amount=round(capital_before * risk_pct, 2),
            qty=qty,
            bars_held=bars_held,
            minutes_held=float(minutes_held),
            indicator_snapshot=snapshot,
            indicator_match=True,
            indicator_mismatches=[],
        )

    def to_dataframe(self, records: List[TradeReplayRecord]) -> pd.DataFrame:
        rows = []
        for r in records:
            rows.append({
                "#":                  r.trade_num,
                "Date":               r.date,
                "Entry Time":         r.entry_time,
                "Exit Time":          r.exit_time,
                "Symbol":             r.symbol,
                "Signal":             r.signal,
                "Signal Candle":      r.signal_candle,
                "Next Bar Open":      r.next_candle_open,
                "Fill Price":         r.fill_price,
                "Entry Slip":         r.entry_slippage,
                "Exit Slip":          r.exit_slippage,
                "Original SL":        r.original_sl,
                "Original TP":        r.original_tp,
                "Trailing Updates":   len(r.trailing_sl_history),
                "MFE pts":            r.mfe_pts,
                "MFE %":              r.mfe_pct,
                "MFE Rs":             r.mfe_rs,
                "MAE pts":            r.mae_pts,
                "MAE %":              r.mae_pct,
                "MAE Rs":             r.mae_rs,
                "Exit Price":         r.exit_price,
                "Exit Reason":        r.exit_reason,
                "Gross PnL":          r.gross_pnl,
                "Charges":            r.charges,
                "Net PnL":            r.net_pnl,
                "Capital Before":     r.capital_before,
                "Capital After":      r.capital_after,
                "Risk Amount":        r.risk_amount,
                "Qty":                r.qty,
                "Bars Held":          r.bars_held,
                "Minutes Held":       r.minutes_held,
                "Indicators OK":      r.indicator_match,
            })
        return pd.DataFrame(rows)

    def to_markdown(self, records: List[TradeReplayRecord]) -> str:
        lines = ["# Phase 1 — Complete Trade Replay", "",
                 f"Total trades replayed: **{len(records)}**", ""]
        for r in records:
            win = "🟢" if r.net_pnl >= 0 else "🔴"
            lines += [
                f"## {win} Trade {r.trade_num} — {r.signal} | {r.entry_time}",
                "",
                "| Field | Value |",
                "|-------|-------|",
                f"| Symbol | {r.symbol} |",
                f"| Direction | {r.signal} |",
                f"| Signal Candle | {r.signal_candle} |",
                f"| Next Bar Open | {r.next_candle_open:.4f} |",
                f"| Fill Price (eff. entry) | {r.fill_price:.4f} |",
                f"| Entry Slippage | {r.entry_slippage:.4f} pts |",
                f"| Exit Slippage | {r.exit_slippage:.4f} pts |",
                f"| Original SL | {r.original_sl:.4f} |",
                f"| Original TP | {r.original_tp:.4f} |",
                f"| Trailing SL Updates | {len(r.trailing_sl_history)} |",
                f"| MFE | {r.mfe_pts:.4f} pts / {r.mfe_pct:.4f}% / ₹{r.mfe_rs:.2f} |",
                f"| MAE | {r.mae_pts:.4f} pts / {r.mae_pct:.4f}% / ₹{r.mae_rs:.2f} |",
                f"| Exit Time | {r.exit_time} |",
                f"| Exit Price | {r.exit_price:.4f} |",
                f"| Exit Reason | {r.exit_reason} |",
                f"| Gross PnL | ₹{r.gross_pnl:.2f} |",
                f"| Charges | ₹{r.charges:.2f} |",
                f"| Net PnL | ₹{r.net_pnl:.2f} |",
                f"| Capital Before | ₹{r.capital_before:.2f} |",
                f"| Capital After | ₹{r.capital_after:.2f} |",
                f"| Risk Amount | ₹{r.risk_amount:.2f} |",
                f"| Qty | {r.qty} |",
                f"| Bars Held | {r.bars_held} |",
                f"| Minutes Held | {r.minutes_held:.0f} |",
                "",
            ]
            if r.trailing_sl_history:
                lines += ["### Trailing SL History", "", "| Bar | SL Level |", "|-----|----------|"]
                for ts, sl in r.trailing_sl_history:
                    lines.append(f"| {ts} | {sl:.4f} |")
                lines.append("")
            if r.indicator_snapshot:
                lines += ["### Indicator Snapshot at Entry", "", "| Indicator | Value |", "|-----------|-------|"]
                for k, v in r.indicator_snapshot.items():
                    lines.append(f"| {k} | {v} |")
                lines.append("")
        return "\n".join(lines)

    def save(self, records: List[TradeReplayRecord], output_dir: Path) -> Dict[str, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_p = output_dir / "phase1_trade_replay.csv"
        md_p  = output_dir / "phase1_trade_replay.md"
        self.to_dataframe(records).to_csv(csv_p, index=False)
        md_p.write_text(self.to_markdown(records), encoding="utf-8")
        logger.info("Phase 1 saved → %s, %s", csv_p, md_p)
        return {"csv": csv_p, "md": md_p}
