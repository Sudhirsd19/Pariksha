"""
Phase 6 — Performance Attribution
====================================
For every losing trade: identifies root cause(s).
For every winning trade: identifies success factor(s).

DO NOT modify any strategy or engine files.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)

# Thresholds for attribution labels
ATR_LOW_THRESHOLD     = 5.0    # pts — below this = LOW_ATR
ATR_SIDEWAYS_THRESH   = 8.0    # pts
ADX_WEAK_THRESHOLD    = 20.0   # below this = WEAK_MOMENTUM
ADX_STRONG_THRESHOLD  = 25.0   # above this = STRONG_TREND
LATE_ENTRY_HOUR       = 13     # entries after 13:30 = LATE_ENTRY
SLIPPAGE_DRAG_BPS     = 10     # slippage > 10bps of entry = SLIPPAGE_DRAG


@dataclass
class AttributionRecord:
    """Attribution labels for one trade."""
    trade_num:   int
    entry_time:  str
    signal:      str
    net_pnl:     float
    outcome:     str    # WIN | LOSS | BREAKEVEN
    labels:      List[str] = field(default_factory=list)


class PerformanceAttributor:
    """
    Assigns root-cause / success-factor labels to every trade.

    Usage::

        attr    = PerformanceAttributor()
        records = attr.attribute(result, df_processed)
        attr.save(records, Path("reports"))
    """

    def attribute(
        self,
        result:       Dict[str, Any],
        df_processed: pd.DataFrame,
    ) -> List[AttributionRecord]:
        """Assign attribution labels to all trades."""
        trades = result.get("trades", [])
        if not trades:
            return []

        df = df_processed.copy()
        dt_map: Dict[str, int] = {}
        if "datetime" in df.columns:
            df["_dt_str"] = df["datetime"].astype(str).str[:19]
            dt_map = {row["_dt_str"]: i for i, row in df.iterrows()}

        records: List[AttributionRecord] = []
        for n, trade in enumerate(trades, 1):
            rec = self._attribute_one(n, trade, df, dt_map)
            records.append(rec)

        logger.info("Phase 6: Attributed %d trades", len(records))
        return records

    def _attribute_one(
        self,
        trade_num: int,
        trade:     Dict[str, Any],
        df:        pd.DataFrame,
        dt_map:    Dict[str, int],
    ) -> AttributionRecord:
        entry_time  = str(trade.get("entry_time", ""))[:19]
        signal      = trade.get("signal", "")
        net_pnl     = float(trade.get("net_pnl", 0.0))
        gross_pnl   = float(trade.get("gross_pnl", 0.0))
        charges     = float(trade.get("charges", 0.0))
        atr         = float(trade.get("atr", 0.0))
        eff_entry   = float(trade.get("effective_entry", 0.0))
        exit_reason = str(trade.get("exit_reason", ""))
        entry_slip  = float(trade.get("entry_slip", 0.0))
        exit_slip   = float(trade.get("exit_slip", 0.0))

        outcome = "WIN" if net_pnl > 0 else ("BREAKEVEN" if net_pnl == 0 else "LOSS")
        labels: List[str] = []

        # ── Get entry bar indicators ──────────────────────────────────────────
        idx = dt_map.get(entry_time)
        adx = 0.0
        fvg_b = fvg_br = False
        vwap = 0.0
        macd_h = 0.0
        if idx is not None:
            bar    = df.iloc[idx]
            adx    = float(bar.get("adx_14",  0) or 0)
            fvg_b  = bool(bar.get("fvg_bull", False))
            fvg_br = bool(bar.get("fvg_bear", False))
            vwap   = float(bar.get("vwap",    eff_entry) or eff_entry)
            macd_h = float(bar.get("macd_hist", 0) or 0)

        # ── LOSS attributions ─────────────────────────────────────────────────
        if outcome == "LOSS":
            if atr < ATR_LOW_THRESHOLD:
                labels.append("LOW_ATR")
            if atr < ATR_SIDEWAYS_THRESH:
                labels.append("SIDEWAYS_MARKET")
            if adx < ADX_WEAK_THRESHOLD:
                labels.append("LOW_MOMENTUM")
            if abs(charges) > abs(gross_pnl) and gross_pnl != 0:
                labels.append("CHARGES_DRAG")
            total_slip = (entry_slip + exit_slip)
            slip_bps   = (total_slip / eff_entry * 10000) if eff_entry > 0 else 0
            if slip_bps > SLIPPAGE_DRAG_BPS:
                labels.append("SLIPPAGE_DRAG")
            # Late entry
            try:
                entry_hour = int(entry_time[11:13])
                entry_min  = int(entry_time[14:16])
                if entry_hour > LATE_ENTRY_HOUR or (entry_hour == LATE_ENTRY_HOUR and entry_min >= 30):
                    labels.append("LATE_ENTRY")
            except (ValueError, IndexError):
                pass
            if "SQUAREOFF" in exit_reason:
                labels.append("TIME_STOP")
            if "FORCED" in exit_reason:
                labels.append("FORCED_CLOSE")
            # Gap open check (prior bar close vs entry bar open)
            if idx is not None and idx > 0:
                prev_close = float(df.iloc[idx - 1]["close"])
                bar_open   = float(df.iloc[idx]["open"])
                if abs(bar_open - prev_close) > atr * 0.5:
                    labels.append("GAP_OPEN")
            if not labels:
                labels.append("NORMAL_LOSS")

        # ── WIN attributions ──────────────────────────────────────────────────
        elif outcome == "WIN":
            if adx > ADX_STRONG_THRESHOLD:
                labels.append("STRONG_TREND")
            if fvg_b and signal == "BUY":
                labels.append("BULLISH_FVG_PRESENT")
            if fvg_br and signal == "SELL":
                labels.append("BEARISH_FVG_PRESENT")
            if signal == "BUY" and eff_entry > vwap > 0:
                labels.append("VWAP_SUPPORT")
            elif signal == "SELL" and eff_entry < vwap:
                labels.append("VWAP_RESISTANCE")
            if macd_h > 0 and signal == "BUY":
                labels.append("MOMENTUM_CONTINUATION")
            elif macd_h < 0 and signal == "SELL":
                labels.append("MOMENTUM_CONTINUATION")
            # Check exit bar ATR vs entry bar ATR for ATR expansion
            exit_time = str(trade.get("exit_time", ""))[:19]
            exit_idx  = dt_map.get(exit_time)
            if exit_idx is not None:
                exit_atr = float(df.iloc[exit_idx].get("atr_14", 0) or 0)
                if exit_atr > atr * 1.1:
                    labels.append("ATR_EXPANSION")
            if "TP" in exit_reason:
                labels.append("CLEAN_TP_HIT")
            if not labels:
                labels.append("NORMAL_WIN")

        return AttributionRecord(
            trade_num=trade_num,
            entry_time=entry_time,
            signal=signal,
            net_pnl=round(net_pnl, 2),
            outcome=outcome,
            labels=labels,
        )

    def summary(self, records: List[AttributionRecord]) -> pd.DataFrame:
        """Returns label frequency summary."""
        from collections import Counter
        all_labels: list = []
        for r in records:
            all_labels.extend(r.labels)
        cnt = Counter(all_labels)
        df = pd.DataFrame(
            [(lbl, count, "WIN" if any(
                lbl in r.labels and r.outcome == "WIN" for r in records
            ) else "LOSS") for lbl, count in cnt.most_common()],
            columns=["Label", "Count", "Outcome_Type"],
        )
        return df

    def to_markdown(self, records: List[AttributionRecord]) -> str:
        wins   = [r for r in records if r.outcome == "WIN"]
        losses = [r for r in records if r.outcome == "LOSS"]
        lines  = [
            "# Phase 6 — Performance Attribution",
            "",
            f"| Trades | Winners | Losers |",
            f"|--------|---------|--------|",
            f"| {len(records)} | {len(wins)} | {len(losses)} |",
            "",
            "## Trade Attribution",
            "",
            "| # | Time | Signal | Net PnL | Outcome | Labels |",
            "|---|------|--------|---------|---------|--------|",
        ]
        for r in records:
            icon = "🟢" if r.outcome == "WIN" else ("🔴" if r.outcome == "LOSS" else "⚪")
            lines.append(
                f"| {r.trade_num} | {r.entry_time} | {r.signal} "
                f"| ₹{r.net_pnl:.2f} | {icon} {r.outcome} | `{', '.join(r.labels)}` |"
            )

        # Summary
        smry = self.summary(records)
        if not smry.empty:
            lines += ["", "## Label Frequency", "", smry.to_markdown(index=False)]
        return "\n".join(lines)

    def save(self, records: List[AttributionRecord], output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "phase6_attribution.md"
        out.write_text(self.to_markdown(records), encoding="utf-8")
        # Also CSV
        csv_p = output_dir / "phase6_attribution.csv"
        pd.DataFrame([
            {"#": r.trade_num, "Time": r.entry_time, "Signal": r.signal,
             "Net_PnL": r.net_pnl, "Outcome": r.outcome, "Labels": "|".join(r.labels)}
            for r in records
        ]).to_csv(csv_p, index=False)
        logger.info("Phase 6 saved → %s", out)
        return out
