import pandas as pd
import numpy as np
from datetime import datetime
from backend.indicators.technical_indicators import TechnicalIndicators

class StrictChecklistEngine:
    """
    Implements the 100-Point Confluence-Based Scorecard for Ultra-High Conviction Trades.
    
    Scoring Categories:
      - SMC Structure (25 pts): BOS, CHoCH, MSS, FVG, Pullback
      - Trend & MTF  (20 pts): EMA alignment, Supertrend, +DI/-DI, HTF alignment
      - Momentum     (20 pts): RSI sweet spot, MACD crossover, MACD histogram, RSI slope
      - Volume/VWAP  (20 pts): VWAP position, directional volume spike, market depth
      - Candlestick  (10 pts): Engulfing, Hammer, Doji at key level
      - Risk Quality  (5 pts): RR quality, session quality
    
    Penalty System: Subtracts points for overbought/oversold, ATR exhaustion, chasing.
    Confluence Counter: Counts how many independent categories confirm direction.
    """
    def __init__(self):
        pass
        
    def evaluate(self, symbol: str, df: pd.DataFrame, 
                 is_nifty_bullish: bool = True, 
                 market_depth_buyer_ratio: float = 1.0,
                 structure_result: dict = None,
                 candle_result: dict = None,
                 mtf_result: dict = None,
                 volume_result: dict = None,
                 momentum_result: dict = None,
                 trend_direction: str = "Neutral") -> dict:
        """
        Evaluates the stock against the 100-point strict checklist.
        Returns a dictionary with score, strict_signal, reasons, breakdown, and confluence_count.
        """
        if df is None or df.empty or len(df) < 30:
            return {"score": 0, "strict_signal": "NONE", "signal": "NONE",
                    "reasons": ["Not enough data"], "breakdown": {},
                    "confluence_count": 0, "entry": 0, "sl": 0, "tp": 0, "atr": 0}
            
        # Standardize columns to lowercase
        df.columns = [col.lower() for col in df.columns]
        
        # Ensure all indicators are calculated
        if 'MACD' not in df.columns or 'EMA_21' not in df.columns or 'ATR' not in df.columns:
            df = TechnicalIndicators.apply_all(df)
            
        # Default engine results if not provided
        structure_result = structure_result or {}
        candle_result = candle_result or {}
        mtf_result = mtf_result or {}
        volume_result = volume_result or {}
        momentum_result = momentum_result or {}

        last_idx = -1
        current = df.iloc[last_idx]
        prev = df.iloc[last_idx - 1]
        
        buy_score = 0
        sell_score = 0
        buy_reasons = []
        sell_reasons = []
        
        buy_breakdown = {
            "SMC Structure": 0, "Trend & MTF": 0, "Momentum": 0,
            "Volume & VWAP": 0, "Candlestick": 0, "Risk Quality": 0
        }
        sell_breakdown = {
            "SMC Structure": 0, "Trend & MTF": 0, "Momentum": 0,
            "Volume & VWAP": 0, "Candlestick": 0, "Risk Quality": 0
        }
        
        # Confluence tracking: count how many categories confirm each direction
        buy_confluences = set()
        sell_confluences = set()
        
        # ==========================================
        # 1. SMC Structure (25 Points)
        # ==========================================
        
        # BOS in direction (10 pts)
        bos = structure_result.get('bos', 'None')
        if bos == "Bullish":
            buy_score += 10
            buy_breakdown["SMC Structure"] += 10
            buy_reasons.append("BOS Bullish")
            buy_confluences.add("SMC")
        elif bos == "Bearish":
            sell_score += 10
            sell_breakdown["SMC Structure"] += 10
            sell_reasons.append("BOS Bearish")
            sell_confluences.add("SMC")
            
        # CHoCH / MSS confirmation (8 pts)
        if structure_result.get('mss_bullish', False):
            buy_score += 8
            buy_breakdown["SMC Structure"] += 8
            buy_reasons.append("MSS Bullish confirmed")
            buy_confluences.add("SMC")
        elif structure_result.get('choch_bullish', False):
            buy_score += 5  # CHoCH alone = 5, MSS (CHoCH+BOS) = 8
            buy_breakdown["SMC Structure"] += 5
            buy_reasons.append("CHoCH Bullish")
            buy_confluences.add("SMC")
            
        if structure_result.get('mss_bearish', False):
            sell_score += 8
            sell_breakdown["SMC Structure"] += 8
            sell_reasons.append("MSS Bearish confirmed")
            sell_confluences.add("SMC")
        elif structure_result.get('choch_bearish', False):
            sell_score += 5
            sell_breakdown["SMC Structure"] += 5
            sell_reasons.append("CHoCH Bearish")
            sell_confluences.add("SMC")
        
        # FVG / Pullback retest in direction (7 pts)
        if structure_result.get('bullish_fvg', False):
            buy_score += 4
            buy_breakdown["SMC Structure"] += 4
            buy_reasons.append("Bullish FVG")
        if structure_result.get('bearish_fvg', False):
            sell_score += 4
            sell_breakdown["SMC Structure"] += 4
            sell_reasons.append("Bearish FVG")
            
        if structure_result.get('pullback_to_support', False):
            buy_score += 3
            buy_breakdown["SMC Structure"] += 3
            buy_reasons.append("Pullback to support")
        if structure_result.get('pullback_to_resistance', False):
            sell_score += 3
            sell_breakdown["SMC Structure"] += 3
            sell_reasons.append("Pullback to resistance")

        # Breakout bonus (3 pts extra if breakout aligns)
        if structure_result.get('breakout_bullish', False):
            buy_score += 3
            buy_breakdown["SMC Structure"] += 3
            buy_reasons.append("Bullish breakout confirmed")
        if structure_result.get('breakout_bearish', False):
            sell_score += 3
            sell_breakdown["SMC Structure"] += 3
            sell_reasons.append("Bearish breakout confirmed")
        
        # ==========================================
        # 2. Trend & MTF (20 Points)
        # ==========================================
        
        # HTF trend alignment (8 pts)
        htf_trend = mtf_result.get('htf_trend', 'Neutral')
        if htf_trend == "Bullish":
            buy_score += 8
            buy_breakdown["Trend & MTF"] += 8
            buy_reasons.append("HTF trend Bullish")
            buy_confluences.add("MTF")
        elif htf_trend == "Bearish":
            sell_score += 8
            sell_breakdown["Trend & MTF"] += 8
            sell_reasons.append("HTF trend Bearish")
            sell_confluences.add("MTF")
            
        # LTF EMA 9 > 20 alignment (5 pts)
        ema9 = current.get('EMA_9', 0)
        ema20 = current.get('EMA_20', 0)
        if ema9 and ema20 and ema9 > ema20:
            buy_score += 5
            buy_breakdown["Trend & MTF"] += 5
            buy_confluences.add("Trend")
        elif ema9 and ema20 and ema9 < ema20:
            sell_score += 5
            sell_breakdown["Trend & MTF"] += 5
            sell_confluences.add("Trend")
        
        # Supertrend direction (4 pts)
        supertrend = current.get('Supertrend', None)
        if supertrend is True:
            buy_score += 4
            buy_breakdown["Trend & MTF"] += 4
            buy_confluences.add("Trend")
        elif supertrend is False:
            sell_score += 4
            sell_breakdown["Trend & MTF"] += 4
            sell_confluences.add("Trend")
        
        # +DI/-DI directional (3 pts)
        plus_di = current.get('PLUS_DI', 0)
        minus_di = current.get('MINUS_DI', 0)
        if plus_di and minus_di:
            if plus_di > minus_di:
                buy_score += 3
                buy_breakdown["Trend & MTF"] += 3
            elif minus_di > plus_di:
                sell_score += 3
                sell_breakdown["Trend & MTF"] += 3

        # ==========================================
        # 3. Momentum (20 Points)
        # ==========================================
        
        # RSI sweet spot (7 pts)
        rsi = current.get('RSI', 50)
        if not pd.isna(rsi):
            if 55 <= rsi <= 70:
                buy_score += 7
                buy_breakdown["Momentum"] += 7
                buy_reasons.append(f"RSI in bullish zone ({rsi:.0f})")
                buy_confluences.add("Momentum")
            elif 30 <= rsi <= 45:
                sell_score += 7
                sell_breakdown["Momentum"] += 7
                sell_reasons.append(f"RSI in bearish zone ({rsi:.0f})")
                sell_confluences.add("Momentum")
        
        # MACD histogram direction (6 pts)
        macd_hist = current.get('MACD_Hist', 0)
        prev_macd_hist = prev.get('MACD_Hist', 0)
        if not pd.isna(macd_hist) and not pd.isna(prev_macd_hist):
            if macd_hist > 0 and macd_hist > prev_macd_hist:
                buy_score += 6
                buy_breakdown["Momentum"] += 6
                buy_reasons.append("MACD histogram rising positive")
                buy_confluences.add("Momentum")
            elif macd_hist > 0:
                buy_score += 3  # Positive but not growing
                buy_breakdown["Momentum"] += 3
            elif macd_hist < 0 and macd_hist < prev_macd_hist:
                sell_score += 6
                sell_breakdown["Momentum"] += 6
                sell_reasons.append("MACD histogram falling negative")
                sell_confluences.add("Momentum")
            elif macd_hist < 0:
                sell_score += 3
                sell_breakdown["Momentum"] += 3
        
        # MACD line > signal (4 pts)
        macd_line = current.get('MACD', 0)
        macd_signal = current.get('MACD_Signal', 0)
        if not pd.isna(macd_line) and not pd.isna(macd_signal):
            if macd_line > macd_signal:
                buy_score += 4
                buy_breakdown["Momentum"] += 4
            elif macd_line < macd_signal:
                sell_score += 4
                sell_breakdown["Momentum"] += 4
        
        # RSI slope / rising-falling (3 pts)
        prev_rsi = prev.get('RSI', 50)
        if not pd.isna(rsi) and not pd.isna(prev_rsi):
            if rsi > prev_rsi and rsi > 50:
                buy_score += 3
                buy_breakdown["Momentum"] += 3
            elif rsi < prev_rsi and rsi < 50:
                sell_score += 3
                sell_breakdown["Momentum"] += 3
        
        # ==========================================
        # 4. Volume & VWAP (20 Points)
        # ==========================================
        
        # VWAP position (8 pts)
        vwap = current.get('VWAP', 0)
        if vwap and not pd.isna(vwap) and vwap > 0:
            if current['close'] > vwap:
                buy_score += 8
                buy_breakdown["Volume & VWAP"] += 8
                buy_reasons.append("Price above VWAP")
                buy_confluences.add("Volume")
            elif current['close'] < vwap:
                sell_score += 8
                sell_breakdown["Volume & VWAP"] += 8
                sell_reasons.append("Price below VWAP")
                sell_confluences.add("Volume")
        
        # DIRECTIONAL volume spike (7 pts) — FIX: no longer given to both sides
        vol_20_avg = df['volume'].iloc[-21:-1].mean() if len(df) > 21 else df['volume'].mean()
        if vol_20_avg and vol_20_avg > 0 and not pd.isna(vol_20_avg):
            is_vol_spike = current['volume'] >= (2.0 * vol_20_avg)
            if is_vol_spike:
                # Directional: green candle spike = bullish, red candle spike = bearish
                if current['close'] > current['open']:
                    buy_score += 7
                    buy_breakdown["Volume & VWAP"] += 7
                    buy_reasons.append("Bullish volume spike (2x+)")
                    buy_confluences.add("Volume")
                elif current['close'] < current['open']:
                    sell_score += 7
                    sell_breakdown["Volume & VWAP"] += 7
                    sell_reasons.append("Bearish volume spike (2x+)")
                    sell_confluences.add("Volume")
        
        # Market depth (5 pts)
        if market_depth_buyer_ratio >= 1.5:
            buy_score += 5
            buy_breakdown["Volume & VWAP"] += 5
            buy_reasons.append(f"Buyers dominate ({market_depth_buyer_ratio:.1f}x)")
        elif 0 < market_depth_buyer_ratio <= (1/1.5):
            sell_score += 5
            sell_breakdown["Volume & VWAP"] += 5
            sell_reasons.append(f"Sellers dominate ({1/market_depth_buyer_ratio:.1f}x)")
        elif market_depth_buyer_ratio == 0:
            sell_score += 5
            sell_breakdown["Volume & VWAP"] += 5
            sell_reasons.append("Sellers dominate (no buyers)")
            
        # ==========================================
        # 5. Candlestick Patterns (10 Points)
        # ==========================================
        
        # Bullish/Bearish engulfing (5 pts)
        if candle_result.get('bullish_engulfing', False):
            buy_score += 5
            buy_breakdown["Candlestick"] += 5
            buy_reasons.append("Bullish engulfing pattern")
            buy_confluences.add("Candlestick")
        if candle_result.get('bearish_engulfing', False):
            sell_score += 5
            sell_breakdown["Candlestick"] += 5
            sell_reasons.append("Bearish engulfing pattern")
            sell_confluences.add("Candlestick")
        
        # Hammer / Inverted hammer (3 pts)
        if candle_result.get('hammer', False):
            buy_score += 3
            buy_breakdown["Candlestick"] += 3
            buy_reasons.append("Hammer at support")
            buy_confluences.add("Candlestick")
        if candle_result.get('inverted_hammer', False):
            sell_score += 3
            sell_breakdown["Candlestick"] += 3
            sell_reasons.append("Inverted hammer at resistance")
            sell_confluences.add("Candlestick")
        
        # Doji at key level (2 pts) — directional by type
        if candle_result.get('doji', False):
            doji_type = candle_result.get('doji_type', 'standard')
            if doji_type == 'dragonfly':  # Bullish reversal
                buy_score += 2
                buy_breakdown["Candlestick"] += 2
                buy_reasons.append("Dragonfly doji (bullish)")
            elif doji_type == 'gravestone':  # Bearish reversal
                sell_score += 2
                sell_breakdown["Candlestick"] += 2
                sell_reasons.append("Gravestone doji (bearish)")
        
        # Morning / Evening star (3 pts bonus)
        if candle_result.get('morning_star', False):
            buy_score += 3
            buy_breakdown["Candlestick"] += 3
            buy_reasons.append("Morning star reversal")
            buy_confluences.add("Candlestick")
        if candle_result.get('evening_star', False):
            sell_score += 3
            sell_breakdown["Candlestick"] += 3
            sell_reasons.append("Evening star reversal")
            sell_confluences.add("Candlestick")
        
        # ==========================================
        # 6. Risk Quality (5 Points)
        # ==========================================
        
        # Risk-Reward SL quality (3 pts) — using 10-candle window for better swings
        lookback_window = min(20, len(df) - 1)
        swing_low = df['low'].iloc[-lookback_window:].min()
        swing_high = df['high'].iloc[-lookback_window:].max()
        
        buy_risk = current['close'] - swing_low
        sell_risk = swing_high - current['close']
        
        if buy_risk > 0 and (buy_risk / current['close']) < 0.015:
            buy_score += 3
            buy_breakdown["Risk Quality"] += 3
        if sell_risk > 0 and (sell_risk / current['close']) < 0.015:
            sell_score += 3
            sell_breakdown["Risk Quality"] += 3
        
        # Session quality (2 pts) — directional time scoring
        try:
            dt = current.get('date', None)
            if dt is not None:
                dt = dt if isinstance(dt, datetime) else pd.to_datetime(dt)
                hour = dt.hour
                minute = dt.minute
                time_val = hour * 100 + minute
                
                # Best sessions: 9:20-11:30 and 13:30-14:30
                if (920 <= time_val <= 1130) or (1330 <= time_val <= 1430):
                    buy_score += 2
                    buy_breakdown["Risk Quality"] += 2
                    sell_score += 2
                    sell_breakdown["Risk Quality"] += 2
                # Lunch chop: 11:30-13:00 → no bonus (0 pts)
                # After 14:30 → no bonus (0 pts)
        except Exception:
            pass  # If parsing fails, no bonus given (not free points)
            
        # ==========================================
        # PENALTY SYSTEM (Subtract Points)
        # ==========================================
        
        # RSI Overbought penalty on BUY (-8 pts)
        if not pd.isna(rsi) and rsi > 78:
            buy_score -= 8
            buy_reasons.append(f"PENALTY: RSI overbought ({rsi:.0f})")
        
        # RSI Oversold penalty on SELL (-8 pts)
        if not pd.isna(rsi) and rsi < 22:
            sell_score -= 8
            sell_reasons.append(f"PENALTY: RSI oversold ({rsi:.0f})")
        
        # ATR Exhaustion penalty (-5 pts for both sides)
        atr_14 = current.get('ATR', 0)
        if atr_14 and not pd.isna(atr_14) and atr_14 > 0:
            day_high = df['high'].iloc[-75:].max() if len(df) > 75 else df['high'].max()
            day_low = df['low'].iloc[-75:].min() if len(df) > 75 else df['low'].min()
            day_range = day_high - day_low
            if day_range > (0.9 * atr_14):
                buy_score -= 5
                sell_score -= 5
                buy_reasons.append("PENALTY: ATR exhausted (>90%)")
                sell_reasons.append("PENALTY: ATR exhausted (>90%)")
        
        # Chasing penalty — buying near day high or selling near day low (-3 pts)
        if len(df) > 10:
            recent_high = df['high'].iloc[-75:].max() if len(df) > 75 else df['high'].max()
            recent_low = df['low'].iloc[-75:].min() if len(df) > 75 else df['low'].min()
            if recent_high > 0 and abs(current['close'] - recent_high) / recent_high < 0.003:
                buy_score -= 3
                buy_reasons.append("PENALTY: Chasing near day high")
            if recent_low > 0 and abs(current['close'] - recent_low) / recent_low < 0.003:
                sell_score -= 3
                sell_reasons.append("PENALTY: Chasing near day low")
        
        # MACD divergence penalty (-5 pts)
        # Price making higher high but MACD making lower high = bearish divergence
        if len(df) > 10 and not pd.isna(macd_line):
            price_hh = current['close'] > df['close'].iloc[-10:-1].max()
            macd_lh = macd_line < df['MACD'].iloc[-10:-1].max() if 'MACD' in df.columns else False
            if price_hh and macd_lh:
                buy_score -= 5
                buy_reasons.append("PENALTY: Bearish MACD divergence")
            
            price_ll = current['close'] < df['close'].iloc[-10:-1].min()
            macd_hl = macd_line > df['MACD'].iloc[-10:-1].min() if 'MACD' in df.columns else False
            if price_ll and macd_hl:
                sell_score -= 5
                sell_reasons.append("PENALTY: Bullish MACD divergence")
        
        # Floor at 0
        buy_score = max(0, buy_score)
        sell_score = max(0, sell_score)
        
        # ==========================================
        # Final Decision
        # ==========================================
        signal = "NONE"
        final_score = 0
        confluences = 0
        
        if buy_score >= sell_score:
            final_score = buy_score
            confluences = len(buy_confluences)
            if final_score >= 80:
                signal = "STRONG BUY"
            elif 70 <= final_score <= 79:
                signal = "MODERATE BUY"
        else:
            final_score = sell_score
            confluences = len(sell_confluences)
            if final_score >= 80:
                signal = "STRONG SELL"
            elif 70 <= final_score <= 79:
                signal = "MODERATE SELL"
        
        # ==========================================
        # Entry, SL, TP Calculation
        # ==========================================
        entry_price = float(current['close'])
        atr_val = float(current.get('ATR', 0)) if not pd.isna(current.get('ATR', 0)) else 0.0
        
        if "BUY" in signal:
            if atr_val > 0:
                sl_price = round(entry_price - (2.0 * atr_val), 2)
            else:
                sl_price = round(swing_low, 2)
            risk = abs(entry_price - sl_price)
            tp_price = round(entry_price + (2.0 * risk), 2)  # 1:2 RR
        elif "SELL" in signal:
            if atr_val > 0:
                sl_price = round(entry_price + (2.0 * atr_val), 2)
            else:
                sl_price = round(swing_high, 2)
            risk = abs(sl_price - entry_price)
            tp_price = round(entry_price - (2.0 * risk), 2)  # 1:2 RR
        else:
            sl_price = round(entry_price * 0.98, 2)
            tp_price = round(entry_price * 1.04, 2)

        # Simplified side for downstream compatibility
        if "BUY" in signal:
            simple_signal = "BUY"
        elif "SELL" in signal:
            simple_signal = "SELL"
        else:
            simple_signal = "NONE"
                
        return {
            "strict_signal": signal,
            "signal": simple_signal,
            "strict_score": final_score,
            "buy_score": buy_score,
            "sell_score": sell_score,
            "breakdown": buy_breakdown if (buy_score >= sell_score) else sell_breakdown,
            "reasons": buy_reasons if (buy_score >= sell_score) else sell_reasons,
            "confluence_count": confluences,
            "entry": entry_price,
            "sl": sl_price,
            "tp": tp_price,
            "atr": atr_val,
        }

strict_checklist_engine = StrictChecklistEngine()
