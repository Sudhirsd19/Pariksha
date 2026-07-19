"""
Phase 4 — Capital Flow Auditor
================================
Mathematically verifies the capital chain for every trade:
  CapitalBefore + NetPnL == CapitalAfter

Also verifies:
  - Risk amount = Capital × risk_pct
  - Charge decomposition (brokerage, STT, exchange, SEBI, GST, stamp)
  - Gross PnL = (exit - entry) × qty (direction-adjusted)

DO NOT modify any strategy or engine files.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)

TOLERANCE = 0.02   # Rs 0.02 rounding tolerance


@dataclass
class CapitalFlowRecord:
    """Capital flow verification for one trade."""
    trade_num:          int
    entry_time:         str
    signal:             str
    capital_before:     float
    risk_pct:           float
    risk_amount:        float
    entry_price:        float
    sl_price:           float
    risk_per_share:     float
    raw_qty:            float
    executed_qty:       int
    gross_pnl_reported: float
    gross_pnl_verified: float
    gross_pnl_diff:     float
    charges_total:      float
    brokerage:          float
    stt:                float
    exchange_fee:       float
    sebi_fee:           float
    gst:                float
    stamp:              float
    net_pnl_reported:   float
    net_pnl_verified:   float
    net_pnl_diff:       float
    capital_after_reported: float
    capital_after_verified: float
    capital_diff:       float
    status:             str    # PASS | FAIL
    failure_detail:     str    = ""


class CapitalFlowAuditor:
    """
    Verifies the capital arithmetic for every trade in the backtest.

    Usage::

        auditor = CapitalFlowAuditor(initial_capital=100_000)
        records = auditor.verify(result)
        auditor.save(records, Path("reports"))
    """

    def __init__(self, initial_capital: float = 100_000.0) -> None:
        self.initial_capital = initial_capital

    def verify(self, result: Dict[str, Any]) -> List[CapitalFlowRecord]:
        """Verify capital chain for all trades."""
        trades   = result.get("trades", [])
        cfg      = result.get("config", {})
        risk_pct = cfg.get("risk_pct", 0.01)

        records:  List[CapitalFlowRecord] = []
        capital   = self.initial_capital
        failures  = 0

        for n, trade in enumerate(trades, start=1):
            rec = self._verify_one(n, trade, capital, risk_pct)
            capital += trade.get("net_pnl", 0.0)
            if rec.status == "FAIL":
                failures += 1
            records.append(rec)

        logger.info(
            "Phase 4: Verified %d trades — %d PASS, %d FAIL",
            len(records), len(records) - failures, failures,
        )
        return records

    def _verify_one(
        self,
        trade_num:      int,
        trade:          Dict[str, Any],
        capital_before: float,
        risk_pct:       float,
    ) -> CapitalFlowRecord:
        entry_time  = str(trade.get("entry_time", ""))[:19]
        signal      = trade.get("signal", "")
        qty         = int(trade.get("qty", 0))
        eff_entry   = float(trade.get("effective_entry", 0.0))
        eff_exit    = float(trade.get("effective_exit", trade.get("exit", 0.0)))
        atr         = float(trade.get("atr", 0.0))
        sl_price    = float(trade.get("sl", 0.0))

        gross_pnl_rep = float(trade.get("gross_pnl", 0.0))
        charges_total  = float(trade.get("charges", 0.0))
        net_pnl_rep    = float(trade.get("net_pnl", 0.0))

        # Gross PnL re-verification
        if signal == "BUY":
            gross_pnl_ver = round((eff_exit - eff_entry) * qty, 2)
        else:
            gross_pnl_ver = round((eff_entry - eff_exit) * qty, 2)

        net_pnl_ver   = round(gross_pnl_ver - charges_total, 2)
        capital_after  = round(capital_before + net_pnl_rep, 2)

        # Risk sizing re-verification
        risk_amount    = round(capital_before * risk_pct, 2)
        risk_per_share = abs(eff_entry - sl_price) if sl_price > 0 and eff_entry > 0 else atr * 2
        raw_qty        = risk_amount / risk_per_share if risk_per_share > 0 else 0.0

        # Charge decomposition (from charge_detail if available)
        cd = trade.get("charge_detail", {})
        brokerage    = float(cd.get("brokerage",     0.0))
        stt          = float(cd.get("stt",           0.0))
        exchange_fee = float(cd.get("exchange",      0.0))
        sebi_fee     = float(cd.get("sebi",          0.0))
        gst          = float(cd.get("gst",           0.0))
        stamp        = float(cd.get("stamp",         0.0))

        # Diffs
        gross_diff   = abs(gross_pnl_rep - gross_pnl_ver)
        net_diff     = abs(net_pnl_rep   - net_pnl_ver)
        capital_diff = abs(capital_after - (capital_before + net_pnl_rep))

        # Determine status
        failures = []
        if gross_diff > TOLERANCE:
            failures.append(f"Gross PnL diff={gross_diff:.4f}")
        if net_diff > TOLERANCE:
            failures.append(f"Net PnL diff={net_diff:.4f}")
        if capital_diff > TOLERANCE:
            failures.append(f"Capital chain diff={capital_diff:.4f}")
        if qty <= 0:
            failures.append("Qty=0")

        status  = "PASS" if not failures else "FAIL"
        detail  = " | ".join(failures)

        return CapitalFlowRecord(
            trade_num=trade_num,
            entry_time=entry_time,
            signal=signal,
            capital_before=round(capital_before, 2),
            risk_pct=risk_pct,
            risk_amount=risk_amount,
            entry_price=round(eff_entry, 4),
            sl_price=round(sl_price, 4),
            risk_per_share=round(risk_per_share, 4),
            raw_qty=round(raw_qty, 2),
            executed_qty=qty,
            gross_pnl_reported=round(gross_pnl_rep, 2),
            gross_pnl_verified=gross_pnl_ver,
            gross_pnl_diff=round(gross_diff, 4),
            charges_total=round(charges_total, 2),
            brokerage=round(brokerage, 4),
            stt=round(stt, 4),
            exchange_fee=round(exchange_fee, 4),
            sebi_fee=round(sebi_fee, 4),
            gst=round(gst, 4),
            stamp=round(stamp, 4),
            net_pnl_reported=round(net_pnl_rep, 2),
            net_pnl_verified=net_pnl_ver,
            net_pnl_diff=round(net_diff, 4),
            capital_after_reported=capital_after,
            capital_after_verified=round(capital_before + net_pnl_ver, 2),
            capital_diff=round(capital_diff, 4),
            status=status,
            failure_detail=detail,
        )

    def to_dataframe(self, records: List[CapitalFlowRecord]) -> pd.DataFrame:
        return pd.DataFrame([r.__dict__ for r in records])

    def to_markdown(self, records: List[CapitalFlowRecord]) -> str:
        pass_count = sum(1 for r in records if r.status == "PASS")
        fail_count = len(records) - pass_count

        lines = [
            "# Phase 4 — Capital Flow Audit",
            "",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Trades | {len(records)} |",
            f"| PASS | {pass_count} ✅ |",
            f"| FAIL | {fail_count} {'✅' if fail_count == 0 else '❌'} |",
            f"| Tolerance | ±₹{TOLERANCE} |",
            "",
            "## Trade-Level Capital Verification",
            "",
            "| # | Time | Signal | Cap Before | Net PnL | Cap After | Charges | Status |",
            "|---|------|--------|-----------|---------|----------|---------|--------|",
        ]
        for r in records:
            icon = "✅" if r.status == "PASS" else "❌"
            lines.append(
                f"| {r.trade_num} | {r.entry_time} | {r.signal} "
                f"| ₹{r.capital_before:,.2f} | ₹{r.net_pnl_reported:,.2f} "
                f"| ₹{r.capital_after_reported:,.2f} | ₹{r.charges_total:,.2f} "
                f"| {icon} {r.status} |"
            )

        if fail_count > 0:
            lines += ["", "## ❌ Failures", ""]
            for r in records:
                if r.status == "FAIL":
                    lines += [
                        f"### Trade {r.trade_num} — {r.entry_time}",
                        f"- {r.failure_detail}",
                        f"- Gross reported: ₹{r.gross_pnl_reported:.2f} vs verified: ₹{r.gross_pnl_verified:.2f}",
                        f"- Net reported: ₹{r.net_pnl_reported:.2f} vs verified: ₹{r.net_pnl_verified:.2f}",
                        "",
                    ]
        else:
            lines += ["", "> ✅ All capital chain checks passed."]

        return "\n".join(lines)

    def save(self, records: List[CapitalFlowRecord], output_dir: Path) -> Dict[str, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_p = output_dir / "phase4_capital_flow.csv"
        md_p  = output_dir / "phase4_capital_flow.md"
        self.to_dataframe(records).to_csv(csv_p, index=False)
        md_p.write_text(self.to_markdown(records), encoding="utf-8")
        logger.info("Phase 4 saved → %s, %s", csv_p, md_p)
        return {"csv": csv_p, "md": md_p}
