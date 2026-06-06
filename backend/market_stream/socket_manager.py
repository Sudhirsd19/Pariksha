from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from backend.config.config import config
from backend.safety.health_monitor import health_monitor
import threading
import time

class MarketWebSocket:
    def __init__(self, auth_token, api_key, client_code, feed_token):
        self.auth_token = auth_token
        self.api_key = api_key
        self.client_code = client_code
        self.feed_token = feed_token
        self.ltp_data = {}
        self.sws = None
        self.running = False

    def on_data(self, wsapp, msg):
        """Callback when data is received"""
        if 'last_traded_price' in msg:
            token = msg['token']
            self.ltp_data[token] = msg['last_traded_price'] / 100 # Convert to actual price
            health_monitor.update_tick()

    def on_open(self, wsapp):
        print("WebSocket Connected!")
        self.running = True
        correlation_id = "quantum_index_feed"
        action = 1 # Subscribe
        mode = 3 # Full data (includes LTP)
        
        from backend.utils.token_manager import token_manager
        nifty_token = token_manager.get_token("NIFTY")
        banknifty_token = token_manager.get_token("BANKNIFTY")
        
        tokens = [
            {"exchangeType": 2, "tokens": [nifty_token, banknifty_token]},   # NFO Futures
            {"exchangeType": 1, "tokens": ["99926000", "99926009"]}  # NSE Index
        ]
        self.sws.subscribe(correlation_id, mode, tokens)

    def on_error(self, wsapp, error):
        print(f"WebSocket Error: {error}")
        health_monitor.record_api_failure()

    def on_close(self, wsapp):
        print("WebSocket Closed")
        self.running = False
        # FIX L-5: Removed is_connected guard — was False on first connect so reconnection was SKIPPED
        # FIX L-6: Replaced blocking time.sleep(5) with a daemon thread to avoid blocking the WS thread
        print("Attempting to reconnect WebSocket in 5s...")
        def delayed_reconnect():
            time.sleep(5)
            if not self.running:  # Only reconnect if still disconnected
                self.connect()
        t = threading.Thread(target=delayed_reconnect, daemon=True)
        t.start()

    def connect(self):
        self.sws = SmartWebSocketV2(self.auth_token, self.api_key, self.client_code, self.feed_token)
        self.sws.on_open = self.on_open
        self.sws.on_data = self.on_data
        self.sws.on_error = self.on_error
        self.sws.on_close = self.on_close
        
        # Run in background thread
        ws_thread = threading.Thread(target=self.sws.connect)
        ws_thread.daemon = True
        ws_thread.start()

    def subscribe_token(self, token, exchange_type=2):
        """Dynamically subscribe to a new token feed (like an option contract)."""
        if self.sws and self.running:
            correlation_id = f"sub_{token}"
            tokens = [{"exchangeType": exchange_type, "tokens": [token]}]
            try:
                self.sws.subscribe(correlation_id, 3, tokens)
                print(f"[WebSocket] Dynamically subscribed to option token: {token}")
            except Exception as e:
                print(f"[WebSocket] Error subscribing to {token}: {e}")

    def get_ltp(self, token):
        return self.ltp_data.get(token)

