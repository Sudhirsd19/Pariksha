from SmartApi import SmartConnect
from backend.config.config import config
import pyotp

class AngelOneBroker:
    def __init__(self):
        self.smart_api = SmartConnect(api_key=config.ANGEL_API_KEY)
        self.session = None
        self.feed_token = None  # FIX: Initialize so attribute always exists before login

    def login(self):
        """
        Authenticate with Angel One using credentials from backend.config.
        """
        if not config.ANGEL_PIN or config.ANGEL_PIN == "your_mpin_here":
            print("ERROR: Please set your ANGEL_PIN (MPIN) in the .env file.")
            return False

        try:
            totp = pyotp.TOTP(config.ANGEL_TOTP_KEY).now()
            data = self.smart_api.generateSession(config.ANGEL_CLIENT_ID, config.ANGEL_PIN, totp)

            if data.get('status'):  # FIX: use .get() to avoid KeyError on unexpected response
                self.session = data['data']
                self.feed_token = self.smart_api.getfeedToken()
                print("SUCCESS: Angel One Login Successful")
                return True
            else:
                print(f"FAILED: Angel One Login: {data.get('message', 'Unknown error')}")
                return False
        except Exception as e:
            print(f"EXCEPTION during login: {e}")
            return False

    def place_order(self, symbol, token, qty, side, price=0, order_type="MARKET", exchange="NFO"):
        """
        Place a trade order with slippage protection.
        side: BUY or SELL
        price: 0 for MARKET orders (broker ignores price for MARKET type)
        """
        if not self.session:
            print("ERROR: No active session. Please login first.")
            return None

        # --- PRODUCTION SAFETY: Slippage & Spread Check (only for MARKET orders) ---
        if order_type == "MARKET" and price > 0:
            current_ltp = self.get_market_data(exchange, symbol, token)
            if current_ltp > 0:
                slippage = abs(current_ltp - price) / price
                if slippage > 0.005:  # 0.5% max slippage
                    print(f"[Broker] BLOCKED: High slippage detected ({slippage:.4f})")
                    return None

        try:
            order_params = {
                "variety": "NORMAL",
                "tradingsymbol": symbol,
                "symboltoken": token,
                "transactiontype": side,
                "exchange": exchange,
                "ordertype": order_type,
                "producttype": "INTRADAY",
                "duration": "DAY",
                "quantity": qty
            }
            res = self.smart_api.placeOrder(order_params)
            
            # Auto-recovery: If token is missing/expired, trigger a re-login and retry placing the order
            is_token_error = False
            if not res:
                is_token_error = True
            elif not res.get('status'):
                err_code = res.get('errorCode', '')
                err_msg = res.get('message', '').lower()
                if err_code in ["AG8003", "AB1000"] or "token" in err_msg or "session" in err_msg:
                    is_token_error = True
                    
            if is_token_error:
                print("[Broker] Detected invalid/expired session. Attempting auto-login recovery...")
                if self.login():
                    res = self.smart_api.placeOrder(order_params)

            if res and res.get('status'):  # guard against None response
                order_data = res.get('data') or {}
                order_id = order_data.get('orderid')
                if order_id:
                    return order_id
            print(f"[Broker] Order failed: {res.get('message', 'No response') if res else 'None response'}")
            return None
        except Exception as e:
            print(f"ERROR placing order for {symbol}: {e}")
            return None

    def get_order_status(self, order_id):
        try:
            res = self.smart_api.orderBook()
            if res and res.get('status') and res.get('data'):
                for order in res['data']:
                    if order['orderid'] == order_id:
                        return order['status']
            return "UNKNOWN"
        except Exception as e:
            print(f"ERROR fetching order status: {e}")
            return "ERROR"

    def get_market_data(self, exchange, symbol, token):
        """
        Fetch Last Traded Price (LTP) for a token.
        """
        try:
            data = self.smart_api.ltpData(exchange, symbol, token)
            if data and data.get('status'):  # FIX: guard against None
                return data['data']['ltp']
        except Exception as e:
            print(f"ERROR fetching market data for {symbol}: {e}")
        return 0.0

    def square_off_all(self):
        """
        Fetch all open positions and close them at MARKET price.
        FIX: price param is now optional (default 0) for MARKET orders — was crashing with TypeError.
        """
        if not self.session:
            return False

        try:
            positions = self.smart_api.position()
            if positions and positions.get('status') and positions.get('data'):
                for pos in positions['data']:
                    net_qty = int(pos.get('netqty', 0))
                    if net_qty != 0:
                        side = "SELL" if net_qty > 0 else "BUY"
                        result = self.place_order(
                            symbol=pos['tradingsymbol'],
                            token=pos['symboltoken'],
                            qty=abs(net_qty),
                            side=side,
                            price=0,           # FIX: MARKET order — price is ignored by broker
                            order_type="MARKET"
                        )
                        if not result:
                            print(f"[SquareOff] WARNING: Failed to close {pos['tradingsymbol']}")
            return True
        except Exception as e:
            print(f"ERROR during square off: {e}")
        return False
