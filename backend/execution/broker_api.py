from SmartApi import SmartConnect
from config.config import config
import pyotp

class AngelOneBroker:
    def __init__(self):
        self.smart_api = SmartConnect(api_key=config.ANGEL_API_KEY)
        self.session = None

    def login(self):
        """
        Authenticate with Angel One using credentials from config.
        """
        if not config.ANGEL_PIN or config.ANGEL_PIN == "your_mpin_here":
            print("ERROR: Please set your ANGEL_PIN (MPIN) in the .env file.")
            return False

        try:
            totp = pyotp.TOTP(config.ANGEL_TOTP_KEY).now()
            data = self.smart_api.generateSession(config.ANGEL_CLIENT_ID, config.ANGEL_PIN, totp)

            
            if data['status']:
                self.session = data['data']
                # Feed token is needed for WebSocket
                self.feed_token = self.smart_api.getfeedToken()
                print("SUCCESS: Angel One Login Successful")
                return True
            else:
                print(f"FAILED: Angel One Login: {data['message']}")
                return False
        except Exception as e:
            print(f"EXCEPTION during login: {e}")
            return False

    def place_order(self, symbol, token, qty, side, price, order_type="MARKET"):
        """
        Place a trade order with slippage protection.
        side: BUY or SELL
        """
        if not self.session:
            print("ERROR: No active session. Please login first.")
            return None

        # --- PRODUCTION SAFETY: Slippage & Spread Check ---
        current_ltp = self.get_market_data("NFO", symbol, token)
        if current_ltp > 0:
            slippage = abs(current_ltp - price) / price
            if slippage > 0.005: # 0.5% max slippage
                print(f"[Broker] BLOCKED: High slippage detected ({slippage:.4f})")
                return None

        try:
            order_params = {
                "variety": "NORMAL",
                "tradingsymbol": symbol,
                "symboltoken": token,
                "transactiontype": side,
                "exchange": "NFO",
                "ordertype": order_type,
                "producttype": "INTRADAY",
                "duration": "DAY",
                "quantity": qty
            }
            res = self.smart_api.placeOrder(order_params)
            if res['status']:
                return res['data']['orderid']
            return None
        except Exception as e:
            print(f"ERROR placing order for {symbol}: {e}")
            return None

    def get_order_status(self, order_id):
        try:
            res = self.smart_api.orderBook()
            if res['status'] and res['data']:
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
            if data['status']:
                return data['data']['ltp']
        except Exception as e:
            print(f"ERROR fetching market data for {symbol}: {e}")
        return 0.0

    def square_off_all(self):
        """
        Fetch all open positions and close them.
        """
        if not self.session:
            return False
        
        try:
            positions = self.smart_api.position()
            if positions['status'] and positions['data']:
                for pos in positions['data']:
                    net_qty = int(pos['netqty'])
                    if net_qty != 0:
                        side = "SELL" if net_qty > 0 else "BUY"
                        self.place_order(
                            symbol=pos['tradingsymbol'],
                            token=pos['symboltoken'],
                            qty=abs(net_qty),
                            side=side
                        )
                return True
        except Exception as e:
            print(f"ERROR during square off: {e}")
        return False
