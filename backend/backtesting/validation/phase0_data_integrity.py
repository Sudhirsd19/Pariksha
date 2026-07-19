"""
Phase 0 — Data Integrity Auditor
==================================
Validates the raw OHLCV dataset before any backtest validation begins.
If critical issues are found, downstream phases are halted.

DO NOT import or modify any strategy/engine trading logic.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

NSE_MARKET_OPEN  = time(9, 15)
NSE_MARKET_CLOSE = time(15, 30)

NSE_HOLIDAYS: set = {
    date(2024,  1, 22), date(2024,  3, 25), date(2024,  3, 29),
    date(2024,  4, 14), date(2024,  5,  1), date(2024,  8, 15),
    date(2024, 10,  2), date(2024, 12, 25),
    date(2025,  2, 26), date(2025,  3, 14), date(2025,  4, 14),
    date(2025,  5,  1), date(2025,  8, 15), date(2025, 10,  2),
    date(2025, 12, 25),
    date(2026,  1, 26), date(2026,  3, 19), date(2026,  4,  2),
    date(2026,  4,  3), date(2026,  4, 14), date(2026,  5,  1),
    date(2026,  8, 15), date(2026, 10,  2), date(2026, 12, 25),
}


@dataclass
class IntegrityIssue:
    """Single data integrity finding."""
    severity:    str    # CRITICAL | WARNING | INFO
    category:    str
    description: str
    count:       int  = 0
    sample:      str  = ""


@dataclass
class IntegrityReport:
    """Full Phase 0 integrity report."""
    symbol:         str
    interval_min:   int
    total_rows:     int
    trading_rows:   int
    issues:         List[IntegrityIssue] = field(default_factory=list)
    passed:         bool = True
    critical_count: int  = 0
    warning_count:  int  = 0

    def add(self, issue: IntegrityIssue) -> None:
        self.issues.append(issue)
        if issue.severity == "CRITICAL":
            self.critical_count += 1
            self.passed = False
        elif issue.severity == "WARNING":
            self.warning_count += 1

    def to_markdown(self) -> str:
        status = "✅ PASS" if self.passed else "❌ FAIL"
        lines = [
            "# Phase 0 — Data Integrity Report",
            "",
            "| Field | Value |",
            "|-------|-------|",
            f"| Symbol | {self.symbol} |",
            f"| Interval | {self.interval_min}m |",
            f"| Total rows | {self.total_rows:,} |",
            f"| Trading rows | {self.trading_rows:,} |",
            f"| Critical issues | {self.critical_count} |",
            f"| Warning issues | {self.warning_count} |",
            f"| Overall | {status} |",
            "",
            "## Issues Found",
            "",
            "| Severity | Category | Count | Description |",
            "|----------|----------|-------|-------------|",
        ]
        if not self.issues:
            lines.append("| INFO | NO_ISSUES | 0 | All checks passed — dataset is clean |")
        for iss in self.issues:
            lines.append(
                f"| {iss.severity} | {iss.category} | {iss.count} | {iss.description} |"
            )
        if self.passed:
            lines += ["", "## Certification", "", "> ✅ Dataset passed all critical checks. Proceeding to Phase 1."]
        else:
            lines += ["", "## Certification", "", "> ❌ CRITICAL issues found. Downstream validation halted."]
        return "\n".join(lines)


class DataIntegrityAuditor:
    """
    Runs comprehensive data integrity checks on a raw OHLCV DataFrame.

    Usage::

        auditor = DataIntegrityAuditor(symbol="RELIANCE", interval_minutes=5)
        report  = auditor.audit(df_raw)
        if not report.passed:
            raise RuntimeError("Data integrity failed — aborting validation")
    """

    def __init__(
        self,
        symbol:           str   = "UNKNOWN",
        interval_minutes: int   = 5,
        outlier_sigma:    float = 5.0,
    ) -> None:
        self.symbol        = symbol
        self.interval_min  = interval_minutes
        self.outlier_sigma = outlier_sigma

    def audit(self, df_raw: pd.DataFrame) -> IntegrityReport:
        """Run all integrity checks. Returns an IntegrityReport."""
        if df_raw is None or df_raw.empty:
            raise RuntimeError("Phase 0: Input DataFrame is None or empty")

        df = df_raw.copy()
        df.columns = [c.lower().strip() for c in df.columns]

        report = IntegrityReport(
            symbol=self.symbol,
            interval_min=self.interval_min,
            total_rows=len(df),
            trading_rows=0,
        )

        # 1. Required columns
        required = {"open", "high", "low", "close"}
        missing  = required - set(df.columns)
        if missing:
            report.add(IntegrityIssue(
                severity="CRITICAL", category="MISSING_COLUMNS",
                description=f"Required columns missing: {missing}", count=len(missing),
            ))
            return report

        # 2. Timestamp column
        ts_col = next((c for c in ["datetime", "date", "time", "timestamp"]
                       if c in df.columns), None)
        if ts_col is None:
            report.add(IntegrityIssue(
                severity="CRITICAL", category="NO_TIMESTAMP",
                description="No timestamp column (expected: datetime/date/timestamp)", count=1,
            ))
            return report
        if ts_col != "datetime":
            df = df.rename(columns={ts_col: "datetime"})

        # 3. Parse and tz-normalise
        try:
            df["datetime"] = pd.to_datetime(df["datetime"], utc=True, errors="coerce")
            df["datetime"] = df["datetime"].dt.tz_convert("Asia/Kolkata")
        except Exception as exc:
            report.add(IntegrityIssue(
                severity="CRITICAL", category="TIMESTAMP_PARSE_FAILED",
                description=f"Timestamp parse error: {exc}", count=1,
            ))
            return report

        nat_count = df["datetime"].isna().sum()
        if nat_count > 0:
            report.add(IntegrityIssue(
                severity="WARNING", category="NAT_TIMESTAMPS",
                description=f"{nat_count} NaT timestamps after parsing", count=int(nat_count),
            ))
            df = df.dropna(subset=["datetime"])

        # 4. Sorted
        if not df["datetime"].is_monotonic_increasing:
            unsorted = (~df["datetime"].diff().dt.total_seconds().gt(0)).sum()
            report.add(IntegrityIssue(
                severity="WARNING", category="UNSORTED_TIMESTAMPS",
                description=f"{unsorted} rows out of chronological order (auto-sorted)",
                count=int(unsorted),
            ))
            df = df.sort_values("datetime").reset_index(drop=True)

        # 5. Duplicates
        dupes = df.duplicated(subset=["datetime"]).sum()
        if dupes > 0:
            sample = df[df.duplicated(subset=["datetime"], keep=False)]["datetime"].head(3).astype(str).tolist()
            report.add(IntegrityIssue(
                severity="WARNING", category="DUPLICATE_TIMESTAMPS",
                description=f"{dupes} duplicate timestamps (keeping last)",
                count=int(dupes), sample=", ".join(sample),
            ))
            df = df.drop_duplicates(subset=["datetime"], keep="last")

        # 6. Weekend bars
        weekend = (df["datetime"].dt.weekday >= 5).sum()
        if weekend > 0:
            report.add(IntegrityIssue(
                severity="WARNING", category="WEEKEND_BARS",
                description=f"{weekend} bars on Saturday/Sunday", count=int(weekend),
            ))

        # 7. NSE holiday bars
        holiday_mask = df["datetime"].dt.date.isin(NSE_HOLIDAYS)
        holidays_found = holiday_mask.sum()
        if holidays_found > 0:
            report.add(IntegrityIssue(
                severity="WARNING", category="NSE_HOLIDAY_BARS",
                description=f"{holidays_found} bars on known NSE holidays", count=int(holidays_found),
            ))

        # Trading rows (weekdays, non-holidays)
        trading_df = df[
            (df["datetime"].dt.weekday < 5) &
            (~df["datetime"].dt.date.isin(NSE_HOLIDAYS))
        ].copy()
        report.trading_rows = len(trading_df)

        # 8. IST session timing
        if len(trading_df) > 0:
            bar_times = trading_df["datetime"].dt.time
            pre_mkt  = (bar_times < NSE_MARKET_OPEN).sum()
            post_mkt = (bar_times > NSE_MARKET_CLOSE).sum()
            if pre_mkt > 0:
                report.add(IntegrityIssue(
                    severity="WARNING", category="PRE_MARKET_BARS",
                    description=f"{pre_mkt} bars before NSE open (09:15 IST)", count=int(pre_mkt),
                ))
            if post_mkt > 0:
                report.add(IntegrityIssue(
                    severity="WARNING", category="POST_MARKET_BARS",
                    description=f"{post_mkt} bars after NSE close (15:30 IST)", count=int(post_mkt),
                ))

        # 9. OHLC validity
        checks = [
            (df["high"] < df["low"],    "HIGH_LT_LOW"),
            (df["close"] > df["high"],  "CLOSE_GT_HIGH"),
            (df["close"] < df["low"],   "CLOSE_LT_LOW"),
            (df["open"]  > df["high"],  "OPEN_GT_HIGH"),
            (df["open"]  < df["low"],   "OPEN_LT_LOW"),
        ]
        for mask, label in checks:
            cnt = int(mask.sum())
            if cnt > 0:
                report.add(IntegrityIssue(
                    severity="WARNING", category=f"OHLC_{label}",
                    description=f"{cnt} rows violate OHLC constraint ({label})", count=cnt,
                ))

        # 10. Negative / zero prices
        for col in ["open", "high", "low", "close"]:
            neg = int((df[col] <= 0).sum())
            if neg > 0:
                sev = "CRITICAL" if neg > 10 else "WARNING"
                report.add(IntegrityIssue(
                    severity=sev, category=f"NON_POSITIVE_{col.upper()}",
                    description=f"{neg} rows with non-positive {col}", count=neg,
                ))

        # 11. NaN / Inf values
        for col in ["open", "high", "low", "close"]:
            nan_c = int(df[col].isna().sum())
            inf_c = int(np.isinf(df[col].fillna(0)).sum())
            if nan_c > 0:
                report.add(IntegrityIssue(
                    severity="CRITICAL", category=f"NAN_{col.upper()}",
                    description=f"{nan_c} NaN values in {col}", count=nan_c,
                ))
            if inf_c > 0:
                report.add(IntegrityIssue(
                    severity="CRITICAL", category=f"INF_{col.upper()}",
                    description=f"{inf_c} Inf values in {col}", count=inf_c,
                ))

        # 12. Volume checks
        if "volume" in df.columns:
            neg_vol  = int((df["volume"] < 0).sum())
            zero_vol = int((df["volume"] == 0).sum())
            nan_vol  = int(df["volume"].isna().sum())
            if neg_vol > 0:
                report.add(IntegrityIssue(severity="WARNING", category="NEGATIVE_VOLUME",
                    description=f"{neg_vol} rows with negative volume", count=neg_vol))
            if zero_vol > 0.2 * len(df):
                pct = 100 * zero_vol / max(len(df), 1)
                report.add(IntegrityIssue(severity="WARNING", category="EXCESSIVE_ZERO_VOLUME",
                    description=f"{zero_vol}/{len(df)} ({pct:.1f}%) rows have zero volume", count=zero_vol))
            if nan_vol > 0:
                report.add(IntegrityIssue(severity="WARNING", category="NAN_VOLUME",
                    description=f"{nan_vol} NaN volume values", count=nan_vol))
        else:
            report.add(IntegrityIssue(severity="WARNING", category="MISSING_VOLUME",
                description="No 'volume' column — slippage model degraded", count=1))

        # 13. Intraday gaps
        if len(trading_df) > 1:
            expected_delta = timedelta(minutes=self.interval_min)
            diffs = trading_df["datetime"].diff().dropna()
            same_day_gaps = diffs[
                (diffs > expected_delta * 2) & (diffs < timedelta(hours=17))
            ]
            if not same_day_gaps.empty:
                report.add(IntegrityIssue(
                    severity="WARNING", category="INTRADAY_GAPS",
                    description=f"{len(same_day_gaps)} intraday gaps (max={same_day_gaps.max()})",
                    count=len(same_day_gaps),
                    sample=str(same_day_gaps.head(3).tolist()),
                ))

        # 14. Outlier candles (price spikes)
        for col in ["open", "high", "low", "close"]:
            series = df[col].dropna()
            if len(series) > 30:
                z = (series - series.mean()) / (series.std() + 1e-9)
                outliers = int((z.abs() > self.outlier_sigma).sum())
                if outliers > 0:
                    report.add(IntegrityIssue(
                        severity="WARNING", category=f"PRICE_OUTLIER_{col.upper()}",
                        description=f"{outliers} {col} values >{self.outlier_sigma}σ (possible bad ticks)",
                        count=outliers,
                    ))

        # 15. Timezone consistency
        tz_name = str(df["datetime"].dt.tz) if hasattr(df["datetime"].dt, "tz") else "unknown"
        if "Kolkata" not in tz_name and "IST" not in tz_name:
            report.add(IntegrityIssue(
                severity="WARNING", category="TIMEZONE_MISMATCH",
                description=f"Timestamps not in IST/Kolkata — found tz={tz_name}", count=1,
            ))

        # 16. Indicator NaN check (if indicators already attached)
        ind_cols = [c for c in df.columns if c.startswith(
            ("ema_", "rsi_", "macd", "adx", "vwap", "atr_", "supertrend")
        )]
        for col in ind_cols:
            nan_cnt = int(df[col].isna().sum())
            if nan_cnt > 0:
                report.add(IntegrityIssue(
                    severity="INFO", category=f"INDICATOR_NAN_{col.upper()}",
                    description=f"{nan_cnt} NaN in '{col}' (warmup period expected)",
                    count=nan_cnt,
                ))

        logger.info(
            "Phase 0 complete — %s: %d critical, %d warnings | PASSED=%s",
            self.symbol, report.critical_count, report.warning_count, report.passed,
        )
        return report

    def save_report(self, report: IntegrityReport, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / "phase0_data_integrity.md"
        out_path.write_text(report.to_markdown(), encoding="utf-8")
        logger.info("Phase 0 report saved → %s", out_path)
        return out_path
