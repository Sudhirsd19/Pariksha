"""
Master Validation Runner
========================
Runs all 12 phases of the Institutional Validation Framework
in sequence. Each phase is independent and self-contained.

Usage (from project root):

    python -m backend.backtesting.validation.run_validation \
        --symbol RELIANCE \
        --capital 100000 \
        --days 60

Or import programmatically:

    from backend.backtesting.validation.run_validation import run_all_phases
    run_all_phases(engine_cls, engine_kwargs, df_raw, output_dir)

DO NOT modify any strategy or engine files.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("validation.runner")

# ── Default output directory ──────────────────────────────────────────────────
DEFAULT_REPORTS_DIR = Path(__file__).parent / "reports"


def _print_phase_header(n: int, name: str) -> None:
    print(f"\n{'='*70}")
    print(f"  Phase {n}: {name}")
    print(f"{'='*70}")


def _print_phase_result(status: str, detail: str = "") -> None:
    icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "DONE": "[DONE]", "SKIP": "[SKIP]", "ERROR": "[ERROR]"}.get(status, "[INFO]")
    print(f"  {icon} {status}" + (f" - {detail}" if detail else ""))


def run_all_phases(
    engine_cls:    Any,
    engine_kwargs: Dict[str, Any],
    df_raw,                          # pd.DataFrame
    output_dir:    Path = DEFAULT_REPORTS_DIR,
    run_multi_asset:      bool = True,
    run_walk_forward:     bool = True,
    run_deterministic:    bool = True,
    run_charts:           bool = True,
    multi_asset_days:     int  = 60,
    skip_on_data_failure: bool = True,
) -> Dict[str, Any]:
    """
    Run all 12 validation phases.

    Args:
        engine_cls:           QuantumBacktestEngine class
        engine_kwargs:        Constructor kwargs dict
        df_raw:               Raw OHLCV DataFrame (unprocessed)
        output_dir:           Directory for all report output
        run_multi_asset:      Whether to run Phase 7 (downloads extra data)
        run_walk_forward:     Whether to run Phase 9
        run_deterministic:    Whether to run Phase 10 (runs engine 3 times)
        run_charts:           Whether to run Phase 11 (matplotlib required)
        multi_asset_days:     Lookback days for Phase 7
        skip_on_data_failure: Stop if Phase 0 critical issues found

    Returns:
        Dict with all phase outputs and paths
    """
    import pandas as pd

    output_dir.mkdir(parents=True, exist_ok=True)
    charts_dir = output_dir / "charts"
    charts_dir.mkdir(exist_ok=True)

    phase_outputs: Dict[str, Any] = {}
    saved_paths:   Dict[str, Any] = {}
    t_start = time.perf_counter()

    print("\n" + "=" * 70)
    print("  QUANTUM INDEX - INSTITUTIONAL VALIDATION FRAMEWORK")
    print("  12-Phase Audit | Strategy Logic: UNTOUCHED")
    print("=" * 70)

    # ── PHASE 0: Data Integrity ───────────────────────────────────────────────
    _print_phase_header(0, "Data Integrity Audit")
    from .phase0_data_integrity import DataIntegrityAuditor
    symbol = engine_kwargs.get("symbol", "UNKNOWN")
    interval_min = engine_kwargs.get("interval_minutes", 5)
    p0_auditor = DataIntegrityAuditor(symbol=symbol, interval_minutes=interval_min)
    try:
        p0_report = p0_auditor.audit(df_raw)
        phase_outputs["p0_report"] = p0_report
        p0_path = p0_auditor.save_report(p0_report, output_dir)
        saved_paths["phase0"] = str(p0_path)
        status = "PASS" if p0_report.passed else "FAIL"
        _print_phase_result(
            status,
            f"{p0_report.critical_count} critical, {p0_report.warning_count} warnings | "
            f"{p0_report.total_rows:,} rows, {p0_report.trading_rows:,} trading rows"
        )
        if not p0_report.passed and skip_on_data_failure:
            print("\n  [HALT] Critical data issues - validation halted.")
            print(f"  Review: {p0_path}")
            return {"status": "HALTED", "reason": "Phase 0 critical failure", **phase_outputs}
    except Exception as exc:
        _print_phase_result("ERROR", str(exc))
        logger.exception("Phase 0 failed")

    print(f"\n{'-'*70}")
    print("  Running primary backtest...")
    print(f"{'-'*70}")
    try:
        kw = dict(engine_kwargs)
        kw["verbose"] = False
        engine = engine_cls(**kw)
        result = engine.run(df_raw.copy())

        # Attach audit log for Phase 2 / Phase 3
        if hasattr(engine, "audit_log"):
            result["_audit_log_obj"] = engine.audit_log

        # Get processed df from engine internals if possible
        df_processed = getattr(engine, "_last_processed_df", None)
        if df_processed is None:
            # Re-process: validate + compute indicators (mirror engine's Step 1 & 2)
            from ..quantum_backtest_engine import DataValidator, Indicators
            validator = DataValidator(interval_min)
            df_processed, _ = validator.validate(df_raw.copy())
            df_processed = Indicators.apply_all(df_processed)

        n_trades = len(result.get("trades", []))
        m = result.get("metrics", {})
        print(f"  [DONE] Backtest complete: {n_trades} trades | "
              f"Win={m.get('win_rate', 0):.1f}% | PF={m.get('profit_factor', 0):.3f} | "
              f"Net=Rs {m.get('net_profit', 0):,.2f}")
    except Exception as exc:
        logger.exception("Primary backtest failed")
        print(f"  [ERROR] Primary backtest failed: {exc}")
        return {"status": "ERROR", "reason": str(exc)}

    initial_capital = float(engine_kwargs.get("initial_capital", 100_000.0))

    # ── PHASE 1: Trade Replay ─────────────────────────────────────────────────
    _print_phase_header(1, "Trade Replay")
    from .replay_engine import TradeReplayEngine
    try:
        replayer = TradeReplayEngine(
            symbol=symbol,
            interval_minutes=interval_min,
            initial_capital=initial_capital,
        )
        p1_records = replayer.replay(result, df_processed)
        phase_outputs["p1_records"] = p1_records
        p1_paths = replayer.save(p1_records, output_dir)
        saved_paths["phase1"] = {k: str(v) for k, v in p1_paths.items()}
        _print_phase_result("DONE", f"{len(p1_records)} trades replayed")
    except Exception as exc:
        logger.exception("Phase 1 failed")
        _print_phase_result("ERROR", str(exc))
        p1_records = []

    # ── PHASE 2: Candle Decision Log ──────────────────────────────────────────
    _print_phase_header(2, "Candle Decision Log")
    from .candle_log import CandleDecisionLogger
    try:
        cdl = CandleDecisionLogger()
        p2_df = cdl.build(result, df_processed)
        phase_outputs["p2_df"] = p2_df
        p2_paths = cdl.save(p2_df, output_dir)
        saved_paths["phase2"] = {k: str(v) for k, v in p2_paths.items()}
        _print_phase_result("DONE", f"{len(p2_df)} candles logged")
    except Exception as exc:
        logger.exception("Phase 2 failed")
        _print_phase_result("ERROR", str(exc))

    # ── PHASE 3: Boolean Expression Audit ────────────────────────────────────
    _print_phase_header(3, "Boolean Expression Audit")
    from .boolean_auditor import BooleanExpressionAuditor
    try:
        p3_auditor = BooleanExpressionAuditor()
        p3_text = p3_auditor.audit(result, df_processed)
        phase_outputs["p3_text"] = p3_text
        p3_path = p3_auditor.save(p3_text, output_dir)
        saved_paths["phase3"] = str(p3_path)
        _print_phase_result("DONE", "Boolean expressions logged")
    except Exception as exc:
        logger.exception("Phase 3 failed")
        _print_phase_result("ERROR", str(exc))

    # ── PHASE 4: Capital Flow Audit ───────────────────────────────────────────
    _print_phase_header(4, "Capital Flow Audit")
    from .capital_flow import CapitalFlowAuditor
    try:
        p4_auditor = CapitalFlowAuditor(initial_capital=initial_capital)
        p4_records = p4_auditor.verify(result)
        phase_outputs["p4_records"] = p4_records
        p4_paths = p4_auditor.save(p4_records, output_dir)
        saved_paths["phase4"] = {k: str(v) for k, v in p4_paths.items()}
        p4_fail = sum(1 for r in p4_records if r.status == "FAIL")
        _print_phase_result(
            "PASS" if p4_fail == 0 else "FAIL",
            f"{len(p4_records)} trades verified, {p4_fail} failures"
        )
    except Exception as exc:
        logger.exception("Phase 4 failed")
        _print_phase_result("ERROR", str(exc))
        p4_records = []

    # ── PHASE 5: Execution Validation ────────────────────────────────────────
    _print_phase_header(5, "Execution Validation (20 checks)")
    from .execution_validator import ExecutionValidator
    try:
        p5_validator = ExecutionValidator()
        p5_checks = p5_validator.validate(result, df_processed)
        phase_outputs["p5_checks"] = p5_checks
        p5_path = p5_validator.save(p5_checks, output_dir)
        saved_paths["phase5"] = str(p5_path)
        p5_pass = sum(1 for c in p5_checks if c.status == "PASS")
        p5_fail = sum(1 for c in p5_checks if c.status == "FAIL")
        _print_phase_result(
            "PASS" if p5_fail == 0 else "FAIL",
            f"{p5_pass}/20 PASS, {p5_fail} FAIL"
        )
    except Exception as exc:
        logger.exception("Phase 5 failed")
        _print_phase_result("ERROR", str(exc))
        p5_checks = []

    # ── PHASE 6: Performance Attribution ─────────────────────────────────────
    _print_phase_header(6, "Performance Attribution")
    from .attribution import PerformanceAttributor
    try:
        p6_attr = PerformanceAttributor()
        p6_records = p6_attr.attribute(result, df_processed)
        phase_outputs["p6_records"] = p6_records
        p6_path = p6_attr.save(p6_records, output_dir)
        saved_paths["phase6"] = str(p6_path)
        wins   = sum(1 for r in p6_records if r.outcome == "WIN")
        losses = sum(1 for r in p6_records if r.outcome == "LOSS")
        _print_phase_result("DONE", f"{wins} wins, {losses} losses attributed")
    except Exception as exc:
        logger.exception("Phase 6 failed")
        _print_phase_result("ERROR", str(exc))
        p6_records = []

    # ── PHASE 7: Multi-Asset Validation ──────────────────────────────────────
    _print_phase_header(7, "Multi-Asset Validation")
    if run_multi_asset:
        from .multi_asset import MultiAssetValidator
        try:
            p7_validator = MultiAssetValidator()
            p7_results = p7_validator.run(
                engine_cls=engine_cls,
                engine_kwargs=engine_kwargs,
                lookback_days=multi_asset_days,
                interval="5m",
            )
            phase_outputs["p7_results"] = p7_results
            p7_paths = p7_validator.save(p7_results, output_dir)
            saved_paths["phase7"] = {k: str(v) for k, v in p7_paths.items()}
            ok_count = sum(1 for r in p7_results if r.status == "OK")
            _print_phase_result("DONE", f"{ok_count}/{len(p7_results)} assets completed")
        except Exception as exc:
            logger.exception("Phase 7 failed")
            _print_phase_result("ERROR", str(exc))
            p7_results = []
    else:
        _print_phase_result("SKIP", "run_multi_asset=False")
        p7_results = []

    # ── PHASE 8: Monte Carlo ──────────────────────────────────────────────────
    _print_phase_header(8, "Monte Carlo Simulation (5000 sims)")
    from .monte_carlo import MonteCarloSimulator
    try:
        p8_mc = MonteCarloSimulator(n_simulations=5000, seed=42)
        mc_result = p8_mc.simulate(result, initial_capital=initial_capital)
        phase_outputs["p8_mc"] = mc_result
        p8_path = p8_mc.save(mc_result, output_dir)
        saved_paths["phase8"] = str(p8_path)
        _print_phase_result(
            "DONE",
            f"P(profit)={mc_result.prob_profit:.1f}% | "
            f"Median=Rs {mc_result.median_final:,.0f} | "
            f"P5=Rs {mc_result.p5_final:,.0f} | P95=Rs {mc_result.p95_final:,.0f}"
        )
    except Exception as exc:
        logger.exception("Phase 8 failed")
        _print_phase_result("ERROR", str(exc))

    # ── PHASE 9: Walk-Forward Stability ──────────────────────────────────────
    _print_phase_header(9, "Walk-Forward Stability")
    if run_walk_forward:
        from .walk_forward import WalkForwardAnalyzer
        try:
            p9_wfa = WalkForwardAnalyzer(is_pct=0.67, oos_pct=0.33, n_windows=3)
            p9_result = p9_wfa.analyze(engine_cls, engine_kwargs, df_raw.copy())
            phase_outputs["p9_wf"] = p9_result
            p9_path = p9_wfa.save(p9_result, output_dir)
            saved_paths["phase9"] = str(p9_path)
            _print_phase_result(
                "DONE",
                f"Avg WFE={p9_result.avg_wfe:.3f} | "
                f"Stability={p9_result.avg_stability:.1f}% | {p9_result.verdict}"
            )
        except Exception as exc:
            logger.exception("Phase 9 failed")
            _print_phase_result("ERROR", str(exc))
    else:
        _print_phase_result("SKIP", "run_walk_forward=False")

    # ── PHASE 10: Deterministic Replay ───────────────────────────────────────
    _print_phase_header(10, "Deterministic Replay Check (3 runs)")
    if run_deterministic:
        from .deterministic_replay import DeterministicReplayChecker
        try:
            p10_checker = DeterministicReplayChecker()
            p10_result  = p10_checker.check(engine_cls, engine_kwargs, df_raw.copy())
            phase_outputs["p10_det"] = p10_result
            p10_path = p10_checker.save(p10_result, output_dir)
            saved_paths["phase10"] = str(p10_path)
            _print_phase_result(
                "PASS" if p10_result.all_identical else "FAIL",
                p10_result.verdict
            )
        except Exception as exc:
            logger.exception("Phase 10 failed")
            _print_phase_result("ERROR", str(exc))
    else:
        _print_phase_result("SKIP", "run_deterministic=False")

    # ── PHASE 11: Trade Charts ────────────────────────────────────────────────
    _print_phase_header(11, "Trade Chart Generation")
    if run_charts:
        from .chart_generator import TradeChartGenerator
        try:
            p11_gen   = TradeChartGenerator(output_dir=charts_dir)
            p11_paths = p11_gen.generate_all(result, df_processed, p1_records)
            phase_outputs["p11_paths"] = p11_paths
            chart_index = p11_gen.generate_index(p11_paths, output_dir)
            phase_outputs["chart_index_path"] = chart_index
            saved_paths["phase11"] = str(chart_index)
            _print_phase_result("DONE", f"{len(p11_paths)} charts -> {charts_dir}")
        except Exception as exc:
            logger.exception("Phase 11 failed")
            _print_phase_result("ERROR", str(exc))
            p11_paths = []
    else:
        _print_phase_result("SKIP", "run_charts=False")

    # ── PHASE 12: Final Institutional Report ──────────────────────────────────
    _print_phase_header(12, "Institutional Report Assembly")
    from .report_builder import InstitutionalReportBuilder
    try:
        builder     = InstitutionalReportBuilder()
        report_text = builder.build(
            result=result,
            phase_outputs=phase_outputs,
            engine_kwargs=engine_kwargs,
        )
        p12_path = builder.save(report_text, output_dir)
        saved_paths["phase12_final"] = str(p12_path)
        _print_phase_result("DONE", f"Final report -> {p12_path.name}")
    except Exception as exc:
        logger.exception("Phase 12 failed")
        _print_phase_result("ERROR", str(exc))

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = time.perf_counter() - t_start
    print(f"\n{'='*70}")
    print(f"  VALIDATION COMPLETE in {elapsed:.1f}s")
    print(f"  All reports saved to: {output_dir.resolve()}")
    print(f"{'='*70}\n")

    print("  Reports:")
    for phase, path in saved_paths.items():
        if isinstance(path, str):
            print(f"    {phase}: {Path(path).name}")
        elif isinstance(path, dict):
            for fmt, p in path.items():
                print(f"    {phase} [{fmt}]: {Path(p).name}")

    return {
        "status":        "complete",
        "elapsed_sec":   round(elapsed, 2),
        "output_dir":    str(output_dir),
        "saved_paths":   saved_paths,
        "phase_outputs": phase_outputs,
        "backtest_result": result,
    }


# ── CLI entry point ────────────────────────────────────────────────────────────
def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="QuantumIndex Institutional Validation Framework",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--symbol",   default="RELIANCE",    help="NSE ticker symbol")
    parser.add_argument("--capital",  type=float, default=100_000.0, help="Initial capital")
    parser.add_argument("--days",     type=int,   default=60, help="Historical lookback days")
    parser.add_argument("--interval", default="5m", help="yfinance interval (5m, 15m, 1h)")
    parser.add_argument("--output",   default=str(DEFAULT_REPORTS_DIR), help="Output directory")
    parser.add_argument("--no-multi-asset",  action="store_true", help="Skip Phase 7")
    parser.add_argument("--no-walk-forward", action="store_true", help="Skip Phase 9")
    parser.add_argument("--no-deterministic",action="store_true", help="Skip Phase 10")
    parser.add_argument("--no-charts",       action="store_true", help="Skip Phase 11")
    args = parser.parse_args()

    try:
        import yfinance as yf
    except ImportError:
        print("ERROR: yfinance not installed. Run: pip install yfinance")
        sys.exit(1)

    interval_map = {"5m": 5, "15m": 15, "30m": 30, "1h": 60}
    interval_min = interval_map.get(args.interval, 5)

    print(f"\nDownloading {args.symbol} data ({args.days}d @ {args.interval})...")
    ticker   = args.symbol + ".NS" if not args.symbol.startswith("^") else args.symbol
    df_raw   = yf.download(ticker, period=f"{args.days}d", interval=args.interval,
                           auto_adjust=True, progress=False)
    if df_raw is None or df_raw.empty:
        print(f"ERROR: No data returned for {ticker}")
        sys.exit(1)

    if hasattr(df_raw.columns, "get_level_values"):
        df_raw.columns = df_raw.columns.get_level_values(0)
    df_raw = df_raw.reset_index()
    df_raw.columns = [c.lower().strip() for c in df_raw.columns]
    for alias in ["date", "timestamp"]:
        if alias in df_raw.columns:
            df_raw = df_raw.rename(columns={alias: "datetime"})

    print(f"Downloaded {len(df_raw)} rows for {args.symbol}")

    # Import engine
    try:
        from ..quantum_backtest_engine import QuantumBacktestEngine
        engine_cls = QuantumBacktestEngine
    except ImportError:
        print("ERROR: Cannot import QuantumBacktestEngine. Run from project root.")
        sys.exit(1)

    engine_kwargs = {
        "symbol":          args.symbol,
        "initial_capital": args.capital,
        "interval_minutes":interval_min,
        "verbose":         False,
    }

    run_all_phases(
        engine_cls=engine_cls,
        engine_kwargs=engine_kwargs,
        df_raw=df_raw,
        output_dir=Path(args.output),
        run_multi_asset=not args.no_multi_asset,
        run_walk_forward=not args.no_walk_forward,
        run_deterministic=not args.no_deterministic,
        run_charts=not args.no_charts,
    )


if __name__ == "__main__":
    _cli()
