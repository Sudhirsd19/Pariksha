"""
Phase 8 — Monte Carlo Simulator
=================================
Runs 5000 bootstrap simulations using actual completed trade P&L values.
Randomises: trade sequence, slippage ±20%, charges ±10%.

DO NOT modify any strategy or engine files.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class MonteCarloResult:
    """Monte Carlo simulation summary."""
    n_simulations:    int
    n_trades:         int
    initial_capital:  float
    prob_profit:      float   # % of sims ending above initial capital
    median_final:     float
    p5_final:         float   # 5th percentile (worst 5%)
    p95_final:        float   # 95th percentile (best 5%)
    expected_return:  float   # median_final - initial_capital
    worst_dd_median:  float   # median max drawdown
    worst_dd_p95:     float   # 95th percentile max drawdown
    best_dd_p5:       float   # 5th percentile max drawdown (smallest)
    ci_low:           float   # 95% CI lower bound on net PnL
    ci_high:          float   # 95% CI upper bound on net PnL
    actual_final:     float   # actual (non-simulated) final capital


class MonteCarloSimulator:
    """
    Bootstrap Monte Carlo simulation on a set of completed trade P&Ls.

    Usage::

        mc     = MonteCarloSimulator(n_simulations=5000, seed=42)
        result = mc.simulate(result_dict, initial_capital=100_000)
        mc.save(result, Path("reports"))
    """

    def __init__(
        self,
        n_simulations: int   = 5000,
        seed:          int   = 42,
        slip_range:    float = 0.20,  # ±20% slippage variation
        charge_range:  float = 0.10,  # ±10% charge variation
    ) -> None:
        self.n_simulations = n_simulations
        self.seed          = seed
        self.slip_range    = slip_range
        self.charge_range  = charge_range

    def simulate(
        self,
        result:          Dict[str, Any],
        initial_capital: float = 100_000.0,
    ) -> MonteCarloResult:
        """Run Monte Carlo simulation. Returns MonteCarloResult."""
        trades = result.get("trades", [])
        if not trades:
            logger.warning("Phase 8: No trades for Monte Carlo")
            return MonteCarloResult(
                n_simulations=self.n_simulations, n_trades=0,
                initial_capital=initial_capital, prob_profit=0.0,
                median_final=initial_capital, p5_final=initial_capital,
                p95_final=initial_capital, expected_return=0.0,
                worst_dd_median=0.0, worst_dd_p95=0.0, best_dd_p5=0.0,
                ci_low=0.0, ci_high=0.0, actual_final=initial_capital,
            )

        rng = np.random.default_rng(self.seed)

        # Extract gross PnL and charges separately for perturbation
        gross_pnls = np.array([float(t.get("gross_pnl", 0)) for t in trades])
        charges    = np.array([float(t.get("charges", 0))  for t in trades])
        net_pnls   = gross_pnls - charges   # actual net PnL per trade

        actual_final = initial_capital + net_pnls.sum()
        n = len(trades)

        final_capitals: List[float] = []
        max_drawdowns:  List[float] = []

        for _ in range(self.n_simulations):
            # Resample trade sequence with replacement
            idx   = rng.integers(0, n, size=n)
            g_sim = gross_pnls[idx]
            c_sim = charges[idx]

            # Perturb slippage (embedded in gross_pnl via effective price)
            slip_mult   = rng.uniform(1 - self.slip_range, 1 + self.slip_range, size=n)
            charge_mult = rng.uniform(1 - self.charge_range, 1 + self.charge_range, size=n)

            # Apply perturbations
            g_adj = g_sim * slip_mult
            c_adj = c_sim * charge_mult
            net_sim = g_adj - c_adj

            # Simulate equity curve
            equity = np.empty(n + 1)
            equity[0] = initial_capital
            for i, pnl in enumerate(net_sim):
                equity[i + 1] = equity[i] + pnl

            final_capitals.append(float(equity[-1]))

            # Max drawdown
            running_max = np.maximum.accumulate(equity)
            dd = (running_max - equity) / running_max
            max_drawdowns.append(float(dd.max() * 100))

        arr_cap = np.array(final_capitals)
        arr_dd  = np.array(max_drawdowns)
        net_sim_all = arr_cap - initial_capital

        prob_profit    = float((arr_cap > initial_capital).mean() * 100)
        median_final   = float(np.median(arr_cap))
        p5_final       = float(np.percentile(arr_cap, 5))
        p95_final      = float(np.percentile(arr_cap, 95))
        expected_return= float(median_final - initial_capital)
        worst_dd_median= float(np.median(arr_dd))
        worst_dd_p95   = float(np.percentile(arr_dd, 95))
        best_dd_p5     = float(np.percentile(arr_dd, 5))
        ci_low         = float(np.percentile(net_sim_all, 2.5))
        ci_high        = float(np.percentile(net_sim_all, 97.5))

        logger.info(
            "Phase 8 MC: P(profit)=%.1f%% | Median=₹%.2f | P5=₹%.2f | P95=₹%.2f",
            prob_profit, median_final, p5_final, p95_final,
        )
        return MonteCarloResult(
            n_simulations=self.n_simulations,
            n_trades=n,
            initial_capital=initial_capital,
            prob_profit=round(prob_profit, 2),
            median_final=round(median_final, 2),
            p5_final=round(p5_final, 2),
            p95_final=round(p95_final, 2),
            expected_return=round(expected_return, 2),
            worst_dd_median=round(worst_dd_median, 2),
            worst_dd_p95=round(worst_dd_p95, 2),
            best_dd_p5=round(best_dd_p5, 2),
            ci_low=round(ci_low, 2),
            ci_high=round(ci_high, 2),
            actual_final=round(actual_final, 2),
        )

    def _text_histogram(self, arr: np.ndarray, bins: int = 10, width: int = 40) -> str:
        """Simple ASCII histogram."""
        counts, edges = np.histogram(arr, bins=bins)
        max_count = max(counts) if counts.max() > 0 else 1
        lines = []
        for i, c in enumerate(counts):
            bar   = "█" * int(c / max_count * width)
            label = f"₹{edges[i]:>10,.0f}–{edges[i+1]:,.0f}"
            lines.append(f"{label} | {bar} ({c})")
        return "\n".join(lines)

    def to_markdown(self, mc: MonteCarloResult) -> str:
        prob_icon = "✅" if mc.prob_profit >= 50 else "⚠️"
        lines = [
            "# Phase 8 — Monte Carlo Simulation",
            "",
            f"**{mc.n_simulations:,} bootstrap simulations** | "
            f"**{mc.n_trades} trades** | Seed=42",
            "",
            "## Summary Statistics",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Initial Capital | ₹{mc.initial_capital:,.2f} |",
            f"| Actual Final Capital | ₹{mc.actual_final:,.2f} |",
            f"| Median Simulated Final | ₹{mc.median_final:,.2f} |",
            f"| 5th Percentile Final (Worst 5%) | ₹{mc.p5_final:,.2f} |",
            f"| 95th Percentile Final (Best 5%) | ₹{mc.p95_final:,.2f} |",
            f"| Probability of Profit | {prob_icon} {mc.prob_profit:.1f}% |",
            f"| Expected Return (Median) | ₹{mc.expected_return:,.2f} |",
            f"| 95% Confidence Interval Net PnL | [₹{mc.ci_low:,.2f}, ₹{mc.ci_high:,.2f}] |",
            f"| Median Max Drawdown | {mc.worst_dd_median:.2f}% |",
            f"| P95 Max Drawdown (Worst 5%) | {mc.worst_dd_p95:.2f}% |",
            f"| P5 Max Drawdown (Best 5%) | {mc.best_dd_p5:.2f}% |",
            "",
            "## Interpretation",
            "",
        ]
        if mc.prob_profit >= 60:
            lines.append("> ✅ Strategy is profitable in **{:.1f}%** of simulations.".format(mc.prob_profit))
        elif mc.prob_profit >= 40:
            lines.append("> ⚠️ Strategy is profitable in only **{:.1f}%** of simulations — high uncertainty.".format(mc.prob_profit))
        else:
            lines.append("> ❌ Strategy is profitable in only **{:.1f}%** of simulations — likely unprofitable.".format(mc.prob_profit))
        lines += [
            "",
            f"> **Slippage perturbation**: ±{self.slip_range*100:.0f}%",
            f"> **Charge perturbation**: ±{self.charge_range*100:.0f}%",
        ]
        return "\n".join(lines)

    def save(self, mc: MonteCarloResult, output_dir: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        out = output_dir / "phase8_monte_carlo.md"
        out.write_text(self.to_markdown(mc), encoding="utf-8")
        logger.info("Phase 8 saved → %s", out)
        return out
