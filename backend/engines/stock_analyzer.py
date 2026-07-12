import asyncio
import pandas as pd
from backend.indicators.technical_indicators import TechnicalIndicators
from backend.engines.strict_checklist_engine import strict_checklist_engine
from backend.utils.token_manager import token_manager
from backend.utils.historical_data import fetch_historical_data

# Stock -> Sector Index mapping for Macro Trend Filter
STOCK_SECTOR_MAP = {
    # IT
    "TCS": "^CNXIT", "INFY": "^CNXIT", "WIPRO": "^CNXIT", "HCLTECH": "^CNXIT",
    "TECHM": "^CNXIT", "LTIM": "^CNXIT", "PERSISTENT": "^CNXIT", "COFORGE": "^CNXIT",
    # Banking & Finance
    "HDFCBANK": "^CNXFIN", "ICICIBANK": "^CNXFIN", "SBIN": "^CNXFIN", "KOTAKBANK": "^CNXFIN",
    "AXISBANK": "^CNXFIN", "INDUSINDBK": "^CNXFIN", "BANKBARODA": "^CNXFIN",
    "PNB": "^CNXFIN", "BAJFINANCE": "^CNXFIN", "BAJAJFINSV": "^CNXFIN",
    "CHOLAFIN": "^CNXFIN", "MUTHOOTFIN": "^CNXFIN", "MANAPPURAM": "^CNXFIN",
    # Energy & Oil
    "RELIANCE": "^CNXENERGY", "ONGC": "^CNXENERGY", "BPCL": "^CNXENERGY",
    "IOC": "^CNXENERGY", "NTPC": "^CNXENERGY", "POWERGRID": "^CNXENERGY",
    "TATAPOWER": "^CNXENERGY", "ADANIGREEN": "^CNXENERGY", "ADANIENT": "^CNXENERGY",
    # Metals
    "TATASTEEL": "^CNXMETAL", "JSWSTEEL": "^CNXMETAL", "HINDALCO": "^CNXMETAL",
    "VEDL": "^CNXMETAL", "COALINDIA": "^CNXMETAL", "NMDC": "^CNXMETAL",
    # Pharma & Healthcare
    "SUNPHARMA": "^CNXPHARMA", "DRREDDY": "^CNXPHARMA", "CIPLA": "^CNXPHARMA",
    "DIVISLAB": "^CNXPHARMA", "APOLLOHOSP": "^CNXPHARMA", "LALPATHLAB": "^CNXPHARMA",
    # Auto
    "MARUTI": "^CNXAUTO", "TATAMOTORS": "^CNXAUTO", "M&M": "^CNXAUTO",
    "BAJAJ-AUTO": "^CNXAUTO", "EICHERMOT": "^CNXAUTO", "HEROMOTOCO": "^CNXAUTO",
    "ASHOKLEY": "^CNXAUTO", "BHARATFORG": "^CNXAUTO",
    # FMCG
    "HINDUNILVR": "^CNXFMCG", "ITC": "^CNXFMCG", "NESTLEIND": "^CNXFMCG",
    "BRITANNIA": "^CNXFMCG", "DABUR": "^CNXFMCG", "GODREJCP": "^CNXFMCG",
    "MARICO": "^CNXFMCG", "COLPAL": "^CNXFMCG", "TATACONSUM": "^CNXFMCG",
    # Infra & Realty
    "ULTRACEMCO": "^CNXINFRA", "GRASIM": "^CNXINFRA", "AMBUJACEM": "^CNXINFRA",
    "ACC": "^CNXINFRA", "LT": "^CNXINFRA", "DLF": "^CNXREALTY",
    "GODREJPROP": "^CNXREALTY", "OBEROIRLTY": "^CNXREALTY",
    # Telecom
    "BHARTIARTL": "^NSEI", "IDEA": "^NSEI",
    # Others
    "TITAN": "^NSEI", "ASIANPAINT": "^NSEI", "PIDILITIND": "^NSEI",
    "HAVELLS": "^NSEI", "VOLTAS": "^NSEI", "PAGEIND": "^NSEI",
    "IRCTC": "^NSEI", "ZOMATO": "^NSEI", "PAYTM": "^NSEI",
    "DELHIVERY": "^NSEI", "NYKAA": "^NSEI",
}


class StockAnalyzer:
    """Analyzes individual stocks using technical indicators and strict checklist scoring."""

    async def analyze_stock(self, symbol: str, api_client=None,
                            index_trends: dict = None, provided_ltp: float = 0.0,
                            live_ltp_dict: dict = None) -> dict:
        """
        Full analysis for a single equity stock.

        Args:
            symbol: NSE stock symbol (e.g., 'RELIANCE')
            api_client: AngelOne SmartAPI client (optional)
            index_trends: Dict of sector index -> 'Bullish'/'Bearish' (optional)
            provided_ltp: Fallback LTP if live data unavailable
            live_ltp_dict: Dict of token -> live LTP from WebSocket

        Returns:
            Dict with analysis results or error status.
        """
        index_trends = index_trends or {}
        base_symbol = symbol.upper().replace(".NS", "").replace("-EQ", "")

        # Fetch historical data
        df = None
        token = token_manager.get_token(base_symbol)
        exchange = token_manager.get_exchange(base_symbol) or "NSE"

        if api_client and token:
            try:
                df = await asyncio.to_thread(
                    fetch_historical_data, api_client, token, "FIVE_MINUTE", 5, exchange
                )
            except Exception as e:
                print(f"[StockAnalyzer] AngelOne fetch failed for {base_symbol}: {e}")

        # yfinance fallback
        if df is None or df.empty:
            try:
                import yfinance as yf
                ticker = f"{base_symbol}.NS"
                df = await asyncio.to_thread(
                    lambda: yf.Ticker(ticker).history(period="5d", interval="5m")
                )
            except Exception as e:
                print(f"[StockAnalyzer] yfinance fallback failed for {base_symbol}: {e}")

        if df is None or df.empty:
            return {"status": "error", "symbol": base_symbol,
                    "message": "Failed to fetch data"}

        # Standardize columns
        df.columns = [c.lower() for c in df.columns]

        # Apply all technical indicators
        try:
            df = TechnicalIndicators.apply_all(df)
        except Exception as e:
            print(f"[StockAnalyzer] Indicator error for {base_symbol}: {e}")
            return {"status": "error", "symbol": base_symbol,
                    "message": f"Indicator calc failed: {e}"}

        last = df.iloc[-1]

        # Determine LTP
        ltp = 0.0
        if live_ltp_dict and token and token in live_ltp_dict:
            ltp = float(live_ltp_dict[token])
        if ltp <= 0 and provided_ltp > 0:
            ltp = provided_ltp
        if ltp <= 0:
            ltp = float(last['close'])

        # Sector index trend (Macro Filter)
        sector_index = STOCK_SECTOR_MAP.get(base_symbol, "^NSEI")
        sector_trend = index_trends.get(sector_index, "Neutral")
        is_nifty_bullish = index_trends.get("^NSEI", "Neutral") != "Bearish"

        # Fetch market depth for buyer/seller ratio
        market_depth_buyer_ratio = 1.0
        total_buyers = 0
        total_sellers = 0
        if api_client and token:
            try:
                from backend.execution.broker_api import AngelOneBroker
                depth = api_client.getMarketData(
                    mode="FULL",
                    exchangeTokens={exchange: [token]}
                )
                if depth and depth.get("status") and depth.get("data"):
                    fetched = depth["data"].get("fetched", [])
                    if fetched:
                        item = fetched[0]
                        total_buyers = int(item.get("totBuyQuan", 0))
                        total_sellers = int(item.get("totSellQuan", 0))
                        if total_sellers > 0:
                            market_depth_buyer_ratio = total_buyers / total_sellers
            except Exception:
                pass

        # Run strict checklist engine
        strict_result = strict_checklist_engine.evaluate(
            base_symbol, df.copy(),
            is_nifty_bullish=is_nifty_bullish,
            market_depth_buyer_ratio=market_depth_buyer_ratio
        )

        score = strict_result.get("strict_score", 0)
        strict_signal = strict_result.get("strict_signal", "NONE")

        # HTF Trend (from sector or EMA alignment)
        ema20 = last.get('EMA_20', 0)
        ema50 = last.get('EMA_50', 0)
        if sector_trend != "Neutral":
            htf_trend = sector_trend
        elif ema20 > ema50:
            htf_trend = "Bullish"
        elif ema20 < ema50:
            htf_trend = "Bearish"
        else:
            htf_trend = "Neutral"

        # Value Zone: price near VWAP (within 0.5%)
        vwap = float(last.get('VWAP', 0))
        value_zone = False
        if vwap > 0 and ltp > 0:
            value_zone = abs(ltp - vwap) / ltp < 0.005

        # Volume breakout (2x average)
        vol_avg = df['volume'].rolling(20).mean().iloc[-1]
        volume_breakout = bool(
            last['volume'] > 2 * vol_avg if vol_avg and vol_avg > 0 else False
        )

        # OHOL / OLHC setup detection
        ohol_setup = "None"
        if len(df) >= 75:
            day_open = df['open'].iloc[-75]  # ~6.25 hrs of 5m candles
            day_high = df['high'].iloc[-75:].max()
            day_low = df['low'].iloc[-75:].min()
            if abs(day_open - day_low) / max(day_open, 0.01) < 0.001:
                ohol_setup = "OLHC (Bullish)"
            elif abs(day_open - day_high) / max(day_open, 0.01) < 0.001:
                ohol_setup = "OHLC (Bearish)"

        # Actionable: score >= threshold AND has volume
        actionable = score >= 60 and (volume_breakout or market_depth_buyer_ratio > 1.2)

        reason_parts = []
        if "BUY" in strict_signal:
            reason_parts.append(f"Score {score}/100")
            if htf_trend == "Bullish":
                reason_parts.append("HTF Bullish")
            if volume_breakout:
                reason_parts.append("Vol Breakout")
            if value_zone:
                reason_parts.append("Near VWAP")
        elif "SELL" in strict_signal:
            reason_parts.append(f"Score {score}/100")
            if htf_trend == "Bearish":
                reason_parts.append("HTF Bearish")
            if volume_breakout:
                reason_parts.append("Vol Breakout")
        reason = " | ".join(reason_parts) if reason_parts else "No strong signal"

        return {
            "status": "success",
            "symbol": base_symbol,
            "ltp": round(ltp, 2),
            "score": score,
            "strict_score": score,
            "strict_signal": strict_signal,
            "breakdown": strict_result.get("breakdown", {}),
            "htf_trend": htf_trend,
            "value_zone": value_zone,
            "actionable": actionable,
            "vwap": round(vwap, 2),
            "volume_breakout": volume_breakout,
            "reason": reason,
            "total_buyers": total_buyers,
            "total_sellers": total_sellers,
            "ohol_setup": ohol_setup,
            "signal": strict_signal,
        }


stock_analyzer = StockAnalyzer()
