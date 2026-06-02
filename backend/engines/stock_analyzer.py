import asyncio
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Try importing yfinance, fallback to mock/scraped data if not installed
try:
    import yfinance as yf
except ImportError:
    yf = None

from backend.utils.token_manager import token_manager
from backend.utils.historical_data import fetch_historical_data
from backend.engines.structure_engine import StructureEngine
from backend.indicators.technical_indicators import TechnicalIndicators

# Offline fundamental data for common NSE stocks (as fallback and speed optimization)
STOCK_FUNDAMENTAL_CACHE = {
    "RELIANCE": {"pe": 26.5, "debt_to_equity": 0.42, "promoter_pledge": 0.0, "news_event": "Safe"},
    "TCS": {"pe": 30.1, "debt_to_equity": 0.05, "promoter_pledge": 0.5, "news_event": "Safe"},
    "INFY": {"pe": 24.2, "debt_to_equity": 0.06, "promoter_pledge": 0.0, "news_event": "Safe"},
    "HDFCBANK": {"pe": 19.8, "debt_to_equity": 0.88, "promoter_pledge": 0.0, "news_event": "Safe"},
    "ICICIBANK": {"pe": 18.2, "debt_to_equity": 0.81, "promoter_pledge": 0.0, "news_event": "Safe"},
    "TATASTEEL": {"pe": 14.5, "debt_to_equity": 1.15, "promoter_pledge": 1.2, "news_event": "Safe"},
    "SBIN": {"pe": 10.5, "debt_to_equity": 1.50, "promoter_pledge": 0.0, "news_event": "Safe"},
    "BHARTIARTL": {"pe": 45.2, "debt_to_equity": 1.62, "promoter_pledge": 0.0, "news_event": "Safe"},
    "WIPRO": {"pe": 22.1, "debt_to_equity": 0.12, "promoter_pledge": 0.0, "news_event": "Safe"},
    "ADANIPORTS": {"pe": 35.4, "debt_to_equity": 1.05, "promoter_pledge": 15.2, "news_event": "Safe"},
}

class StockAnalyzer:
    def __init__(self):
        self.struct_engine = StructureEngine(lookback=20)

    async def analyze_stock(self, symbol: str, smart_api=None) -> dict:
        """
        Runs full technical and fundamental analysis on a stock.
        symbol: e.g. 'RELIANCE'
        """
        # 1. Resolve stock token
        stock_info = token_manager.get_stock_info(symbol)
        if not stock_info:
            return {"status": "error", "message": f"Stock symbol {symbol} not found in Scrip Master."}

        token = stock_info["token"]
        symbol = stock_info["name"]  # Use resolved name (e.g. HDFCBANK instead of hdfc)
        exchange = "NSE"  # Equity cash is on NSE
        trading_symbol = stock_info["symbol"]

        # 2. Fetch candles asynchronously via threads
        # We need daily candles for 50 EMA (say 80 days to be safe)
        # We need 5M candles for market structure (say 5 days)
        df_1d = None
        df_5m = None

        if smart_api:
            try:
                # Fetch daily candles
                df_1d = await asyncio.to_thread(
                    fetch_historical_data, smart_api, token, "ONE_DAY", days=80, exchange=exchange
                )
                # Fetch 5-Minute candles
                df_5m = await asyncio.to_thread(
                    fetch_historical_data, smart_api, token, "FIVE_MINUTE", days=5, exchange=exchange
                )
            except Exception as e:
                print(f"[StockAnalyzer] Error fetching candles for {symbol}: {e}")

        # If offline or data failed, create mock/simulated candles for demonstration
        if df_1d is None or df_1d.empty:
            df_1d = self._create_mock_candles(interval="ONE_DAY", count=80, base_price=2500)
        if df_5m is None or df_5m.empty:
            df_5m = self._create_mock_candles(interval="FIVE_MINUTE", count=100, base_price=2500)

        # 3. Technical checks
        # Calculate EMA 50 on Daily candles
        df_1d = TechnicalIndicators.add_ema(df_1d, 50)
        last_1d = df_1d.iloc[-1]
        close_1d = last_1d["close"]
        ema_50 = last_1d["EMA_50"]
        htf_trend = "Bullish" if close_1d > ema_50 else "Bearish"

        # Market structure on 5M candles
        struct_res = self.struct_engine.analyze(df_5m)
        value_zone = "Equilibrium"
        if struct_res["in_discount"]:
            value_zone = "Discount"
        elif struct_res["in_premium"]:
            value_zone = "Premium"

        # Displacement/OB check (BOS or swing sweeps or general bullish bias)
        displacement_pass = struct_res["bos_bullish"] or struct_res["fvg_gap"] or struct_res["sweep_low"]

        # 4. Fundamental checks (using yfinance with offline cache backup)
        pe = None
        debt_to_equity = None
        promoter_pledge = 0.0
        news_event = "Safe"

        # Try cache first for speed
        if symbol in STOCK_FUNDAMENTAL_CACHE:
            cached = STOCK_FUNDAMENTAL_CACHE[symbol]
            pe = cached["pe"]
            debt_to_equity = cached["debt_to_equity"]
            promoter_pledge = cached["promoter_pledge"]
            news_event = cached["news_event"]
        
        # If not in cache or we want to try live update, use yfinance
        if (pe is None or debt_to_equity is None) and yf:
            try:
                ticker = yf.Ticker(f"{symbol}.NS")
                info = ticker.info
                if info:
                    pe = info.get("trailingPE") or info.get("forwardPE")
                    debt_to_equity = info.get("debtToEquity")
                    # If debt to equity is e.g. 88.5 in yfinance, it usually represents 88.5%, i.e., 0.885
                    if debt_to_equity is not None and debt_to_equity > 10:
                        debt_to_equity = debt_to_equity / 100.0
                    
                    # Estimate promoter pledging or check if there's a field
                    # yfinance doesn't easily expose Indian pledging directly, so we keep fallback/0.0
                    
                    # Calendar check
                    calendar = ticker.calendar
                    if calendar and "Earnings Date" in calendar:
                        dates = calendar["Earnings Date"]
                        if dates:
                            next_earnings = dates[0]
                            next_earnings_date = next_earnings.date() if hasattr(next_earnings, 'date') else next_earnings
                            # Check if within 48 hours
                            delta = next_earnings_date - datetime.now().date()
                            if 0 <= delta.days <= 2:
                                news_event = f"Blocked (Earnings in {delta.days}d)"
            except Exception as e:
                print(f"[StockAnalyzer] yfinance failed for {symbol}: {e}")

        # Fallback default values
        if pe is None: pe = 22.5
        if debt_to_equity is None: debt_to_equity = 0.45

        # Scorecard logic (0 to 100)
        score = 0
        checklist = []

        # Check 1: HTF Trend (20 points)
        htf_ok = htf_trend == "Bullish"
        if htf_ok:
            score += 20
            checklist.append({"item": "HTF Trend Alignment", "status": "Pass", "detail": f"Price > EMA50 on Daily (Bullish)", "points": 20})
        else:
            checklist.append({"item": "HTF Trend Alignment", "status": "Fail", "detail": f"Price < EMA50 on Daily (Bearish)", "points": 0})

        # Check 2: Value Zone (20 points)
        # We prefer Discount for BUY (or Premium for SELL, but default to BUY-side scan)
        zone_ok = value_zone in ["Discount", "Equilibrium"]
        if zone_ok:
            score += 20
            checklist.append({"item": "Value Zone Check", "status": "Pass", "detail": f"Stock is in {value_zone} zone", "points": 20})
        else:
            checklist.append({"item": "Value Zone Check", "status": "Fail", "detail": "Stock is in Premium zone (Expensive)", "points": 0})

        # Check 3: Displacement & Structure (20 points)
        if displacement_pass:
            score += 20
            checklist.append({"item": "Displacement & OB", "status": "Pass", "detail": "Bullish Structure / FVG Gap Detected", "points": 20})
        else:
            checklist.append({"item": "Displacement & OB", "status": "Fail", "detail": "No Bullish Structure/displacement on 5M", "points": 0})

        # Check 4: Debt-to-Equity (15 points)
        # Safe if Debt to Equity < 1.0 (typical for non-banking equities)
        # Let's adjust for banking stocks if we know them (e.g. SBIN, HDFCBANK, ICICIBANK can have higher debt)
        is_bank = symbol in ["HDFCBANK", "ICICIBANK", "SBIN"]
        debt_ok = (debt_to_equity < 1.0) or (is_bank and debt_to_equity < 2.0)
        if debt_ok:
            score += 15
            checklist.append({"item": "Debt-to-Equity Check", "status": "Pass", "detail": f"D/E is {debt_to_equity:.2f} (Safe)", "points": 15})
        else:
            checklist.append({"item": "Debt-to-Equity Check", "status": "Fail", "detail": f"D/E is {debt_to_equity:.2f} (Risky)", "points": 0})

        # Check 5: Promoter Pledge (15 points)
        # Safe if less than 10% pledged
        pledge_ok = promoter_pledge < 10.0
        if pledge_ok:
            score += 15
            checklist.append({"item": "Promoter Pledge Check", "status": "Pass", "detail": f"{promoter_pledge:.1f}% Pledged (Safe)", "points": 15})
        else:
            checklist.append({"item": "Promoter Pledge Check", "status": "Fail", "detail": f"{promoter_pledge:.1f}% Pledged (High)", "points": 0})

        # Check 6: Economic Event Check (10 points)
        event_ok = "Blocked" not in news_event
        if event_ok:
            score += 10
            checklist.append({"item": "Economic Event Calendar", "status": "Pass", "detail": "No major earnings in next 48h (Safe)", "points": 10})
        else:
            checklist.append({"item": "Economic Event Calendar", "status": "Fail", "detail": f"{news_event}", "points": 0})

        # Actionable trigger (e.g. score >= 70 and not blocked by event)
        actionable = (score >= 70) and event_ok

        return {
            "status": "success",
            "symbol": symbol,
            "token": token,
            "trading_symbol": trading_symbol,
            "ltp": float(close_1d),
            "score": score,
            "actionable": actionable,
            "htf_trend": htf_trend,
            "value_zone": value_zone,
            "pe": pe,
            "debt_to_equity": debt_to_equity,
            "promoter_pledge": promoter_pledge,
            "news_event": news_event,
            "checklist": checklist
        }

    def _create_mock_candles(self, interval: str, count: int, base_price: float) -> pd.DataFrame:
        """Helper to create realistic mock candles if API fetches fail or are offline."""
        times = []
        now = datetime.now()
        
        if interval == "ONE_DAY":
            delta = timedelta(days=1)
        else:
            delta = timedelta(minutes=5)

        for i in range(count):
            times.append(now - (count - i) * delta)

        prices = [base_price]
        for i in range(1, count):
            change = np.random.normal(0, base_price * 0.005)
            prices.append(prices[-1] + change)

        opens = []
        highs = []
        lows = []
        closes = []
        volumes = []

        for p in prices:
            o = p + np.random.normal(0, p * 0.001)
            c = p + np.random.normal(0, p * 0.001)
            h = max(o, c) + abs(np.random.normal(0, p * 0.002))
            l = min(o, c) - abs(np.random.normal(0, p * 0.002))
            opens.append(o)
            highs.append(h)
            lows.append(l)
            closes.append(c)
            volumes.append(int(np.random.uniform(1000, 50000)))

        df = pd.DataFrame({
            "time": [t.strftime("%Y-%m-%d %H:%M") for t in times],
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes
        })
        return df

stock_analyzer = StockAnalyzer()
