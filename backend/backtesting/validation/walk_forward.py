"""
Phase 9 — Walk-Forward Stability Analyzer
==========================================
Splits available data into IS/OOS windows.
DO NOT optimize parameters — only measures stability decay.

Metrics:
  WFE = OOS_PF / IS_PF  (Walk-Forward Efficiency)
  Stability = 1 − |IS_PF − OOS_PF| / IS_PF × 100

DO NOT modify any strategy or engine files.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class WFWindow:
    """One IS/OOS walk-forward window."""
    window_num:      int
    is_start:        str
    is_end:          str
    oos_start:       str
    oos_end:         str
    # In-Sample metrics
    is_trades:       int   = 0
    is_win_rate:     float = 0.0
    is_profit_factor: float = 0.0
    is_net_pnl:      float = 0.0
    is_sharpe:       float = 0.0
    # Out-of-Sample metrics
    oos_trades:      int   = 0
    oos_win_rate:    float = 0.0
    oos_profit_factor: float = 0.0
    oos_net_pnl:     float = 0.0
    oos_sharpe:      float = 0.0
    # Stability metrics
    wfe:             float = 0.0   # Walk-Forward Efficiency
    stability_score: float = 0.0  # 0–100
    pf_decay:        float = 0.0  # IS_PF - OOS_PF
    win_rate_decay:  float = 0.0  # IS_WR - OOS_WR


@dataclass
class WalkForwardResult:
    """Overall walk-forward analysis result."""
    windows:         List[WFWindow] = field(default_factory=list)
    avg_wfe:         float = 0.0
    avg_stability:   float = 0.0
    avg_pf_decay:    float = 0.0
    avg_wr_decay:    float = 0.0
    verdict:         str   = ""


class WalkForwardAnalyzer:
    """
    IS/OOS walk-forward stability analysis — NO parameter optimization.

    Usage::

        wfa    = WalkForwardAnalyzer(is_pct=0.67, oos_pct=0.33)
        result = wfa.analyze(engine_cls, engine_kwargs, df_raw)
        wfa.save(result, Path("reports"))
    """

    def __init__(
        self,
        is_pct:  float = 0.67,   # 67% for in-sample
        oos_pct: float = 0.33,   # 33% for out-of-sample
        n_windows: int = 3,      # number of walk-forward windows
    ) -> None:
        self.is_pct    = is_pct
        self.oos_pct   = oos_pct
        self.n_windows = n_windows

    def analyze(
        self,
        engine_cls:    Any,
        engine_kwargs: Dict[str, Any],
        df_raw:        pd.DataFrame,
    ) -> WalkForwardResult:
        """
        Run walk-forward analysis.

        Args:
            engine_cls:    QuantumBacktestEngine class
            engine_kwargs: Constructor kwargs (no parameter changes)
            df_raw:        Full OHLCV DataFrame
        """
        if df_raw.empty:
            logger.warning("Phase 9: Empty dataframe — skipping")
            return WalkForwardResult(verdict="SKIPPED: empty data")

        n      = len(df_raw)
        window_size = n // self.n_windows
        windows: List[WFWindow] = []

        for w in range(self.n_windows):
            start = w * window_size
            end   = start + window_size if w < self.n_windows - 1 else n

            chunk    = df_raw.iloc[start:end].reset_index(drop=True)
            is_size  = int(len(chunk) * self.is_pct)
            df_is    = chunk.iloc[:is_size]
            df_oos   = chunk.iloc[is_size:]

            is_start  = self._ts(chunk, 0)
            is_end    = self._ts(chunk, is_size - 1)
            oos_start = self._ts(chunk, is_size)
            oos_end   = self._ts(chunk, len(chunk) - 1)

            win = WFWindow(
                window_num=w + 1,
                is_start=is_start, is_end=is_end,
                oos_start=oos_start, oos_end=oos_end,
            )

            # Run IS
            is_metrics = self._run_engine(engine_cls, engine_kwargs, df_is)
            if is_metrics:
                win.is_trades       = is_metrics.get("total_trades", 0)
                win.is_win_rate     = is_metrics.get("win_rate", 0.0)
                win.is_profit_factor= is_metrics.get("profit_factor", 0.0)
                win.is_net_pnl      = is_metrics.get("net_profit", 0.0)
                win.is_sharpe       = is_metrics.get("sharpe_ratio", 0.0)

            # Run OOS (same params — no optimization)
            oos_metrics = self._run_engine(engine_cls, engine_kwargs, df_oos)
            if oos_metrics:
                win.oos_trades        = oos_metrics.get("total_trades", 0)
                win.oos_win_rate      = oos_metrics.get("win_rate", 0.0)
                win.oos_profit_factor = oos_metrics.get("profit_factor", 0.0)
                win.oos_net_pnl       = oos_metrics.get("net_profit", 0.0)
                win.oos_sharpe        = oos_metrics.get("sharpe_ratio", 0.0)

            # Stability metrics
            if win.is_profit_factor > 0:
                win.wfe = round(win.oos_profit_factor / win.is_profit_factor, 4)
                decay   = abs(win.is_profit_factor - win.oos_profit_factor)
                win.stability_score = round((1 - decay / win.is_profit_factor) * 100, 2)
            win.pf_decay      = round(win.is_profit_factor - win.oos_profit_factor, 4)
            win.win_rate_decay = round(win.is_win_rate     - win.oos_win_rate,      4)

            windows.append(win)
            logger.info(
                "  Window %d: IS PF=%.3f OOS PF=%.3f WFE=%.3f Stability=%.1f%%",
                w + 1, win.is_profit_factor, win.oos_profit_factor,
                win.wfe, win.stability_score,
            )

        # Aggregate
        valid = [w for w in windows if w.is_profit_factor > 0]
        avg_wfe     = sum(w.wfe for w in valid) / len(valid) if valid else 0.0
        avg_stab    = sum(w.stability_score for w in valid) / len(valid) if valid else 0.0
        avg_pf_dec  = sum(w.pf_decay for w in valid) / len(valid) if valid else 0.0
        avg_wr_dec  = sum(w.win_rate_decay for w in valid) / len(valid) if valid else 0.0

        if avg_wfe >= 0.7:
            verdict = "✅ STABLE — WFE ≥ 0.7: Strategy shows good OOS performance"
        elif avg_wfe >= 0.5:
            verdict = "⚠️ MARGINAL — WFE ≥ 0.5: Some OOS degradation detected"
        else:
            verdict = "❌ UNSTABLE — WFE < 0.5: Significant IS→OOS performance decay"

        logger.info("Phase 9 WF: avg_WFE=%.3f stability=%.1f%% — %s", avg_wfe, avg_stab, verdict)
        return WalkForwardResult(
            windows=windows,
            avg_wfe=round(avg_wfe, 4),
            avg_stability=round(avg_stab, 2),
            avg_pf_decay=round(avg_pf_dec, 4),
            avg_wr_decay=round(avg_wr_dec, 4),
            verdict=verdict,
        )

    def _run_engine(
        self,
        engine_cls:    Any,
        engine_kwargs: Dict[str, Any],
        df:            pd.DataFrame,
    ) -> Optional[Dict[str, Any]]:
        """Run engine on a data slice and return metrics dict."""
        try:
            kw = dict(engine_kwargs)
            kw["verbose"] = False
            engine = engine_cls(**kw)
            result = engine.run(df.copy())
            if result.get("status") == "error":
                return None
            return result.get("metrics", {})
        except Exception as exc:
            logger.warning("WF engine run failed: %s", exc)
            return None

    @staticmethod
    def _ts(df: pd.DataFrame, idx: int) -> str:
        if "datetime" in df.columns and idx < len(df):
            return str(df.iloc[idx]["datetime"])[:19]
        return str(idx)

    def to_markdown(self, result: WalkForwardResult) -> str:
        lines = [
            "# Phase 9 — Walk-Forward Stability Analysis",
            "",
            "> No parameter optimization performed. Same fixed parameters across all windows.",
            "",
            "## Overall Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Average WFE | {result.avg_wfe:.4f} |",
            f"| Average Stability Score | {result.avg_stability:.2f}% |",
            f"| Average PF Decay | {result.avg_pf_decay:.4f} |",
            f"| Average Win Rate Decay | {result.avg_wr_decay:.4f}% |",
            f"| Verdict | {result.verdict} |",
            "",
            "## Window-by-Window Results",
            "",
            "| Window | IS Period | IS Trades | IS PF | IS WR% | OOS Period | OOS Trades | OOS PF | OOS WR% | WFE | Stability |",
            "|--------|-----------|-----------|-------|--------|------------|------------|--------|---------|-----|-----------|",
        ]
        for w in result.windows:
            lines.append(
                f"| {w.window_num} | {w.is_start[:10]}–{w.is_end[:10]} "
                f"| {w.is_trades} | {w.is_profit_factor:.3f} | {w.is_win_rate:.1f}% "
                f"| {w.oos_start[:10]}–{w.oos_end[:10]} "
                f"| {w.oos_trades} | {w.oos_profit_factor:.3f} | {w.oos_win_rate:.1f}% "
                f"| {w.wfe:.3f} | {w.stability_score:.1f}% |"
            )
        lines += [
            "",
            "## Formula Reference",
            "",
            "- **WFE** = `OOS_PF / IS_PF` (1.0 = perfect stability, <0.5 = significant decay)",
            "- **Stability Score** = `(1 − |IS_PF − OOS_PF| / IS_PF) × 100`",
        ]
        return "\n".join(lines)

    def save(self, result: WalkForwardResult, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "phase9_walk_forward.md"
        out.write_text(self.to_markdown(result), encoding="utf-8")
        logger.info("Phase 9 saved → %s", out)
        return out
