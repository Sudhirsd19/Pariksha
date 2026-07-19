"""
QuantumIndex — Institutional Validation Framework
===================================================
12-Phase independent validation suite.
Strategy code is NEVER imported or modified.

Phases:
  0  DataIntegrityAuditor         — raw OHLCV sanity checks
  1  TradeReplayEngine            — MFE, MAE, trailing SL replay
  2  CandleDecisionLogger         — per-candle BUY/SELL/REJECT log
  3  BooleanExpressionAuditor     — exact boolean expression evaluation
  4  CapitalFlowAuditor           — CapitalBefore + NetPnL == CapitalAfter
  5  ExecutionValidator           — 20 institutional execution checks
  6  PerformanceAttributor        — root-cause attribution per trade
  7  MultiAssetValidator          — cross-symbol stress test
  8  MonteCarloSimulator          — 5000 bootstrap simulations
  9  WalkForwardAnalyzer          — IS/OOS WFE stability analysis
  10 DeterministicReplayChecker   — 3-run determinism verification
  11 TradeChartGenerator          — per-trade candlestick charts
  12 InstitutionalReportBuilder   — final score + certification

Entry point:
  from backend.backtesting.validation.run_validation import run_all_phases
"""

from .phase0_data_integrity   import DataIntegrityAuditor,     IntegrityReport
from .replay_engine           import TradeReplayEngine,         TradeReplayRecord
from .candle_log              import CandleDecisionLogger
from .boolean_auditor         import BooleanExpressionAuditor
from .capital_flow            import CapitalFlowAuditor,        CapitalFlowRecord
from .execution_validator     import ExecutionValidator,         CheckResult
from .attribution             import PerformanceAttributor,     AttributionRecord
from .multi_asset             import MultiAssetValidator,        AssetResult
from .monte_carlo             import MonteCarloSimulator,        MonteCarloResult
from .walk_forward            import WalkForwardAnalyzer,        WalkForwardResult
from .deterministic_replay    import DeterministicReplayChecker, DeterministicReplayResult
from .chart_generator         import TradeChartGenerator
from .report_builder          import InstitutionalReportBuilder
from .run_validation          import run_all_phases

__all__ = [
    # Phase 0
    "DataIntegrityAuditor", "IntegrityReport",
    # Phase 1
    "TradeReplayEngine", "TradeReplayRecord",
    # Phase 2
    "CandleDecisionLogger",
    # Phase 3
    "BooleanExpressionAuditor",
    # Phase 4
    "CapitalFlowAuditor", "CapitalFlowRecord",
    # Phase 5
    "ExecutionValidator", "CheckResult",
    # Phase 6
    "PerformanceAttributor", "AttributionRecord",
    # Phase 7
    "MultiAssetValidator", "AssetResult",
    # Phase 8
    "MonteCarloSimulator", "MonteCarloResult",
    # Phase 9
    "WalkForwardAnalyzer", "WalkForwardResult",
    # Phase 10
    "DeterministicReplayChecker", "DeterministicReplayResult",
    # Phase 11
    "TradeChartGenerator",
    # Phase 12
    "InstitutionalReportBuilder",
    # Master runner
    "run_all_phases",
]

__version__ = "1.0.0"
