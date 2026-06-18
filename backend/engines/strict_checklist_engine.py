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
                 market_depth_buyer_ratio: float = 1.0) -> dict:
        """
        Evaluates the stock against the 100-point strict checklist.
        Returns a dictionary with score, strict_signal, and reasons.
        """
        if df is None or df.empty or len(df) < 30:
            return {"score": 0, "strict_signal": "NONE", "reasons": ["Not enough data"], "breakdown": {}}
            
        # Ensure all indicators are calculated
        if 'MACD' not in df.columns or 'EMA_21' not in df.columns or 'ATR' not in df.columns:
            df = TechnicalIndicators.apply_all(df)
            
        last_idx = -1
        current = df.iloc[last_idx]
        prev = df.iloc[last_idx - 1]
        
        buy_score = 0
        sell_score = 0
        buy_reasons = []
        sell_reasons = []
        
        buy_breakdown = {"Macro Trend": 0, "Fundamentals": 0, "Price Action": 0, "Volume": 0, "Momentum": 0, "Risk & Execution": 0}
        sell_breakdown = {"Macro Trend": 0, "Fundamentals": 0, "Price Action": 0, "Volume": 0, "Momentum": 0, "Risk & Execution": 0}
        
        # ==========================================
        # 1. Macro Trend Filter (15 Points)
        # ==========================================
        # Index Alignment (8 PTS)
        if is_nifty_bullish:
            buy_score += 8
            buy_breakdown["Macro Trend"] += 8
        else:
            sell_score += 8
            sell_breakdown["Macro Trend"] += 8
            
        # Sector Strength (7 PTS) - Bypassed for now, assumed +7 if sector matches index direction
        # Here we just assume +7 for simplicity as we don't have sector indices intraday APIs
        buy_score += 7
        buy_breakdown["Macro Trend"] += 7
        sell_score += 7
        sell_breakdown["Macro Trend"] += 7
            
        # ==========================================
        # 2. Fundamental Strength Filter (10 Points)
        # ==========================================
        # Earnings & News - Bypassed with +10 PTS as approved by user
        buy_score += 10
        buy_breakdown["Fundamentals"] += 10
        sell_score += 10
        sell_breakdown["Fundamentals"] += 10
            
        # ==========================================
        # 3. Price Action & Trend Filter (25 Points)
        # ==========================================
        # VWAP (10 pts)
        if current['close'] > current['VWAP']:
            buy_score += 10
            buy_breakdown["Price Action"] += 10
        elif current['close'] < current['VWAP']:
            sell_score += 10
            sell_breakdown["Price Action"] += 10
            
        # EMA Crossover (8 pts) - EMA 9 > EMA 21
        if current['EMA_9'] > current['EMA_21']:
            buy_score += 8
            buy_breakdown["Price Action"] += 8
        elif current['EMA_9'] < current['EMA_21']:
            sell_score += 8
            sell_breakdown["Price Action"] += 8
            
        # 2-Hour Breakout (24 candles on 5m chart) (7 pts)
        if len(df) > 24:
            recent_2h_high = df['high'].iloc[-25:-1].max()
            recent_2h_low = df['low'].iloc[-25:-1].min()
            
            if current['close'] > recent_2h_high:
                buy_score += 7
                buy_breakdown["Price Action"] += 7
            elif current['close'] < recent_2h_low:
                sell_score += 7
                sell_breakdown["Price Action"] += 7
                
        # ==========================================
        # 4. Volume Filter (20 Points)
        # ==========================================
        # Relative Volume (10 pts): 2x of 20 SMA
        vol_20_avg = df['volume'].iloc[-21:-1].mean()
        if vol_20_avg > 0:
            if current['volume'] >= (2.0 * vol_20_avg):
                buy_score += 10
                buy_breakdown["Volume"] += 10
                sell_score += 10 # Volume spike is good for both breakouts and breakdowns
                sell_breakdown["Volume"] += 10
                
        # Market Depth (10 pts)
        if market_depth_buyer_ratio >= 1.5: 
            buy_score += 10
            buy_breakdown["Volume"] += 10
        elif market_depth_buyer_ratio <= (1/1.5): # Sellers >= 1.5x Buyers
            sell_score += 10
            sell_breakdown["Volume"] += 10
            
        # ==========================================
        # 5. Momentum Filter (15 Points)
        # ==========================================
        # RSI 55-70 (8 pts)
        rsi = current['RSI']
        if 55 <= rsi <= 70:
            buy_score += 8
            buy_breakdown["Momentum"] += 8
        elif rsi > 75:
            buy_reasons.append("RSI Overbought (>75)")
            # Score is 0
            
        if 30 <= rsi <= 45:
            sell_score += 8
            sell_breakdown["Momentum"] += 8
        elif rsi < 25:
            sell_reasons.append("RSI Oversold (<25)")
            
        # ATR Exhaustion Check (7 pts)
        atr_14 = current['ATR']
        if atr_14 and not pd.isna(atr_14) and atr_14 > 0:
            day_high = df['high'].iloc[-75:].max() # Approximation of daily high
            day_low = df['low'].iloc[-75:].min()
            day_range = day_high - day_low
            # If stock hasn't exhausted 90% of ATR
            if day_range < (0.9 * atr_14):
                buy_score += 7
                buy_breakdown["Momentum"] += 7
                sell_score += 7
                sell_breakdown["Momentum"] += 7
            else:
                buy_reasons.append("ATR Exhausted (>90%)")
                sell_reasons.append("ATR Exhausted (>90%)")
        else:
            # Fallback if ATR is not valid
            buy_score += 7
            buy_breakdown["Momentum"] += 7
            sell_score += 7
            sell_breakdown["Momentum"] += 7
            
        # ==========================================
        # 6. Risk & Execution Filter (15 Points)
        # ==========================================
        # Risk Reward 1:2 (8 pts)
        swing_low = df['low'].iloc[-5:].min()
        swing_high = df['high'].iloc[-5:].max()
        
        buy_risk = current['close'] - swing_low
        sell_risk = swing_high - current['close']
        
        if buy_risk > 0 and (buy_risk / current['close']) < 0.02: 
            buy_score += 8
            buy_breakdown["Risk & Execution"] += 8
        if sell_risk > 0 and (sell_risk / current['close']) < 0.02:
            sell_score += 8
            sell_breakdown["Risk & Execution"] += 8
            
        # Time Filter (4 pts) - 09:30 AM to 02:30 PM
        try:
            dt = current['date'] if isinstance(current['date'], datetime) else pd.to_datetime(current['date'])
            hour = dt.hour
            minute = dt.minute
            
            time_val = hour * 100 + minute
            if 930 <= time_val <= 1430:
                buy_score += 4
                buy_breakdown["Risk & Execution"] += 4
                sell_score += 4
                sell_breakdown["Risk & Execution"] += 4
        except:
            # Fallback +4 if parsing fails
            buy_score += 4
            buy_breakdown["Risk & Execution"] += 4
            sell_score += 4
            sell_breakdown["Risk & Execution"] += 4
            
        # Slippage / Spread Filter (3 pts) - Bypassed with default +3
        buy_score += 3
        buy_breakdown["Risk & Execution"] += 3
        sell_score += 3
        sell_breakdown["Risk & Execution"] += 3
            
        # ==========================================
        # Final Decision
        # ==========================================
        signal = "NONE"
        final_score = 0
        
        if buy_score >= sell_score:
            final_score = buy_score
            if final_score >= 80:
                signal = "STRONG BUY"
            elif 65 <= final_score <= 79:
                signal = "MODERATE BUY"
        else:
            final_score = sell_score
            if final_score >= 80:
                signal = "STRONG SELL"
            elif 65 <= final_score <= 79:
                signal = "MODERATE SELL"
                
        return {
            "strict_signal": signal,
            "strict_score": final_score,
            "buy_score": buy_score,
            "sell_score": sell_score,
            "breakdown": buy_breakdown if (buy_score >= sell_score) else sell_breakdown
        }

strict_checklist_engine = StrictChecklistEngine()
