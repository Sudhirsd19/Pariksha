import json
import os
import time
from datetime import datetime

class TokenManager:
    def __init__(self, token_file='backend/config/tokens.json'):
        self.token_file = token_file
        self.tokens = {}
        self.options_index = {}
        self.stocks_index = {}
        self.load_tokens()
        self.load_scrip_master()

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
        if 'BANKNIFTY' in symbol: return 15
        return 25

    # --- OPTIONS TRADING FEATURES (₹10,000 Capital Support) ---

    def download_scrip_master(self):
        """Downloads the OpenAPI Scrip Master if not cached or if cache is stale (>24h)."""
        import requests
        cache_path = 'backend/data/OpenAPIScripMaster.json'
        
        # Check if cache is fresh
        if os.path.exists(cache_path):
            mtime = os.path.getmtime(cache_path)
            if (time.time() - mtime) < 86400:  # 24 hours
                return cache_path
                
        print("[TokenManager] Cache missing/stale. Downloading Scrip Master from Angel One (this may take a few seconds)...")
        try:
            url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                os.makedirs(os.path.dirname(cache_path), exist_ok=True)
                with open(cache_path, 'wb') as f:
                    f.write(response.content)
                print("[TokenManager] Scrip Master cached successfully!")
                return cache_path
        except Exception as e:
            print(f"[TokenManager] Error downloading Scrip Master: {e}")
            if os.path.exists(cache_path):
                print("[TokenManager] Falling back to stale local cache.")
                return cache_path
        return None

    def resolve_active_futures(self, data):
        """Finds nearest active futures contract for NIFTY and BANKNIFTY from Scrip Master data."""
        from datetime import timezone, timedelta
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        today = datetime.now(ist_tz).date()
        nifty_futs = []
        banknifty_futs = []
        
        for item in data:
            if item.get('exch_seg') == 'NFO' and item.get('instrumenttype') == 'FUTIDX':
                name = item.get('name')
                expiry_str = item.get('expiry')
                if not expiry_str:
                    continue
                try:
                    expiry_date = datetime.strptime(expiry_str, "%d%b%Y").date()
                except Exception:
                    continue
                    
                if expiry_date >= today:
                    entry = {
                        "token": item.get("token"),
                        "symbol": item.get("symbol"),
                        "expiry": expiry_date,
                        "lotsize": int(item.get("lotsize", 1))
                    }
                    if name == "NIFTY":
                        nifty_futs.append(entry)
                    elif name == "BANKNIFTY":
                        banknifty_futs.append(entry)
                        
        nifty_futs.sort(key=lambda x: x["expiry"])
        banknifty_futs.sort(key=lambda x: x["expiry"])
        
        updated = False
        if nifty_futs:
            nifty = nifty_futs[0]
            self.tokens["NIFTY"] = {
                "token": nifty["token"],
                "exchange": "NFO",
                "symbol": nifty["symbol"],
                "lotsize": nifty["lotsize"]
            }
            updated = True
            
        if banknifty_futs:
            bn = banknifty_futs[0]
            self.tokens["BANKNIFTY"] = {
                "token": bn["token"],
                "exchange": "NFO",
                "symbol": bn["symbol"],
                "lotsize": bn["lotsize"]
            }
            updated = True
            
        if updated:
            print(f"[TokenManager] Dynamically resolved active futures: NIFTY={self.tokens['NIFTY']['symbol']} ({self.tokens['NIFTY']['token']}), BANKNIFTY={self.tokens['BANKNIFTY']['symbol']} ({self.tokens['BANKNIFTY']['token']})")
            try:
                os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
                with open(self.token_file, 'w') as f:
                    json.dump(self.tokens, f, indent=4)
            except Exception as e:
                print(f"[TokenManager] Error saving resolved tokens: {e}")

    def load_scrip_master(self):
        """Builds an O(1) fast lookup index of active options in memory."""
        cache_path = self.download_scrip_master()
        if not cache_path or not os.path.exists(cache_path):
            print("[TokenManager] ERROR: Scrip Master cache not available.")
            return
            
        print("[TokenManager] Building Option Contract Index...")
        try:
            with open(cache_path, 'r') as f:
                data = json.load(f)
                
            self.resolve_active_futures(data)
            
            self.options_index = {}
            self.stocks_index = {}
            for target in ["NIFTY", "BANKNIFTY"]:
                self.options_index[target] = {"CE": {}, "PE": {}}
                
            from datetime import timezone, timedelta
            ist_tz = timezone(timedelta(hours=5, minutes=30))
            today = datetime.now(ist_tz).date()
            count = 0
            
            for item in data:
                exch_seg = item.get('exch_seg')
                if exch_seg == 'NSE' and item.get('symbol', '').endswith('-EQ'):
                    name = item.get('name')
                    if name:
                        self.stocks_index[name] = {
                            "name": name,
                            "token": item.get("token"),
                            "symbol": item.get("symbol"),
                            "lotsize": int(item.get("lotsize", 1))
                        }
                    continue
                if (item.get('name') in ["NIFTY", "BANKNIFTY"] and 
                    exch_seg == 'NFO' and 
                    item.get('instrumenttype') == 'OPTIDX'):
                    
                    symbol = item.get('name')
                    raw_strike = float(item.get('strike', 0))
                    strike = int(raw_strike / 100.0)
                    
                    expiry_str = item.get('expiry')
                    if not expiry_str:
                        continue
                    try:
                        expiry_date = datetime.strptime(expiry_str, "%d%b%Y").date()
                    except Exception:
                        continue
                        
                    # Skip expired contracts
                    if expiry_date < today:
                        continue
                        
                    trading_symbol = item.get('symbol', '')
                    if trading_symbol.endswith("CE"):
                        opt_type = "CE"
                    elif trading_symbol.endswith("PE"):
                        opt_type = "PE"
                    else:
                        continue
                        
                    if strike not in self.options_index[symbol][opt_type]:
                        self.options_index[symbol][opt_type][strike] = []
                        
                    self.options_index[symbol][opt_type][strike].append({
                        "token": item.get("token"),
                        "symbol": trading_symbol,
                        "lotsize": int(item.get("lotsize", 25)),
                        "expiry": expiry_date
                    })
                    count += 1
                    
            # Sort contracts under each strike by expiry (nearest first)
            for target in ["NIFTY", "BANKNIFTY"]:
                for opt_type in ["CE", "PE"]:
                    for strike in self.options_index[target][opt_type]:
                        self.options_index[target][opt_type][strike].sort(key=lambda x: x["expiry"])
                        
            print(f"[TokenManager] Successfully indexed {count} active option contracts!")
        except Exception as e:
            print(f"[TokenManager] Error building options index: {e}")

    def get_atm_option(self, symbol, index_ltp, option_type, force_next_weekly=False):
        """
        Fetch nearest weekly expiry ATM Option contract details.
        option_type: CE or PE
        """
        if not self.options_index:
            self.load_scrip_master()
            
        if not self.options_index or symbol not in self.options_index:
            return None
            
        # Nifty strike interval = 50, BankNifty = 100
        if symbol == "NIFTY":
            strike = int(round(index_ltp / 50.0) * 50)
        elif symbol == "BANKNIFTY":
            strike = int(round(index_ltp / 100.0) * 100)
        else:
            return None
            
        try:
            contracts = self.options_index.get(symbol, {}).get(option_type, {}).get(strike, [])
            if contracts:
                # Get current date in IST
                from datetime import timezone, timedelta
                ist_tz = timezone(timedelta(hours=5, minutes=30))
                today = datetime.now(ist_tz).date()
                
                # Check if the nearest contract expires today. If so, return next week's contract (index 1) to avoid theta decay.
                if len(contracts) > 1 and (contracts[0]["expiry"] == today or force_next_weekly):
                    return contracts[1]
                return contracts[0]  # Nearest expiry is first
        except Exception as e:
            print(f"[TokenManager] Error looking up ATM Option for {symbol}: {e}")
            
        return None

    def get_stock_info(self, symbol):
        """
        Fetch stock details (token, symbol, lotsize) for an NSE stock.
        Supports fuzzy/partial matching if exact match fails.
        """
        if not self.stocks_index:
            self.load_scrip_master()
            
        symbol_upper = symbol.upper().strip()
        
        # 1. Try exact match first
        info = self.stocks_index.get(symbol_upper)
        if info:
            return info
            
        # 2. Try prefix/contains matching to resolve partial symbols (e.g. 'HDFC' -> 'HDFCBANK')
        matches = [k for k in self.stocks_index.keys() if symbol_upper in k]
        if matches:
            # Sort matches so that:
            # - Matches starting with the query come first
            # - Shorter names come first (exact-ish match preference)
            matches.sort(key=lambda name: (not name.startswith(symbol_upper), len(name)))
            best_match = matches[0]
            print(f"[TokenManager] Fuzzy resolved '{symbol}' to '{best_match}'")
            return self.stocks_index.get(best_match)
            
        return None

token_manager = TokenManager()
