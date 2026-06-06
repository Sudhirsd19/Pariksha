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
from backend.engines.signal_engine import SignalEngine  # This has check_killzone method
from backend.utils.historical_data import fetch_historical_data
from backend.utils.token_manager import token_manager
from backend.config.firebase_config import init_firebase
from backend.utils.db_manager import db_manager
from backend.utils.trade_manager import trade_manager
from firebase_admin import messaging
from backend.safety.health_monitor import health_monitor
from backend.utils.persistence_manager import persistence_manager
from backend.engines.correlation_engine import CorrelationEngine

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

# --- CORE COMPONENTS ---
broker = AngelOneBroker()
risk_manager = RiskManager(initial_capital=100000)
signal_engine = SignalEngine()
correlation_engine = CorrelationEngine()
cooldown_engine = CooldownEngine(minutes=10) # 10 min cooldown

@app.on_event("startup")
async def startup_event():
    init_firebase()
    # Resume state from local SQLite
    trade_manager.load_state()
    trade_manager.risk_manager = risk_manager
    
    # Try to login to broker on startup to generate active session
    try:
        broker.login()
    except Exception as e:
        print(f"[Startup] Angel One Login failed: {e}")
        
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
                risk_manager.daily_loss = abs(float(data.get("total_pnl", 0))) if float(data.get("total_pnl", 0)) < 0 else 0
                risk_manager.trades_today = int(data.get("total_trades", 0))
                persistence_manager.log_event("INFO", "DAILY_RESTORE", f"Restored: trades={risk_manager.trades_today}, loss=Rs.{risk_manager.daily_loss:.2f}")
                print(f"[Startup] Restored today's stats: trades={risk_manager.trades_today}, daily_loss=Rs.{risk_manager.daily_loss:.2f}")
            
            # Restore today's signals to populate in-memory list
            from datetime import timezone, timedelta
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
    
    while True:
        try:
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

            # Fetch or simulate price for all active trade tokens (e.g. options premium)
            for token in active_trade_tokens:
                if token in current_ltps:
                    continue
                ltp = ws_manager.get_ltp(token) if (ws_manager and is_healthy) else 0
                if not ltp or ltp == 0:
                    if token not in simulated_ltps:
                        # Find the initial premium entry price as a base
                        entry_premium = 100.0
                        with trade_manager._lock:
                            for t in trade_manager.active_trades:
                                if t.get("token") == token:
                                    entry_premium = t.get("entry", 100.0)
                                    break
                        simulated_ltps[token] = entry_premium
                    
                    # Scaled drift: max 0.05% of the asset price per tick (e.g. max 0.06 for 120 Rs stock)
                    max_drift = max(0.01, simulated_ltps[token] * 0.0005)
                    drift = random.uniform(-max_drift, max_drift)
                    simulated_ltps[token] = max(1.0, round(simulated_ltps[token] + drift, 2))
                    ltp = simulated_ltps[token]
                else:
                    simulated_ltps[token] = ltp
                current_ltps[token] = ltp

            # 2. Monitor open trades (only during market hours to prevent simulated drift from closing trades)
            now_ist = config.get_ist_time()
            is_market_open = (
                now_ist.weekday() < 5 and  # Monday-Friday
                dt_time(9, 15) <= now_ist.time() <= dt_time(15, 30)  # 9:15 AM to 3:30 PM IST
            )
            # FIX C-4: Don't run trade monitoring outside market hours to prevent false SL/TP hits from drift
            if is_market_open or is_paper_trading:
                closed_trades = await asyncio.to_thread(trade_manager.monitor_trades, current_ltps)
                for trade in (closed_trades or []):
                    send_push_notification(f"🏁 {trade['symbol']} CLOSED: {trade['close_data']['result']}", f"PnL: Rs. {trade['close_data']['pnl']:.2f}")

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
                
                payload = json.dumps({
                    "ltp": current_ltp,
                    "ltps": current_ltps,
                    "connected": True,
                    "sentiment": ws_sentiment,
                    "sentiment_score": ws_sentiment_score,
                    "in_killzone": signal_engine.check_killzone(now_time),
                    "is_active": trading_active,
                    "trades_today": risk_manager.trades_today,
                    "daily_loss": risk_manager.daily_loss,
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
    in_killzone = signal_engine.check_killzone(now) if hasattr(signal_engine, 'check_killzone') else True

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
    count = trade_manager.emergency_square_off(ltp_dict)
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
    count = trade_manager.emergency_square_off(ltp_dict)
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

# Top ~250 liquid NSE stocks for smart screener (F&O + NIFTY 500 core)
SCREENER_UNIVERSE = [
    "RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK","SBIN","BHARTIARTL","WIPRO","TATASTEEL",
    "ADANIPORTS","LT","AXISBANK","KOTAKBANK","BAJFINANCE","HCLTECH","SUNPHARMA","ONGC",
    "MARUTI","NTPC","POWERGRID","COALINDIA","TITAN","BAJAJFINSV","M&M","NESTLEIND",
    "TECHM","ULTRACEMCO","ASIANPAINT","JSWSTEEL","HINDALCO","GRASIM","DRREDDY","DIVISLAB",
    "HDFCLIFE","SBILIFE","CIPLA","EICHERMOT","APOLLOHOSP","TATACONSUM","BRITANNIA",
    "INDUSINDBK","HEROMOTOCO","BPCL","SHREECEM","PIIND","GLAND","MUTHOOTFIN","BANKBARODA",
    "PNB","CANBK","FEDERALBNK","IDFCFIRSTB","RBLBANK","BANDHANBNK","AUBANK","INDIGO",
    "INTERGLOBE","SPICEJET","IRCTC","ZOMATO","NYKAA","PAYTM","POLICYBZR","CARTRADE",
    "DELHIVERY","MAPMYINDIA","HAL","BEL","BHEL","SAIL","NMDC","GAIL","IGL","MGL",
    "PETRONET","IOC","HPCL","HINDPETRO","MRPL","CPCL","CHENNPETRO","APLAPOLLO",
    "HINDZINC","NATIONALUM","WELCORP","RATNAMANI","MAHINDCIE","TATAELXSI","MPHASIS",
    "LTTS","PERSISTENT","COFORGE","HAPPSTMNDS","MINDTREE","OFSS","NIITTECH","KPITTECH",
    "CYIENT","MASTEK","ZENSAR","HEXAWARE","RAMSARUP","HAVELLS","VOLTAS","CROMPTON",
    "POLYCAB","KEI","FINCABLES","KTKBANK","SOUTHBANK","DCBBANK","UJJIVANSFB","ESAFSFB",
    "EQUITASBNK","SURYODAY","REPCO","MANAPPURAM","CHOLAFIN","SHRIRAMFIN","BAJAJHFL",
    "LICHSGFIN","PNBHOUSING","CANFINHOME","GRUH","AAVAS","HOMEFIRST","APTUS","FIVE STAR",
    "CREDITACC","ARMANFIN","SBFC","MOTILALOFS","ANGELONE","5PAISA","ICICIGI","NIACL",
    "STARHEALTH","GODIGIT","GICRE","ORIENTINS","NEWGEN","ROUTES","CAMPUS","METAHEALTH",
    "TATAMOTORS","M&MFIN","ASHOKLEY","ESCORTS","TIINDIA","MOTHERSON","BALKRISIND",
    "MRF","APOLLOTYRE","CEATLTD","GOODYEAR","JKTYRE","TVSMOTORS","BAJAJ-AUTO","ROYALENFIELD",
    "FORCE","SUNDRMFAST","BOSCHLTD","WABCOINDIA","ENDURANCE","SUPRAJIT","GABRIEL",
    "SHARDACROP","ASTRAL","SUPRIYA","ALKYLAMINE","DEEPAKNITR","GNFC","GSFC","FACT",
    "COROMANDEL","RALLIS","PI","DHANUKA","INSECTICID","ASTERDM","METROPOLIS","THYROCARE",
    "KRSNAA","VIJAYABANK","LATENTVIEW","ROUTE","AWFIS","YATRA","EASEMYTRIP","THOMAS",
    "LAXMIMACH","HEG","GRAPHITE","INOXWIND","SUZLON","GREENKO","RENEW","TORNTPOWER",
    "ADANIGREEN","TATAPOWER","CESC","KSKPOWER","RPOWER","ORIENTELEC","JPPOWER","NHPC",
    "SJVN","IRPOWER","NPTC","INOXGFL","CLEAN","GREENPANEL","CENTURY","WPIL","GODREJCP",
    "DABUR","MARICO","EMAMILTD","COLPAL","GILLETTE","PG","JYOTHYLAB","VBL","RADICO",
    "GLOBUSSPR","ABCAPITAL","EDELWEISS","IFCI","PFC","REC","IRFC","HUDCO","NABFID"
]

@app.get("/smart-screener")
async def smart_screener(max_price: float = 500.0):
    """
    Bulk screen NSE stocks: fetch prices via yfinance, filter by max_price,
    run full analysis in parallel, return only score=100 stocks.
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

    # Step 1: Bulk price fetch
    tickers = [f"{s}.NS" for s in SCREENER_UNIVERSE]
    try:
        raw = await asyncio.to_thread(
            lambda: yf.download(tickers, period="1d", interval="1d", progress=False, threads=True)
        )
        # raw["Close"] is a DataFrame with columns = ticker symbols
        close_row = raw["Close"].iloc[-1] if not raw.empty else {}
        price_map = {}
        for sym in SCREENER_UNIVERSE:
            col = f"{sym}.NS"
            val = close_row.get(col)
            if val is not None and not (hasattr(val, '__float__') and val != val):  # nan check
                try:
                    price_map[sym] = float(val)
                except Exception:
                    pass
    except Exception as e:
        print(f"[SmartScreener] Bulk price fetch failed: {e}")
        price_map = {}

    # Step 2: Filter by price
    affordable = [s for s in SCREENER_UNIVERSE if price_map.get(s, 9999) <= max_price]
    if not affordable:
        return {"status": "success", "results": [], "scanned": 0, "affordable": 0}

    # Step 3: Run full analysis sequentially with throttling to avoid AngelOne rate limit (3 req/sec)
    async def analyze_one(sym):
        try:
            res = await stock_analyzer.analyze_stock(sym, api_client)
            if res and res.get("status") == "success":
                return res
        except Exception:
            pass
        return None

    results_raw = []
    for sym in affordable[:20]:  # cap at 20
        res = await analyze_one(sym)
        results_raw.append(res)
        if api_client:
            # Each stock analysis makes 2 API calls, so sleep 0.75s to stay well below 3 req/sec limit
            await asyncio.sleep(0.75)

    # Step 4: Filter score == 100
    top_picks = [
        {
            "symbol": r["symbol"],
            "ltp": r["ltp"],
            "score": r["score"],
            "htf_trend": r["htf_trend"],
            "value_zone": r["value_zone"],
        }
        for r in results_raw if r and r.get("score", 0) == 100
    ]
    # Sort by price ascending
    top_picks.sort(key=lambda x: x["ltp"])

    return {
        "status": "success",
        "results": top_picks,
        "scanned": len(affordable),
        "affordable": len(affordable),
    }

@app.get("/analyze-stock")
async def analyze_stock(symbol: str):
    symbol = symbol.upper()
    from backend.engines.stock_analyzer import stock_analyzer
    
    if not broker.session:
        try:
            broker.login()
        except Exception as e:
            print(f"[AnalyzeStock] Startup-fallback broker login failed: {e}")
            
    api_client = broker.smart_api if broker.session else None
    res = await stock_analyzer.analyze_stock(symbol, api_client)
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
async def execute_stock_trade(symbol: str, side: str, qty: int = 1, background_tasks: BackgroundTasks = None):
    # Check if Equity trading is enabled in settings
    settings = await asyncio.to_thread(db_manager.get_settings) or {}
    equity_trading = settings.get("equity_trading", True)
    if not equity_trading:
        return {"status": "error", "message": "Equity Intraday trading is disabled in settings"}

    symbol = symbol.upper()
    side = side.upper()
    if side not in ["BUY", "SELL"]:
        return {"status": "error", "message": "Invalid transaction side"}
        
    # Daily Trade Check: prevent trading the same stock symbol if it has already been traded and closed today
    symbol_closed_trades = [
        sig for sig in signals 
        if (sig.get("symbol") == symbol or sig.get("symbol") == f"{symbol}-EQ") 
        and sig.get("status") == "CLOSED"
    ]
    if symbol_closed_trades:
        return {
            "status": "error", 
            "message": f"Daily lock active for {symbol}. Only one trade per stock is allowed daily."
        }
        
    from backend.engines.stock_analyzer import stock_analyzer
    res = await stock_analyzer.analyze_stock(symbol, broker.smart_api)
    if res.get("status") == "error":
        return res
        
    token = res["token"]
    trading_symbol = res["trading_symbol"]
    price = res["ltp"]
    
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
        
    signal_data = {
        "signal": side,
        "symbol": trading_symbol,
        "entry": price,
        "actual_entry": price,
        "sl": price - (price * 0.02) if side == "BUY" else price + (price * 0.02),
        "tp": price + (price * 0.04) if side == "BUY" else price - (price * 0.04),
        "reason": f"ALGO EQUITY {side} - Score: {res['score']}%",
        "is_paper": is_paper_trading,
        "timestamp": int(time.time() * 1000),
        "token": token,
        "qty": qty,
        "instrument_type": "EQUITY",
        "original_signal": side
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
            price=0,
            order_type="MARKET",
            exchange="NSE"
        )
        if not order_id:
            return {"status": "error", "message": "Broker execution failed"}
        signal_data["order_id"] = order_id
        
    signals.append(signal_data)
    if ws_manager:
        ws_manager.subscribe_token(token, 1) # 1 = NSE Equity Cash
    
    background_tasks.add_task(
        background_save_and_notify,
        signal_data,
        side,
        symbol,
        qty,
        trading_symbol,
        price
    )
    
    return {
        "status": "success",
        "message": "Stock trade executed successfully",
        "order_id": order_id,
        "trade": signal_data
    }

async def trading_loop():
    global trading_active, ws_manager
    
    # Always ensure a fresh session on toggle
    success = broker.login()
    if not success:
        trading_active = False
        return
    
    # Refresh WebSocket with fresh tokens
    if ws_manager:
        try:
            ws_manager.auth_token = broker.session['jwtToken']
            ws_manager.feed_token = broker.feed_token
            ws_manager.connect()
        except:
            ws_manager = None # Force recreation if refresh fails

    if not ws_manager:
        ws_manager = MarketWebSocket(
            broker.session['jwtToken'], 
            config.ANGEL_API_KEY, 
            config.ANGEL_CLIENT_ID, 
            broker.feed_token
        )
        ws_manager.connect()

    symbols = ["NIFTY", "BANKNIFTY"]
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
                    trade_manager.emergency_square_off(ltp_dict)
                    await asyncio.to_thread(broker.square_off_all)
                break  # FIX C-1: Always exit loop after 3:10 PM — no more iterations
            
            # Midnight Reset Check for continuous 24/7 VPS deployments
            today_date = now.date()
            global last_reset_date
            if today_date != last_reset_date:
                print(f"[Reset] Date changed from {last_reset_date} to {today_date}. Resetting daily risk stats.")
                risk_manager.reset_daily()
                last_reset_date = today_date

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
                
                # API Rate Limit (3 req/sec) Management: Fetch sequentially with delay
                df_1m = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "ONE_MINUTE", 2, exchange)
                await asyncio.sleep(0.4)
                df_5m = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "FIVE_MINUTE", 5, exchange)
                await asyncio.sleep(0.4)
                df_15m = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "FIFTEEN_MINUTE", 10, exchange)
                await asyncio.sleep(0.4)
                df_1h = await asyncio.to_thread(fetch_historical_data, broker.smart_api, token, "ONE_HOUR", 30, exchange)
                await asyncio.sleep(0.4)
                
                if any(df is None or df.empty for df in [df_1m, df_5m, df_15m, df_1h]): continue

                # Active signal engine computes ATR and EMA 50 on the fly; redundant indicator calculations are removed for performance.
                
                signal_data = signal_engine.generate_signal(df_1m, df_5m, df_15m, df_1h)
                side = signal_data['signal']

                # --- CORRELATION GUARD (Nifty vs BankNifty) ---
                if symbol == "NIFTY":
                    bn_token = token_manager.get_token("BANKNIFTY")
                    bn_exchange = token_manager.get_exchange("BANKNIFTY")
                    df_bn_5m = await asyncio.to_thread(fetch_historical_data, broker.smart_api, bn_token, "FIVE_MINUTE", 5, bn_exchange)
                    await asyncio.sleep(0.4)
                    if df_bn_5m is not None and not df_bn_5m.empty:
                        if not correlation_engine.check_index_alignment(df_5m, df_bn_5m):
                            print(f"[CorrelationGuard] NIFTY/BANKNIFTY divergence detected. Skipping {symbol}.")
                            continue
                            
                    # Heavyweight Check: Reliance
                    rel_token = token_manager.get_token("RELIANCE")
                    rel_exchange = token_manager.get_exchange("RELIANCE")
                    if rel_token:
                        df_rel_5m = await asyncio.to_thread(fetch_historical_data, broker.smart_api, rel_token, "FIVE_MINUTE", 5, rel_exchange)
                        await asyncio.sleep(0.4)
                        if not correlation_engine.check_heavyweight_alignment(symbol, df_5m, df_rel_5m):
                            continue

                elif symbol == "BANKNIFTY":
                    # Heavyweight Check: HDFC Bank
                    hdfc_token = token_manager.get_token("HDFCBANK")
                    hdfc_exchange = token_manager.get_exchange("HDFCBANK")
                    if hdfc_token:
                        df_hdfc_5m = await asyncio.to_thread(fetch_historical_data, broker.smart_api, hdfc_token, "FIVE_MINUTE", 5, hdfc_exchange)
                        await asyncio.sleep(0.4)
                        if not correlation_engine.check_heavyweight_alignment(symbol, df_5m, df_hdfc_5m):
                            continue

                # --- RISK & NEWS HARD LOCKS ---
                can_trade, reason = risk_manager.check_hard_locks(settings) if hasattr(risk_manager, 'check_hard_locks') else (True, "OK")
                if not can_trade:
                    print(f"[HardLock] {reason}")
                    continue
                
                if side in ["BUY", "SELL"] and risk_manager.can_trade(side):
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
                    
                    trade_symbol = symbol
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
                        signal_data.update({
                            'instrument_type': "OPTIONS",
                            'original_signal': side,
                            'underlying_token': token,
                            'underlying_entry': signal_data['entry'],
                            'underlying_sl': signal_data['sl'],
                            'underlying_tp': signal_data['tp'],
                            'option_premium': option_premium,
                        })
                    else:
                        qty = risk_manager.calculate_position_size(signal_data['entry'], signal_data['sl'], symbol)
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

        # ---------------------------------------------------------------------------

def sync_status_to_db():
    status = {
        "is_active": trading_active,
        "paper_trading": config.PAPER_TRADING,
        "signal_count": len(signals),
        "daily_loss": risk_manager.daily_loss,
        "trades_today": risk_manager.trades_today,
    }
    db_manager.update_system_status(status)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
