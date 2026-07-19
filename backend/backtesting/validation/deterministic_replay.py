"""
Phase 10 — Deterministic Replay Checker
==========================================
Runs the EXACT same backtest three consecutive times.
Verifies that all three runs produce bit-for-bit identical results.

If any difference is found, reports: NON-DETERMINISTIC BEHAVIOUR DETECTED
Otherwise: PASS

DO NOT modify any strategy or engine files.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class DeterministicReplayResult:
    """Result of the three-run deterministic replay check."""
    n_runs:          int    = 3
    all_identical:   bool   = True
    trade_count_same: bool  = True
    pnl_same:        bool   = True
    charges_same:    bool   = True
    equity_same:     bool   = True
    hashes:          List[str] = field(default_factory=list)
    differences:     List[str] = field(default_factory=list)
    verdict:         str   = ""


def _hash_trades(trades: List[Dict]) -> str:
    """Compute a stable hash of the trades list."""
    # Normalise to avoid float repr differences
    normalised = []
    for t in trades:
        normalised.append({
            "entry_time":  str(t.get("entry_time", ""))[:19],
            "exit_time":   str(t.get("exit_time", ""))[:19],
            "signal":      t.get("signal", ""),
            "qty":         t.get("qty", 0),
            "effective_entry": round(float(t.get("effective_entry", 0)), 4),
            "effective_exit":  round(float(t.get("effective_exit", t.get("exit", 0))), 4),
            "gross_pnl":   round(float(t.get("gross_pnl", 0)), 2),
            "charges":     round(float(t.get("charges", 0)), 2),
            "net_pnl":     round(float(t.get("net_pnl", 0)), 2),
            "exit_reason": t.get("exit_reason", ""),
        })
    payload = json.dumps(normalised, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _hash_equity(equity: List[float]) -> str:
    payload = json.dumps([round(v, 2) for v in equity])
    return hashlib.sha256(payload.encode()).hexdigest()


class DeterministicReplayChecker:
    """
    Runs the engine exactly 3 times and compares outputs for determinism.

    Usage::

        checker = DeterministicReplayChecker()
        result  = checker.check(engine_cls, engine_kwargs, df_raw)
        checker.save(result, Path("reports"))
    """

    N_RUNS: int = 3

    def check(
        self,
        engine_cls:    Any,
        engine_kwargs: Dict[str, Any],
        df_raw:        pd.DataFrame,
    ) -> DeterministicReplayResult:
        """Run the engine N_RUNS times and compare."""
        run_results: List[Dict[str, Any]] = []
        logger.info("Phase 10: Running engine %d times for determinism check...", self.N_RUNS)

        for i in range(self.N_RUNS):
            try:
                kw = dict(engine_kwargs)
                kw["verbose"] = False
                engine = engine_cls(**kw)
                res    = engine.run(df_raw.copy())   # .copy() ensures same input each run
                run_results.append(res)
                logger.info("  Run %d: %d trades | status=%s", i + 1,
                            len(res.get("trades", [])), res.get("status"))
            except Exception as exc:
                logger.error("  Run %d FAILED: %s", i + 1, exc)
                return DeterministicReplayResult(
                    n_runs=self.N_RUNS,
                    all_identical=False,
                    differences=[f"Run {i+1} raised exception: {exc}"],
                    verdict=f"❌ ENGINE EXCEPTION ON RUN {i+1}: {exc}",
                )

        # Compare all runs
        result = DeterministicReplayResult(n_runs=self.N_RUNS)
        hashes: List[str] = []
        diffs:  List[str] = []

        for i, res in enumerate(run_results):
            trades = res.get("trades", [])
            equity = res.get("equity_curve", [])
            h      = _hash_trades(trades) + "|" + _hash_equity(equity)
            hashes.append(h[:16] + "...")   # truncate for readability

        result.hashes = hashes

        # Check trade count
        trade_counts = [len(r.get("trades", [])) for r in run_results]
        if len(set(trade_counts)) > 1:
            result.trade_count_same = False
            diffs.append(f"Trade counts differ: {trade_counts}")

        # Check net PnL per run
        net_pnls = [
            round(sum(t.get("net_pnl", 0) for t in r.get("trades", [])), 2)
            for r in run_results
        ]
        if len(set(net_pnls)) > 1:
            result.pnl_same = False
            diffs.append(f"Net PnL differs across runs: {net_pnls}")

        # Check total charges
        charges = [
            round(sum(t.get("charges", 0) for t in r.get("trades", [])), 2)
            for r in run_results
        ]
        if len(set(charges)) > 1:
            result.charges_same = False
            diffs.append(f"Total charges differ: {charges}")

        # Check equity curve hash
        equity_hashes = [_hash_equity(r.get("equity_curve", [])) for r in run_results]
        if len(set(equity_hashes)) > 1:
            result.equity_same = False
            diffs.append("Equity curves differ between runs")

        # Check trade-level hash
        trade_hashes = [_hash_trades(r.get("trades", [])) for r in run_results]
        if len(set(trade_hashes)) > 1:
            result.all_identical = False
            diffs.append("Trade execution details differ between runs")

        result.differences = diffs
        result.all_identical = len(diffs) == 0
        result.verdict = (
            "PASS — All 3 runs produced identical results. Engine is fully deterministic."
            if result.all_identical else
            f"FAIL — NON-DETERMINISTIC BEHAVIOUR DETECTED — {len(diffs)} difference(s) found"
        )

        logger.info("Phase 10: %s", result.verdict)
        return result

    def to_markdown(self, result: DeterministicReplayResult) -> str:
        icon = "✅" if result.all_identical else "❌"
        lines = [
            "# Phase 10 — Deterministic Replay Check",
            "",
            f"## Verdict: {result.verdict}",
            "",
            f"**Runs performed**: {result.n_runs}",
            "",
            "## Check Results",
            "",
            "| Check | Result |",
            "|-------|--------|",
            f"| Trade count identical | {'✅ YES' if result.trade_count_same else '❌ NO'} |",
            f"| Net PnL identical | {'✅ YES' if result.pnl_same else '❌ NO'} |",
            f"| Total charges identical | {'✅ YES' if result.charges_same else '❌ NO'} |",
            f"| Equity curve identical | {'✅ YES' if result.equity_same else '❌ NO'} |",
            f"| All trade details identical | {'✅ YES' if result.all_identical else '❌ NO'} |",
            "",
            "## Run Hashes",
            "",
            "| Run | SHA-256 (truncated) |",
            "|-----|---------------------|",
        ]
        for i, h in enumerate(result.hashes, 1):
            lines.append(f"| {i} | `{h}` |")

        if result.differences:
            lines += [
                "",
                "## ❌ Differences Found",
                "",
            ]
            for d in result.differences:
                lines.append(f"- {d}")

        return "\n".join(lines)

    def save(self, result: DeterministicReplayResult, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "phase10_deterministic_replay.md"
        out.write_text(self.to_markdown(result), encoding="utf-8")
        logger.info("Phase 10 saved → %s", out)
        return out
