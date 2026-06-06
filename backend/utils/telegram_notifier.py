"""
Telegram Notifier — QuantumIndex
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sends trade alerts to a Telegram bot on:
  • Trade entry   (signal, SL, TP, R:R)
  • Trade exit    (result, net PnL)
  • Daily summary (win rate, total PnL)
  • Gap scan      (gap-up / gap-down stocks found)

Setup (Railway env vars):
  TELEGRAM_BOT_TOKEN  = "123456:ABC-DEF..."
  TELEGRAM_CHAT_ID    = "-100xxxxxxxxx"  (channel) or "123456789" (personal)
"""
import os
import requests
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")


def _send(text: str):
    """Send a Telegram message. Silently skip if not configured."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
        }, timeout=5)
    except Exception as e:
        print(f"[Telegram] Send failed: {e}")


def notify_trade_entry(signal: str, symbol: str, entry: float, sl: float, tp: float,
                       qty: int, instrument: str = "EQUITY", is_paper: bool = True):
    """Called when a new trade is opened."""
    now   = datetime.now(IST).strftime("%d/%m %H:%M")
    mode  = "📄 PAPER" if is_paper else "🔴 LIVE"
    emoji = "📈" if signal == "BUY" else "📉"
    risk   = abs(entry - sl) * qty
    reward = abs(tp - entry) * qty
    rr     = round(reward / risk, 1) if risk > 0 else 0

    text = (
        f"{emoji} <b>TRADE ENTRY — {mode}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 <b>{signal}</b>  {symbol}  [{instrument}]\n"
        f"💰 Entry  : ₹{entry:.2f}\n"
        f"🛡 SL     : ₹{sl:.2f}  (-₹{risk:.0f})\n"
        f"🎯 Target : ₹{tp:.2f}  (+₹{reward:.0f})\n"
        f"📊 R:R    : 1:{rr}\n"
        f"🔢 Qty    : {qty}\n"
        f"🕐 Time   : {now}"
    )
    _send(text)


def notify_trade_exit(signal: str, symbol: str, entry: float, exit_price: float,
                      qty: int, pnl: float, result: str, is_paper: bool = True):
    """Called when a trade closes (SL / TP / Squareoff)."""
    now    = datetime.now(IST).strftime("%d/%m %H:%M")
    mode   = "📄 PAPER" if is_paper else "🔴 LIVE"
    is_win = pnl >= 0
    emoji  = "✅" if is_win else "❌"
    result_map = {
        "TARGET":     "🎯 TARGET HIT",
        "STOPLOSS":   "🛡 STOPLOSS HIT",
        "SQUARE_OFF": "⚡ AUTO SQUAREOFF",
    }
    result_str = result_map.get(result, result)
    pnl_sign   = "+" if is_win else ""

    text = (
        f"{emoji} <b>TRADE CLOSED — {mode}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📌 {signal}  {symbol}\n"
        f"💸 Entry   : ₹{entry:.2f}\n"
        f"🏁 Exit    : ₹{exit_price:.2f}\n"
        f"{'📈' if is_win else '📉'} Net PnL  : {pnl_sign}₹{pnl:.2f}\n"
        f"🏷 Result  : {result_str}\n"
        f"🔢 Qty     : {qty}\n"
        f"🕐 Time    : {now}"
    )
    _send(text)


def notify_sl_moved_to_breakeven(symbol: str, signal: str, breakeven: float):
    """Called when SL is moved to breakeven (1:1 RR achieved)."""
    now = datetime.now(IST).strftime("%H:%M")
    text = (
        f"🔒 <b>SL → BREAKEVEN</b>\n"
        f"📌 {signal}  {symbol}\n"
        f"🛡 SL moved to ₹{breakeven:.2f}  (entry)\n"
        f"🕐 {now}  |  Risk-free trade now!"
    )
    _send(text)


def notify_daily_summary(total_trades: int, winning: int, losing: int,
                         realized_pnl: float, daily_loss_used: float):
    """Called once at EOD (auto-squareoff time)."""
    now      = datetime.now(IST).strftime("%d/%m/%Y")
    win_rate = round((winning / total_trades) * 100) if total_trades > 0 else 0
    emoji    = "🟢" if realized_pnl >= 0 else "🔴"
    pnl_sign = "+" if realized_pnl >= 0 else ""

    text = (
        f"{emoji} <b>DAILY SUMMARY — {now}</b>\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 Total Trades : {total_trades}\n"
        f"✅ Winning      : {winning}\n"
        f"❌ Losing       : {losing}\n"
        f"🏆 Win Rate     : {win_rate}%\n"
        f"💰 Net PnL      : {pnl_sign}₹{realized_pnl:.2f}\n"
        f"📉 Daily Loss   : ₹{daily_loss_used:.2f}"
    )
    _send(text)


def notify_gap_scan_results(gap_ups: list, gap_downs: list):
    """Called after pre-market gap scan."""
    if not gap_ups and not gap_downs:
        return
    now   = datetime.now(IST).strftime("%d/%m %H:%M")
    lines = [f"🔍 <b>PRE-MARKET GAP SCAN — {now}</b>", "━━━━━━━━━━━━━━━━━━"]

    if gap_ups:
        lines.append("📈 <b>GAP UP</b>")
        for item in gap_ups[:5]:
            lines.append(f"  • {item['symbol']}  +{item['gap_pct']:.1f}%  ₹{item['prev_close']:.0f}→₹{item['current']:.0f}")

    if gap_downs:
        lines.append("📉 <b>GAP DOWN</b>")
        for item in gap_downs[:5]:
            lines.append(f"  • {item['symbol']}  {item['gap_pct']:.1f}%  ₹{item['prev_close']:.0f}→₹{item['current']:.0f}")

    lines.append(f"\n🕐 Auto-added to watchlist for today's trading")
    _send("\n".join(lines))
