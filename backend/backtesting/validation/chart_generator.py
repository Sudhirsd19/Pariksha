"""
Phase 11 — Trade Chart Generator
===================================
Generates one matplotlib chart per trade showing:
  candlesticks, EMAs, VWAP, entry/exit markers,
  SL/TP lines, trailing SL history, volume subplot,
  Supertrend background shading, FVG shading.

Uses ONLY matplotlib — no mplfinance or other paid dependencies.

DO NOT modify any strategy or engine files.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    import matplotlib
    matplotlib.use("Agg")   # non-interactive backend
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import FancyArrowPatch
    _MPL_AVAILABLE = True
except ImportError:
    _MPL_AVAILABLE = False
    logger.warning("matplotlib not available — Phase 11 charts will be skipped")


class TradeChartGenerator:
    """
    Generates one PNG chart per trade.

    Usage::

        gen   = TradeChartGenerator(output_dir=Path("reports/charts"))
        paths = gen.generate_all(result, df_processed, replay_records)
    """

    PRE_BARS  = 30   # candles shown before entry
    POST_BARS = 10   # candles shown after exit

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self.output_dir = output_dir or Path("reports/charts")

    def generate_all(
        self,
        result:          Dict[str, Any],
        df_processed:    pd.DataFrame,
        replay_records:  Optional[List[Any]] = None,
    ) -> List[Path]:
        """Generate one chart per trade. Returns list of saved paths."""
        if not _MPL_AVAILABLE:
            logger.warning("Phase 11: matplotlib not available — skipping charts")
            return []

        trades = result.get("trades", [])
        if not trades:
            logger.warning("Phase 11: No trades — no charts generated")
            return []

        self.output_dir.mkdir(parents=True, exist_ok=True)

        df = df_processed.copy()
        dt_map: Dict[str, int] = {}
        if "datetime" in df.columns:
            df["_dt_str"] = df["datetime"].astype(str).str[:19]
            dt_map = {row["_dt_str"]: i for i, row in df.iterrows()}

        # Build trailing SL map from replay records
        trailing_sl_map: Dict[int, List[Tuple[str, float]]] = {}
        if replay_records:
            for rec in replay_records:
                trailing_sl_map[rec.trade_num] = rec.trailing_sl_history

        paths: List[Path] = []
        for n, trade in enumerate(trades, start=1):
            try:
                p = self._chart_one(n, trade, df, dt_map, trailing_sl_map.get(n, []))
                if p:
                    paths.append(p)
            except Exception as exc:
                logger.error("Phase 11: Chart %d failed — %s", n, exc)

        logger.info("Phase 11: Generated %d charts → %s", len(paths), self.output_dir)
        return paths

    def _chart_one(
        self,
        trade_num:          int,
        trade:              Dict[str, Any],
        df:                 pd.DataFrame,
        dt_map:             Dict[str, int],
        trailing_sl_history: List[Tuple[str, float]],
    ) -> Optional[Path]:
        """Generate chart for one trade. Returns saved path."""
        entry_time = str(trade.get("entry_time", ""))[:19]
        exit_time  = str(trade.get("exit_time",  ""))[:19]
        signal     = trade.get("signal", "BUY")
        eff_entry  = float(trade.get("effective_entry", 0))
        eff_exit   = float(trade.get("effective_exit", trade.get("exit", 0)))
        sl         = float(trade.get("sl", 0))
        tp         = float(trade.get("tp", 0))
        atr        = float(trade.get("atr", 0))
        net_pnl    = float(trade.get("net_pnl", 0))
        exit_reason= str(trade.get("exit_reason", ""))

        entry_idx = dt_map.get(entry_time)
        exit_idx  = dt_map.get(exit_time)

        if entry_idx is None:
            logger.warning("Trade %d: entry_time %s not in dt_map — skipping chart", trade_num, entry_time)
            return None

        # Window: PRE_BARS before entry, POST_BARS after exit
        start = max(0, entry_idx - self.PRE_BARS)
        end   = min(len(df) - 1, (exit_idx or entry_idx) + self.POST_BARS)
        window = df.iloc[start : end + 1].reset_index(drop=True)

        if len(window) < 3:
            return None

        # x-axis indices (relative to window start)
        entry_x = entry_idx - start
        exit_x  = (exit_idx or entry_idx) - start

        fig, (ax1, ax2) = plt.subplots(
            2, 1, figsize=(16, 10),
            gridspec_kw={"height_ratios": [3, 1]},
            sharex=True,
        )

        # ── Candlesticks ──────────────────────────────────────────────────────
        for i, row in window.iterrows():
            o, h, l, c = row["open"], row["high"], row["low"], row["close"]
            color = "#26a69a" if c >= o else "#ef5350"   # teal=up, red=down
            ax1.plot([i, i], [l, h], color=color, linewidth=0.8, zorder=2)
            ax1.add_patch(plt.Rectangle(
                (i - 0.4, min(o, c)), 0.8, abs(c - o),
                color=color, zorder=2,
            ))

        # ── Supertrend background shading ─────────────────────────────────────
        if "supertrend" in window.columns:
            for i, row in window.iterrows():
                bg = "#e8f5e9" if row.get("supertrend", True) else "#ffebee"
                ax1.axvspan(i - 0.5, i + 0.5, alpha=0.15, color=bg, zorder=0)

        # ── FVG shading ────────────────────────────────────────────────────────
        if "fvg_bull" in window.columns:
            for i, row in window.iterrows():
                if row.get("fvg_bull", False):
                    ax1.axvspan(i - 0.5, i + 0.5, alpha=0.20, color="#1565C0", zorder=1)
                if row.get("fvg_bear", False):
                    ax1.axvspan(i - 0.5, i + 0.5, alpha=0.20, color="#B71C1C", zorder=1)

        # ── EMAs ──────────────────────────────────────────────────────────────
        xs = list(range(len(window)))
        for col, color, label in [
            ("ema_9",  "#2196F3", "EMA9"),
            ("ema_20", "#FF9800", "EMA20"),
            ("ema_50", "#9C27B0", "EMA50"),
        ]:
            if col in window.columns:
                vals = window[col].values.astype(float)
                ax1.plot(xs, vals, color=color, linewidth=1.2, label=label, zorder=3)

        # ── VWAP ──────────────────────────────────────────────────────────────
        if "vwap" in window.columns:
            vals = window["vwap"].values.astype(float)
            ax1.plot(xs, vals, color="#00BCD4", linewidth=1.2,
                     linestyle="--", label="VWAP", zorder=3)

        # ── SL / TP lines ─────────────────────────────────────────────────────
        ax1.axhline(sl, color="#F44336", linewidth=1.5, linestyle="--",
                    label=f"SL {sl:.2f}", alpha=0.9)
        ax1.axhline(tp, color="#4CAF50", linewidth=1.5, linestyle="--",
                    label=f"TP {tp:.2f}", alpha=0.9)

        # ── Trailing SL history ───────────────────────────────────────────────
        for ts_str, sl_val in trailing_sl_history[1:]:   # skip initial SL
            t_idx = dt_map.get(ts_str, -1) - start
            if 0 <= t_idx < len(window):
                ax1.axhline(sl_val, xmin=t_idx / len(window), xmax=1.0,
                             color="#FF6F00", linewidth=1.0, linestyle=":",
                             alpha=0.7)

        # ── Entry marker ──────────────────────────────────────────────────────
        marker = "^" if signal == "BUY" else "v"
        color  = "#00C853" if signal == "BUY" else "#D50000"
        ax1.scatter(
            [entry_x], [eff_entry],
            marker=marker, s=200, color=color, zorder=10, label=f"Entry {eff_entry:.2f}",
        )

        # ── Exit marker ───────────────────────────────────────────────────────
        exit_color = "#4CAF50" if net_pnl >= 0 else "#F44336"
        ax1.scatter(
            [exit_x], [eff_exit],
            marker="X", s=200, color=exit_color, zorder=10, label=f"Exit {eff_exit:.2f}",
        )

        # ── Volume subplot ────────────────────────────────────────────────────
        if "volume" in window.columns:
            vols = window["volume"].values
            bar_colors = ["#26a69a" if window.iloc[i]["close"] >= window.iloc[i]["open"]
                          else "#ef5350" for i in range(len(window))]
            ax2.bar(xs, vols, color=bar_colors, width=0.8, alpha=0.7)
            ax2.set_ylabel("Volume", fontsize=8)
            ax2.yaxis.set_major_formatter(
                matplotlib.ticker.FuncFormatter(lambda x, _: f"{x/1e6:.1f}M" if x >= 1e6 else f"{x:.0f}")
            )

        # ── X-axis labels (datetime) ──────────────────────────────────────────
        tick_step = max(1, len(window) // 8)
        tick_xs   = range(0, len(window), tick_step)
        tick_lbls = [str(window.iloc[i].get("datetime", ""))[:16] for i in tick_xs]
        ax2.set_xticks(list(tick_xs))
        ax2.set_xticklabels(tick_lbls, rotation=30, fontsize=7, ha="right")

        # ── Title & labels ────────────────────────────────────────────────────
        pnl_str = f"₹{net_pnl:+,.2f}"
        pnl_col = "green" if net_pnl >= 0 else "red"
        ax1.set_title(
            f"Trade {trade_num} — {signal} | Entry: {entry_time} | "
            f"Exit: {exit_reason} | Net PnL: {pnl_str}",
            fontsize=11, color=pnl_col, fontweight="bold",
        )
        ax1.set_ylabel("Price (₹)", fontsize=9)
        ax1.legend(fontsize=7, loc="upper left", ncol=4)
        ax1.grid(True, alpha=0.3, linewidth=0.5)
        ax2.grid(True, alpha=0.3, linewidth=0.5)

        # ── Save ──────────────────────────────────────────────────────────────
        date_str   = entry_time[:10].replace("-", "")
        time_str   = entry_time[11:16].replace(":", "")
        fname      = f"trade_{trade_num:02d}_{date_str}_{time_str}_{signal}.png"
        out_path   = self.output_dir / fname

        plt.tight_layout()
        plt.savefig(out_path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        return out_path

    def generate_index(self, paths: List[Path], output_dir: Path) -> Path:
        """Generate a markdown index of all trade charts."""
        output_dir.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Phase 11 — Trade Chart Index",
            "",
            f"**{len(paths)} charts generated**",
            "",
        ]
        for p in paths:
            rel = p.name
            lines.append(f"- [{rel}](charts/{rel})")
        out = output_dir / "phase11_chart_index.md"
        out.write_text("\n".join(lines), encoding="utf-8")
        return out
