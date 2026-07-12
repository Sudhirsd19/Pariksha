"""
Equity Backtest Runner
======================
Same logic as /execute-stock-trade but replayed on historical OHLCV candles.
Strategy: StrictChecklistEngine (100-Point Scorecard) + ATR-based SL/TP.
Charges: Real AngelOne brokerage + STT + SEBI + GST + Stamp (same as TradeManager).
"""

import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from backend.engines.strict_checklist_engine import StrictChecklistEngine
from backend.indicators.technical_indicators import TechnicalIndicators

_engine = StrictChecklistEngine()

# ─── AngelOne Charge Calculator (mirrors TradeManager._calculate_charges) ─────
def _calc_charges(entry: float, exit_price: float, qty: int) -> float:
    buy_t  = entry * qty
    sell_t = exit_price * qty
    brokerage = min(20.0, buy_t * 0.001) + min(20.0, sell_t * 0.001)
    stt   = sell_t * 0.00025          # 0.025% on sell (equity intraday)
    txn   = (buy_t + sell_t) * 0.0000345
    sebi  = (buy_t + sell_t) * 0.000001
    gst   = (brokerage + txn + sebi) * 0.18
    stamp = buy_t * 0.00003
    return round(brokerage + stt + txn + sebi + gst + stamp, 2)


def run_equity_backtest(
    symbol: str,
    days: int = 60,
    initial_capital: float = 100_000.0,
    min_score: int = 60,
) -> dict:
    """
    Runs a walk-forward backtest of the Strict Checklist Engine on 5-min OHLCV data.

    Parameters
    ----------
    symbol          : NSE equity symbol, e.g. "RELIANCE"
    days            : Number of calendar days of history to fetch
    initial_capital : Starting capital in INR
    min_score       : Minimum score to take a trade (mirrors MIN_MANUAL_SCORE logic)

    Returns
    -------
    dict with keys: status, metrics, equity_curve, trades, error (on failure)
    """
    import yfinance as yf

    ticker = f"{symbol.upper().replace('-EQ','').replace('.NS','')}.NS"
    period = f"{days}d"

    # ── 1. Fetch Historical Data ───────────────────────────────────────────────
    try:
        raw = yf.download(ticker, period=period, interval="5m", progress=False, auto_adjust=True)
        if raw is None or raw.empty or len(raw) < 50:
            return {"status": "error", "error": f"Not enough data for {symbol}. Try a larger date range or different symbol."}
    except Exception as e:
        return {"status": "error", "error": f"yfinance fetch failed: {e}"}

    # Standardise column names
    raw.columns = [str(c[0]).lower() if isinstance(c, tuple) else str(c).lower() for c in raw.columns]
    if "close" not in raw.columns:
        return {"status": "error", "error": "No 'close' column in fetched data."}

    raw = raw.dropna(subset=["close"])
    raw = raw.reset_index()
    if "datetime" in raw.columns:
        raw = raw.rename(columns={"datetime": "date"})

    # ── 2. Pre-compute ALL indicators once on full series ──────────────────────
    df_full = TechnicalIndicators.apply_all(raw.copy())
    df_full.columns = [c.lower() for c in df_full.columns]

    # ── 3. Walk-Forward Simulation ─────────────────────────────────────────────
    capital        = initial_capital
    equity_curve   = [initial_capital]
    trades         = []
    open_trade     = None          # only one position at a time (same as app logic)
    WINDOW         = 60            # candles fed to engine per evaluation
    ATR_SL_MULT    = 2.0
    ATR_TP_MULT    = 4.0
    MAX_HOLD_BARS  = 78            # ~6.5 hrs at 5-min = 1 full session max hold

    # Only trade during Indian market hours (9:15–14:30 IST) for entries
    # Exits can happen up to 15:10 IST (auto sq-off)
    IST = timezone(timedelta(hours=5, minutes=30))

    for i in range(WINDOW, len(df_full)):
        bar = df_full.iloc[i]
        bar_time = None
        try:
            ts = bar.get("date") or bar.get("index") or bar.name
            if ts is not None:
                if hasattr(ts, "to_pydatetime"):
                    ts = ts.to_pydatetime()
                if hasattr(ts, "tzinfo") and ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                bar_time = ts.astimezone(IST)
        except Exception:
            pass

        close   = float(bar["close"])
        high    = float(bar.get("high", close))
        low     = float(bar.get("low",  close))

        # ── A. Check if open trade should be closed ────────────────────────────
        if open_trade:
            bars_held = i - open_trade["bar_index"]
            hit_tp = hit_sl = False

            if open_trade["signal"] == "BUY":
                if high >= open_trade["tp"]:
                    hit_tp, exit_px = True, open_trade["tp"]
                elif low <= open_trade["sl"]:
                    hit_sl, exit_px = True, open_trade["sl"]
                elif bars_held >= MAX_HOLD_BARS:
                    hit_sl, exit_px = True, close   # forced close

            else:  # SELL
                if low <= open_trade["tp"]:
                    hit_tp, exit_px = True, open_trade["tp"]
                elif high >= open_trade["sl"]:
                    hit_sl, exit_px = True, open_trade["sl"]
                elif bars_held >= MAX_HOLD_BARS:
                    hit_sl, exit_px = True, close

            if hit_tp or hit_sl:
                qty = open_trade["qty"]
                entry_px = open_trade["entry"]
                if open_trade["signal"] == "BUY":
                    gross_pnl = (exit_px - entry_px) * qty
                else:
                    gross_pnl = (entry_px - exit_px) * qty

                charges  = _calc_charges(entry_px, exit_px, qty)
                net_pnl  = gross_pnl - charges
                capital += net_pnl
                equity_curve.append(round(capital, 2))

                trades.append({
                    "entry_time":  open_trade["entry_time"],
                    "exit_time":   str(bar_time)[:19] if bar_time else f"bar_{i}",
                    "signal":      open_trade["signal"],
                    "entry":       round(entry_px, 2),
                    "exit":        round(exit_px, 2),
                    "sl":          round(open_trade["sl"], 2),
                    "tp":          round(open_trade["tp"], 2),
                    "qty":         qty,
                    "gross_pnl":   round(gross_pnl, 2),
                    "charges":     round(charges, 2),
                    "net_pnl":     round(net_pnl, 2),
                    "result":      "TARGET" if hit_tp else "STOPLOSS",
                    "bars_held":   bars_held,
                })
                open_trade = None

        # ── B. Look for new entry (only if flat, during market hours) ──────────
        if open_trade is None:
            # Skip if outside entry window (9:20–14:30 IST) or weekend
            if bar_time:
                wd = bar_time.weekday()
                t  = bar_time.time()
                from datetime import time as dt_time
                if wd >= 5:
                    continue
                if not (dt_time(9, 20) <= t <= dt_time(14, 30)):
                    continue

            # Feed last WINDOW candles to strategy engine
            window_df = df_full.iloc[i - WINDOW + 1: i + 1].copy()
            try:
                result = _engine.evaluate(
                    ticker,
                    window_df,
                    is_nifty_bullish=True,      # simplification for backtest
                    market_depth_buyer_ratio=1.0
                )
            except Exception:
                continue

            score  = result.get("strict_score", 0)
            signal = result.get("strict_signal", "NONE")

            if score < min_score or signal == "NONE":
                continue

            side = "BUY" if "BUY" in signal else ("SELL" if "SELL" in signal else None)
            if not side:
                continue

            # ATR-based SL / TP
            atr_col = next((c for c in df_full.columns if c.startswith("atr")), None)
            atr = float(df_full.iloc[i].get(atr_col, close * 0.01)) if atr_col else close * 0.01
            if atr <= 0:
                atr = close * 0.01

            if side == "BUY":
                sl = close - ATR_SL_MULT * atr
                tp = close + ATR_TP_MULT * atr
            else:
                sl = close + ATR_SL_MULT * atr
                tp = close - ATR_TP_MULT * atr

            # Position sizing: risk 1% of current capital per trade, capped by capital
            risk_per_share = abs(close - sl)
            if risk_per_share <= 0:
                continue
            risk_amount = capital * 0.01
            qty = max(1, int(risk_amount / risk_per_share))
            max_by_capital = max(1, int(capital / close))
            qty = min(qty, max_by_capital)

            open_trade = {
                "signal":     side,
                "entry":      close,
                "sl":         round(sl, 2),
                "tp":         round(tp, 2),
                "qty":        qty,
                "bar_index":  i,
                "entry_time": str(bar_time)[:19] if bar_time else f"bar_{i}",
                "score":      score,
            }

    # ── 4. Force-close any open trade at last bar ──────────────────────────────
    if open_trade and len(df_full) > 0:
        last_bar   = df_full.iloc[-1]
        exit_px    = float(last_bar["close"])
        qty        = open_trade["qty"]
        entry_px   = open_trade["entry"]
        gross_pnl  = (exit_px - entry_px) * qty if open_trade["signal"] == "BUY" else (entry_px - exit_px) * qty
        charges    = _calc_charges(entry_px, exit_px, qty)
        net_pnl    = gross_pnl - charges
        capital   += net_pnl
        equity_curve.append(round(capital, 2))
        trades.append({
            "entry_time": open_trade["entry_time"],
            "exit_time":  "FORCED_CLOSE",
            "signal":     open_trade["signal"],
            "entry":      round(entry_px, 2),
            "exit":       round(exit_px, 2),
            "sl":         round(open_trade["sl"], 2),
            "tp":         round(open_trade["tp"], 2),
            "qty":        qty,
            "gross_pnl":  round(gross_pnl, 2),
            "charges":    round(charges, 2),
            "net_pnl":    round(net_pnl, 2),
            "result":     "FORCED_CLOSE",
            "bars_held":  len(df_full) - 1 - open_trade["bar_index"],
        })
        open_trade = None

    # ── 5. Compute Metrics ─────────────────────────────────────────────────────
    if not trades:
        return {
            "status":       "success",
            "metrics":      {"message": "No trades triggered. Try lowering min_score or increasing days."},
            "equity_curve": equity_curve,
            "trades":       [],
            "symbol":       symbol,
            "days":         days,
        }

    df_t        = pd.DataFrame(trades)
    winners     = df_t[df_t["net_pnl"] > 0]
    losers      = df_t[df_t["net_pnl"] <= 0]
    total_pnl   = df_t["net_pnl"].sum()
    win_rate    = len(winners) / len(df_t) * 100
    avg_win     = winners["net_pnl"].mean() if not winners.empty else 0
    avg_loss    = abs(losers["net_pnl"].mean()) if not losers.empty else 0
    pf          = winners["net_pnl"].sum() / abs(losers["net_pnl"].sum()) if not losers.empty and losers["net_pnl"].sum() != 0 else float("inf")
    expectancy  = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * avg_loss)

    eq          = pd.Series(equity_curve)
    rolling_max = eq.cummax()
    drawdown    = (eq - rolling_max) / rolling_max * 100
    max_dd      = abs(drawdown.min())

    daily_pnl   = df_t["net_pnl"]
    sharpe      = float(daily_pnl.mean() / daily_pnl.std() * (252 ** 0.5)) if daily_pnl.std() > 0 else 0.0

    return_pct  = (capital - initial_capital) / initial_capital * 100

    metrics = {
        "total_trades":     len(df_t),
        "winning_trades":   int(len(winners)),
        "losing_trades":    int(len(losers)),
        "win_rate":         round(win_rate, 1),
        "profit_factor":    round(min(pf, 99.0), 2),
        "total_pnl":        round(total_pnl, 2),
        "return_pct":       round(return_pct, 2),
        "max_drawdown":     round(max_dd, 2),
        "avg_win":          round(avg_win, 2),
        "avg_loss":         round(avg_loss, 2),
        "expectancy":       round(expectancy, 2),
        "sharpe_ratio":     round(sharpe, 2),
        "total_charges":    round(df_t["charges"].sum(), 2),
        "final_capital":    round(capital, 2),
        "initial_capital":  initial_capital,
    }

    return {
        "status":       "success",
        "symbol":       symbol.upper(),
        "days":         days,
        "metrics":      metrics,
        "equity_curve": equity_curve,
        "trades":       trades[-100:],  # cap at last 100 for payload size
    }
