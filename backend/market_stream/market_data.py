from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from backend.config.config import config
import pandas as pd
from datetime import datetime
import json

class MarketDataWebSocket:
    def __init__(self, auth_token, feed_token, on_candle_update=None):
        self.sws = SmartWebSocketV2(auth_token, config.ANGEL_API_KEY, config.ANGEL_CLIENT_ID, feed_token)
        self.on_candle_update = on_candle_update
        self.ticks = []
        # In-memory storage for the latest candles
        self.data_5m = pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])

    def on_data(self, ws, msg):
        """
        Process incoming tick data.
        """
        try:
            # Parse tick data (Simplified)
            # msg usually contains ltp, volume, etc.
            if 'last_traded_price' in msg:
                ltp = float(msg['last_traded_price']) / 100 # Angel One prices are often in paise
                timestamp = datetime.now()
                volume = msg.get('volume', 0)
                
                tick = {'time': timestamp, 'price': ltp, 'volume': volume}
                self.ticks.append(tick)
                
                # Logic to aggregate ticks into a 5m candle
                self._process_candles(tick)
                
        except Exception as e:
            print(f"Error processing tick: {e}")

    def _process_candles(self, tick):
        # Simplified candle aggregation logic
        # In production, use a more robust time-windowing approach
        if self.on_candle_update:
            self.on_candle_update(tick)

    def on_open(self, ws):
        print("WebSocket Connection Opened")
        # Subscribe to NIFTY and BANKNIFTY
        token_list = [
            {"exchangeType": 1, "tokens": ["26000"]}, # Nifty Spot
            {"exchangeType": 1, "tokens": ["26009"]}  # Bank Nifty Spot
        ]
        self.sws.subscribe("quantum_feed", 3, token_list)

    def on_error(self, ws, error):
        print(f"WebSocket Error: {error}")

    def on_close(self, ws):
        print("WebSocket Closed")

    def connect(self):
        self.sws.on_open = self.on_open
        self.sws.on_data = self.on_data
        self.sws.on_error = self.on_error
        self.sws.on_close = self.on_close
        self.sws.connect()


