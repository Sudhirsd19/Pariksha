"""
Phase 2 — Candle-by-Candle Decision Log
=========================================
One row per candle: all OHLCV, all indicators, BUY/SELL scores,
final decision, and the exact rejection reason.

DO NOT modify any strategy or engine files.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)

# Maps audit_log entry keys to their display names
_INDICATOR_COLS = {
    "ema_9":       "EMA9",
    "ema_20":      "EMA20",
    "ema_50":      "EMA50",
    "vwap":        "VWAP",
    "rsi_14":      "RSI",
    "atr_14":      "ATR",
    "macd_line":   "MACD_Line",
    "macd_hist":   "MACD_Hist",
    "adx_14":      "ADX",
    "supertrend":  "Supertrend",
    "fvg_bull":    "FVG_Bull",
    "fvg_bear":    "FVG_Bear",
}


class CandleDecisionLogger:
    """
    Builds a per-candle decision log with full indicator context.

    Two data sources are supported:
    1. Engine audit_log (preferred) — attached via result['_audit_log_obj']
    2. Processed DataFrame fallback — if audit_log not available

    Usage::

        cdl    = CandleDecisionLogger()
        df_log = cdl.build(result, df_processed)
        cdl.save(df_log, Path("reports"))
    """

    NEAR_MISS_THRESHOLD: int = 3

    def build(
        self,
        result:       Dict[str, Any],
        df_processed: pd.DataFrame,
    ) -> pd.DataFrame:
        """Build the candle decision log DataFrame."""
        # Try to get audit entries from result
        audit_entries: List[Dict] = []
        audit_obj = result.get("_audit_log_obj")
        if audit_obj is not None and hasattr(audit_obj, "entries"):
            audit_entries = audit_obj.entries

        df = df_processed.copy()
        dt_map: Dict[str, int] = {}
        if "datetime" in df.columns:
            df["_dt_str"] = df["datetime"].astype(str).str[:19]
            dt_map = {row["_dt_str"]: i for i, row in df.iterrows()}

        if not audit_entries:
            logger.warning(
                "Phase 2: No audit_log in result — building log from df_processed only"
            )
            return self._build_from_df(df)

        rows = []
        for entry in audit_entries:
            dt_str  = str(entry.get("datetime", ""))[:19]
            bar_idx = dt_map.get(dt_str)

            # Pull indicator values from processed df (most accurate)
            ind: Dict[str, Any] = {}
            if bar_idx is not None:
                bar = df.iloc[bar_idx]
                for col, label in _INDICATOR_COLS.items():
                    val = bar.get(col, 0)
                    try:
                        ind[label] = round(float(val), 6) if val is not None and str(val) != "nan" else 0.0
                    except (TypeError, ValueError):
                        ind[label] = str(val)
                ohlcv = {
                    "Open":   round(float(bar.get("open",  0)), 4),
                    "High":   round(float(bar.get("high",  0)), 4),
                    "Low":    round(float(bar.get("low",   0)), 4),
                    "Close":  round(float(bar.get("close", 0)), 4),
                    "Volume": float(bar.get("volume", 0)),
                }
            else:
                ind    = {label: 0.0 for label in _INDICATOR_COLS.values()}
                ohlcv  = {"Open": 0.0, "High": 0.0, "Low": 0.0, "Close": entry.get("price", 0.0), "Volume": 0.0}

            signal    = entry.get("signal",           "NONE")
            rejection = entry.get("rejection",        "")
            buy_score = entry.get("buy_score",         0)
            sell_score= entry.get("sell_score",        0)
            position  = entry.get("position_open",    False)
            daily_tr  = entry.get("trades_today",      0)
            daily_loss= entry.get("daily_loss",        0.0)

            # Build rejection reason if missing
            if not rejection and signal == "NONE":
                max_s = max(buy_score, sell_score)
                if max_s == 0:
                    rejection = "NO_SIGNAL_CONDITIONS"
                else:
                    dir_ = "BUY" if buy_score >= sell_score else "SELL"
                    rejection = f"{dir_}_SCORE_{max_s}_OF_8_BELOW_THRESHOLD_5"

            rows.append({
                "Timestamp":    dt_str,
                **ohlcv,
                **ind,
                "BUY_Score":    buy_score,
                "SELL_Score":   sell_score,
                "Decision":     signal,
                "Rejection":    rejection,
                "Position_Open":position,
                "Trades_Today": daily_tr,
                "Daily_Loss":   round(daily_loss, 2) if isinstance(daily_loss, float) else daily_loss,
                "Bar_Index":    entry.get("bar_idx", bar_idx),
            })

        df_log = pd.DataFrame(rows)
        logger.info("Phase 2: Built candle log with %d rows", len(df_log))
        return df_log

    def _build_from_df(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fallback builder when audit_log is unavailable."""
        rows = []
        for _, bar in df.iterrows():
            ind = {}
            for col, label in _INDICATOR_COLS.items():
                val = bar.get(col, 0)
                try:
                    ind[label] = round(float(val), 6) if val is not None else 0.0
                except (TypeError, ValueError):
                    ind[label] = 0.0
            rows.append({
                "Timestamp": str(bar.get("datetime", ""))[:19],
                "Open":      round(float(bar.get("open",  0)), 4),
                "High":      round(float(bar.get("high",  0)), 4),
                "Low":       round(float(bar.get("low",   0)), 4),
                "Close":     round(float(bar.get("close", 0)), 4),
                "Volume":    float(bar.get("volume", 0)),
                **ind,
                "Decision":  "UNKNOWN",
                "Rejection": "AUDIT_LOG_UNAVAILABLE",
            })
        return pd.DataFrame(rows)

    def rejection_summary(self, df_log: pd.DataFrame) -> pd.DataFrame:
        """Returns a summary of rejection reason counts."""
        if "Rejection" not in df_log.columns:
            return pd.DataFrame()
        none_rows = df_log[df_log["Decision"] == "NONE"]["Rejection"]
        return (
            none_rows.value_counts()
            .reset_index()
            .rename(columns={"index": "Rejection_Reason", "Rejection": "Count"})
        )

    def save(self, df_log: pd.DataFrame, output_dir: Path) -> Dict[str, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_p = output_dir / "phase2_candle_log.csv"
        md_p  = output_dir / "phase2_candle_log.md"
        df_log.to_csv(csv_p, index=False)

        # Rejection summary
        summary = self.rejection_summary(df_log)
        lines = [
            "# Phase 2 — Candle Decision Log",
            "",
            f"**Total candles logged: {len(df_log)}**",
            f"**BUY signals: {(df_log['Decision'] == 'BUY').sum() if 'Decision' in df_log.columns else 'N/A'}**",
            f"**SELL signals: {(df_log['Decision'] == 'SELL').sum() if 'Decision' in df_log.columns else 'N/A'}**",
            "",
            "## Rejection Reason Summary",
            "",
        ]
        if not summary.empty:
            lines.append(summary.head(20).to_markdown(index=False))
        else:
            lines.append("_Audit log unavailable — rejection breakdown not possible._")

        lines += [
            "",
            "## Sample (first 50 rows)",
            "",
            df_log.head(50).to_markdown(index=False),
            "",
            f"> Full data saved to: `{csv_p.name}`",
        ]
        md_p.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Phase 2 saved → %s, %s", csv_p, md_p)
        return {"csv": csv_p, "md": md_p}
