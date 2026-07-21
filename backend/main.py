import socket

# Monkey-patch socket.getaddrinfo to force IPv4 and prevent slow IPv6 timeouts
original_getaddrinfo = socket.getaddrinfo

def ipv4_only_getaddrinfo(*args, **kwargs):
    args = list(args)
    if len(args) > 2:
        args[2] = socket.AF_INET
    else:
        kwargs['family'] = socket.AF_INET
    return original_getaddrinfo(*args, **kwargs)

socket.getaddrinfo = ipv4_only_getaddrinfo

import asyncio
import os
import sys
import json
import random
import time
from datetime import datetime, time as dt_time, timezone, timedelta

# Add project root to sys.path to handle module imports correctly
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks

from backend.config.config import config
from backend.engines.cooldown_engine import CooldownEngine
from backend.execution.broker_api import AngelOneBroker
from backend.indicators.technical_indicators import TechnicalIndicators
from backend.market_stream.socket_manager import MarketWebSocket
from backend.risk_management.risk_manager import RiskManager
from backend.utils.historical_data import fetch_historical_data
from backend.utils.token_manager import token_manager
from backend.config.firebase_config import init_firebase
from backend.utils.db_manager import db_manager
from backend.utils.trade_manager import trade_manager
from firebase_admin import messaging
from backend.safety.health_monitor import health_monitor
from backend.utils.persistence_manager import persistence_manager
from backend.engines.strict_checklist_engine import strict_checklist_engine
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="QuantumIndex Algo-Trading System")

# Enable CORS for Flutter Web
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SCAN CACHE (60s TTL) ---
import time as _time
_scan_cache = {}  # {symbol: {"result": {...}, "timestamp": float}}
_SCAN_CACHE_TTL = 60  # seconds

def _get_cached_scan(symbol: str):
    entry = _scan_cache.get(symbol)
    if entry and (_time.time() - entry["timestamp"]) < _SCAN_CACHE_TTL:
        return entry["result"]
    return None

def _set_cached_scan(symbol: str, result: dict):
    _scan_cache[symbol] = {"result": result, "timestamp": _time.time()}

def send_push_notification(title, body):
    """Send FCM notification to all devices subscribed to 'trading_alerts' topic."""
    try:
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            topic='trading_alerts',
        )
        messaging.send(message)
        safe_title = title.encode('ascii', 'ignore').decode('ascii')
        print(f"SENT NOTIFICATION: {safe_title}")
    except Exception as e:
        # Safe print for exception message as well
        print(f"FCM Notification Error: {str(e).encode('ascii', 'ignore').decode('ascii')}")

# --- GLOBAL STATE & CACHE ---
trading_active = False
is_paper_trading = config.PAPER_TRADING
trading_loop_task = None
signals = []
connected_ws_clients = set()
current_ltp = 0.0
last_broadcast_ltp = 0.0 
last_execution_candle = { "NIFTY": None, "BANKNIFTY": None }
last_checked_candle = { "NIFTY": None, "BANKNIFTY": None }
last_reset_date = config.get_ist_time().date()
ws_manager = None
ws_current_score = 0  # Live market score (0-100) broadcast via WS + synced to Firestore

# --- CORE COMPONENTS ---
broker = AngelOneBroker()
risk_manager = RiskManager(initial_capital=100000)
cooldown_engine = CooldownEngine(minutes=10) # 10 min cooldown

def ensure_websocket_connected():
    global ws_manager
    if not broker.session:
        try:
            broker.login()
        except Exception as e:
            print(f"[WebSocket Init] Broker login failed: {e}")
            return False
            
    if broker.session:
        if not ws_manager:
            try:
                ws_manager = MarketWebSocket(
                    broker.session['jwtToken'], 
                    config.ANGEL_API_KEY, 
                    config.ANGEL_CLIENT_ID, 
                    broker.feed_token
                )
                ws_manager.connect()
                print("[WebSocket Init] Connected successfully.")
            except Exception as e:
                print(f"[WebSocket Init] Connection failed: {e}")
                ws_manager = None
                return False
        elif not ws_manager.running:
            try:
                ws_manager.connect()
                print("[WebSocket Init] Reconnected successfully.")
            except Exception as e:
                print(f"[WebSocket Init] Reconnection failed: {e}")
                return False
        return True
    return False

def get_live_price_fallback(trade):
    sym = trade.get("symbol", "").replace("-EQ", "")
    tok = trade.get("token")
    inst = trade.get("instrument_type", "EQUITY")
    exch = "NSE" if inst == "EQUITY" else "NFO"
    
    # Throttle REST API calls to respect rate limit (max 3 req/sec)
    time.sleep(0.4)
    
    if tok and broker.session:
        try:
            # Query real-time LTP from AngelOne API
            price = broker.get_market_data(exch, sym, tok)
            if price and price > 0:
                print(f"[SquareOff Fallback] Fetched live price from AngelOne for {sym}: {price}")
                return price
        except Exception as e:
            print(f"[SquareOff Fallback] Broker fetch failed for {sym}: {e}")
            
    # Fallback to yfinance if AngelOne fails
    try:
        import yfinance as yf
        ticker = f"{sym}.NS"
        df = yf.Ticker(ticker).history(period="1d")
        if not df.empty:
            price = float(df['Close'].iloc[-1])
            if price > 0:
                print(f"[SquareOff Fallback] Fetched live price from yfinance for {sym}: {price}")
                return price
    except Exception as e:
        print(f"[SquareOff Fallback] yfinance fetch failed for {sym}: {e}")
        
    return None

async def _session_keepalive_loop():
    """Periodically re-login to keep the Angel One JWT session alive.
    Angel One sessions expire after ~24h. On Render, the server may run
    for days without a restart, so we refresh every 6 hours proactively."""
    while True:
        await asyncio.sleep(6 * 3600)   # every 6 hours
        try:
            print("[SessionKeepAlive] Refreshing Angel One session...")
            success = broker.login()
            if success:
                print("[SessionKeepAlive] Session refreshed successfully.")
                ensure_websocket_connected()
            else:
                print("[SessionKeepAlive] WARNING: Session refresh failed — scan may fail.")
        except Exception as e:
            print(f"[SessionKeepAlive] Exception during refresh: {e}")

@app.on_event("startup")
async def startup_event():
    init_firebase()
    # Resume state from local SQLite
    trade_manager.load_state()
    trade_manager.risk_manager = risk_manager
    
    # Try to login to broker on startup to generate active session
    try:
        broker.login()
        # Startup WebSocket immediately if login succeeded
        ensure_websocket_connected()
    except Exception as e:
        print(f"[Startup] Angel One Login failed: {e}")

    # Start background session keep-alive (re-login every 6h to prevent expiry)
    asyncio.create_task(_session_keepalive_loop())
        
    persistence_manager.log_event("INFO", "SYSTEM_STARTUP", "QuantumIndex Engine Initialized")
    
    # FIX 3: Restore today's daily stats from Firestore on startup
    # Prevents daily_loss / trades_today reset bypass after Railway restart
    try:
        from backend.config.firebase_config import get_db
        db = get_db()
        if db:
            today = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")  # FIX H-5: Use IST date
            doc = db.collection("pnl_daily").document(today).get()
            if doc.exists:
                data = doc.to_dict()
                # Fix M-1: Load gross loss directly if available, otherwise fallback to net
                risk_manager.daily_loss = abs(float(data.get("gross_loss", 0))) if data.get("gross_loss") else (abs(float(data.get("total_pnl", 0))) if float(data.get("total_pnl", 0)) < 0 else 0)
                risk_manager.trades_today = int(data.get("total_trades", 0))
                persistence_manager.log_event("INFO", "DAILY_RESTORE", f"Restored: trades={risk_manager.trades_today}, loss=Rs.{risk_manager.daily_loss:.2f}")
                print(f"[Startup] Restored today's stats: trades={risk_manager.trades_today}, daily_loss=Rs.{risk_manager.daily_loss:.2f}")
            
            # Restore today's signals to populate in-memory list
            ist_tz = timezone(timedelta(hours=5, minutes=30))
            start_of_day_ist = datetime.now(ist_tz).replace(hour=0, minute=0, second=0, microsecond=0)
            start_of_day_ms = int(start_of_day_ist.timestamp() * 1000)
            
            trades_query = db.collection("quantum_trades").where("timestamp", ">=", start_of_day_ms).order_by("timestamp").stream()
            
            global signals
            restored_count = 0
            for doc_snapshot in trades_query:
                trade_data = doc_snapshot.to_dict()
                trade_data['id'] = doc_snapshot.id
                if not any(s.get('id') == doc_snapshot.id for s in signals):
                    signals.append(trade_data)
                    restored_count += 1
            print(f"[Startup] Restored {restored_count} signals from Firestore.")
            persistence_manager.log_event("INFO", "SIGNALS_RESTORE", f"Restored {restored_count} signals from Firestore.")

            # Restore open trades from Firestore (in case SQLite was wiped)
            # Fetch all open trades first (no composite index needed), then filter by today's timestamp in Python
            open_trades_query = db.collection("quantum_trades").where("status", "==", "OPEN").stream()
            restored_open_trades = []
            for doc_snapshot in open_trades_query:
                trade_data = doc_snapshot.to_dict()
                trade_data['id'] = doc_snapshot.id
                if trade_data.get('timestamp', 0) >= start_of_day_ms:
                    restored_open_trades.append(trade_data)
            
            if restored_open_trades:
                with trade_manager._lock:
                    for t in restored_open_trades:
                        if not any(at.get('id') == t['id'] for at in trade_manager.active_trades):
                            trade_manager.active_trades.append(t)
                            persistence_manager.save_trade(t)
                print(f"[Startup] Restored {len(restored_open_trades)} open trades from Firestore.")
                persistence_manager.log_event("INFO", "ACTIVE_TRADES_RESTORE", f"Restored {len(restored_open_trades)} open trades from Firestore.")

            # Restore system active state (is_active) from Firestore
            system_status = db_manager.get_system_status()
            if system_status:
                global trading_active, trading_loop_task
                trading_active = system_status.get("is_active", False)
                if trading_active:
                    print("[Startup] System is ACTIVE. Launching trading loop...")
                    persistence_manager.log_event("INFO", "ENGINE_AUTOLUNCH", "System is active. Launching trading loop.")
                    if trading_loop_task is None or trading_loop_task.done():
                        trading_loop_task = asyncio.create_task(trading_loop())
                else:
                    print("[Startup] System is INACTIVE.")
    except Exception as e:
        print(f"[Startup] Could not restore daily stats or signals from Firestore (falling back to SQLite): {e}")
        try:
            # Fallback to local SQLite to restore signals and daily stats
            signals = persistence_manager.get_todays_trades()
            closed_today = [s for s in signals if s.get("status") == "CLOSED"]
            risk_manager.trades_today = len(closed_today)
            
            daily_pnl = sum(float(s.get("pnl", 0)) for s in closed_today)
            risk_manager.daily_loss = abs(daily_pnl) if daily_pnl < 0 else 0
            
            print(f"[Startup] SQLite Fallback: Restored today's stats: trades={risk_manager.trades_today}, daily_loss=Rs.{risk_manager.daily_loss:.2f}")
            persistence_manager.log_event("INFO", "DAILY_RESTORE_SQLITE", f"SQLite Fallback Restored: trades={risk_manager.trades_today}, loss=Rs.{risk_manager.daily_loss:.2f}")
        except Exception as sq_err:
            print(f"[Startup] Could not restore stats from SQLite: {sq_err}")
    
    asyncio.create_task(ltp_broadcaster())

async def ltp_broadcaster():
    """Continuously fetch LTP and push to clients with Adaptive Throttling."""
    global current_ltp, last_broadcast_ltp, connected_ws_clients
    symbols = ["NIFTY", "BANKNIFTY"]
    tokens = {s: token_manager.get_token(s) for s in symbols}
    simulated_ltps = {tokens["NIFTY"]: 24150.0, tokens["BANKNIFTY"]: 55300.0}
    
    # Periodic check timer for WebSocket auto-healing
    last_ws_check = 0
    
    while True:
        try:
            # Auto-heal WebSocket every 15 seconds if disconnected or None
            now_time = time.time()
            if now_time - last_ws_check > 15:
                last_ws_check = now_time
                try:
                    await asyncio.to_thread(ensure_websocket_connected)
                except Exception as ws_err:
                    print(f"[Broadcaster WS AutoHeal Error]: {ws_err}")

            # 1. Health & Stale Feed Check
            is_healthy = health_monitor.is_feed_healthy()
            
            # Only halt live trading on stale feed, paper trading continues with simulation
            if not is_healthy and not is_paper_trading and trading_active:
                persistence_manager.log_event("WARNING", "STALE_FEED", "Trading halted due to frozen data")
                await toggle_trading(False)
            
            # Get open trade tokens to include in current_ltps
            active_trade_tokens = []
            with trade_manager._lock:
                for t in trade_manager.active_trades:
                    tok = t.get("token")
                    if tok:
                        active_trade_tokens.append(tok)

            # Ensure all active trades are subscribed to the WebSocket
            if ws_manager and ws_manager.running:
                with trade_manager._lock:
                    for t in trade_manager.active_trades:
                        tok = t.get("token")
                        inst = t.get("instrument_type", "EQUITY")
                        exch_type = 1 if inst == "EQUITY" else 2
                        if tok:
                            ws_manager.subscribe_token(tok, exch_type)

            # Clean up simulated_ltps for inactive trade tokens
            default_tokens = set(tokens.values())
            for t_key in list(simulated_ltps.keys()):
                if t_key not in active_trade_tokens and t_key not in default_tokens:
                    del simulated_ltps[t_key]

            current_ltps = {}
            for symbol, token in tokens.items():
                # Get live price if healthy, otherwise use simulation if in paper trading
                ltp = ws_manager.get_ltp(token) if (ws_manager and is_healthy) else 0
                
                if not ltp or ltp == 0:
                    # Simulation / Drift logic
                    drift = random.uniform(-1.0, 1.0)
                    simulated_ltps[token] = round(simulated_ltps[token] + drift, 2)
                    ltp = simulated_ltps[token]
                else:
                    # Update simulated base to match live price for smooth transitions
                    simulated_ltps[token] = ltp
                
                current_ltps[token] = ltp
                if symbol == "NIFTY": current_ltp = ltp

            # Fetch or simulate price for all active trade tokens and watchlist tokens
            yf_symbols = []
            token_to_symbol = {}
            
            # Watchlist tokens
            try:
                watchlist_doc = await asyncio.to_thread(db_manager.db.collection('quantum_system').doc('watchlist').get)
                if watchlist_doc.exists:
                    w_items = watchlist_doc.to_dict().get('items', [])
                    for item in w_items:
                        w_sym = item.get('symbol', '').replace("-EQ", "")
                        w_info = token_manager.get_stock_info(w_sym)
                        if w_info:
                            w_tok = w_info['token']
                            if w_tok not in current_ltps:
                                l = ws_manager.get_ltp(w_tok) if (ws_manager and is_healthy) else 0
                                if l and l > 0:
                                    current_ltps[w_tok] = l
                                else:
                                    # Use previous logic but commented as per user request? No, this is NEW logic. 
                                    if w_sym + ".NS" not in yf_symbols:
                                        yf_symbols.append(w_sym + ".NS")
                                    token_to_symbol[w_tok] = w_sym + ".NS"
            except Exception as e:
                pass
                
            with trade_manager._lock:
                for t in trade_manager.active_trades:
                    if t.get("instrument_type") == "EQUITY" and t.get("token") not in current_ltps:
                        sym = t.get("symbol", "").replace("-EQ", "")
                        # OLD LOGIC START (COMMENTED OUT)
                        # yf_symbols.append(f"{sym}.NS")
                        # token_to_symbol[t.get("token")] = f"{sym}.NS"
                        # OLD LOGIC END
                        if sym + ".NS" not in yf_symbols:
                            yf_symbols.append(sym + ".NS")
                        token_to_symbol[t.get("token")] = f"{sym}.NS"

            # Check if any active trade token or watchlist token has a missing/zero price in current_ltps
            has_missing_prices = False
            for tok in active_trade_tokens:
                if tok in token_to_symbol and (not ws_manager or not ws_manager.get_ltp(tok)):
                    has_missing_prices = True
                    break
            
            for sym_ns in yf_symbols:
                w_tok = None
                for t_key, s_val in token_to_symbol.items():
                    if s_val == sym_ns:
                        w_tok = t_key
                        break
                if w_tok and (not ws_manager or not ws_manager.get_ltp(w_tok)):
                    has_missing_prices = True
                    break

            if (not is_healthy or has_missing_prices) and yf_symbols:
                # Throttle yfinance calls to once every 10 seconds per loop
                if not hasattr(ltp_broadcaster, "last_yf_time") or time.time() - ltp_broadcaster.last_yf_time > 10:
                    import yfinance as yf
                    import pandas as pd
                    try:
                        raw = await asyncio.to_thread(lambda: yf.download(yf_symbols, period="1d", interval="1m", progress=False))
                        if not raw.empty:
                            if isinstance(raw.columns, pd.MultiIndex) and 'Close' in raw.columns.levels[0]:
                                ltp_broadcaster.last_yf_data = raw['Close'].iloc[-1]
                            elif "Close" in raw.columns:
                                if len(yf_symbols) == 1:
                                    ltp_broadcaster.last_yf_data = pd.Series({yf_symbols[0]: raw["Close"].iloc[-1]})
                                else:
                                    ltp_broadcaster.last_yf_data = raw["Close"].iloc[-1]
                        ltp_broadcaster.last_yf_time = time.time()
                    except Exception as e:
                        print(f"[YF Poll] {e}")
            
            for token in active_trade_tokens:
                if token in current_ltps:
                    continue
                ltp = ws_manager.get_ltp(token) if (ws_manager and is_healthy) else 0
                if not ltp or ltp == 0:
                    # Fallback to yfinance if available
                    symbol_ns = token_to_symbol.get(token)
                    if symbol_ns and hasattr(ltp_broadcaster, "last_yf_data"):
                        try:
                            val = ltp_broadcaster.last_yf_data.get(symbol_ns)
                            if val and not pd.isna(val):
                                ltp = float(val)
                        except: pass

                if not ltp or ltp == 0:
                    if token not in simulated_ltps:
                        entry_premium = 100.0
                        with trade_manager._lock:
                            for t in trade_manager.active_trades:
                                if t.get("token") == token:
                                    entry_premium = t.get("entry", 100.0)
                                    break
                        simulated_ltps[token] = entry_premium
                    # Do not apply fake random drift; just hold the last known price
                    ltp = simulated_ltps[token]
                else:
                    simulated_ltps[token] = ltp
                current_ltps[token] = ltp

            # 2. Monitor open trades (ONLY during real market hours — Mon-Fri, 9:15 AM to 3:30 PM IST)
            # FIX C-4 (IMPROVED): Paper trading mode no longer bypasses market hour check.
            # Previously `or is_paper_trading` caused simulated drift to trigger false SL/TP hits
            # at any hour of the day/night. Now monitoring is strictly market-hours only for both
            # live and paper trading modes.
            now_ist = config.get_ist_time()
            is_market_open = (
                now_ist.weekday() < 5 and  # Monday-Friday only
                dt_time(9, 15) <= now_ist.time() <= dt_time(15, 30)  # 9:15 AM to 3:30 PM IST
            )
            if is_market_open:
                # --- TRAILING SL + TIME EXIT WIRING (from ExecutionEngine) ---
                from backend.engines.execution_engine import ExecutionEngine
                if not hasattr(ltp_broadcaster, '_exec_engines'):
                    ltp_broadcaster._exec_engines = {}  # trade_token -> ExecutionEngine instance

                with trade_manager._lock:
                    for t in trade_manager.active_trades:
                        tok = t.get("token")
                        if not tok or tok not in current_ltps:
                            continue

                        live_price = current_ltps[tok]
                        trade_side = t.get("original_signal", t.get("signal", "BUY"))
                        atr_val = t.get("atr", 0)

                        # Initialize execution engine for this trade if not exists
                        if tok not in ltp_broadcaster._exec_engines:
                            eng = ExecutionEngine()
                            eng.entry_time = t.get("timestamp", time.time() * 1000) / 1000
                            ltp_broadcaster._exec_engines[tok] = eng

                        eng = ltp_broadcaster._exec_engines[tok]

                        entry_price = t.get("actual_entry", t.get("entry", 0))

                        # Partial Profit Booking (50% close at 1:1 RR equivalent 1.0% target)
                        if entry_price > 0 and eng.check_partial_profit(live_price, entry_price, trade_side):
                            original_qty = t.get("qty", 0)
                            partial_qty = original_qty // 2
                            if partial_qty > 0:
                                print(f"[PartialClose] Triggered 50% profit booking for {t.get('symbol')} at {live_price}")
                                t["qty"] = original_qty - partial_qty
                                opp_side_order = "SELL" if t.get("instrument_type") == "OPTIONS" else ("SELL" if trade_side == "BUY" else "BUY")
                                if not is_paper_trading:
                                    try:
                                        time.sleep(0.4)
                                        broker.place_order(t.get("symbol"), t.get("token"), partial_qty, opp_side_order, live_price)
                                    except Exception as p_err:
                                        print(f"[PartialClose Error] Failed to place order: {p_err}")
                                send_push_notification(f"💰 PARTIAL CLOSE: {t.get('symbol')}", f"Booked 50% profit at {live_price}")

                        # Score-Decay Exit (reversal guard)
                        current_score = t.get("current_score", 0)
                        entry_score = t.get("strict_score", 0)
                        if current_score > 0 and eng.check_score_decay_exit(current_score, entry_score):
                            t["sl"] = live_price  # Force exit
                            print(f"[ScoreDecayExit] {t.get('symbol')} score dropped from {entry_score} to {current_score} — forcing exit")

                        # Update trailing SL if ATR is available
                        if atr_val and atr_val > 0:
                            phase = "EXPANSION" if t.get("volume_spike", False) else "NORMAL"
                            new_sl = eng.update_trailing_sl(live_price, atr_val, trade_side, phase)
                            if new_sl:
                                current_sl = t.get("sl", 0)
                                # Only tighten SL (move in favorable direction)
                                if trade_side == "BUY" and new_sl > current_sl:
                                    t["sl"] = round(new_sl, 2)
                                elif trade_side == "SELL" and (current_sl == 0 or new_sl < current_sl):
                                    t["sl"] = round(new_sl, 2)

                        # Time-based exit: close if held > 25 min without momentum
                        if eng.check_time_exit():
                            if entry_price > 0:
                                pnl_pct = (live_price - entry_price) / entry_price * 100
                                if trade_side == "SELL":
                                    pnl_pct = -pnl_pct
                                # Only time-exit if trade is flat or negative
                                if pnl_pct < 0.5:
                                    t["sl"] = live_price  # Force SL hit on next monitor cycle
                                    print(f"[TimeExit] {t.get('symbol')} held >{eng.max_hold_time_mins}min with {pnl_pct:.2f}% PnL — forcing exit")

                # Clean up execution engines for closed trades
                active_tokens = set()
                with trade_manager._lock:
                    for t in trade_manager.active_trades:
                        if t.get("token"):
                            active_tokens.add(t["token"])
                for old_tok in list(ltp_broadcaster._exec_engines.keys()):
                    if old_tok not in active_tokens:
                        del ltp_broadcaster._exec_engines[old_tok]

                # Fix M-5: Throttle monitor_trades DB writes to 1Hz
                now_ts = time.time()
                if not hasattr(ltp_broadcaster, '_last_monitor'):
                    ltp_broadcaster._last_monitor = 0
                    
                if (now_ts - ltp_broadcaster._last_monitor) >= 1.0:
                    ltp_broadcaster._last_monitor = now_ts
                    closed_trades = await asyncio.to_thread(trade_manager.monitor_trades, current_ltps)
                    for trade in (closed_trades or []):
                        send_push_notification(f"🏁 {trade['symbol']} CLOSED: {trade['close_data']['result']}", f"PnL: Rs. {trade['close_data']['pnl']:.2f}")

                # BUG-9 FIX: Auto Square-Off at 3:10 PM for ALL active trades (including equity)
                # trading_loop() only covers F&O engine trades. Equity trades executed manually
                # via /execute-stock-trade are monitored here in ltp_broadcaster.
                if now_ist.hour == 15 and now_ist.minute >= 10:
                    _sq_date = getattr(ltp_broadcaster, '_sq_date', None)
                    if _sq_date != now_ist.date() and trade_manager.active_trades:
                        ltp_broadcaster._sq_date = now_ist.date()
                        sq_count = await asyncio.to_thread(trade_manager.emergency_square_off, current_ltps, get_live_price_fallback)
                        if sq_count > 0:
                            print(f"[AutoSquareOff-Broadcaster] {sq_count} position(s) squared off at 3:10 PM IST")
                            send_push_notification(
                                "⚡ AUTO SQUARE-OFF",
                                f"{sq_count} position(s) auto-closed at 3:10 PM IST to avoid broker penalties"
                            )

            # 3. Adaptive Throttling (Broadcast only if movement > 0.1 points)
            if connected_ws_clients and abs(current_ltp - last_broadcast_ltp) > 0.1:
                last_broadcast_ltp = current_ltp
                
                # FIX 1: Include sentiment, killzone & score in WS payload
                # Frontend trading_provider.dart reads these from WebSocket
                now_time = config.get_ist_time().time()
                ws_sentiment = "Neutral"
                ws_sentiment_score = 0.5
                if signals:
                    ws_sentiment = "Bullish" if signals[-1].get('signal') == "BUY" else "Bearish"
                    ws_sentiment_score = 0.8 if ws_sentiment == "Bullish" else 0.2
                    
                # Create symbol-based ltps for watchlist
                symbol_ltps = {}
                for s_name, s_info in token_manager.stocks_index.items():
                    tok = s_info.get("token")
                    if tok in current_ltps:
                        symbol_ltps[s_name] = current_ltps[tok]
                
                payload = json.dumps({
                    "ltp": current_ltp,
                    "ltps": current_ltps,
                    "symbol_ltps": symbol_ltps,
                    "connected": True,
                    "sentiment": ws_sentiment,
                    "sentiment_score": ws_sentiment_score,
                    "in_killzone": False,
                    "is_active": trading_active,
                    "trades_today": risk_manager.trades_today,
                    "daily_loss": risk_manager.daily_loss,
                    "current_score": ws_current_score,  # Live score — updated on every scan
                })
                for client in list(connected_ws_clients):
                    try: await client.send_text(payload)
                    except Exception: connected_ws_clients.discard(client)

        except Exception as e:
            print(f"[Broadcaster Error]: {e}")
        await asyncio.sleep(0.05) # 20 updates/sec for smooth price movement

# --- ENDPOINTS ---
@app.get("/")
async def root():
    return {"message": "QuantumIndex Backend Running"}

@app.get("/health")
async def health():
    return {"status": "ok", "message": "QuantumIndex Backend Healthy"}

async def refresh_signals():
    global signals
    try:
        from backend.config.firebase_config import get_db
        db = get_db()
        if db:
            from datetime import timezone, timedelta
            ist_tz = timezone(timedelta(hours=5, minutes=30))
            start_of_day_ist = datetime.now(ist_tz).replace(hour=0, minute=0, second=0, microsecond=0)
            start_of_day_ms = int(start_of_day_ist.timestamp() * 1000)
            
            trades_query = db.collection("quantum_trades").where("timestamp", ">=", start_of_day_ms).order_by("timestamp").stream()
            new_signals = []
            for doc in trades_query:
                trade_data = doc.to_dict()
                trade_data['id'] = doc.id
                new_signals.append(trade_data)
            signals = new_signals
    except Exception as e:
        print(f"Error refreshing signals from Firestore (falling back to SQLite): {e}")
        try:
            signals = persistence_manager.get_todays_trades()
        except Exception as sq_err:
            print(f"Failed to fetch todays signals from local SQLite: {sq_err}")

@app.get("/logs")
async def get_logs():
    await refresh_signals()
    return signals

@app.get("/status")
async def get_status():
    global current_ltp
    await refresh_signals()
    
    sentiment = "Neutral"
    sentiment_score = 0.5
    if signals:
        last = signals[-1]
        sentiment = "Bullish" if last['signal'] == "BUY" else "Bearish"
        sentiment_score = 0.8 if sentiment == "Bullish" else 0.2

    can_trade, lock_reason = risk_manager.check_hard_locks() if hasattr(risk_manager, 'check_hard_locks') else (True, None)
    now = config.get_ist_time().time()
    in_killzone = False

    return {
        "is_active": trading_active,
        "paper_trading": config.PAPER_TRADING,
        "signal_count": len(signals),
        "last_signal": signals[-1]['signal'] if signals else "None",
        "daily_loss": risk_manager.daily_loss,
        "trades_today": risk_manager.trades_today,
        "ltp": current_ltp,
        "sentiment": sentiment,
        "sentiment_score": sentiment_score,
        "hard_lock_reason": lock_reason if not can_trade else None,
        "in_killzone": in_killzone,
        "current_score": signals[-1].get('score', 0) if signals else 0
    }

@app.websocket("/ws/market")
async def websocket_market(websocket: WebSocket):
    await websocket.accept()
    connected_ws_clients.add(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_ws_clients.discard(websocket)
    except Exception as e:
        connected_ws_clients.discard(websocket)

@app.post("/toggle-trading")
async def toggle_trading(active: bool):
    global trading_active, trading_loop_task
    trading_active = active
    if trading_active:
        if trading_loop_task is None or trading_loop_task.done():
            trading_loop_task = asyncio.create_task(trading_loop())
            
    # Sync new status directly to Firestore immediately
    await asyncio.to_thread(sync_status_to_db)
    
    persistence_manager.log_event("INFO", "ENGINE_TOGGLED", f"Active: {active}")
    return {"status": "success", "trading_active": trading_active}

@app.get("/settings")
async def get_settings():
    settings = await asyncio.to_thread(db_manager.get_settings)
    return settings or {}

@app.post("/settings")
async def update_settings(settings: dict):
    success = await asyncio.to_thread(db_manager.update_settings, settings)
    return {"status": "success" if success else "error"}


@app.get("/analytics")
async def get_analytics():
    """Returns real analytics from trade_manager."""
    tm = trade_manager
    win_rate = (tm.winning_trades / tm.total_trades * 100) if tm.total_trades > 0 else 0.0
    profit_factor = (tm.gross_profit / tm.gross_loss) if tm.gross_loss > 0 else (tm.gross_profit if tm.gross_profit > 0 else 0.0)
    avg_winner = (tm.gross_profit / tm.winning_trades) if tm.winning_trades > 0 else 0.0
    avg_loser = (tm.gross_loss / tm.losing_trades) if tm.losing_trades > 0 else 0.0

    return {
        "win_rate": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "avg_winner": round(avg_winner, 2),
        "avg_loser": round(avg_loser, 2),
        "total_trades": tm.total_trades,
        "winning_trades": tm.winning_trades,
        "losing_trades": tm.losing_trades,
        "realized_pnl": round(tm.realized_pnl, 2),
        "total_charges": round(tm.total_charges, 2),
        "max_drawdown": round(tm.max_drawdown, 2),
        "pnl_history": tm.pnl_history[-20:]
    }

@app.get("/pnl-history")
def get_pnl_history():
    return trade_manager.pnl_history

# Legacy /backtest endpoint (kept for compatibility)
@app.post("/backtest")
async def run_backtest_endpoint(days: int = 30):
    from backend.analytics.analytics_engine import AnalyticsEngine
    from backend.backtesting.backtest_engine import BacktestEngine
    engine = AnalyticsEngine()
    df = await asyncio.to_thread(engine.fetch_recent_trades, days)
    if df.empty:
        return {"error": "No trades to backtest"}
    bt = BacktestEngine(initial_capital=100000)
    for _, row in df.iterrows():
        if row.get('status') == 'CLOSED' and row.get('entry') and row.get('exit_price'):
            bt.execute_trade(row['entry'], row['exit_price'], row.get('qty', 50), row.get('signal', 'BUY'))
    return bt.get_metrics()

@app.post("/api/backtest/run")
async def run_equity_backtest_api(
    symbol:      str   = "RELIANCE",
    days:        int   = 60,
    capital:     float = 100_000.0,
    instrument:  str   = "EQUITY",      # EQUITY | FUTURES | OPTIONS
    mode:        str   = "INTRADAY",    # INTRADAY | POSITIONAL
    risk_pct:    float = 0.01,          # 1% risk per trade
    atr_sl:      float = 2.0,
    atr_tp:      float = 4.0,
    lot_size:    int   = 1,
    slippage_bps:float = 2.0,
    monte_carlo: bool  = True,
    walk_fwd:    bool  = False,
):
    """
    Institutional-Grade Quantum Backtest Engine v3.0.

    Audited for:
    - No look-ahead bias (entry at NEXT candle open)
    - Realistic NSE charges (brokerage, STT, exchange, SEBI, GST, stamp)
    - ATR-based dynamic slippage
    - Intraday session rules (9:20–14:30 entry, 15:10 auto sq-off)
    - Data validation (gaps, duplicates, holidays, OHLC sanity)
    - Per-candle signal audit log
    - Monte Carlo confidence intervals (1000 simulations)
    - All 18 performance metrics

    Parameters
    ----------
    symbol      : NSE symbol (e.g. RELIANCE, NIFTY, BANKNIFTY)
    days        : Calendar days of history (60–180 recommended)
    capital     : Initial capital in ₹
    instrument  : EQUITY | FUTURES | OPTIONS
    mode        : INTRADAY | POSITIONAL
    risk_pct    : Risk per trade as fraction of capital (0.01 = 1%)
    atr_sl      : ATR multiplier for stop-loss
    atr_tp      : ATR multiplier for take-profit
    lot_size    : Lot size for F&O (1 for equity)
    slippage_bps: Slippage in basis points (2 bps = 0.02%)
    monte_carlo : Run Monte Carlo simulations (1000 runs)
    walk_fwd    : Run walk-forward optimization (slower)
    """
    from backend.backtesting.quantum_backtest_engine import run_quantum_backtest
    try:
        result = await asyncio.to_thread(
            run_quantum_backtest,
            symbol, days, capital, instrument, mode,
            risk_pct, atr_sl, atr_tp, lot_size, slippage_bps,
            60,           # min_score
            monte_carlo,  # run_monte_carlo
            walk_fwd,     # run_walk_fwd
            False,        # verbose
        )
        return result
    except Exception as e:
        import traceback
        return {"status": "error", "error": str(e), "traceback": traceback.format_exc()[-500:]}

    
@app.get("/pnl")
async def get_pnl():
    """Returns real PnL summary from trade_manager."""
    tm = trade_manager
    return {
        "realized_pnl": round(tm.realized_pnl, 2),
        "total_charges": round(tm.total_charges, 2),
        # FIX M-3: realized_pnl is already NET of charges (net_pnl = pnl - charges in monitor_trades)
        # Previously was: tm.realized_pnl - tm.total_charges which double-deducted brokerage
        "net_pnl": round(tm.realized_pnl, 2),
        "gross_pnl": round(tm.realized_pnl + tm.total_charges, 2),
        "total_trades": tm.total_trades,
        "winning_trades": tm.winning_trades,
        "losing_trades": tm.losing_trades,
        "max_drawdown": round(tm.max_drawdown, 2),
        "pnl_history": tm.pnl_history[-20:],
        "active_trades": len(tm.active_trades)
    }

@app.post("/test-trade")
async def trigger_test_trade():
    global current_ltp
    ltp = current_ltp if current_ltp > 0 else 24150.0
    
    # Check instrument type from settings
    settings = db_manager.get_settings() or {}
    instrument_type = settings.get("instrument_type", "FUTURES")
    capital_limit = float(settings.get("capital_limit", 10000))
    
    signal_data = {
        "signal": "BUY",
        "symbol": "NIFTY",
        "entry": ltp,
        "actual_entry": ltp + 0.5,
        "sl": ltp - 3.0,
        "tp": ltp + 3.0,
        "reason": "TEST - Option/Future Flow Verification",
        "is_paper": True,
        "timestamp": int(time.time() * 1000)
    }
    
    if instrument_type == "OPTIONS":
        option_contract = token_manager.get_atm_option("NIFTY", ltp, "CE")
        if not option_contract:
            return {"status": "error", "message": "No active option contract found"}
            
        trade_token = option_contract["token"]
        trade_symbol = option_contract["symbol"]
        lotsize = option_contract["lotsize"]
        
        # Premium estimation
        option_premium = 100.0  # Standard test premium
        afford_lots = int(capital_limit / (option_premium * lotsize))
        if afford_lots <= 0:
            afford_lots = 1
        qty = afford_lots * lotsize
        
        if ws_manager:
            ws_manager.subscribe_token(trade_token, 2)
            
        signal_data.update({
            'token': trade_token,
            'symbol': trade_symbol,
            'qty': qty,
            'instrument_type': "OPTIONS",
            'original_signal': "BUY",
            'underlying_token': token_manager.get_token("NIFTY"),
            'underlying_entry': ltp,
            'underlying_sl': ltp - 3.0,
            'underlying_tp': ltp + 3.0,
            'actual_entry': option_premium,  # Entry price is the premium
            'sl': option_premium - 15.0,      # Option premium targets
            'tp': option_premium + 30.0,
        })
    else:
        signal_data.update({
            'token': token_manager.get_token("NIFTY"),
            'qty': 50,
            'instrument_type': "FUTURES",
            'original_signal': "BUY"
        })
        
    signals.append(signal_data)
    doc_id = db_manager.save_signal(signal_data)
    if doc_id:
        trade_manager.add_trade(signal_data, doc_id)
        
    return {"status": "success", "message": "Test trade injected", "trade": signal_data}

@app.post("/emergency-kill")
async def emergency_kill():
    """Emergency Kill Switch: Flatten all positions and stop trading."""
    global trading_active
    trading_active = False
    persistence_manager.log_event("CRITICAL", "KILL_SWITCH_ACTIVATED", "User triggered emergency shutdown")
    # FIX: Pass real LTP dict so trade PnL is calculated correctly on close
    ltp_dict = ws_manager.ltp_data if ws_manager else {}
    count = trade_manager.emergency_square_off(ltp_dict, get_live_price_fallback)
    broker.square_off_all()
    await asyncio.to_thread(sync_status_to_db)  # FIX: was not awaited
    return {"status": "killed", "trades_closed": count}

@app.post("/square-off")
async def square_off():
    """Emergency Exit: Closes all orders on broker and updates internal state."""
    global trading_active
    trading_active = False
    broker.square_off_all()
    ltp_dict = ws_manager.ltp_data if ws_manager else {}
    count = trade_manager.emergency_square_off(ltp_dict, get_live_price_fallback)
    await asyncio.to_thread(sync_status_to_db)  # FIX: was not awaited
    return {"status": "success", "message": f"Square Off: {count} trades closed."}

@app.get("/search-stocks")
async def search_stocks(q: str = ""):
    query = q.upper().strip()
    if not query:
        return []
    results = []
    for name, info in token_manager.stocks_index.items():
        if query in name or query in info.get("symbol", "").upper():
            results.append(info)
    # Sort results: exact prefix matches first, then by name length
    results.sort(key=lambda x: (not x["name"].startswith(query), len(x["name"])))
    return results[:30]

# Top liquid NSE F&O + NIFTY 500 stocks for smart screener
# Cleaned: removed delisted (GRUH), merged (MINDTREE→LTIM), invalid symbols (FIVE STAR, ROYALENFIELD, HEXAWARE, METAHEALTH)
SCREENER_UNIVERSE = [
    # --- NIFTY 50 CORE ---
    "RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK","SBIN","BHARTIARTL","WIPRO","TATASTEEL",
    "ADANIPORTS","LT","AXISBANK","KOTAKBANK","BAJFINANCE","HCLTECH","SUNPHARMA","ONGC",
    "MARUTI","NTPC","POWERGRID","COALINDIA","TITAN","BAJAJFINSV","M&M","NESTLEIND",
    "TECHM","ULTRACEMCO","ASIANPAINT","JSWSTEEL","HINDALCO","GRASIM","DRREDDY","DIVISLAB",
    "HDFCLIFE","SBILIFE","CIPLA","EICHERMOT","APOLLOHOSP","TATACONSUM","BRITANNIA",
    "INDUSINDBK","HEROMOTOCO","BPCL","TRENT","SHREECEM","TATAMOTORS",
    # --- BANKING & FINANCE ---
    "INDIGO","IRCTC","ZOMATO","NYKAA","PAYTM",
    "PNB","CANBK","FEDERALBNK","IDFCFIRSTB","BANDHANBNK","AUBANK",
    "BANKBARODA","MUTHOOTFIN","CHOLAFIN","SHRIRAMFIN","MANAPPURAM",
    "LICHSGFIN","PNBHOUSING","CANFINHOME","ANGELONE","MOTILALOFS",
    # --- IT ---
    "LTIM","OFSS","MPHASIS","LTTS","PERSISTENT","COFORGE","KPITTECH","CYIENT",
    # --- INFRA & DEFENCE ---
    "HAL","BEL","BHEL","SAIL","NMDC","GAIL","IGL","MGL","PETRONET","IOC","HPCL",
    # --- AUTO ---
    "BAJAJ-AUTO","TVSMOTORS","ASHOKLEY","ESCORTS","MOTHERSON","BALKRISIND",
    "MRF","APOLLOTYRE","BOSCHLTD","SUNDRMFAST",
    # --- POWER & ENERGY ---
    "TATAPOWER","ADANIGREEN","TORNTPOWER","CESC","NHPC","SJVN","SUZLON",
    # --- CONSUMER ---
    "DABUR","MARICO","EMAMILTD","COLPAL","JYOTHYLAB","VBL","RADICO","HAVELLS",
    "VOLTAS","CROMPTON","POLYCAB","GODREJCP","PIIND",
    # --- PHARMA & HEALTH ---
    "METROPOLIS","THYROCARE","ASTERDM",
    # --- CHEMICALS ---
    "DEEPAKNITR","GNFC","COROMANDEL","RALLIS","ASTRAL",
]


@app.get("/smart-screener")
async def smart_screener(max_price: float = 500.0, min_score: int = 70):
    """
    Bulk screen NSE stocks: fetch prices via yfinance, filter by max_price,
    run full analysis sequentially, return stocks with score >= min_score (default 70).
    Score 70+ = strong setup. Score 90+ = very high conviction.
    """
    import yfinance as yf
    from backend.engines.stock_analyzer import stock_analyzer

    # Ensure active session if possible, otherwise run offline/mock
    if not broker.session:
        try:
            broker.login()
        except Exception as e:
            print(f"[SmartScreener] Startup-fallback broker login failed: {e}")

    api_client = broker.smart_api if broker.session else None

    # Step 1: Bulk price fetch via yfinance
    tickers = [f"{s}.NS" for s in SCREENER_UNIVERSE]
    price_map = {}
    try:
        import yfinance as yf
        raw = await asyncio.to_thread(
            lambda: yf.download(tickers, period="2d", interval="1d", progress=False, threads=False)
        )
        import pandas as pd
        if not raw.empty:
            close_row = None
            if isinstance(raw.columns, pd.MultiIndex) and 'Close' in raw.columns.levels[0]:
                close_row = raw['Close'].iloc[-1]
            elif "Close" in raw.columns:
                # Fallback if only 1 ticker or older yfinance
                if len(tickers) == 1:
                    close_row = pd.Series({tickers[0]: raw["Close"].iloc[-1]})
                else:
                    close_row = raw["Close"].iloc[-1]
            
            if close_row is not None and not close_row.empty:
                for sym in SCREENER_UNIVERSE:
                    col = f"{sym}.NS"
                    try:
                        val = close_row.get(col)
                        if val is not None and str(val) != 'nan':
                            price_map[sym] = float(val)
                    except Exception:
                        pass
    except Exception as e:
        print(f"[SmartScreener] Bulk price fetch failed: {e}. Proceeding without price filter.")

    # Step 2: Filter by price (if price_map empty, scan all to avoid empty results)
    if price_map:
        affordable = [s for s in SCREENER_UNIVERSE if price_map.get(s, 9999) <= max_price]
    else:
        affordable = list(SCREENER_UNIVERSE)  # No prices fetched — scan all anyway

    if not affordable:
        return {"status": "success", "results": [], "scanned": 0, "affordable": 0,
                "message": f"No stocks found under ₹{max_price:.0f}"}

    index_trends = {}
    try:
        import yfinance as yf
        index_tickers = ["^NSEI", "^NSEBANK", "^CNXIT", "^CNXENERGY", "^CNXFIN", "^CNXMETAL", "^CNXPHARMA", "^CNXFMCG", "^CNXAUTO", "^CNXINFRA", "^CNXREALTY"]
        
        async def fetch_index_trend(ticker):
            try:
                t_obj = yf.Ticker(ticker)
                fast_info = await asyncio.to_thread(lambda: t_obj.fast_info)
                last_price = float(getattr(fast_info, "last_price", 0))
                prev_close = float(getattr(fast_info, "previous_close", 0))
                if last_price > 0 and prev_close > 0:
                    return ticker, ("Bullish" if last_price > prev_close else "Bearish")
            except Exception as ex:
                print(f"[IndexTrend] Failed to fetch {ticker}: {ex}")
            return ticker, "Neutral"

        tasks = [fetch_index_trend(t) for t in index_tickers]
        index_trends = dict(await asyncio.gather(*tasks))
    except Exception as e:
        print(f"[SmartScreener] Parallel index trends fetch failed: {e}")

    # Step 3: Run full analysis sequentially (throttled for AngelOne 3 req/sec)
    async def analyze_one(sym):
        try:
            fallback_price = price_map.get(sym, 0.0)
            res = await stock_analyzer.analyze_stock(sym, api_client, index_trends, provided_ltp=fallback_price)
            if res and res.get("status") == "success":
                return res
        except Exception as e:
            print(f"[SmartScreener] {sym} analysis error: {e}")
        return None

    results_raw = []
    cap = min(len(affordable), 25)  # Scan up to 25 affordable stocks
    for sym in affordable[:cap]:
        res = await analyze_one(sym)
        if res:
            results_raw.append(res)
        if api_client:
            await asyncio.sleep(0.75)  # stay below 3 req/sec

    # Step 4: Filter by score >= min_score and actionable (VWAP/Event pass)
    top_picks = [
        {
            "symbol": r["symbol"],
            "ltp": round(float(r.get("ltp") or 0.0), 2),
            "score": r.get("score", 0),
            # BUG-3 FIX: Include strict_score/strict_signal/strict_breakdown so
            # the frontend SmartScreener card can display Whale Score correctly.
            "strict_score": r.get("strict_score", r.get("score", 0)),
            "strict_signal": r.get("strict_signal", "BUY" if r.get("htf_trend") == "Bullish" else "SELL"),
            "strict_breakdown": r.get("breakdown", {}),
            "htf_trend": r.get("htf_trend", "NEUTRAL"),
            "value_zone": r.get("value_zone", False),
            "signal": r.get("strict_signal", "BUY" if r.get("htf_trend") == "Bullish" else "SELL"),
            "reason": r.get("reason", ""),
            "total_buyers": r.get("total_buyers", 0),
            "total_sellers": r.get("total_sellers", 0),
            "vwap": round(float(r.get("vwap") or 0.0), 2),
            "volume_breakout": r.get("volume_breakout", False),
            "ohol_setup": r.get("ohol_setup", "None")
        }
        for r in results_raw if r and r.get("score", 0) >= min_score and r.get("actionable", False)
    ]
    # Sort: highest score first, then lowest price
    top_picks.sort(key=lambda x: (-x["score"], x["ltp"]))

    return {
        "status": "success",
        "results": top_picks[:15],  # Return top 15 picks
        "scanned": len(results_raw),
        "affordable": len(affordable),
        "min_score_used": min_score,
    }

@app.get("/api/scanner/scan")
async def scan_stock_signals(symbol: str):
    """
    Returns signals for a stock, automatically routed through 
    the best engine based on trend strength (ADX).
    """
    symbol = symbol.upper()
    if not symbol.endswith(".NS"):
        ticker = symbol + ".NS"
        base_symbol = symbol
    else:
        ticker = symbol
        base_symbol = symbol.replace(".NS", "")
    
    # Check cache first
    cached = _get_cached_scan(base_symbol)
    if cached:
        return cached
    
    token = token_manager.get_token(base_symbol)
    exchange = token_manager.get_exchange(base_symbol)
    
    # Try fetching data via AngelOne API first to bypass yfinance IP blocks
    df = None
    nifty_df = None
    
    if not broker.session:
        try:
            broker.login()
        except Exception as e:
            print(f"[Scan Endpoint] Broker login failed: {e}")
            
    if broker.session:
        if token:
            df = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "FIVE_MINUTE", 5, exchange)
            
        # Fetch Nifty data for Strict Checklist Macro Filter
        nifty_token = token_manager.get_token("NIFTY")
        if nifty_token:
            nifty_df = await asyncio.to_thread(fetch_historical_data, broker.smart_api, nifty_token, "FIFTEEN_MINUTE", 5, "NSE")
            
    if df is None or df.empty:
        try:
            import yfinance as yf
            # FIX: Add 15-second timeout — without it, a rate-limited Render IP hangs indefinitely
            df = await asyncio.wait_for(
                asyncio.to_thread(lambda: yf.Ticker(ticker).history(period="5d", interval="5m")),
                timeout=15.0
            )
        except asyncio.TimeoutError:
            print(f"[Scan Endpoint] yfinance timed out after 15s for {ticker} (IP rate-limited)")
            df = None
        except Exception as e:
            print(f"[Scan Endpoint] yfinance fallback failed for {ticker}: {e}")
            df = None
            
    if df is None or df.empty:
        return {"status": "error", "message": "Failed to fetch stock data (broker session expired and yfinance rate-limited)"}
            
    # Standardize columns to lowercase for engine consistency
    df.columns = [c.lower() for c in df.columns]

    is_nifty_bullish = True
    if nifty_df is not None and not nifty_df.empty:
        from backend.indicators.technical_indicators import TechnicalIndicators
        nifty_df = TechnicalIndicators.add_ema(nifty_df, 50)
        last_nifty = nifty_df.iloc[-1]
        if last_nifty['close'] < last_nifty['EMA_50']:
            is_nifty_bullish = False
            
    # Extract current LTP from historical data
    current_price = 0.0
    if df is not None and not df.empty:
        for col in ['close', 'Close']:
            if col in df.columns:
                current_price = float(df.iloc[-1][col])
                break

    # Fetch live market depth for buyer/seller ratio
    market_depth_buyer_ratio = 1.0
    if broker.session and token:
        try:
            depth = await asyncio.to_thread(broker.get_market_depth, exchange, base_symbol, token)
            if depth:
                tot_buy = depth.get("totBuyQuan", 0)
                tot_sell = depth.get("totSellQuan", 0)
                if tot_sell > 0:
                    market_depth_buyer_ratio = tot_buy / tot_sell
        except Exception as e:
            print(f"[Scan Endpoint] Failed to fetch market depth for {base_symbol}: {e}")

    # Fetch HTF data for MTF Engine
    df_15m = None
    df_1h = None
    if broker.session and token:
        try:
            df_15m = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "FIFTEEN_MINUTE", 5, exchange)
            df_1h = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "ONE_HOUR", 10, exchange)
        except Exception:
            pass
    if df_15m is None or df_15m.empty:
        try:
            import yfinance as yf
            df_15m = await asyncio.to_thread(lambda: yf.Ticker(ticker).history(period="10d", interval="15m"))
        except Exception:
            pass
    if df_1h is None or df_1h.empty:
        try:
            import yfinance as yf
            df_1h = await asyncio.to_thread(lambda: yf.Ticker(ticker).history(period="20d", interval="1h"))
        except Exception:
            pass

    # Run all engines to get structured results
    from backend.engines.structure_engine import StructureEngine
    from backend.engines.candlestick_engine import candlestick_engine
    from backend.engines.mtf_engine import mtf_engine
    from backend.engines.volume_engine import VolumeEngine
    from backend.engines.momentum_engine import MomentumEngine
    from backend.engines.trend_engine import TrendEngine

    structure_engine = StructureEngine()
    volume_engine = VolumeEngine()
    momentum_engine = MomentumEngine()
    trend_engine = TrendEngine()

    structure_result = structure_engine.analyze(df)
    candle_result = candlestick_engine.analyze(df)
    mtf_result = mtf_engine.analyze(df, df, df_15m, df_1h)
    volume_result = volume_engine.analyze(df)
    momentum_result = momentum_engine.analyze(df)
    trend_result = trend_engine.analyze(df)

    strict_result = await asyncio.to_thread(
        strict_checklist_engine.evaluate, 
        ticker, 
        df.copy(), 
        is_nifty_bullish=is_nifty_bullish,
        market_depth_buyer_ratio=market_depth_buyer_ratio,
        structure_result=structure_result,
        candle_result=candle_result,
        mtf_result=mtf_result,
        volume_result=volume_result,
        momentum_result=momentum_result,
        trend_direction=trend_result
    )
    
    # Update global score so it gets broadcast via WebSocket + written to Firestore
    global ws_current_score
    ws_current_score = strict_result.get("strict_score", 0)

    # Return directly from strict_checklist_engine
    result = {
        "status": "success",
        "symbol": base_symbol,
        "ltp": current_price,
        "strict_signal": strict_result.get("strict_signal", "NONE"),
        "strict_score": strict_result.get("strict_score", 0),
        "breakdown": strict_result.get("breakdown", {}),
        "strict_breakdown": strict_result.get("breakdown", {})
    }
    _set_cached_scan(base_symbol, result)
    asyncio.create_task(check_and_trigger_auto_execution(
        base_symbol,
        strict_result.get("strict_signal", "NONE"),
        current_price,
        strict_result.get("strict_score", 0)
    ))
    return result

@app.get("/api/scanner/batch-scan")
async def batch_scan_signals(symbols: str = ""):
    """
    Batch scan multiple symbols in parallel. Accepts comma-separated symbols.
    Uses cache to avoid redundant computation. Returns results for all symbols.
    """
    if not symbols:
        return {"status": "error", "message": "No symbols provided"}
    
    symbol_list = [s.strip().upper().replace(".NS", "") for s in symbols.split(",") if s.strip()]
    if not symbol_list:
        return {"status": "error", "message": "No valid symbols provided"}
    
    # Return cached results immediately, collect uncached symbols
    results = {}
    uncached_symbols = []
    for sym in symbol_list:
        cached = _get_cached_scan(sym)
        if cached:
            results[sym] = cached
        else:
            uncached_symbols.append(sym)
    
    if not uncached_symbols:
        return {"status": "success", "results": results}
    
    # Ensure broker is logged in
    if not broker.session:
        try:
            broker.login()
        except Exception as e:
            print(f"[Batch Scan] Broker login failed: {e}")
    
    # Fetch Nifty data ONCE
    nifty_df = None
    is_nifty_bullish = True
    if broker.session:
        nifty_token = token_manager.get_token("NIFTY")
        if nifty_token:
            try:
                nifty_df = await asyncio.to_thread(fetch_historical_data, broker.smart_api, nifty_token, "FIFTEEN_MINUTE", 5, "NSE")
                if nifty_df is not None and not nifty_df.empty:
                    from backend.indicators.technical_indicators import TechnicalIndicators
                    nifty_df = TechnicalIndicators.add_ema(nifty_df, 50)
                    last_nifty = nifty_df.iloc[-1]
                    if last_nifty['close'] < last_nifty['EMA_50']:
                        is_nifty_bullish = False
            except Exception as e:
                print(f"[Batch Scan] Failed to fetch Nifty: {e}")
    
    # Fetch batch market depth for all uncached symbols
    market_depths = {}
    if broker.session and uncached_symbols:
        try:
            tokens_to_fetch = []
            for s in uncached_symbols:
                t = token_manager.get_token(s)
                if t:
                    tokens_to_fetch.append(str(t))
            if tokens_to_fetch:
                exchangeTokens = {"NSE": tokens_to_fetch}
                res = await asyncio.to_thread(broker.smart_api.getMarketData, "FULL", exchangeTokens)
                if res and res.get('status') and res.get('data'):
                    data_list = res.get('data', {}).get('fetched', [])
                    for item in data_list:
                        tok_str = str(item.get('symbolToken'))
                        market_depths[tok_str] = {
                            "totBuyQuan": item.get("totBuyQuan", 0),
                            "totSellQuan": item.get("totSellQuan", 0)
                        }
        except Exception as e:
            print(f"[Batch Scan] Failed to fetch batch market depth: {e}")
    
    # Process uncached symbols in parallel with semaphore
    sem = asyncio.Semaphore(3)  # Max 3 concurrent to respect API rate limits
    
    async def scan_one(sym):
        async with sem:
            try:
                ticker = f"{sym}.NS"
                token = token_manager.get_token(sym)
                exchange = token_manager.get_exchange(sym) or "NSE"
                
                df = None
                if broker.session and token:
                    df = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "FIVE_MINUTE", 5, exchange)
                    await asyncio.sleep(0.35)  # Rate limit
                
                if df is None or df.empty:
                    try:
                        import yfinance as yf
                        df = await asyncio.to_thread(lambda t=ticker: yf.Ticker(t).history(period="5d", interval="5m"))
                    except Exception:
                        return sym, None
                
                if df is None or df.empty:
                    return sym, None
                
                df.columns = [c.lower() for c in df.columns]
                
                # Market depth
                market_depth_buyer_ratio = 1.0
                if token and str(token) in market_depths:
                    depth_info = market_depths[str(token)]
                    tot_buy = depth_info.get("totBuyQuan", 0)
                    tot_sell = depth_info.get("totSellQuan", 0)
                    if tot_sell > 0:
                        market_depth_buyer_ratio = tot_buy / tot_sell
                
                # Run ALL engines (full parity with /api/scanner/scan)
                from backend.engines.structure_engine import StructureEngine
                from backend.engines.candlestick_engine import candlestick_engine
                from backend.engines.volume_engine import VolumeEngine
                from backend.engines.momentum_engine import MomentumEngine
                from backend.engines.trend_engine import TrendEngine
                from backend.engines.mtf_engine import mtf_engine
                
                structure_engine = StructureEngine()
                volume_engine = VolumeEngine()
                momentum_engine = MomentumEngine()
                trend_engine = TrendEngine()
                
                structure_result = structure_engine.analyze(df)
                candle_result = candlestick_engine.analyze(df)
                volume_result = volume_engine.analyze(df)
                momentum_result = momentum_engine.analyze(df)
                trend_result = trend_engine.analyze(df)
                
                # Fetch HTF data for MTF
                df_15m = None
                df_1h = None
                if broker.session and token:
                    try:
                        df_15m = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "FIFTEEN_MINUTE", 5, exchange)
                        await asyncio.sleep(0.35)
                        df_1h = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "ONE_HOUR", 10, exchange)
                        await asyncio.sleep(0.35)
                    except Exception:
                        pass
                
                mtf_result = mtf_engine.analyze(df, df, df_15m, df_1h)
                
                strict_result = await asyncio.to_thread(
                    strict_checklist_engine.evaluate,
                    ticker, df.copy(),
                    is_nifty_bullish=is_nifty_bullish,
                    market_depth_buyer_ratio=market_depth_buyer_ratio,
                    structure_result=structure_result,
                    candle_result=candle_result,
                    mtf_result=mtf_result,
                    volume_result=volume_result,
                    momentum_result=momentum_result,
                    trend_direction=trend_result
                )
                
                current_price = float(df['close'].iloc[-1]) if 'close' in df.columns else 0.0
                
                scan_result = {
                    "status": "success",
                    "symbol": sym,
                    "ltp": current_price,
                    "strict_signal": strict_result.get("strict_signal", "NONE"),
                    "strict_score": strict_result.get("strict_score", 0),
                    "breakdown": strict_result.get("breakdown", {}),
                    "strict_breakdown": strict_result.get("breakdown", {})
                }
                _set_cached_scan(sym, scan_result)
                asyncio.create_task(check_and_trigger_auto_execution(
                    sym,
                    strict_result.get("strict_signal", "NONE"),
                    current_price,
                    strict_result.get("strict_score", 0)
                ))
                return sym, scan_result
            except Exception as e:
                print(f"[Batch Scan] Error processing {sym}: {e}")
                return sym, None
    
    # Run all uncached in parallel
    tasks = [scan_one(sym) for sym in uncached_symbols]
    scan_results = await asyncio.gather(*tasks)
    
    for sym, result in scan_results:
        if result:
            results[sym] = result
    
    return {"status": "success", "results": results}

@app.get("/api/scanner/bulk-scan")
async def bulk_scan_signals(min_price: float = 0.0, max_price: float = 3000.0):
    """
    Runs the Auto-Router Engine across the entire SCREENER_UNIVERSE 
    and returns only the stocks that have actionable signals today and are below max_price.
    Uses AngelOne API sequentially to prevent yfinance IP blocks.
    """
    active_trades = []
    
    # Ensure broker is logged in
    if not broker.session:
        try:
            broker.login()
        except Exception as e:
            print(f"[Bulk Scan] Broker login failed: {e}")

    # Fetch Nifty data ONCE for the entire bulk scan (Macro Filter)
    nifty_df = None
    is_nifty_bullish = True
    if broker.session:
        nifty_token = token_manager.get_token("NIFTY")
        if nifty_token:
            try:
                nifty_df = await asyncio.to_thread(fetch_historical_data, broker.smart_api, nifty_token, "FIFTEEN_MINUTE", 5, "NSE")
                if nifty_df is not None and not nifty_df.empty:
                    from backend.indicators.technical_indicators import TechnicalIndicators
                    nifty_df = TechnicalIndicators.add_ema(nifty_df, 50)
                    last_nifty = nifty_df.iloc[-1]
                    if last_nifty['close'] < last_nifty['EMA_50']:
                        is_nifty_bullish = False
            except Exception as e:
                print(f"[Bulk Scan] Failed to fetch Nifty: {e}")

    # 1. Pre-filter by price using yfinance to save time and API limits
    affordable_symbols = list(SCREENER_UNIVERSE)
    try:
        import yfinance as yf
        import pandas as pd
        tickers = [f"{s}.NS" for s in SCREENER_UNIVERSE]
        raw = await asyncio.to_thread(
            lambda: yf.download(tickers, period="2d", interval="1d", progress=False, threads=False)
        )
        if not raw.empty:
            close_row = None
            if isinstance(raw.columns, pd.MultiIndex) and 'Close' in raw.columns.levels[0]:
                close_row = raw['Close'].iloc[-1]
            elif "Close" in raw.columns:
                if len(tickers) == 1:
                    close_row = pd.Series({tickers[0]: raw["Close"].iloc[-1]})
                else:
                    close_row = raw["Close"].iloc[-1]
            
            if close_row is not None and not close_row.empty:
                affordable_symbols = []
                for sym in SCREENER_UNIVERSE:
                    try:
                        val = close_row.get(f"{sym}.NS")
                        if val is not None and str(val) != 'nan' and min_price <= float(val) <= max_price:
                            affordable_symbols.append(sym)
                    except Exception:
                        pass
    except Exception as e:
        print(f"[Bulk Scan] Fast price filter failed: {e}")
        
    # Cap to max 15 stocks to prevent frontend timeouts
    scan_list = affordable_symbols[:15]

    # Fetch batch market depth for all selected stocks to avoid rate limit issues
    market_depths = {}
    if broker.session and scan_list:
        try:
            tokens_to_fetch = []
            for s in scan_list:
                t = token_manager.get_token(s.replace(".NS", ""))
                if t:
                    tokens_to_fetch.append(str(t))
            if tokens_to_fetch:
                exchangeTokens = {"NSE": tokens_to_fetch}
                res = await asyncio.to_thread(broker.smart_api.getMarketData, "FULL", exchangeTokens)
                if res and res.get('status') and res.get('data'):
                    data_list = res.get('data', {}).get('fetched', [])
                    for item in data_list:
                        tok_str = str(item.get('symbolToken'))
                        market_depths[tok_str] = {
                            "totBuyQuan": item.get("totBuyQuan", 0),
                            "totSellQuan": item.get("totSellQuan", 0)
                        }
        except Exception as e:
            print(f"[Bulk Scan] Failed to fetch batch market depth: {e}")

    sem = asyncio.Semaphore(5)  # Max 5 concurrent — balanced between speed and API rate limits
    
    async def scan_one(sym):
        async with sem:
            try:
                base_symbol = sym.replace(".NS", "")
                ticker = f"{base_symbol}.NS"
                
                # Check cache first
                cached = _get_cached_scan(base_symbol)
                if cached:
                    return cached
                
                df = None
                token = None
                exchange = "NSE"
                if broker.session:
                    token = token_manager.get_token(base_symbol)
                    exchange = token_manager.get_exchange(base_symbol)
                    if token:
                        df = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "FIVE_MINUTE", 5, exchange)
                        await asyncio.sleep(0.35)  # Rate limit
                        
                if df is None or df.empty:
                    try:
                        import yfinance as yf
                        df = await asyncio.to_thread(lambda: yf.Ticker(ticker).history(period="5d", interval="5m"))
                    except Exception as e:
                        print(f"[Bulk Scan] yfinance fallback failed for {ticker}: {e}")
    
                if df is not None and not df.empty:
                    df.columns = [c.lower() for c in df.columns]
                    market_depth_buyer_ratio = 1.0
                    if token and str(token) in market_depths:
                        depth_info = market_depths[str(token)]
                        tot_buy = depth_info.get("totBuyQuan", 0)
                        tot_sell = depth_info.get("totSellQuan", 0)
                        if tot_sell > 0:
                            market_depth_buyer_ratio = tot_buy / tot_sell
    
                    # Run ALL engines (full parity with /api/scanner/scan)
                    from backend.engines.structure_engine import StructureEngine
                    from backend.engines.candlestick_engine import candlestick_engine
                    from backend.engines.volume_engine import VolumeEngine
                    from backend.engines.momentum_engine import MomentumEngine
                    from backend.engines.trend_engine import TrendEngine
                    from backend.engines.mtf_engine import mtf_engine
    
                    structure_engine = StructureEngine()
                    volume_engine = VolumeEngine()
                    momentum_engine = MomentumEngine()
                    trend_engine = TrendEngine()
    
                    structure_result = structure_engine.analyze(df)
                    candle_result = candlestick_engine.analyze(df)
                    volume_result = volume_engine.analyze(df)
                    momentum_result = momentum_engine.analyze(df)
                    trend_result = trend_engine.analyze(df)
                    
                    # Fetch HTF data for MTF Engine to make scores strictly consistent
                    df_15m = None
                    df_1h = None
                    if broker.session and token:
                        try:
                            df_15m = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "FIFTEEN_MINUTE", 5, exchange)
                            await asyncio.sleep(0.35)
                            df_1h = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "ONE_HOUR", 10, exchange)
                            await asyncio.sleep(0.35)
                        except Exception:
                            pass
                    
                    mtf_result = mtf_engine.analyze(df, df, df_15m, df_1h)
    
                    strict_result = await asyncio.to_thread(
                        strict_checklist_engine.evaluate, 
                        ticker, 
                        df.copy(), 
                        is_nifty_bullish=is_nifty_bullish,
                        market_depth_buyer_ratio=market_depth_buyer_ratio,
                        structure_result=structure_result,
                        candle_result=candle_result,
                        mtf_result=mtf_result,
                        volume_result=volume_result,
                        momentum_result=momentum_result,
                        trend_direction=trend_result
                    )
                    
                    # Fetch LTP from the most recent candle
                    ltp = df['close'].iloc[-1] if 'close' in df.columns else df['Close'].iloc[-1]
                    
                    scan_result = {
                        "status": "success",
                        "symbol": base_symbol,
                        "ltp": ltp,
                        "strict_signal": strict_result.get("strict_signal", "NONE"),
                        "strict_score": strict_result.get("strict_score", 0),
                        "breakdown": strict_result.get("breakdown", {}),
                        "strict_breakdown": strict_result.get("breakdown", {})
                    }
                    _set_cached_scan(base_symbol, scan_result)
                    asyncio.create_task(check_and_trigger_auto_execution(
                        base_symbol,
                        strict_result.get("strict_signal", "NONE"),
                        ltp,
                        strict_result.get("strict_score", 0)
                    ))
                    return scan_result
            except Exception as e:
                print(f"[Bulk Scan] Error processing {sym}: {e}")
            return None

    tasks = [scan_one(sym) for sym in scan_list]
    scan_results = await asyncio.gather(*tasks)
    
    for res in scan_results:
        if res and min_price <= res["ltp"] <= max_price:
            # Only show high-conviction stocks with score >= 70 in screener
            if res.get("strict_score", 0) >= 70:
                active_trades.append({
                    "status": "success",
                    "symbol": res["symbol"],
                    "ltp": res["ltp"],
                    "strict_signal": res["strict_signal"],
                    "strict_score": res["strict_score"],
                    "breakdown": res["strict_breakdown"]
                })

    # Sort by Strict Score (Strongest setups at the top)
    active_trades.sort(key=lambda x: x.get("strict_score", 0), reverse=True)
            
    return {
        "status": "success",
        "scanned": len(scan_list),
        "active_trades_found": len(active_trades),
        "max_price_applied": max_price,
        "results": active_trades
    }

@app.get("/analyze-stock")
async def analyze_stock(symbol: str, ltp: float = 0.0):
    symbol = symbol.upper()
    from backend.engines.stock_analyzer import stock_analyzer
    
    if not broker.session:
        try:
            broker.login()
        except Exception as e:
            print(f"[AnalyzeStock] Startup-fallback broker login failed: {e}")
            
    from backend.engines.stock_analyzer import STOCK_SECTOR_MAP
    index_ticker = STOCK_SECTOR_MAP.get(symbol, "^NSEI")
    index_trends = {}
    try:
        import yfinance as yf
        t_obj = yf.Ticker(index_ticker)
        fast_info = await asyncio.to_thread(lambda: t_obj.fast_info)
        last_price = float(getattr(fast_info, "last_price", 0))
        prev_close = float(getattr(fast_info, "previous_close", 0))
        if last_price > 0 and prev_close > 0:
            index_trends[index_ticker] = "Bullish" if last_price > prev_close else "Bearish"
    except Exception as e:
        print(f"[AnalyzeStock] Trend fetch failed for index {index_ticker}: {e}")
            
    api_client = broker.smart_api if broker.session else None
    live_ltp_dict = ws_manager.ltp_data if ws_manager else {}
    res = await stock_analyzer.analyze_stock(symbol, api_client, index_trends, provided_ltp=ltp, live_ltp_dict=live_ltp_dict)
    return res

def background_save_and_notify(signal_data, side, symbol, qty, trading_symbol, price):
    doc_id = db_manager.save_signal(signal_data)
    if doc_id:
        trade_manager.add_trade(signal_data, doc_id)
        
    send_push_notification(
        f"STOCK ALGO: {side} {symbol}",
        f"Executed {qty} shares of {trading_symbol} @ Rs.{price:.2f}. SL: {signal_data['sl']:.2f}, TP: {signal_data['tp']:.2f}"
    )

@app.post("/execute-stock-trade")
async def execute_stock_trade(symbol: str, side: str, qty: int = 1, ltp: float = 0.0, background_tasks: BackgroundTasks = None, trusted_score: int = None):
    # ── MARKET HOURS GUARD ─────────────────────────────────────────────────
    # Intraday entries only allowed: Mon-Fri, 9:15 AM – 2:30 PM IST
    # After 2:30 PM: less than 40 min left → auto sq-off at 3:10 PM → bad RRR
    ist_tz_guard = timezone(timedelta(hours=5, minutes=30))
    now_guard = datetime.now(ist_tz_guard)
    market_open  = dt_time(9, 15)
    entry_cutoff = dt_time(14, 30)   # No new entries after 2:30 PM
    market_close = dt_time(15, 30)
    current_time = now_guard.time()
    weekday      = now_guard.weekday()  # 0=Mon … 4=Fri, 5=Sat, 6=Sun

    if weekday >= 5:  # Saturday or Sunday
        return {
            "status": "error",
            "message": f"Market closed on {'Saturday' if weekday == 5 else 'Sunday'}. NSE trades Mon–Fri only."
        }
    if current_time < market_open:
        return {
            "status": "error",
            "message": f"Market not yet open. NSE opens at 9:15 AM IST. Current time: {now_guard.strftime('%I:%M %p')} IST."
        }
    if current_time >= entry_cutoff:
        return {
            "status": "error",
            "message": (
                f"Entry blocked after 2:30 PM IST. Current time: {now_guard.strftime('%I:%M %p')} IST. "
                "Auto square-off is at 3:10 PM — not enough time for a new intraday position."
            )
        }
    # ───────────────────────────────────────────────────────────────────────

    # Check if Equity trading is enabled in settings
    settings = await asyncio.to_thread(db_manager.get_settings) or {}
    equity_trading = settings.get("equity_trading", True)
    if not equity_trading:
        return {"status": "error", "message": "Equity Intraday trading is disabled in settings"}

    symbol = symbol.upper()
    side = side.upper()
    if side not in ["BUY", "SELL"]:
        return {"status": "error", "message": "Invalid transaction side"}

        
    # Daily Trade Check: prevent trading the same stock if it has already been traded AND CLOSED today
    # FIX: Must filter by TODAY's IST date — without this, yesterday's closed trades lock today's entries
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist_tz)
    start_of_day_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_ms = int(start_of_day_ist.timestamp() * 1000)

    symbol_closed_today = [
        sig for sig in signals
        if (sig.get("symbol") == symbol or sig.get("symbol") == f"{symbol}-EQ")
        and sig.get("status") == "CLOSED"
        and int(sig.get("timestamp", 0)) >= start_of_day_ms
    ]
    if symbol_closed_today:
        closed_time_ms = symbol_closed_today[-1].get("exit_time", 0)
        closed_dt = datetime.fromtimestamp(closed_time_ms / 1000, tz=ist_tz).strftime("%H:%M") if closed_time_ms else "earlier today"
        return {
            "status": "error",
            "message": f"{symbol} aaj {closed_dt} pe already trade hua aur close ho gaya. Kal dobara try karo."
        }
        
    # Check Risk Limits
    can_trade_global, lock_reason = risk_manager.check_hard_locks(settings)
    if not can_trade_global:
        return {"status": "error", "message": f"Execution Blocked by Risk Manager: {lock_reason}"}
        
    if not risk_manager.can_trade(side):
        if risk_manager.trades_today >= risk_manager.max_trades:
            reason = f"Max daily trades limit reached ({risk_manager.trades_today}/{risk_manager.max_trades})"
        elif risk_manager.consecutive_losses >= risk_manager.max_consecutive_losses:
            reason = f"Consecutive loss limit reached ({risk_manager.consecutive_losses}/{risk_manager.max_consecutive_losses})"
        else:
            reason = f"Directional exposure limit hit for {side} trades"
        return {"status": "error", "message": f"Execution Blocked by Risk Manager: {reason}"}

    ticker = f"{symbol}.NS" if not symbol.endswith(".NS") else symbol
    
    # Pre-fetch AngelOne data to avoid yfinance server blocks on Render
    from backend.utils.token_manager import token_manager
    base_symbol = symbol.replace(".NS", "").replace("-EQ", "")
    token = token_manager.get_token(base_symbol)
    exchange = token_manager.get_exchange(base_symbol) or "NSE"
    
    df = None
    if broker.session and token:
        from backend.utils.historical_data import fetch_historical_data
        df = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "FIVE_MINUTE", 5, exchange)
        
    if df is None or df.empty:
        try:
            import yfinance as yf
            df = await asyncio.to_thread(lambda: yf.Ticker(ticker).history(period="5d", interval="5m"))
        except Exception:
            return {"status": "error", "message": "Failed to fetch stock data for execution."}
            
    if df is None or df.empty:
        return {"status": "error", "message": "Failed to fetch stock data for execution (broker session expired and yfinance rate-limited)"}
            
    # Fetch live market depth for buyer/seller ratio
    market_depth_buyer_ratio = 1.0
    if broker.session and token:
        try:
            depth = await asyncio.to_thread(broker.get_market_depth, exchange, base_symbol, token)
            if depth:
                tot_buy = depth.get("totBuyQuan", 0)
                tot_sell = depth.get("totSellQuan", 0)
                if tot_sell > 0:
                    market_depth_buyer_ratio = tot_buy / tot_sell
        except Exception as e:
            print(f"[Execute Stock Trade] Failed to fetch market depth for {base_symbol}: {e}")

    # FIX: Skip redundant re-evaluation when called from auto-execution (score already validated)
    if trusted_score is not None:
        strict_score = trusted_score
    else:
        strict_result = await asyncio.to_thread(
            strict_checklist_engine.evaluate, 
            ticker, 
            df.copy(), 
            is_nifty_bullish=True, # Assume true for manual execution if not fetched
            market_depth_buyer_ratio=market_depth_buyer_ratio
        )
        
        strict_score = strict_result.get("strict_score", 0)

    # BUG-6 FIX: Enforce minimum score guard for both BUY and SELL.
    # Score < 20/100 means no single technical or fundamental condition is met.
    # This is a safety rail, not a restriction on informed manual trades.
    MIN_MANUAL_SCORE = 20
    if strict_score < MIN_MANUAL_SCORE:
        return {
            "status": "error",
            "message": (
                f"{symbol} ka Whale Score bahut kam hai ({strict_score}/100). "
                f"Minimum {MIN_MANUAL_SCORE}/100 required. "
                "Scan dobara karo ya dusra stock choose karo."
            )
        }
        
    trading_symbol = f"{base_symbol}-EQ"
    
    # FIX: Fetch real-time LTP from broker to avoid stale scanner prices
    real_ltp = 0.0
    if broker.session and token:
        try:
            real_ltp = await asyncio.to_thread(broker.get_market_data, exchange, base_symbol, token)
        except Exception:
            pass
    
    if real_ltp > 0:
        price = real_ltp
    elif ltp > 0:
        price = ltp
    else:
        price = float(df['close'].iloc[-1]) if 'close' in df.columns else float(df['Close'].iloc[-1])
    
    if price <= 0:
        return {"status": "error", "message": "Invalid stock price"}
        
    settings = db_manager.get_settings() or {}
    capital_limit = float(settings.get("capital_limit", 10000))
    
    # Calculate maximum allowed quantity under the set capital limit
    max_allowed_qty = int(capital_limit / price)
    if max_allowed_qty <= 0:
        max_allowed_qty = 1
        
    if qty <= 0:
        qty = 1
    elif qty > max_allowed_qty:
        return {
            "status": "error", 
            "message": f"Requested quantity ({qty}) exceeds daily capital limit. Max allowed is {max_allowed_qty} shares."
        }
        
    # Standard ATR estimation since we don't have old auto_router
    from backend.indicators.technical_indicators import TechnicalIndicators
    try:
        df_atr = TechnicalIndicators.add_atr(df.copy(), 14)
        atr = df_atr['ATR_14'].iloc[-1]
    except:
        atr = 0.0
        
    if atr > 0:
        sl = price - (2.0 * atr) if side == "BUY" else price + (2.0 * atr)
        tp = price + (4.0 * atr) if side == "BUY" else price - (4.0 * atr)
    else:
        sl = price - (price * 0.02) if side == "BUY" else price + (price * 0.02)
        tp = price + (price * 0.04) if side == "BUY" else price - (price * 0.04)

    signal_data = {
        "signal": side,
        "symbol": trading_symbol,
        "entry": price,
        "actual_entry": price,
        "sl": sl,
        "tp": tp,
        "reason": f"ALGO EQUITY {side} - 100-Point Score: {strict_score}",
        "is_paper": is_paper_trading,
        "timestamp": int(time.time() * 1000),
        "token": token,
        "qty": qty,
        "instrument_type": "EQUITY",
        "original_signal": side,
        "atr": atr
    }
    
    order_id = None
    if not is_paper_trading:
        if not broker.session:
            broker.login()
        order_id = broker.place_order(
            symbol=trading_symbol,
            token=token,
            qty=qty,
            side=side,
            price=price,
            order_type="MARKET",
            exchange="NSE"
        )
        if not order_id:
            return {"status": "error", "message": "Broker execution failed"}
        signal_data["order_id"] = order_id
        
    risk_manager.record_entry(side)
    signals.append(signal_data)
    if ws_manager:
        ws_manager.subscribe_token(token, 1) # 1 = NSE Equity Cash
    
    # FIX: Save trade SYNCHRONOUSLY to guarantee it's registered in TradeManager
    # before returning. Only defer the push notification to background.
    doc_id = db_manager.save_signal(signal_data)
    if doc_id:
        trade_manager.add_trade(signal_data, doc_id)
    
    # Defer only the push notification to background
    notification_title = f"STOCK ALGO: {side} {symbol}"
    notification_body = f"Executed {qty} shares of {trading_symbol} @ Rs.{price:.2f}. SL: {signal_data['sl']:.2f}, TP: {signal_data['tp']:.2f}"
    if background_tasks:
        background_tasks.add_task(send_push_notification, notification_title, notification_body)
    else:
        try:
            send_push_notification(notification_title, notification_body)
        except Exception:
            pass
    
    return {
        "status": "success",
        "message": "Stock trade executed successfully",
        "order_id": order_id,
        "trade": signal_data
    }

async def check_and_trigger_auto_execution(symbol: str, side: str, ltp: float, strict_score: int):
    """
    Check if Auto-Execution is enabled in settings.
    If yes, perform risk checks and programmatically execute trade.
    """
    settings = await asyncio.to_thread(db_manager.get_settings) or {}
    
    # Check if auto execution is enabled
    auto_execution = settings.get("equity_auto_execution", False)
    if not auto_execution:
        return
        
    side = side.upper()
    if side not in ["BUY", "SELL"]:
        return
        
    min_score = int(settings.get("equity_min_score", 70))
    if strict_score < min_score:
        return
        
    # Check if already in active trade to prevent double entry
    symbol = symbol.upper()
    for active_trade in trade_manager.active_trades:
        active_sym = active_trade.get("symbol", "").upper().replace("-EQ", "")
        if active_sym == symbol:
            print(f"[AutoExecution] Blocked: Active trade already exists for {symbol}")
            return
    
    # FIX: Also check in-memory signals for OPEN trades (covers trades not yet in trade_manager)
    for sig in signals:
        sig_sym = sig.get("symbol", "").upper().replace("-EQ", "")
        if sig_sym == symbol and sig.get("status") != "CLOSED":
            print(f"[AutoExecution] Blocked: Open signal already exists for {symbol}")
            return
            
    # Check if closed today already
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    now_ist = datetime.now(ist_tz)
    start_of_day_ist = now_ist.replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_ms = int(start_of_day_ist.timestamp() * 1000)
    
    symbol_closed_today = [
        sig for sig in signals
        if (sig.get("symbol") == symbol or sig.get("symbol") == f"{symbol}-EQ")
        and sig.get("status") == "CLOSED"
        and int(sig.get("timestamp", 0)) >= start_of_day_ms
    ]
    if symbol_closed_today:
        print(f"[AutoExecution] Blocked: {symbol} was already traded and closed today.")
        return
        
    # Calculate quantity
    qty_mode = settings.get("equity_qty_mode", "FIXED")
    capital_limit = float(settings.get("capital_limit", 10000.0))
    
    if qty_mode == "CAPITAL_LIMIT":
        qty = int(capital_limit / ltp) if ltp > 0 else 1
    else:  # FIXED
        qty = int(settings.get("equity_fixed_qty", 1))
        
    if qty <= 0:
        qty = 1
        
    print(f"[AutoExecution] Triggering auto trade for {symbol} - Side: {side}, Qty: {qty}, LTP: {ltp}, Score: {strict_score}")
    try:
        # FIX: Pass trusted_score to skip redundant re-evaluation
        res = await execute_stock_trade(symbol=symbol, side=side, qty=qty, ltp=ltp, trusted_score=strict_score)
        if res and res.get("status") == "success":
            print(f"[AutoExecution] Success: Order placed for {symbol}")
            send_push_notification(
                f"⚡ AUTO-EXECUTION SUCCESS: {side} {symbol}",
                f"Executed {qty} shares of {symbol} @ Rs.{ltp:.2f} (Score: {strict_score}/100)"
            )
        else:
            print(f"[AutoExecution] Execution failed: {res.get('message', 'Unknown error')}")
    except Exception as e:
        print(f"[AutoExecution] Exception during order: {e}")

async def trading_loop():
    global trading_active, ws_manager
    
    # Always ensure a fresh session on toggle
    success = broker.login()
    if not success:
        trading_active = False
        return
    
    # Refresh/Connect WebSocket with fresh tokens using helper
    await asyncio.to_thread(ensure_websocket_connected)

    symbols = ["NIFTY", "BANKNIFTY"]
    gap_scan_done = False  # Reset on each trading_loop start (once per day)
    while trading_active:
        try:
            # Check if F&O trading is enabled in settings
            settings = await asyncio.to_thread(db_manager.get_settings) or {}
            fno_trading = settings.get("fno_trading", True)
            if not fno_trading:
                print("[Loop] F&O Trading is disabled. Skipping cycle.")
                await asyncio.sleep(5)
                continue

            now = config.get_ist_time()
            
            # --- AUTO-SQUAREOFF ---
            # 3:10 PM forced square-off to beat the broker's 3:15 PM auto-square-off penalty (approx Rs.60)
            if now.hour == 15 and now.minute >= 10:
                if trading_active:  # FIX C-1: Check flag first to prevent re-entry on repeated loop iterations
                    print("[Auto-Squareoff] 3:10 PM reached. Squaring off all positions.")
                    trading_active = False  # FIX C-1: Set flag BEFORE calling square_off to prevent double-call
                    await asyncio.to_thread(sync_status_to_db)
                    ltp_dict = ws_manager.ltp_data if ws_manager else {}
                    await asyncio.to_thread(trade_manager.emergency_square_off, ltp_dict, get_live_price_fallback)
                    await asyncio.to_thread(broker.square_off_all)

                    # Telegram: daily summary
                    try:
                        from backend.utils.telegram_notifier import notify_daily_summary
                        notify_daily_summary(
                            total_trades=trade_manager.total_trades,
                            winning=trade_manager.winning_trades,
                            losing=trade_manager.losing_trades,
                            realized_pnl=trade_manager.realized_pnl,
                            daily_loss_used=getattr(risk_manager, 'daily_loss', 0.0),
                        )
                    except Exception as e:
                        print(f"[Telegram] Daily summary failed: {e}")

                break  # FIX C-1: Always exit loop after 3:10 PM — no more iterations
            
            # Midnight Reset Check for continuous 24/7 VPS deployments
            today_date = now.date()
            global last_reset_date
            if today_date != last_reset_date:
                print(f"[Reset] Date changed from {last_reset_date} to {today_date}. Resetting daily risk stats.")
                risk_manager.reset_daily()
                cooldown_engine.reset()  # FIX ISSUE-4: Reset cooldown so new day starts fresh
                last_reset_date = today_date
                gap_scan_done = False  # Allow gap scan again on new day

            # ─────────────────────────────────────────────────────────────────────
            # PRE-MARKET GAP SCAN  (9:00 – 9:14 IST, once per day)
            # Detects gap-up/gap-down ≥1% from prev close via yfinance.
            # Auto-adds qualifying stocks to Firestore watchlist.
            # ─────────────────────────────────────────────────────────────────────
            if now.hour == 9 and now.minute < 15 and not gap_scan_done:
                gap_scan_done = True
                print("[GapScan] Running pre-market gap scan...")
                try:
                    import yfinance as yf
                    gap_symbols = list(SCREENER_UNIVERSE[:40])  # Top 40 liquid stocks
                    tickers     = [f"{s}.NS" for s in gap_symbols]
                    raw = await asyncio.to_thread(
                        lambda: yf.download(tickers, period="2d", interval="1d",
                                            progress=False, threads=True)
                    )
                    gap_ups, gap_downs = [], []
                    if not raw.empty and "Close" in raw.columns:
                        closes = raw["Close"]
                        if len(closes) >= 2:
                            # Fix M-3: Safe extraction of gap scan row ignoring partial day
                            import pandas as pd
                            today_partial = closes.index[-1].date() == pd.Timestamp.now(tz='Asia/Kolkata').date()
                            if today_partial and len(closes) >= 3:
                                prev_row = closes.iloc[-2]
                                curr_row = closes.iloc[-1]
                            elif not today_partial:
                                prev_row = closes.iloc[-2]
                                curr_row = closes.iloc[-1]
                            else:
                                continue # Cannot run gap scan, only 1 valid row
                                
                            for sym in gap_symbols:
                                col = f"{sym}.NS"
                                try:
                                    prev = float(prev_row.get(col))
                                    curr = float(curr_row.get(col))
                                    if prev > 0 and str(prev) != 'nan' and str(curr) != 'nan':
                                        gap_pct = ((curr - prev) / prev) * 100
                                        entry = {"symbol": sym, "gap_pct": round(gap_pct, 2),
                                                 "prev_close": prev, "current": curr}
                                        if gap_pct >= 1.0:
                                            gap_ups.append(entry)
                                        elif gap_pct <= -1.0:
                                            gap_downs.append(entry)
                                except Exception:
                                    pass

                    # Sort by gap magnitude
                    gap_ups.sort(key=lambda x: -x['gap_pct'])
                    gap_downs.sort(key=lambda x: x['gap_pct'])

                    # BUG-8 FIX: Write to correct Firestore path.
                    # App reads watchlist from 'quantum_system/watchlist' (items array),
                    # NOT from 'watchlist/{symbol}' (old wrong path).
                    try:
                        wl_ref = db_manager.db.collection("quantum_system").document("watchlist")
                        wl_doc = wl_ref.get()
                        existing_items = wl_doc.to_dict().get("items", []) if wl_doc.exists else []
                        existing_symbols = {e.get("symbol") for e in existing_items}
                        for item in (gap_ups[:5] + gap_downs[:5]):
                            if item['symbol'] not in existing_symbols:
                                direction = "BUY" if item['gap_pct'] > 0 else "SELL"
                                existing_items.append({
                                    "symbol": item['symbol'],
                                    "side": direction,
                                    "gap_pct": item['gap_pct'],
                                    "source": "GAP_SCAN",
                                    "ltp": item.get('current', 0),
                                    "strict_score": 0,
                                    "strict_signal": direction,
                                    "added_at": int(time.time() * 1000),
                                })
                                existing_symbols.add(item['symbol'])
                        wl_ref.set({"items": existing_items}, merge=True)
                        print(f"[GapScan] Added {len(gap_ups[:5]) + len(gap_downs[:5])} stocks to quantum_system/watchlist")
                    except Exception as wl_err:
                        print(f"[GapScan] Watchlist write failed: {wl_err}")

                    # Telegram alert
                    try:
                        from backend.utils.telegram_notifier import notify_gap_scan_results
                        notify_gap_scan_results(gap_ups[:5], gap_downs[:5])
                    except Exception:
                        pass

                    total_gaps = len(gap_ups) + len(gap_downs)
                    print(f"[GapScan] Done: {len(gap_ups)} gap-up, {len(gap_downs)} gap-down. "
                          f"Added {min(total_gaps, 10)} stocks to watchlist.")
                except Exception as e:
                    print(f"[GapScan] Failed: {e}")

            # Candle Lock Check (Wait for new minute)
            if now.second > 55: await asyncio.sleep(5); continue

            for symbol in symbols:
                # Candle Lock: One check/trade per symbol per minute to prevent rate limiting
                candle_id = now.strftime("%Y-%m-%d %H:%M")
                if last_checked_candle[symbol] == candle_id: continue
                if last_execution_candle[symbol] == candle_id: continue
                last_checked_candle[symbol] = candle_id

                token = token_manager.get_token(symbol)
                exchange = token_manager.get_exchange(symbol)
                
                # Update option chain OI data for PCR calculation
                try:
                    from backend.engines.oi_engine import oi_engine
                    await asyncio.to_thread(oi_engine.fetch_options_chain, symbol, broker.smart_api)
                except Exception as e:
                    print(f"[Loop] Options chain OI update failed for {symbol}: {e}")

                # API Rate Limit (3 req/sec) Management: Fetch sequentially with delay
                df_1m = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "ONE_MINUTE", 2, exchange)
                await asyncio.sleep(0.4)
                df_5m = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "FIVE_MINUTE", 5, exchange)
                await asyncio.sleep(0.4)
                df_15m = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "FIFTEEN_MINUTE", 10, exchange)
                await asyncio.sleep(0.4)
                df_1h = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "ONE_HOUR", 30, exchange)
                await asyncio.sleep(0.4)
                
                # BUG #2 FIX: Previously ANY df being None would skip the entire symbol.
                # 15m and 1h are optional — MTF engine handles None gracefully.
                # Only 1m and 5m are required (they provide the actual entry signals).
                if df_1m is None or df_1m.empty:
                    print(f"[Loop] {symbol}: 1m data missing. Skipping candle.")
                    continue
                if df_5m is None or df_5m.empty:
                    print(f"[Loop] {symbol}: 5m data missing. Skipping candle.")
                    continue
                if df_15m is None or df_15m.empty:
                    print(f"[Loop] {symbol}: 15m data missing — HTF analysis degraded.")
                if df_1h is None or df_1h.empty:
                    print(f"[Loop] {symbol}: 1h data missing — HTF analysis degraded.")

                # Active signal engine computes ATR and EMA 50 on the fly; redundant indicator calculations are removed for performance.
                
                # ================================================================
                # PHASE 2 WIRING: Apply indicators + run ALL engines
                # ================================================================
                
                # Step 1: Apply technical indicators to each timeframe
                # BUG #12 FIX: Replace silent pass with structured error logging
                for tf_df in [df_1m, df_5m, df_15m, df_1h]:
                    if tf_df is None or tf_df.empty:
                        continue
                    try:
                        TechnicalIndicators.apply_all(tf_df)
                    except Exception as e:
                        print(f"[INDICATOR ERROR] apply_all failed for {symbol}: {e}")

                # Step 2: Multi-Timeframe Analysis (HTF = Direction, LTF = Entry)
                from backend.engines.mtf_engine import mtf_engine
                mtf_result = mtf_engine.analyze(df_1m, df_5m, df_15m, df_1h)
                htf_trend = mtf_result.get('htf_trend', 'Neutral')
                ltf_entry_valid = mtf_result.get('ltf_entry_valid', False)

                # Step 3: Structure Analysis (BOS, CHoCH, FVG, MSS, Breakout, Pullback)
                from backend.engines.structure_engine import StructureEngine
                structure_engine = StructureEngine(lookback=20)
                structure_result = structure_engine.analyze(df_5m)

                # Step 4: Liquidity Analysis (EQH/EQL, Sweeps)
                from backend.engines.liquidity_engine import LiquidityEngine
                liquidity_engine = LiquidityEngine()
                liquidity_result = liquidity_engine.analyze(df_5m)

                # Step 5: Trend Confirmation (EMA + Supertrend + ADX scoring)
                from backend.engines.trend_engine import TrendEngine
                trend_engine = TrendEngine()
                trend_direction = trend_engine.analyze(df_5m)

                # Step 6: Volume Confirmation (Spike + VWAP bias)
                from backend.engines.volume_engine import VolumeEngine
                volume_engine = VolumeEngine()
                volume_result = volume_engine.analyze(df_5m)

                # Step 7: Momentum Check (RSI strength)
                from backend.engines.momentum_engine import MomentumEngine
                momentum_engine = MomentumEngine()
                momentum_result = momentum_engine.analyze(df_5m)

                # Step 8: Candlestick Patterns (Engulfing, Doji, Hammer)
                from backend.engines.candlestick_engine import candlestick_engine
                candle_result = candlestick_engine.analyze(df_5m)

                # Log structure analysis for debugging
                if structure_result.get('choch_bullish') or structure_result.get('choch_bearish'):
                    choch_dir = "Bullish" if structure_result['choch_bullish'] else "Bearish"
                    print(f"[SMC] CHoCH detected: {choch_dir} for {symbol}")
                if structure_result.get('mss_bullish') or structure_result.get('mss_bearish'):
                    mss_dir = "Bullish" if structure_result['mss_bullish'] else "Bearish"
                    print(f"[SMC] MSS confirmed: {mss_dir} for {symbol}")
                if structure_result.get('fake_breakout_up') or structure_result.get('fake_breakout_down'):
                    print(f"[SMC] FAKE BREAKOUT detected for {symbol} — avoiding entry")
                
                # Fetch Real-time LTP to avoid stale entry prices from 1m historical candles
                real_ltp = None
                try:
                    real_ltp = await asyncio.to_thread(broker.get_market_data, exchange, symbol, token)
                except Exception as e:
                    print(f"[Loop] Failed to fetch LTP for {symbol}: {e}")

                # Fetch live market depth for buyer/seller ratio
                market_depth_buyer_ratio = 1.0
                if broker.session and token:
                    try:
                        depth = await asyncio.to_thread(broker.get_market_depth, exchange, symbol, token)
                        if depth:
                            tot_buy = depth.get("totBuyQuan", 0)
                            tot_sell = depth.get("totSellQuan", 0)
                            if tot_sell > 0:
                                market_depth_buyer_ratio = tot_buy / tot_sell
                    except Exception as e:
                        print(f"[Loop] Failed to fetch market depth for {symbol}: {e}")

                # Step 9: Scorecard (100-point confluence-based checklist — primary signal)
                signal_data = strict_checklist_engine.evaluate(
                    symbol, 
                    df_5m, 
                    is_nifty_bullish=(htf_trend != "Bearish"),
                    market_depth_buyer_ratio=market_depth_buyer_ratio,
                    structure_result=structure_result,
                    candle_result=candle_result,
                    mtf_result=mtf_result,
                    volume_result=volume_result,
                    momentum_result=momentum_result,
                    trend_direction=trend_direction
                )
                
                # Enrich signal_data with all engine results
                signal_data['htf_trend'] = htf_trend
                signal_data['ltf_entry_valid'] = ltf_entry_valid
                signal_data['mtf_alignment'] = mtf_result.get('alignment_score', 0)
                signal_data['trend_direction'] = trend_direction
                signal_data['volume_strength'] = volume_result.get('strength', 'Weak')
                signal_data['volume_spike'] = volume_result.get('volume_spike', False)
                signal_data['vwap_status'] = volume_result.get('vwap_status', 'Unknown')
                signal_data['rsi'] = momentum_result.get('rsi', 50)
                signal_data['momentum_strength'] = momentum_result.get('strength', 'Neutral')
                signal_data['bos'] = structure_result.get('bos', 'None')
                signal_data['choch_bullish'] = structure_result.get('choch_bullish', False)
                signal_data['choch_bearish'] = structure_result.get('choch_bearish', False)
                signal_data['mss_bullish'] = structure_result.get('mss_bullish', False)
                signal_data['mss_bearish'] = structure_result.get('mss_bearish', False)
                signal_data['fvg_gap'] = structure_result.get('fvg_gap', False)
                signal_data['bullish_fvg'] = structure_result.get('bullish_fvg', False)
                signal_data['bearish_fvg'] = structure_result.get('bearish_fvg', False)
                signal_data['sweep'] = liquidity_result.get('sweep', None)
                signal_data['breakout_bullish'] = structure_result.get('breakout_bullish', False)
                signal_data['breakout_bearish'] = structure_result.get('breakout_bearish', False)
                signal_data['fake_breakout_up'] = structure_result.get('fake_breakout_up', False)
                signal_data['fake_breakout_down'] = structure_result.get('fake_breakout_down', False)
                signal_data['pullback_to_support'] = structure_result.get('pullback_to_support', False)
                signal_data['pullback_to_resistance'] = structure_result.get('pullback_to_resistance', False)
                signal_data['candlestick'] = candle_result
                signal_data['confluence_count'] = signal_data.get('confluence_count', 0)

                # Update current score for any active trade of this symbol
                with trade_manager._lock:
                    for t in trade_manager.active_trades:
                        if t.get("symbol", "").startswith(symbol):
                            t["current_score"] = signal_data['strict_score']

                raw_side = signal_data.get('strict_signal', 'NONE')
                if "BUY" in raw_side:
                    side = "BUY"
                elif "SELL" in raw_side:
                    side = "SELL"
                else:
                    side = "NONE"

                # ================================================================
                # SMART FILTERS: Use SMC + MTF to reject weak signals
                # ================================================================
                
                # Filter 1: HTF/LTF alignment
                # BUG #1 FIX: Previously blocked ALL trades when HTF=Neutral.
                # Neutral trend is common (60-70% of time in NSE). Instead of hard-blocking,
                # require a higher score when LTF is not aligned with a confirmed HTF direction.
                if side != "NONE" and not ltf_entry_valid and htf_trend != "Neutral":
                    print(f"[MTF Filter] {symbol} {side} blocked: LTF not aligned with confirmed {htf_trend} HTF")
                    continue
                elif side != "NONE" and not ltf_entry_valid and htf_trend == "Neutral":
                    # Neutral HTF: require higher score instead of hard block
                    curr_sc = signal_data.get('strict_score', 0)
                    if curr_sc < 65:
                        print(f"[MTF Filter] {symbol} {side}: Neutral HTF, score {curr_sc}<65. Skipping.")
                        continue
                
                # Filter 2: HTF trend vs trade direction mismatch
                if side == "BUY" and htf_trend == "Bearish":
                    print(f"[MTF Filter] {symbol} BUY blocked: HTF trend is Bearish")
                    continue
                if side == "SELL" and htf_trend == "Bullish":
                    print(f"[MTF Filter] {symbol} SELL blocked: HTF trend is Bullish")
                    continue

                # Filter 3: Fake breakout trap — do NOT enter if fake breakout detected
                if side == "BUY" and structure_result.get('fake_breakout_up', False):
                    print(f"[SMC Filter] {symbol} BUY blocked: Fake breakout UP detected (trap)")
                    continue
                if side == "SELL" and structure_result.get('fake_breakout_down', False):
                    print(f"[SMC Filter] {symbol} SELL blocked: Fake breakout DOWN detected (trap)")
                    continue

                # Filter 4: CONFLUENCE MINIMUM
                # BUG #11 FIX: Reduced from 3 to 2 independent confluences.
                # Requiring 3 categories (SMC + Trend + Momentum + Volume) simultaneously
                # in ranging markets was blocking ~80% of valid signals.
                confluence_count = signal_data.get('confluence_count', 0)
                if side != "NONE" and confluence_count < 2:
                    print(f"[Confluence Filter] {symbol} {side} blocked: Only {confluence_count}/2 confluences")
                    continue

                # Filter 5: SESSION-AWARE DYNAMIC THRESHOLDS
                # BUG #3 FIX: Lowered thresholds to realistic levels.
                # 80-85 pts was impossible in normal markets (typical score: 40-65 pts).
                current_score = signal_data.get('strict_score', 0)
                now_time = now.hour * 100 + now.minute
                if 920 <= now_time <= 945:
                    # Opening drive: still cautious but 65 is achievable
                    session_threshold = 65   # Was 80 — way too high
                elif 1130 <= now_time <= 1300:
                    # Lunch chop: require high conviction, but 85 was impossible
                    session_threshold = 68   # Was 85 — impossibly high
                else:
                    # Normal sessions: standard threshold (60+)
                    session_threshold = 60   # Was 70 — blocked most valid signals
                
                if side != "NONE" and current_score < session_threshold:
                    print(f"[Session Filter] {symbol} {side} blocked: Score {current_score} < session threshold {session_threshold}")
                    continue

                # Filter 6: MANDATORY SMC STRUCTURE
                # BUG #6 FIX: FVG (Fair Value Gap) now satisfies the SMC requirement.
                # BOS/CHoCH/MSS are rare; FVG appears more frequently and is a valid
                # SMC institutional footprint. Without this fix, 70-80% of candles
                # with good scores were blocked by the mandatory SMC filter.
                smc_score = signal_data.get('breakdown', {}).get('SMC Structure', 0)
                has_fvg = signal_data.get('bullish_fvg', False) or signal_data.get('bearish_fvg', False)
                if side != "NONE" and smc_score <= 0 and not has_fvg:
                    print(f"[SMC Structure Filter] {symbol} {side} blocked: No BOS/CHoCH/MSS/FVG (smc_score={smc_score})")
                    continue

                # Filter 7: MANDATORY VWAP ALIGNMENT — price must be on the correct side of VWAP
                vwap_status = signal_data.get('vwap_status', 'Unknown')
                if side == "BUY" and vwap_status == "Below":
                    print(f"[VWAP Filter] {symbol} BUY blocked: Price is below VWAP")
                    continue
                if side == "SELL" and vwap_status == "Above":
                    print(f"[VWAP Filter] {symbol} SELL blocked: Price is above VWAP")
                    continue

                # --- CORRELATION GUARD (Nifty vs BankNifty) ---
                # (Replaced by strict_checklist_engine internal checks)

                # --- RISK & NEWS HARD LOCKS ---
                can_trade, reason = risk_manager.check_hard_locks(settings) if hasattr(risk_manager, 'check_hard_locks') else (True, "OK")
                if not can_trade:
                    print(f"[HardLock] {reason}")
                    continue
                
                if side in ["BUY", "SELL"] and risk_manager.can_trade(side):
                    # Old stock_analyzer scorecard validation has been deprecated and removed.
                    # The strict_checklist_engine now holds full authority.

                    # BUG-2 FIX: OI Filter — use the PCR + Max Pain data that was already being fetched
                    from backend.engines.oi_engine import oi_engine
                    current_ltp_for_oi = real_ltp or float(df_5m['close'].iloc[-1])
                    if not oi_engine.is_oi_supportive(symbol, side, current_ltp_for_oi):
                        print(f"[OI Filter] Trade REJECTED by OI analysis for {symbol} {side} (PCR/MaxPain guard)")
                        continue

                    # FIX 2: CooldownEngine check — prevents trades within 10 min window
                    if not cooldown_engine.can_trade():
                        remaining = int(cooldown_engine.cooldown_period.total_seconds() / 60)
                        print(f"[CooldownEngine] Blocked: {remaining}min cooldown active after last trade.")
                        continue
                    # Dynamic Instrument Configuration & Sizing
                    instrument_type = settings.get("instrument_type", "FUTURES")
                    
                    # --- INDIA VIX VOLATILITY GUARD ---
                    vix_token = token_manager.get_token("INDIA VIX")
                    vix_exchange = token_manager.get_exchange("INDIA VIX")
                    if vix_token:
                        current_vix = broker.get_market_data(vix_exchange, "INDIA VIX", vix_token)
                        if current_vix and 0 < current_vix < 12:
                            if instrument_type == "OPTIONS":
                                print(f"[VIX Guard] Volatility too low ({current_vix}). Switching to FUTURES to prevent Theta decay.")
                                instrument_type = "FUTURES"
                                
                    capital_limit = float(settings.get("capital_limit", 10000))
                    
                    trade_symbol = token_manager.get_symbol(symbol)
                    trade_token = token
                    trade_side = side
                    qty = 0
                    
                    if instrument_type == "OPTIONS":
                        option_type = "CE" if side == "BUY" else "PE"
                        option_contract = token_manager.get_atm_option(symbol, signal_data['entry'], option_type)
                        if not option_contract:
                            print(f"[OptionsEngine] ERROR: No active option contract found for {symbol} ATM {option_type}")
                            continue
                            
                        trade_token = option_contract["token"]
                        trade_symbol = option_contract["symbol"]
                        lotsize = option_contract["lotsize"]
                        trade_side = "BUY"  # Options buying is always a BUY order
                        
                        # Dynamic position sizing
                        option_premium = broker.get_market_data("NFO", trade_symbol, trade_token)
                        if not option_premium or option_premium <= 0:
                            # Fallback premium estimate (~0.5% of Index LTP)
                            option_premium = round(signal_data['entry'] * 0.005, 2)
                            
                        afford_lots = int(capital_limit / (option_premium * lotsize))
                        if afford_lots <= 0:
                            afford_lots = 1
                        qty = afford_lots * lotsize
                        
                        # Dynamic subscription for websocket feed
                        if ws_manager:
                            ws_manager.subscribe_token(trade_token, 2)
                            
                        # Save options metadata for Synthetic Exits
                        # Capture underlying SL/TP distances BEFORE overwriting signal_data['sl'/'tp']
                        underlying_entry_val = signal_data['entry']
                        underlying_sl_val    = signal_data['sl']
                        underlying_tp_val    = signal_data['tp']
                        sl_dist = abs(underlying_entry_val - underlying_sl_val)  # index points to SL
                        tp_dist = abs(underlying_tp_val   - underlying_entry_val) # index points to TP

                        # ATM delta ≈ 0.45 — convert underlying points to approximate premium movement
                        ATM_DELTA = 0.45
                        premium_sl = round(max(option_premium * 0.5, option_premium - sl_dist * ATM_DELTA), 2)
                        premium_tp = round(option_premium + tp_dist * ATM_DELTA, 2)

                        signal_data.update({
                            'instrument_type': "OPTIONS",
                            'original_signal': side,
                            'underlying_token': token,
                            'underlying_entry': underlying_entry_val,
                            'underlying_sl':    underlying_sl_val,
                            'underlying_tp':    underlying_tp_val,
                            'option_premium':   option_premium,
                            # FIX BUG-10: Override sl/tp with PREMIUM levels for correct frontend display
                            # Exit logic still uses underlying_sl/underlying_tp — these are display only
                            'sl': premium_sl,
                            'tp': premium_tp,
                        })
                    else:
                        qty = risk_manager.calculate_position_size(signal_data['entry'], signal_data['sl'], symbol, signal_data.get('atr', 0.0))
                        # FIX BUG-4: Validate qty before proceeding — zero qty would send invalid order
                        if qty <= 0:
                            print(f"[SizingError] Calculated qty=0 for {symbol} (entry={signal_data['entry']}, sl={signal_data['sl']}). Skipping trade.")
                            continue
                        signal_data.update({
                            'instrument_type': "FUTURES",
                            'original_signal': side,
                        })
                        
                    order_id = None
                    if is_paper_trading:
                        order_id = f"VIRTUAL_{int(time.time())}"
                    else:
                        order_id = broker.place_order(trade_symbol, trade_token, qty, trade_side, signal_data['entry'] if instrument_type == "FUTURES" else option_premium)
                    
                    if order_id:
                        last_execution_candle[symbol] = candle_id
                        risk_manager.record_entry(side)
                        
                        # Finalize signal details
                        signal_data.update({
                            'symbol': trade_symbol,
                            'actual_entry': signal_data['entry'] if instrument_type == "FUTURES" else option_premium,
                            'token': trade_token,
                            'qty': qty,
                            'timestamp': int(time.time()*1000)
                        })
                        doc_id = db_manager.save_signal(signal_data)
                        trade_manager.add_trade(signal_data, doc_id)
                        signals.append(signal_data)
                        # FIX C-6: Cap in-memory signals list to prevent memory leak on long deployments
                        if len(signals) > 200:
                            signals = signals[-200:]
                        send_push_notification(f"🚀 SIGNAL: {trade_symbol} {side}", f"Entry: {signal_data['actual_entry']}")
                        cooldown_engine.update_last_trade()
                        await asyncio.to_thread(sync_status_to_db)
            
            await asyncio.sleep(1)
        except Exception as e:
            print(f"[Trading Loop Error]: {e}")
            await asyncio.sleep(5)

    # Sync status to Firestore when the loop exits
    await asyncio.to_thread(sync_status_to_db)



def sync_status_to_db():
    status = {
        "is_active": trading_active,
        "paper_trading": config.PAPER_TRADING,
        "signal_count": len(signals),
        "daily_loss": risk_manager.daily_loss,
        "trades_today": risk_manager.trades_today,
        "current_score": ws_current_score,  # Live Whale Score (0-100) for dashboard display
    }
    db_manager.update_system_status(status)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
