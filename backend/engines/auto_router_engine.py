import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

from backend.indicators.technical_indicators import TechnicalIndicators
from backend.backtesting.balanced_quality_engine import BalancedQualityEngine
from backend.backtesting.ultra_high_quality_engine import UltraHighQualitySignalEngine

class AutoRouterEngine:
    def __init__(self, adx_threshold=25.0):
        """
        adx_threshold: The boundary separating trending vs choppy market.
        > 25 = Trending (Use Balanced Engine)
        <= 25 = Choppy (Use Ultra-High Quality Engine)
        """
        self.adx_threshold = adx_threshold

    def _fetch_data(self, symbol: str, days: int = 5) -> pd.DataFrame:
        """Fetches latest 5-min intraday data using yfinance."""
        try:
            ticker = yf.Ticker(symbol)
            # Fetch recent 5 days of 5m data to have enough history for ADX & EMAs
            df = ticker.history(period=f"{days}d", interval="5m")
            if df.empty:
                return pd.DataFrame()
                
            df.reset_index(inplace=True)
            df.rename(columns={
                'Datetime': 'date', 'Date': 'date', 
                'Open': 'open', 'High': 'high', 
                'Low': 'low', 'Close': 'close', 
                'Volume': 'volume'
            }, inplace=True)
            
            # Convert timezone and set standard index
            if df['date'].dt.tz is not None:
                df['date'] = df['date'].dt.tz_convert('Asia/Kolkata')
            else:
                df['date'] = df['date'].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
            
            return df
            
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            return pd.DataFrame()

    def get_signals_for_symbol(self, symbol: str) -> dict:
        """
        Main entry point for API.
        Fetches data, calculates ADX, routes to the right engine, and returns signals.
        """
        df = self._fetch_data(symbol)
        
        if df.empty or len(df) < 50:
            return {
                "symbol": symbol,
                "status": "error",
                "message": "Not enough data available.",
                "adx_score": 0.0,
                "engine_used": None,
                "signals": []
            }

        # 1. Market Condition Check (Calculate ADX)
        df_with_indicators = TechnicalIndicators.add_adx(df.copy(), length=14)
        latest_adx = float(df_with_indicators['ADX'].iloc[-1])
        
        # 2. Dynamic Routing Logic
        if latest_adx > self.adx_threshold:
            engine_name = "Balanced Quality Engine"
            engine = BalancedQualityEngine(df, capital=100000, risk_per_trade=2.0)
        else:
            engine_name = "Ultra-High Quality Engine"
            engine = UltraHighQualitySignalEngine(df, capital=100000, risk_per_trade=2.0)
            
        # 3. Generate Signals
        raw_signals = engine.generate_signals()
        
        # 4. Format Output for Frontend Scanner
        formatted_signals = []
        for s in raw_signals:
            idx = s.get("index", 0)
            dt_obj = df['date'].iloc[idx] if idx < len(df) else pd.Timestamp.now()
            
            formatted_signals.append({
                "time": dt_obj.strftime("%Y-%m-%d %H:%M:%S") if isinstance(dt_obj, pd.Timestamp) else str(dt_obj),
                "type": s.get("type", ""),
                "price": float(s.get("price", 0.0)),
                "reason": s.get("reason", "")
            })
            
        # Optional: Only return the latest signal (or signals from the last 24 hours)
        # To avoid sending the whole week's history. We'll filter for the latest day.
        if len(formatted_signals) > 0:
            latest_date = df['date'].iloc[-1].date()
            # Filter signals that belong to the most recent trading day
            formatted_signals = [s for s in formatted_signals if s['time'].startswith(str(latest_date))]
            
            # Sort descending (newest first)
            formatted_signals.reverse()

        latest_price = float(df['close'].iloc[-1])

        return {
            "symbol": symbol,
            "status": "success",
            "adx_score": round(latest_adx, 2),
            "engine_used": engine_name,
            "ltp": latest_price,
            "total_signals_today": len(formatted_signals),
            "signals": formatted_signals
        }
