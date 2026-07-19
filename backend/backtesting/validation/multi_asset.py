"""
Phase 7 — Multi-Asset Validator
=================================
Runs the SAME QuantumBacktestEngine (zero parameter changes) on
multiple NSE symbols and generates a comparison table.

DO NOT modify any strategy or engine files.
"""
from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

DEFAULT_ASSETS = {
    "RELIANCE":  "RELIANCE.NS",
    "TCS":       "TCS.NS",
    "INFY":      "INFY.NS",
    "SBIN":      "SBIN.NS",
    "ICICIBANK": "ICICIBANK.NS",
    "HDFCBANK":  "HDFCBANK.NS",
    "NIFTY":     "^NSEI",
    "BANKNIFTY": "^NSEBANK",
}


@dataclass
class AssetResult:
    """Single-asset backtest summary."""
    symbol:         str
    ticker:         str
    status:         str
    trades:         int     = 0
    win_rate:       float   = 0.0
    profit_factor:  float   = 0.0
    net_pnl:        float   = 0.0
    max_dd_pct:     float   = 0.0
    sharpe:         float   = 0.0
    expectancy:     float   = 0.0
    total_charges:  float   = 0.0
    error:          str     = ""


class MultiAssetValidator:
    """
    Runs the existing QuantumBacktestEngine on multiple assets.
    No parameter changes — same engine, same settings.

    Usage::

        engine_cls = QuantumBacktestEngine
        engine_kwargs = dict(symbol="X", initial_capital=100000, verbose=False)
        validator = MultiAssetValidator()
        results   = validator.run(engine_cls, engine_kwargs, lookback_days=60)
        validator.save(results, Path("reports"))
    """

    def __init__(self, assets: Optional[Dict[str, str]] = None) -> None:
        self.assets = assets or DEFAULT_ASSETS

    def run(
        self,
        engine_cls:    Any,
        engine_kwargs: Dict[str, Any],
        lookback_days: int = 60,
        interval:      str = "5m",
    ) -> List[AssetResult]:
        """
        Run engine on each asset. Returns list of AssetResult.

        Args:
            engine_cls:    QuantumBacktestEngine class
            engine_kwargs: kwargs dict passed to engine constructor (symbol will be overridden)
            lookback_days: days of history to download
            interval:      yfinance interval ('5m' or '1h')
        """
        try:
            import yfinance as yf
        except ImportError:
            logger.error("yfinance not installed — Phase 7 skipped")
            return [AssetResult(sym, tkr, "SKIPPED", error="yfinance not installed")
                    for sym, tkr in self.assets.items()]

        results: List[AssetResult] = []

        for symbol, ticker in self.assets.items():
            logger.info("Phase 7: Running %s (%s)...", symbol, ticker)
            try:
                df_raw = yf.download(
                    ticker,
                    period=f"{lookback_days}d",
                    interval=interval,
                    auto_adjust=True,
                    progress=False,
                )
                if df_raw is None or df_raw.empty:
                    results.append(AssetResult(symbol, ticker, "NO_DATA",
                                               error="yfinance returned empty DataFrame"))
                    continue

                # Flatten MultiIndex if present
                if isinstance(df_raw.columns, pd.MultiIndex):
                    df_raw.columns = df_raw.columns.get_level_values(0)

                df_raw = df_raw.reset_index()
                df_raw.columns = [c.lower().strip() for c in df_raw.columns]
                # Rename Datetime/Date → datetime
                for alias in ["datetime", "date", "timestamp"]:
                    if alias in df_raw.columns and alias != "datetime":
                        df_raw = df_raw.rename(columns={alias: "datetime"})
                        break

                # Build engine with this symbol's kwargs
                kw = dict(engine_kwargs)
                kw["symbol"]  = symbol
                kw["verbose"] = False
                engine = engine_cls(**kw)
                result = engine.run(df_raw)

                if result.get("status") == "error":
                    results.append(AssetResult(symbol, ticker, "ENGINE_ERROR",
                                               error=result.get("error", "unknown")))
                    continue

                m = result.get("metrics", {})
                results.append(AssetResult(
                    symbol=symbol,
                    ticker=ticker,
                    status="OK",
                    trades=int(m.get("total_trades", 0)),
                    win_rate=float(m.get("win_rate", 0.0)),
                    profit_factor=float(m.get("profit_factor", 0.0)),
                    net_pnl=float(m.get("net_profit", 0.0)),
                    max_dd_pct=float(m.get("max_drawdown_pct", 0.0)),
                    sharpe=float(m.get("sharpe_ratio", 0.0)),
                    expectancy=float(m.get("expectancy", 0.0)),
                    total_charges=float(m.get("total_charges", 0.0)),
                ))
                logger.info(
                    "  %s: %d trades | Win=%.1f%% | PF=%.3f | PnL=₹%.2f",
                    symbol, results[-1].trades, results[-1].win_rate,
                    results[-1].profit_factor, results[-1].net_pnl,
                )
            except Exception as exc:
                logger.error("Phase 7: %s failed — %s", symbol, exc)
                results.append(AssetResult(symbol, ticker, "EXCEPTION", error=str(exc)))

        return results

    def to_markdown(self, results: List[AssetResult]) -> str:
        lines = [
            "# Phase 7 — Multi-Asset Validation",
            "",
            "> Same engine, same parameters, no optimization.",
            "",
            "| Symbol | Ticker | Status | Trades | Win% | Profit Factor | Net PnL | Max DD% | Sharpe | Expectancy |",
            "|--------|--------|--------|--------|------|--------------|---------|---------|--------|-----------|",
        ]
        for r in results:
            if r.status == "OK":
                lines.append(
                    f"| {r.symbol} | {r.ticker} | ✅ | {r.trades} "
                    f"| {r.win_rate:.1f}% | {r.profit_factor:.3f} "
                    f"| ₹{r.net_pnl:,.2f} | {r.max_dd_pct:.2f}% "
                    f"| {r.sharpe:.3f} | ₹{r.expectancy:.2f} |"
                )
            else:
                lines.append(
                    f"| {r.symbol} | {r.ticker} | ⚠️ {r.status} | — | — | — | — | — | — | — |"
                )
        return "\n".join(lines)

    def save(self, results: List[AssetResult], output_dir: Path) -> Dict[str, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        md_p  = output_dir / "phase7_multi_asset.md"
        csv_p = output_dir / "phase7_multi_asset.csv"
        md_p.write_text(self.to_markdown(results), encoding="utf-8")
        pd.DataFrame([r.__dict__ for r in results]).to_csv(csv_p, index=False)
        logger.info("Phase 7 saved → %s", md_p)
        return {"md": md_p, "csv": csv_p}
