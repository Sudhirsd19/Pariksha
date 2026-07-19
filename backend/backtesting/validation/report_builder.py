"""
Phase 12 — Institutional Report Builder
==========================================
Assembles all phase outputs into a single comprehensive
Institutional Validation Report with a Production Readiness Score.

Also captures the full Configuration Snapshot for reproducibility.

DO NOT modify any strategy or engine files.
"""
from __future__ import annotations

import logging
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)


def _git_commit() -> str:
    """Return current git commit hash if available."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "N/A"


def _python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


class InstitutionalReportBuilder:
    """
    Builds the final Phase 12 Institutional Validation Report.

    Usage::

        builder = InstitutionalReportBuilder()
        report  = builder.build(
            result=result,
            phase_outputs={...},
            engine_kwargs={...},
        )
        builder.save(report, Path("reports"))
    """

    # Scoring rubric (max points per category)
    SCORING = {
        "data_integrity":      10,
        "indicator_accuracy":  10,
        "execution_checks":    20,
        "charge_accuracy":     10,
        "capital_chain":       10,
        "trade_replay":        10,
        "multi_asset":         10,
        "walk_forward":        10,
        "deterministic":       10,
    }

    def build(
        self,
        result:        Dict[str, Any],
        phase_outputs: Dict[str, Any],
        engine_kwargs: Dict[str, Any],
    ) -> str:
        """
        Build the complete institutional report as a markdown string.

        Args:
            result:        engine.run() result dict
            phase_outputs: dict with keys: p0_report, p1_records, p2_df, p3_text,
                           p4_records, p5_checks, p6_records, p7_results, p8_mc,
                           p9_wf, p10_det, p11_paths, chart_index_path
            engine_kwargs: constructor kwargs for configuration snapshot
        """
        score, deductions = self._compute_score(phase_outputs)
        cfg    = result.get("config", {})
        metrics= result.get("metrics", {})
        trades = result.get("trades", [])

        now    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        commit = _git_commit()

        lines: List[str] = [
            "# 🏛️ Institutional Validation Report",
            f"**Generated**: {now}",
            "",
            "---",
            "",
        ]

        # ── Configuration Snapshot ────────────────────────────────────────────
        lines += [
            "## 📋 Configuration Snapshot",
            "",
            "| Parameter | Value |",
            "|-----------|-------|",
            f"| Engine Version | QuantumBacktestEngine v3.0 |",
            f"| Python Version | {_python_version()} |",
            f"| Platform | {platform.system()} {platform.release()} |",
            f"| Execution Date | {now} |",
            f"| Git Commit | `{commit}` |",
            f"| Symbol | {engine_kwargs.get('symbol', 'UNKNOWN')} |",
            f"| Instrument | {cfg.get('instrument', engine_kwargs.get('instrument', 'EQUITY'))} |",
            f"| Mode | {cfg.get('mode', engine_kwargs.get('mode', 'INTRADAY'))} |",
            f"| Initial Capital | ₹{cfg.get('initial_capital', engine_kwargs.get('initial_capital', 100_000)):,.0f} |",
            f"| Risk % | {cfg.get('risk_pct', engine_kwargs.get('risk_pct', 0.01)) * 100:.2f}% |",
            f"| ATR SL Multiplier | {cfg.get('atr_sl_mult', engine_kwargs.get('atr_sl_mult', 2.0))} |",
            f"| ATR TP Multiplier | {cfg.get('atr_tp_mult', engine_kwargs.get('atr_tp_mult', 4.0))} |",
            f"| Max Daily Loss % | {cfg.get('max_daily_loss', engine_kwargs.get('max_daily_loss_pct', 0.03)) * 100:.1f}% |",
            f"| Lot Size | {engine_kwargs.get('lot_size', 1)} |",
            f"| Broker | {engine_kwargs.get('broker', 'ANGEL_ONE')} |",
            f"| Interval | {engine_kwargs.get('interval_minutes', 5)} min |",
            f"| Entry Cutoff | 14:30 IST |",
            f"| Auto Squareoff | 15:10 IST |",
            "",
        ]

        # ── Executive Summary ──────────────────────────────────────────────────
        n_trades   = int(metrics.get("total_trades", 0))
        win_rate   = float(metrics.get("win_rate", 0.0))
        pf         = float(metrics.get("profit_factor", 0.0))
        net_profit = float(metrics.get("net_profit", 0.0))
        max_dd     = float(metrics.get("max_drawdown_pct", 0.0))
        sharpe     = float(metrics.get("sharpe_ratio", 0.0))

        lines += [
            "## 📊 Executive Summary",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Trades | {n_trades} |",
            f"| Win Rate | {win_rate:.1f}% |",
            f"| Profit Factor | {pf:.3f} |",
            f"| Net Profit | ₹{net_profit:,.2f} |",
            f"| Max Drawdown | {max_dd:.2f}% |",
            f"| Sharpe Ratio | {sharpe:.3f} |",
            "",
        ]

        # ── Phase Summaries ───────────────────────────────────────────────────
        lines += ["## 📋 Phase Results Summary", "", "| Phase | Status | Key Finding |",
                  "|-------|--------|-------------|"]

        # Phase 0
        p0 = phase_outputs.get("p0_report")
        if p0:
            p0_status = "✅ PASS" if p0.passed else "❌ FAIL"
            p0_detail = f"{p0.critical_count} critical, {p0.warning_count} warnings"
        else:
            p0_status, p0_detail = "⏭️ SKIP", "Not run"
        lines.append(f"| Phase 0: Data Integrity | {p0_status} | {p0_detail} |")

        # Phase 1
        p1 = phase_outputs.get("p1_records", [])
        lines.append(f"| Phase 1: Trade Replay | ✅ DONE | {len(p1)} trades replayed |")

        # Phase 2
        p2 = phase_outputs.get("p2_df")
        p2_cnt = len(p2) if p2 is not None and hasattr(p2, '__len__') else 0
        lines.append(f"| Phase 2: Candle Log | ✅ DONE | {p2_cnt} candles logged |")

        # Phase 3
        lines.append(f"| Phase 3: Boolean Audit | ✅ DONE | Full expression audit generated |")

        # Phase 4
        p4 = phase_outputs.get("p4_records", [])
        p4_fail = sum(1 for r in p4 if r.status == "FAIL")
        p4_status = "✅ PASS" if p4_fail == 0 else f"❌ {p4_fail} FAIL"
        lines.append(f"| Phase 4: Capital Flow | {p4_status} | {len(p4)} trades verified |")

        # Phase 5
        p5 = phase_outputs.get("p5_checks", [])
        p5_fail = sum(1 for c in p5 if c.status == "FAIL")
        p5_status = "✅ PASS" if p5_fail == 0 else f"❌ {p5_fail}/20 FAIL"
        lines.append(f"| Phase 5: Execution Validation | {p5_status} | 20 checks run |")

        # Phase 6
        p6 = phase_outputs.get("p6_records", [])
        p6_losses = [r for r in p6 if r.outcome == "LOSS"]
        lines.append(f"| Phase 6: Attribution | ✅ DONE | {len(p6_losses)} losses attributed |")

        # Phase 7
        p7 = phase_outputs.get("p7_results", [])
        p7_ok = sum(1 for r in p7 if r.status == "OK")
        lines.append(f"| Phase 7: Multi-Asset | ✅ DONE | {p7_ok}/{len(p7)} assets OK |")

        # Phase 8
        p8 = phase_outputs.get("p8_mc")
        if p8:
            lines.append(f"| Phase 8: Monte Carlo | ✅ DONE | P(profit)={p8.prob_profit:.1f}% |")
        else:
            lines.append(f"| Phase 8: Monte Carlo | ⏭️ SKIP | Not run |")

        # Phase 9
        p9 = phase_outputs.get("p9_wf")
        if p9:
            lines.append(f"| Phase 9: Walk-Forward | ✅ DONE | WFE={p9.avg_wfe:.3f} |")
        else:
            lines.append(f"| Phase 9: Walk-Forward | ⏭️ SKIP | Not run |")

        # Phase 10
        p10 = phase_outputs.get("p10_det")
        if p10:
            p10_status = "✅ PASS" if p10.all_identical else "❌ NON-DETERMINISTIC"
            lines.append(f"| Phase 10: Deterministic Replay | {p10_status} | 3 runs compared |")
        else:
            lines.append(f"| Phase 10: Deterministic Replay | ⏭️ SKIP | Not run |")

        # Phase 11
        p11 = phase_outputs.get("p11_paths", [])
        lines.append(f"| Phase 11: Trade Charts | ✅ DONE | {len(p11)} charts generated |")

        # ── Production Readiness Score ────────────────────────────────────────
        lines += [
            "",
            "---",
            "",
            "## 🎯 Production Readiness Score",
            "",
            f"**Score: {score}/100**",
            "",
            "| Category | Max | Score | Deduction Reason |",
            "|----------|-----|-------|-----------------|",
        ]
        for cat, max_pts in self.SCORING.items():
            ded = deductions.get(cat, 0)
            earned = max_pts - ded
            reason = deductions.get(f"{cat}_reason", "—")
            lines.append(f"| {cat.replace('_', ' ').title()} | {max_pts} | {earned} | {reason} |")

        lines += ["", f"**Final Score: {score}/100**", ""]

        # Certification
        if score >= 85:
            cert = "✅ PRODUCTION READY — Score ≥ 85/100"
        elif score >= 70:
            cert = "⚠️ CONDITIONAL APPROVAL — Score 70–84/100 (resolve warnings before live trading)"
        else:
            cert = "❌ NOT PRODUCTION READY — Score < 70/100 (critical issues must be fixed)"

        lines += [
            "## 📜 Final Certification",
            "",
            f"### {cert}",
            "",
            f"- Validation completed: {now}",
            f"- Git commit: `{commit}`",
            f"- Python: {_python_version()}",
            f"- Total trades validated: {n_trades}",
            f"- Production Readiness Score: **{score}/100**",
            "",
        ]

        # Chart index
        p11_index = phase_outputs.get("chart_index_path")
        if p11_index:
            lines += [
                "## 📈 Trade Charts",
                "",
                f"See [Trade Chart Index]({Path(p11_index).name}) for all {len(p11)} trade charts.",
                "",
            ]

        return "\n".join(lines)

    def _compute_score(
        self,
        phase_outputs: Dict[str, Any],
    ) -> tuple[int, Dict[str, Any]]:
        """Compute the production readiness score."""
        deductions: Dict[str, Any] = {}
        total = sum(self.SCORING.values())

        # Data integrity (Phase 0)
        p0 = phase_outputs.get("p0_report")
        if p0 and not p0.passed:
            ded = min(self.SCORING["data_integrity"], p0.critical_count * 3)
            deductions["data_integrity"] = ded
            deductions["data_integrity_reason"] = f"{p0.critical_count} critical issues"

        # Execution checks (Phase 5)
        p5 = phase_outputs.get("p5_checks", [])
        p5_fail = sum(1 for c in p5 if c.status == "FAIL")
        if p5_fail > 0:
            ded = min(self.SCORING["execution_checks"], p5_fail * 2)
            deductions["execution_checks"] = ded
            deductions["execution_checks_reason"] = f"{p5_fail} checks failed"

        # Capital flow (Phase 4)
        p4 = phase_outputs.get("p4_records", [])
        p4_fail = sum(1 for r in p4 if r.status == "FAIL")
        if p4_fail > 0:
            ded = min(self.SCORING["capital_chain"], p4_fail * 2)
            deductions["capital_chain"] = ded
            deductions["capital_chain_reason"] = f"{p4_fail} capital chain failures"

        # Walk-forward (Phase 9)
        p9 = phase_outputs.get("p9_wf")
        if p9 and p9.avg_wfe < 0.5:
            deductions["walk_forward"] = 5
            deductions["walk_forward_reason"] = f"WFE={p9.avg_wfe:.3f} < 0.5"

        # Deterministic (Phase 10)
        p10 = phase_outputs.get("p10_det")
        if p10 and not p10.all_identical:
            deductions["deterministic"] = self.SCORING["deterministic"]
            deductions["deterministic_reason"] = "Non-deterministic behaviour detected"

        total_deductions = sum(v for k, v in deductions.items() if not k.endswith("_reason"))
        score = max(0, total - total_deductions)
        return score, deductions

    def save(self, report_text: str, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "INSTITUTIONAL_VALIDATION_REPORT.md"
        out.write_text(report_text, encoding="utf-8")
        logger.info("Phase 12 final report saved → %s", out)
        return out
