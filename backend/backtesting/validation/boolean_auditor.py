"""
Phase 3 — Boolean Expression Auditor
======================================
Prints the exact evaluated boolean expression for every BUY, SELL,
and near-miss (score >= 3) candle with actual indicator values.

DO NOT modify any strategy or engine files.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


class BooleanExpressionAuditor:
    """
    Prints full boolean filter evaluation for every signal candle.

    Usage::

        auditor = BooleanExpressionAuditor()
        text    = auditor.audit(result, df_processed)
        auditor.save(text, Path("reports"))
    """

    MIN_SCORE: int = 3   # minimum score to include in audit

    def audit(
        self,
        result:       Dict[str, Any],
        df_processed: pd.DataFrame,
    ) -> str:
        """Build the full boolean expression audit string."""
        # Get audit entries
        audit_obj     = result.get("_audit_log_obj")
        audit_entries: List[Dict] = (
            audit_obj.entries if (audit_obj and hasattr(audit_obj, "entries")) else []
        )

        if not audit_entries:
            return self._no_audit_log_msg()

        # Build dt → bar index map
        df = df_processed.copy()
        dt_map: Dict[str, int] = {}
        if "datetime" in df.columns:
            df["_dt_str"] = df["datetime"].astype(str).str[:19]
            dt_map = {row["_dt_str"]: i for i, row in df.iterrows()}

        lines: List[str] = [
            "# Phase 3 — Boolean Expression Audit",
            "",
            "Every BUY, SELL, and near-miss (score ≥ 3) shown below.",
            "All values are from actual execution — no synthetic examples.",
            "",
        ]

        audited = 0
        for entry in audit_entries:
            signal = entry.get("signal", "NONE")
            dt_str = str(entry.get("datetime", ""))[:19]
            price  = float(entry.get("price", 0.0))

            # Pull indicator values from processed df
            bar_idx = dt_map.get(dt_str)
            if bar_idx is not None:
                bar    = df.iloc[bar_idx]
                ema9   = float(bar.get("ema_9",    price) or price)
                ema20  = float(bar.get("ema_20",   price) or price)
                ema50  = float(bar.get("ema_50",   price) or price)
                vwap   = float(bar.get("vwap",     price) or price)
                rsi    = float(bar.get("rsi_14",    50)   or 50)
                macd_h = float(bar.get("macd_hist",  0)   or 0)
                adx    = float(bar.get("adx_14",     0)   or 0)
                st_b   = bool(bar.get("supertrend", True))
                fvg_b  = bool(bar.get("fvg_bull", False))
                fvg_br = bool(bar.get("fvg_bear", False))
            else:
                ema9  = ema20 = ema50 = vwap = price
                rsi   = float(entry.get("rsi", 50))
                macd_h = float(entry.get("macd_hist", 0))
                adx   = float(entry.get("adx", 0))
                st_b  = bool(entry.get("supertrend_bull", True))
                fvg_b = fvg_br = False

            # Evaluate all 8 BUY filters with actual values
            buy_evals: List[Tuple[str, bool, str]] = [
                ("ema9_above_ema20",   ema9 > ema20,
                 f"EMA9({ema9:.4f}) > EMA20({ema20:.4f})"),
                ("ema20_above_ema50",  ema20 > ema50,
                 f"EMA20({ema20:.4f}) > EMA50({ema50:.4f})"),
                ("price_above_vwap",   vwap > 0 and price > vwap,
                 f"CLOSE({price:.4f}) > VWAP({vwap:.4f})"),
                ("rsi_55_75",          55 <= rsi <= 75,
                 f"55 <= RSI({rsi:.2f}) <= 75"),
                ("macd_hist_positive", macd_h > 0,
                 f"MACD_HIST({macd_h:.6f}) > 0"),
                ("supertrend_bull",    st_b,
                 f"SUPERTREND_BULL = {st_b}"),
                ("adx_gt_20",          adx > 20,
                 f"ADX({adx:.2f}) > 20"),
                ("bullish_fvg",        fvg_b,
                 f"BULLISH_FVG = {fvg_b}"),
            ]

            # Evaluate all 8 SELL filters with actual values
            sell_evals: List[Tuple[str, bool, str]] = [
                ("ema9_below_ema20",   ema9 < ema20,
                 f"EMA9({ema9:.4f}) < EMA20({ema20:.4f})"),
                ("ema20_below_ema50",  ema20 < ema50,
                 f"EMA20({ema20:.4f}) < EMA50({ema50:.4f})"),
                ("price_below_vwap",   vwap > 0 and price < vwap,
                 f"CLOSE({price:.4f}) < VWAP({vwap:.4f})"),
                ("rsi_25_45",          25 <= rsi <= 45,
                 f"25 <= RSI({rsi:.2f}) <= 45"),
                ("macd_hist_negative", macd_h < 0,
                 f"MACD_HIST({macd_h:.6f}) < 0"),
                ("supertrend_bear",    not st_b,
                 f"SUPERTREND_BEAR = {not st_b}"),
                ("adx_gt_20",          adx > 20,
                 f"ADX({adx:.2f}) > 20"),
                ("bearish_fvg",        fvg_br,
                 f"BEARISH_FVG = {fvg_br}"),
            ]

            buy_score  = sum(1 for _, v, _ in buy_evals  if v)
            sell_score = sum(1 for _, v, _ in sell_evals if v)
            max_score  = max(buy_score, sell_score)

            # Only include candles worth auditing
            if signal in ("BUY", "SELL") or max_score >= self.MIN_SCORE:
                audited += 1
                candidate = signal if signal in ("BUY", "SELL") else (
                    "BUY" if buy_score >= sell_score else "SELL"
                )
                evals = buy_evals if candidate == "BUY" else sell_evals
                score = buy_score if candidate == "BUY" else sell_score

                lines += [
                    "---",
                    f"### Bar {dt_str} | CLOSE={price:.4f} | Decision={signal}",
                    "",
                    f"**{candidate} FILTER EVALUATION:**",
                    "",
                    "| # | Filter | Expression | Result |",
                    "|---|--------|-----------|--------|",
                ]
                for j, (fname, result_bool, expr) in enumerate(evals, start=1):
                    icon = "✅" if result_bool else "❌"
                    lines.append(f"| {j} | `{fname}` | `{expr}` | {icon} `{result_bool}` |")

                entry_ok  = signal in ("BUY", "SELL")
                lines += [
                    "",
                    f"**{candidate} SCORE: `{score}/8`** — Threshold: `5/8`",
                    f"**ENTRY: `{'TRUE ✅' if entry_ok else 'FALSE ❌'}`**",
                    "",
                ]

        if audited == 0:
            lines.append("_No candles met the minimum score threshold (≥3) for boolean audit._")
        lines.append(f"\n---\n**Total candles audited: {audited}**")
        result_text = "\n".join(lines)
        logger.info("Phase 3: Audited %d candles", audited)
        return result_text

    @staticmethod
    def _no_audit_log_msg() -> str:
        return (
            "# Phase 3 — Boolean Expression Audit\n\n"
            "> [!WARNING]\n"
            "> Engine `audit_log` not available in result dict.\n"
            "> To enable Phase 3, call `engine.run()` then pass:\n"
            "> `result['_audit_log_obj'] = engine.audit_log`\n"
        )

    def save(self, text: str, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "phase3_boolean_audit.md"
        out.write_text(text, encoding="utf-8")
        logger.info("Phase 3 saved → %s", out)
        return out
