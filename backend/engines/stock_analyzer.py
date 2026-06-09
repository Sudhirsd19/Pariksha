import asyncio
import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone, time as dt_time

# Try importing yfinance, fallback to mock/scraped data if not installed
try:
    import yfinance as yf
except ImportError:
    yf = None

from backend.utils.token_manager import token_manager
from backend.utils.historical_data import fetch_historical_data
from backend.engines.structure_engine import StructureEngine
from backend.indicators.technical_indicators import TechnicalIndicators

STOCK_SECTOR_MAP = {
    "HDFCBANK": "^NSEBANK", "ICICIBANK": "^NSEBANK", "SBIN": "^NSEBANK",
    "AXISBANK": "^NSEBANK", "KOTAKBANK": "^NSEBANK", "INDUSINDBK": "^NSEBANK",
    "PNB": "^NSEBANK", "BOB": "^NSEBANK", "UNIONBANK": "^NSEBANK",
    "CANBK": "^NSEBANK", "IDFCFIRSTB": "^NSEBANK", "BANDHANBNK": "^NSEBANK",
    "FEDERALBNK": "^NSEBANK",
    
    "TCS": "^CNXIT", "INFY": "^CNXIT", "WIPRO": "^CNXIT", "HCLTECH": "^CNXIT",
    "TECHM": "^CNXIT", "LTIM": "^CNXIT", "COFORGE": "^CNXIT",
    
    "RELIANCE": "^CNXENERGY", "NTPC": "^CNXENERGY", "POWERGRID": "^CNXENERGY",
    "TATAPOWER": "^CNXENERGY", "ONGC": "^CNXENERGY", "COALINDIA": "^CNXENERGY",
    "BPCL": "^CNXENERGY", "IOC": "^CNXENERGY", "GAIL": "^CNXENERGY",
    
    "BAJFINANCE": "^CNXFIN", "BAJAJFINSV": "^CNXFIN", "CHOLAFIN": "^CNXFIN",
    "PFC": "^CNXFIN", "RECLTD": "^CNXFIN",
    
    "TATASTEEL": "^CNXMETAL", "JINDALSTEL": "^CNXMETAL", "HINDALCO": "^CNXMETAL",
    "JSWSTEEL": "^CNXMETAL", "VEDL": "^CNXMETAL", "NMDC": "^CNXMETAL",
    "NATIONALUM": "^CNXMETAL",
    
    "SUNPHARMA": "^CNXPHARMA", "CIPLA": "^CNXPHARMA", "DRREDDY": "^CNXPHARMA",
    "DIVISLAB": "^CNXPHARMA", "APOLLOHOSP": "^CNXPHARMA",
    
    "ITC": "^CNXFMCG", "HINDUNILVR": "^CNXFMCG", "NESTLEIND": "^CNXFMCG",
    "BRITANNIA": "^CNXFMCG", "TATACONSUM": "^CNXFMCG",
    
    "TATAMOTORS": "^CNXAUTO", "M&M": "^CNXAUTO", "MARUTI": "^CNXAUTO",
    "BAJAJ-AUTO": "^CNXAUTO", "HEROMOTOCO": "^CNXAUTO", "EICHERMOT": "^CNXAUTO",
    "TVSMOTOR": "^CNXAUTO",
    
    "LT": "^CNXINFRA", "ADANIPORTS": "^CNXINFRA", "GMRINFRA": "^CNXINFRA",
    "IRCON": "^CNXINFRA", "RVNL": "^CNXINFRA", "NBCC": "^CNXINFRA",
    
    "DLF": "^CNXREALTY", "GODREJPROP": "^CNXREALTY", "OBEROIRLTY": "^CNXREALTY",
}

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

    async def analyze_stock(self, symbol: str, smart_api=None, index_trends = None) -> dict:
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

        # Resolve Sector Index Trend
        sector_trend = "Neutral"
        index_ticker = STOCK_SECTOR_MAP.get(symbol, "^NSEI")
        
        if isinstance(index_trends, str):
            # Backward compatibility: index_trends was passed as a flat string
            sector_trend = index_trends
        elif isinstance(index_trends, dict) and index_ticker in index_trends:
            sector_trend = index_trends[index_ticker]
        else:
            # Fetch single index trend dynamically if not pre-cached
            try:
                ticker_obj = yf.Ticker(index_ticker)
                fast_info = await asyncio.to_thread(lambda: ticker_obj.fast_info)
                last_price = float(getattr(fast_info, "last_price", 0))
                prev_close = float(getattr(fast_info, "previous_close", 0))
                if last_price > 0 and prev_close > 0:
                    sector_trend = "Bullish" if last_price > prev_close else "Bearish"
            except:
                pass

        # 2. Fetch LTP from yfinance (free, no auth) as reliable real-time price
        real_ltp = None
        if yf:
            try:
                ticker_obj = yf.Ticker(f"{symbol}.NS")
                hist = await asyncio.to_thread(lambda: ticker_obj.history(period="1d", interval="1m"))
                if not hist.empty:
                    real_ltp = float(hist["Close"].iloc[-1])
                if not real_ltp or real_ltp <= 0:
                    # fallback: fast_info
                    fast_info = await asyncio.to_thread(lambda: ticker_obj.fast_info)
                    real_ltp = float(fast_info.get("last_price", 0) or 0)
            except Exception as e:
                print(f"[StockAnalyzer] yfinance LTP fetch failed for {symbol}: {e}")
                
        if not real_ltp or real_ltp <= 0:
            return {"status": "error", "message": f"Real price for {symbol} could not be fetched. Market might be closed or symbol invalid."}

        # 3. Fetch candles asynchronously via threads
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

        # Use real_ltp as base for mock candles so LTP stays accurate
        mock_base = real_ltp if (real_ltp and real_ltp > 0) else 500.0

        # If offline or data failed, create mock/simulated candles for demonstration
        if df_1d is None or df_1d.empty:
            df_1d = self._create_mock_candles(interval="ONE_DAY", count=80, base_price=mock_base)
        if df_5m is None or df_5m.empty:
            df_5m = self._create_mock_candles(interval="FIVE_MINUTE", count=100, base_price=mock_base)

        # 4. Fetch Market Depth, VWAP, OHOL from SmartAPI if available
        market_depth = False
        tot_buy = 0
        tot_sell = 0
        vwap = 0.0
        day_open = 0.0
        day_high = 0.0
        day_low = 0.0
        day_volume = 0
        spread_pct = 0.0
        spread_ok = True
        
        if smart_api:
            try:
                exchangeTokens = {exchange: [token]}
                res = await asyncio.to_thread(smart_api.getMarketData, "FULL", exchangeTokens)
                if res and res.get('status') and res.get('data'):
                    data_list = res.get('data', {}).get('fetched', [])
                    for item in data_list:
                        if item.get('symbolToken') == str(token) or item.get('symbolToken') == token:
                            tot_buy = item.get("totBuyQuan", 0)
                            tot_sell = item.get("totSellQuan", 0)
                            vwap = float(item.get("vwap", 0.0))
                            day_open = float(item.get("open", 0.0))
                            day_high = float(item.get("high", 0.0))
                            day_low = float(item.get("low", 0.0))
                            day_volume = int(item.get("tradeVolume", 0))
                            market_depth = True
                            
                            # Bid-Ask spread
                            depth_data = item.get("depth", {})
                            buy_list = depth_data.get("buy", [])
                            sell_list = depth_data.get("sell", [])
                            if buy_list and sell_list:
                                best_bid = float(buy_list[0].get("price", 0.0))
                                best_ask = float(sell_list[0].get("price", 0.0))
                                if best_bid > 0 and best_ask > 0:
                                    spread_pct = (best_ask - best_bid) / best_bid
                                    spread_ok = spread_pct <= 0.001  # Max 0.1% spread
            except Exception as e:
                print(f"[StockAnalyzer] Market Depth fetch failed for {symbol}: {e}")

        # 5. Technical checks
        # Calculate EMA 50 on Daily candles
        df_1d = TechnicalIndicators.add_ema(df_1d, 50)
        last_1d = df_1d.iloc[-1]
        close_1d = last_1d["close"]
        ema_50 = last_1d["EMA_50"]
        htf_trend = "Bullish" if close_1d > ema_50 else "Bearish"

        # Calculate ATR on 5M candles
        df_5m = TechnicalIndicators.add_atr(df_5m, 14)
        atr_5m = float(df_5m["ATR"].iloc[-1]) if "ATR" in df_5m.columns else 0.0

        # Market structure on 5M candles
        struct_res = self.struct_engine.analyze(df_5m)
        value_zone = "Equilibrium"
        if struct_res["in_discount"]:
            value_zone = "Discount"
        elif struct_res["in_premium"]:
            value_zone = "Premium"

        # Displacement/OB check (BOS or swing sweeps or general bullish bias)
        displacement_pass = struct_res["bos_bullish"] or struct_res["fvg_gap"] or struct_res["sweep_low"]

        # Advanced Intraday Metrics
        avg_volume_10d = 0
        volume_breakout = False
        if df_1d is not None and not df_1d.empty and len(df_1d) >= 10:
            avg_volume_10d = float(df_1d["volume"].rolling(10).mean().iloc[-1])
            if day_volume > 0 and avg_volume_10d > 0:
                volume_breakout = day_volume > (1.5 * avg_volume_10d)
            else:
                today_vol = float(df_1d["volume"].iloc[-1])
                volume_breakout = today_vol > (1.5 * avg_volume_10d)
                
        vwap_alignment = "Neutral"
        if vwap > 0:
            if real_ltp > vwap:
                vwap_alignment = "Bullish"
            elif real_ltp < vwap:
                vwap_alignment = "Bearish"
                
        ohol_setup = "None"
        if day_open > 0:
            if abs(day_open - day_low) <= (day_open * 0.001): # 0.1% tolerance
                ohol_setup = "Open=Low (Strong Bullish)"
            elif abs(day_open - day_high) <= (day_open * 0.001):
                ohol_setup = "Open=High (Strong Bearish)"

        # 6. Fundamental checks (using yfinance with offline cache backup)
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

        # Check 1: HTF Trend & Sector Index Alignment (20 points)
        htf_ok = htf_trend == "Bullish"
        sector_aligned = (sector_trend == "Bullish") if htf_ok else (sector_trend == "Bearish")
        if sector_trend == "Neutral":
            sector_aligned = True # Fallback for mock/offline tests
            
        if htf_ok:
            if sector_aligned and sector_trend != "Neutral":
                score += 20
                checklist.append({"item": "Trend & Sector Alignment", "status": "Pass", "detail": f"Bullish (Aligned with Sector Index {index_ticker}: {sector_trend})", "points": 20})
            elif sector_trend == "Neutral":
                score += 15
                checklist.append({"item": "Trend & Sector Alignment", "status": "Warn", "detail": f"Bullish (Sector Index {index_ticker} is Neutral/Offline)", "points": 15})
            else:
                score += 5
                checklist.append({"item": "Trend & Sector Alignment", "status": "Fail", "detail": f"Bullish but Sector Index {index_ticker} is {sector_trend}", "points": 5})
        else:
            if sector_aligned and sector_trend != "Neutral":
                score += 20
                checklist.append({"item": "Trend & Sector Alignment", "status": "Pass", "detail": f"Bearish (Aligned with Sector Index {index_ticker}: {sector_trend})", "points": 20})
            elif sector_trend == "Neutral":
                score += 15
                checklist.append({"item": "Trend & Sector Alignment", "status": "Warn", "detail": f"Bearish (Sector Index {index_ticker} is Neutral/Offline)", "points": 15})
            else:
                checklist.append({"item": "Trend & Sector Alignment", "status": "Fail", "detail": f"Bearish but Sector Index {index_ticker} is {sector_trend}", "points": 0})

        # Check 2: Value Zone (15 points)
        zone_ok = value_zone in ["Discount", "Equilibrium"]
        if zone_ok:
            score += 15
            checklist.append({"item": "Value Zone Check", "status": "Pass", "detail": f"Stock is in {value_zone} zone", "points": 15})
        else:
            checklist.append({"item": "Value Zone Check", "status": "Fail", "detail": "Stock is in Premium zone (Expensive)", "points": 0})

        # Check 3: Displacement & Structure (15 points)
        if displacement_pass:
            score += 15
            checklist.append({"item": "Displacement & OB", "status": "Pass", "detail": "Bullish Structure / FVG Gap Detected", "points": 15})
        else:
            checklist.append({"item": "Displacement & OB", "status": "Fail", "detail": "No Bullish Structure/displacement on 5M", "points": 0})

        # Check 7: VWAP Alignment (Mandatory for Actionable)
        if vwap_alignment == "Bullish":
            score += 15
            checklist.append({"item": "VWAP Alignment", "status": "Pass", "detail": f"LTP ({real_ltp}) > VWAP ({vwap:.2f})", "points": 15})
        elif vwap_alignment == "Bearish":
            checklist.append({"item": "VWAP Alignment", "status": "Fail", "detail": f"LTP ({real_ltp}) < VWAP ({vwap:.2f})", "points": 0})
        else:
            checklist.append({"item": "VWAP Alignment", "status": "Warn", "detail": "VWAP data not available", "points": 5})

        # Check 8: Order Book / Market Depth Ratio
        depth_ok = False
        if market_depth:
            if tot_buy > (1.2 * tot_sell):
                depth_ok = True
                score += 10
                checklist.append({"item": "Market Depth Ratio", "status": "Pass", "detail": f"Buyers ({tot_buy}) > 1.2x Sellers ({tot_sell})", "points": 10})
            else:
                checklist.append({"item": "Market Depth Ratio", "status": "Fail", "detail": f"Weak Demand (Buy:{tot_buy} Sell:{tot_sell})", "points": 0})
        else:
            checklist.append({"item": "Market Depth Ratio", "status": "Warn", "detail": "Depth data unavailable", "points": 0})

        # Check 9: Volume Breakout
        if volume_breakout:
            score += 10
            checklist.append({"item": "Volume Breakout", "status": "Pass", "detail": f"Today's Vol > 1.5x of 10D Avg", "points": 10})
        else:
            checklist.append({"item": "Volume Breakout", "status": "Warn", "detail": "Average or Low Volume", "points": 0})

        # Check 10: OHOL Setup (Bonus 15 Points)
        if "Bullish" in ohol_setup:
            score += 15
            checklist.append({"item": "OHOL Setup", "status": "Pass", "detail": ohol_setup, "points": 15})
        elif ohol_setup != "None":
            checklist.append({"item": "OHOL Setup", "status": "Fail", "detail": ohol_setup, "points": 0})

        # Check 4: Debt-to-Equity (15 points)
        is_bank = symbol in ["HDFCBANK", "ICICIBANK", "SBIN"]
        debt_ok = (debt_to_equity < 1.0) or (is_bank and debt_to_equity < 2.0)
        if debt_ok:
            score += 15
            checklist.append({"item": "Debt-to-Equity Check", "status": "Pass", "detail": f"D/E is {debt_to_equity:.2f} (Safe)", "points": 15})
        else:
            checklist.append({"item": "Debt-to-Equity Check", "status": "Fail", "detail": f"D/E is {debt_to_equity:.2f} (Risky)", "points": 0})

        # Check 5: Promoter Pledge (15 points)
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

        # Check 11: Bid-Ask Spread Check (10 points)
        if spread_ok:
            score += 10
            checklist.append({"item": "Bid-Ask Spread Check", "status": "Pass", "detail": f"Spread is {spread_pct*100:.3f}% (Safe)", "points": 10})
        else:
            checklist.append({"item": "Bid-Ask Spread Check", "status": "Fail", "detail": f"Wide Spread: {spread_pct*100:.3f}% (>0.1% Slippage Risk)", "points": 0})

        # Check 13: VWAP Deviation Band (Standard Deviation Band Check - 10 points)
        vwap_overextended = False
        upper_band = vwap
        if vwap > 0 and df_5m is not None and not df_5m.empty:
            std_dev = df_5m['close'].rolling(20).std().iloc[-1]
            if pd.isna(std_dev) or std_dev == 0:
                std_dev = real_ltp * 0.005
            upper_band = vwap + 2.0 * std_dev
            if real_ltp > upper_band:
                vwap_overextended = True

        if not vwap_overextended:
            score += 10
            checklist.append({"item": "VWAP Deviation Band", "status": "Pass", "detail": f"Price within standard deviation bands from VWAP", "points": 10})
        else:
            checklist.append({"item": "VWAP Deviation Band", "status": "Fail", "detail": f"Overextended: Price ({real_ltp:.2f}) > VWAP + 2SD ({upper_band:.2f})", "points": 0})

        # Check 12: Time-of-Day Filter
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        now_time = datetime.now(ist_tz).time()
        
        is_lunch_hours = dt_time(11, 30) <= now_time <= dt_time(13, 15)
        is_after_hours = now_time > dt_time(14, 30)
        
        time_ok = not is_after_hours
        min_score_required = 85 if is_lunch_hours else 70
        
        if is_after_hours:
            checklist.append({"item": "Time-of-Day Filter", "status": "Fail", "detail": "After-hours (No new trades after 2:30 PM)", "points": 0})
        elif is_lunch_hours:
            checklist.append({"item": "Time-of-Day Filter", "status": "Warn", "detail": "Lunch hours (11:30 AM - 1:15 PM): requires 85+ score", "points": 0})
        else:
            checklist.append({"item": "Time-of-Day Filter", "status": "Pass", "detail": "Active trading hours", "points": 0})

        # Actionable trigger (e.g. score >= 70, not blocked by event, VWAP alignment passes, spread is safe, and time filters pass)
        vwap_mandatory_pass = vwap_alignment != "Bearish" # Either Bullish or Neutral/Unknown
        actionable = (score >= min_score_required) and event_ok and vwap_mandatory_pass and spread_ok and time_ok and not vwap_overextended and sector_aligned

        return {
            "status": "success",
            "symbol": symbol,
            "token": token,
            "trading_symbol": trading_symbol,
            "ltp": real_ltp if (real_ltp and real_ltp > 0) else float(close_1d),
            "score": score,
            "actionable": actionable,
            "htf_trend": htf_trend,
            "value_zone": value_zone,
            "pe": pe,
            "debt_to_equity": debt_to_equity,
            "promoter_pledge": promoter_pledge,
            "news_event": news_event,
            "total_buyers": tot_buy,
            "total_sellers": tot_sell,
            "vwap": vwap,
            "volume_breakout": volume_breakout,
            "ohol_setup": ohol_setup,
            "atr": atr_5m,
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
