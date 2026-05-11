import json
import os

class TokenManager:
    def __init__(self, token_file='backend/config/tokens.json'):
        self.token_file = token_file
        self.tokens = {}
        self.load_tokens()

    def load_tokens(self):
        if os.path.exists(self.token_file):
            with open(self.token_file, 'r') as f:
                self.tokens = json.load(f)
        else:
            # Current active futures (May 2026 expiry)
            # Index tokens (NSE) - for reference only, not for candle data
            # Futures tokens (NFO) - used for candle data + order placement
            self.tokens = {
                "NIFTY":     {"token": "66071", "exchange": "NFO", "symbol": "NIFTY26MAY26FUT",     "lotsize": 25},
                "BANKNIFTY": {"token": "66068", "exchange": "NFO", "symbol": "BANKNIFTY26MAY26FUT", "lotsize": 15},
            }

    def get_token(self, symbol):
        entry = self.tokens.get(symbol)
        if isinstance(entry, dict):
            return entry['token']
        return entry # If it's a flat string from fetch_tokens.py

    def get_exchange(self, symbol):
        entry = self.tokens.get(symbol)
        if isinstance(entry, dict):
            return entry.get('exchange', 'NFO')
        # Heuristic: If it's NIFTY or BANKNIFTY and 8 digits, it's likely NSE Index
        # But for trading, we default to NFO if not specified
        return 'NFO'

    def get_symbol(self, symbol):
        entry = self.tokens.get(symbol)
        if isinstance(entry, dict):
            return entry.get('symbol', symbol)
        return symbol

    def get_lotsize(self, symbol):
        entry = self.tokens.get(symbol)
        if isinstance(entry, dict):
            return entry.get('lotsize', 25 if 'BANKNIFTY' not in symbol else 15)
        # Fallback lotsizes for 2026 (Nifty: 25, BankNifty: 15)
        if 'BANKNIFTY' in symbol: return 15
        return 25

token_manager = TokenManager()
