import asyncio
import os
import sys
import json
import random
import time
from datetime import datetime, time as dt_time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from config.config import config
from engines.cooldown_engine import CooldownEngine
from execution.broker_api import AngelOneBroker
from indicators.technical_indicators import TechnicalIndicators
from market_stream.socket_manager import MarketWebSocket
from risk_management.risk_manager import RiskManager
from signal_engine.signal_engine import SignalEngine
from utils.historical_data import fetch_historical_data
from utils.token_manager import token_manager
from config.firebase_config import init_firebase
from utils.db_manager import db_manager
from utils.trade_manager import trade_manager
from firebase_admin import messaging
from safety.health_monitor import health_monitor
from utils.persistence_manager import persistence_manager

app = FastAPI(title="QuantumIndex Algo-Trading System")

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
        print(f"SENT NOTIFICATION: {title}")
    except Exception as e:
        print(f"FCM Notification Error: {e}")

@app.on_event("startup")
async def startup_event():
    init_firebase()
    asyncio.create_task(ltp_broadcaster())

# Shared State
trading_active = False
trading_loop_task = None
signals = []
connected_ws_clients = set()  # Active Flutter WebSocket clients
current_ltp = 23997.55       # Shared live price

# Core Components
broker = AngelOneBroker()
risk_manager = RiskManager(initial_capital=100000)
signal_engine = SignalEngine()
cooldown_engine = CooldownEngine(minutes=10) # 10 min cooldown
ws_manager = None

@app.get("/")
async def root():
    return {"message": "QuantumIndex Backend Running"}

@app.get("/logs")
async def get_logs():
    return signals # Returning the list of signals as trade logs

@app.get("/status")
async def get_status():
    global current_ltp
    
    # Calculate simple sentiment from last signal
    sentiment = "Neutral"
    sentiment_score = 0.5
    if signals:
        last = signals[-1]
        sentiment = "Bullish" if last['signal'] == "BUY" else "Bearish"
        sentiment_score = 0.8 if sentiment == "Bullish" else 0.2

    return {
        "is_active": trading_active,
        "paper_trading": config.PAPER_TRADING,
        "signal_count": len(signals),
        "last_signal": signals[-1]['signal'] if signals else "None",
        "daily_loss": risk_manager.daily_loss,
        "trades_today": risk_manager.trades_today,
        "ltp": current_ltp,
        "sentiment": sentiment,
        "sentiment_score": sentiment_score
    }

@app.websocket("/ws/market")
async def websocket_market(websocket: WebSocket):
    """Real-time LTP stream to Flutter app."""
    await websocket.accept()
    print(f"DEBUG: Flutter Client Connected from {websocket.client.host}")
    connected_ws_clients.add(websocket)
    try:
        while True:
            # Keep connection alive; broadcasting is done by ltp_broadcaster
            await websocket.receive_text()
    except WebSocketDisconnect:
        print("DEBUG: Flutter Client Disconnected")
        connected_ws_clients.discard(websocket)
    except Exception as e:
        print(f"DEBUG: WebSocket Error: {e}")
        connected_ws_clients.discard(websocket)

# --- GLOBAL STATE & CACHE ---
trading_active = False
is_paper_trading = True
trading_loop_task = None
connected_ws_clients = set()
current_ltp = 0.0
last_broadcast_ltp = 0.0 # For adaptive throttling
last_execution_candle = { "NIFTY": None, "BANKNIFTY": None } # Candle lock

@app.on_event("startup")
async def startup_event():
    init_firebase()
    # Resume state from local SQLite
    trade_manager.load_state()
    trade_manager.risk_manager = risk_manager
    persistence_manager.log_event("INFO", "SYSTEM_STARTUP", "QuantumIndex Engine Initialized")
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
            if not health_monitor.is_feed_healthy() and not is_paper_trading:
                if trading_active:
                    persistence_manager.log_event("WARNING", "STALE_FEED", "Trading halted due to frozen data")
                    await toggle_trading(False)
            
            current_ltps = {}
            for symbol, token in tokens.items():
                ltp = ws_manager.get_ltp(token) if ws_manager else 0
                if not ltp or ltp == 0:
                    drift = random.uniform(-1.5, 1.5)
                    simulated_ltps[token] = round(simulated_ltps[token] + drift, 2)
                    ltp = simulated_ltps[token]
                current_ltps[token] = ltp
                if symbol == "NIFTY": current_ltp = ltp

            # 2. Monitor open trades (Thread-safe)
            closed_trades = await asyncio.to_thread(trade_manager.monitor_trades, current_ltps)
            for trade in (closed_trades or []):
                send_push_notification(f"🏁 TRADE CLOSED: {trade['close_data']['result']}", f"PnL: Rs. {trade['close_data']['pnl']:.2f}")

            # 3. Adaptive Throttling (Broadcast only if movement > 0.5 points)
            if connected_ws_clients and abs(current_ltp - last_broadcast_ltp) > 0.5:
                last_broadcast_ltp = current_ltp
                payload = json.dumps({"ltp": current_ltp, "ltps": current_ltps, "connected": True})
                for client in list(connected_ws_clients):
                    try: await client.send_text(payload)
                    except: connected_ws_clients.discard(client)

        except Exception as e:
            print(f"[Broadcaster Error]: {e}")
        await asyncio.sleep(0.05)

@app.post("/toggle-trading")
async def toggle_trading(active: bool):
    global trading_active, trading_loop_task
    trading_active = active
    if trading_active:
        if trading_loop_task is None or trading_loop_task.done():
            trading_loop_task = asyncio.create_task(trading_loop())
    persistence_manager.log_event("INFO", "ENGINE_TOGGLED", f"Active: {active}")
    return {"status": "success", "trading_active": trading_active}

@app.get("/analytics")
async def get_analytics():
    # Simulated analytics based on signal count to make it somewhat dynamic
    base_win_rate = 62.5
    base_profit_factor = 1.75
    
    if signals:
        bonus = min(len(signals) * 0.5, 10)
        win_rate = base_win_rate + bonus
        profit_factor = base_profit_factor + (bonus * 0.05)
    else:
        win_rate = base_win_rate
        profit_factor = base_profit_factor

    return {
        "win_rate": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "avg_winner": 2850.0,
        "avg_loser": 1420.0
    }

@app.get("/pnl")
async def get_pnl():
    # Deprecated: Now using Firebase PnL
    pass

@app.post("/test-trade")
async def trigger_test_trade():
    import random
    ltp = 23997.55
    signal_data = {
        "signal": "BUY",
        "symbol": "NIFTY",
        "entry": ltp,
        "actual_entry": ltp + 0.5,
        "sl": ltp - 3.0,
        "tp": ltp + 3.0,
        "reason": "TEST - PnL Accuracy Verification",
        "is_paper": True,
        "timestamp": int(asyncio.get_event_loop().time() * 1000)
    }
    
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
    count = trade_manager.emergency_square_off({}) # Square off all active trades
    broker.square_off_all()
    return {"status": "killed", "trades_closed": count}

@app.post("/square-off")
async def square_off():
    """Emergency Exit: Closes all orders on broker and updates internal state."""
    global trading_active
    trading_active = False
    broker.square_off_all()
    ltp_dict = ws_manager.ltp_data if ws_manager else {}
    count = trade_manager.emergency_square_off(ltp_dict)
    sync_status_to_db()
    return {"status": "success", "message": f"Square Off: {count} trades closed."}

async def trading_loop():
    global trading_active, ws_manager
    

    if not broker.session:
        success = broker.login()
        if not success:
            trading_active = False
            return
        
        # Start WebSocket after successful login
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
            now = datetime.now()
            # Candle Lock Check (Wait for new minute)
            if now.second > 55: await asyncio.sleep(5); continue

            for symbol in symbols:
                # Candle Lock: One trade per symbol per minute
                candle_id = now.strftime("%Y-%m-%d %H:%M")
                if last_execution_candle[symbol] == candle_id: continue

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

                indicator_tasks = [
                    asyncio.to_thread(TechnicalIndicators.apply_all, df_1m),
                    asyncio.to_thread(TechnicalIndicators.apply_all, df_5m),
                    asyncio.to_thread(TechnicalIndicators.apply_all, df_15m),
                    asyncio.to_thread(TechnicalIndicators.apply_all, df_1h)
                ]
                df_1m, df_5m, df_15m, df_1h = await asyncio.gather(*indicator_tasks)
                
                signal_data = signal_engine.generate_signal(df_1m, df_5m, df_15m, df_1h)
                side = signal_data['signal']
                
                if side in ["BUY", "SELL"] and risk_manager.can_trade(side):
                    # Execution
                    qty = risk_manager.calculate_position_size(signal_data['entry'], signal_data['sl'], symbol)
                    order_id = None
                    if is_paper_trading:
                        order_id = f"VIRTUAL_{int(time.time())}"
                    else:
                        order_id = broker.place_order(symbol, token, qty, side, signal_data['entry'])
                    
                    if order_id:
                        last_execution_candle[symbol] = candle_id
                        risk_manager.record_entry(side)
                        signal_data.update({'actual_entry': signal_data['entry'], 'token': token, 'qty': qty, 'timestamp': int(time.time()*1000)})
                        doc_id = db_manager.save_signal(signal_data)
                        trade_manager.add_trade(signal_data, doc_id)
                        send_push_notification(f"🚀 SIGNAL: {symbol} {side}", f"Entry: {signal_data['entry']}")
                        cooldown_engine.update_last_trade()
                        await asyncio.to_thread(sync_status_to_db)
            
            await asyncio.sleep(1)
        except Exception as e:
            print(f"[Trading Loop Error]: {e}")
            await asyncio.sleep(5)

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
