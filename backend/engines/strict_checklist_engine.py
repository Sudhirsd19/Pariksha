import pandas as pd
import numpy as np
from datetime import datetime
from backend.indicators.technical_indicators import TechnicalIndicators

class StrictChecklistEngine:
    """
    Implements the 100-Point Scorecard for Ultra-High Conviction Trades.
    """
    def __init__(self):
        pass
        
    def evaluate(self, symbol: str, df: pd.DataFrame, 
                 is_nifty_bullish: bool = True, 
                 is_sector_green: bool = True, 
                 market_depth_buyer_ratio: float = 1.6, 
                 promoter_holding: float = 55.0, 
                 debt_to_equity: float = 0.5) -> dict:
        """
        Evaluates the stock against the 100-point strict checklist.
        Returns a dictionary with score, strict_signal, and reasons.
        """
        if df is None or df.empty or len(df) < 30:
            return {"score": 0, "strict_signal": "NONE", "reasons": ["Not enough data"]}
            
        # Ensure all indicators are calculated
        if 'MACD' not in df.columns or 'EMA_9' not in df.columns:
            df = TechnicalIndicators.apply_all(df)
            
        last_idx = -1
        current = df.iloc[last_idx]
        prev = df.iloc[last_idx - 1]
        
        buy_score = 0
        sell_score = 0
        buy_reasons = []
        sell_reasons = []
        
        # ==========================================
        # 1. Macro Trend Filter (15 Points)
        # ==========================================
        if is_nifty_bullish:
            buy_score += 10
        else:
            sell_score += 10
            
        if is_sector_green:
            buy_score += 5
        else:
            sell_score += 5
            
        # ==========================================
        # 2. Fundamental Strength Filter (10 Points)
        # ==========================================
        if promoter_holding >= 50.0:
            buy_score += 5
            sell_score += 5
            
        if debt_to_equity < 1.0:
            buy_score += 5
            sell_score += 5
            
        # ==========================================
        # 3. Price Action & Trend Filter (25 Points)
        # ==========================================
        # VWAP (10 pts)
        if current['close'] > current['VWAP'] and prev['close'] > prev['VWAP']:
            buy_score += 10
        elif current['close'] < current['VWAP'] and prev['close'] < prev['VWAP']:
            sell_score += 10
            
        # EMA Crossover (5 pts)
        if current['EMA_9'] > current['EMA_20']:
            buy_score += 5
        elif current['EMA_9'] < current['EMA_20']:
            sell_score += 5
            
        # 2-Hour Breakout (24 candles on 5m chart) (10 pts)
        if len(df) > 24:
            recent_2h_high = df['high'].iloc[-25:-1].max()
            recent_2h_low = df['low'].iloc[-25:-1].min()
            
            if current['close'] > recent_2h_high:
                buy_score += 10
            elif current['close'] < recent_2h_low:
                sell_score += 10
                
        # ==========================================
        # 4. Volume Filter (20 Points)
        # ==========================================
        vol_20_avg = df['volume'].iloc[-21:-1].mean()
        if vol_20_avg > 0:
            if current['volume'] >= (1.5 * vol_20_avg):
                buy_score += 10
                sell_score += 10 # Volume spike is good for both breakouts and breakdowns
                
        # Market Depth (10 pts)
        if market_depth_buyer_ratio >= 1.55: # Buyers are 55% more than sellers
            buy_score += 10
        elif market_depth_buyer_ratio <= 0.45: # Sellers are 55% more than buyers
            sell_score += 10
            
        # ==========================================
        # 5. Momentum Filter (15 Points)
        # ==========================================
        rsi = current['RSI']
        if 50 < rsi < 70:
            buy_score += 10
        elif rsi > 75:
            buy_reasons.append("RSI Overbought (>75)")
            
        if 30 < rsi < 50:
            sell_score += 10
        elif rsi < 25:
            sell_reasons.append("RSI Oversold (<25)")
            
        # MACD (5 pts)
        if current['MACD'] > current['MACD_Signal'] and current['MACD_Hist'] > prev['MACD_Hist']:
            buy_score += 5
        elif current['MACD'] < current['MACD_Signal'] and current['MACD_Hist'] < prev['MACD_Hist']:
            sell_score += 5
            
        # ==========================================
        # 6. Risk & Execution Filter (15 Points)
        # ==========================================
        # Risk Reward 1:2 (10 pts)
        # Approximation based on recent swing and realistic volatility
        swing_low = df['low'].iloc[-5:].min()
        swing_high = df['high'].iloc[-5:].max()
        
        buy_risk = current['close'] - swing_low
        sell_risk = swing_high - current['close']
        
        if buy_risk > 0 and (buy_risk / current['close']) < 0.02: 
            buy_score += 10
        if sell_risk > 0 and (sell_risk / current['close']) < 0.02:
            sell_score += 10
            
        # Time Filter (5 pts) - 09:30 AM to 02:30 PM
        try:
            # Assume current is IST datetime
            dt = current['date'] if isinstance(current['date'], datetime) else pd.to_datetime(current['date'])
            hour = dt.hour
            minute = dt.minute
            
            time_val = hour * 100 + minute
            if 930 <= time_val <= 1430:
                buy_score += 5
                sell_score += 5
        except:
            pass # fallback if parsing fails
            
        # ==========================================
        # Final Decision
        # ==========================================
        signal = "NONE"
        final_score = 0
        
        if buy_score >= 100:
            signal = "BUY"
            final_score = buy_score
        elif sell_score >= 100:
            signal = "SELL"
            final_score = sell_score
        else:
            # Return the dominant score for UI
            if buy_score >= sell_score:
                final_score = buy_score
            else:
                final_score = sell_score
                
        return {
            "strict_signal": signal,
            "strict_score": final_score,
            "buy_score": buy_score,
            "sell_score": sell_score
        }

strict_checklist_engine = StrictChecklistEngine()
