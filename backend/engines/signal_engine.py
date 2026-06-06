import pandas as pd
import numpy as np
import datetime

class SignalEngine:
    def __init__(self):
        self.min_score = 6
        self._struct_engine = None  # FIX: Lazy init once, not on every signal call

    @property
    def struct_engine(self):
        if self._struct_engine is None:
            from backend.engines.structure_engine import StructureEngine
            self._struct_engine = StructureEngine()
        return self._struct_engine

    def detect_market_phase(self, df):
        """Classify market phase: Trending, Expansion, Consolidation."""
        atr = df['high'].rolling(14).max() - df['low'].rolling(14).min()
        atr_avg = atr.rolling(50).mean().iloc[-1]
        current_atr = atr.iloc[-1]
        
        # Consolidation check: Narrow ATR + overlapping candles
        if current_atr < (atr_avg * 0.7):
            return "CONSOLIDATION"
        
        # Trending vs Expansion
        # Expansion is sudden move, Trending is sustained
        sma20 = df['close'].rolling(20).mean().iloc[-1]
        sma50 = df['close'].rolling(50).mean().iloc[-1]
        
        if abs(df['close'].iloc[-1] - sma20) > (current_atr * 2):
            return "EXPANSION"
        elif (df['close'].iloc[-1] > sma20 > sma50) or (df['close'].iloc[-1] < sma20 < sma50):
            return "TRENDING"
        
        return "NEUTRAL"

    def get_daily_bias(self, current_price, daily_open, pdh, pdl):
        """Calculate Daily Bias based on Open, PDH, and PDL."""
        bias = "NEUTRAL"
        if current_price > daily_open and current_price > pdh:
            bias = "BULLISH"
        elif current_price < daily_open and current_price < pdl:
            bias = "BEARISH"
        return bias

    def check_killzone(self, current_time):
        """Define Indian Market Killzones for high-probability setups."""
        # IST Windows: 9:15-10:45 (Morning Volatility) and 13:15-15:00 (Afternoon Trend)
        morning_start = datetime.time(9, 15)
        morning_end = datetime.time(10, 45)
        afternoon_start = datetime.time(13, 15)
        afternoon_end = datetime.time(15, 0)
        
        is_morning = morning_start <= current_time <= morning_end
        is_afternoon = afternoon_start <= current_time <= afternoon_end
        
        return is_morning or is_afternoon

    def get_htf_trend(self, htf_df):
        """Determine trend on the Higher Timeframe (HTF)."""
        ema50 = htf_df['close'].rolling(50).mean().iloc[-1]
        last_close = htf_df['close'].iloc[-1]
        return "BULLISH" if last_close > ema50 else "BEARISH"

    def evaluate(self, htf_df, mtf_df, structure_data, daily_data, session_info):
        """Evaluate full confluence with advanced filters."""
        from datetime import timezone, timedelta
        ist_tz = timezone(timedelta(hours=5, minutes=30))
        now = datetime.datetime.now(ist_tz).time()
        in_killzone = self.check_killzone(now)
        htf_trend = self.get_htf_trend(htf_df)
        
        last_close = mtf_df['close'].iloc[-1]
        phase = self.detect_market_phase(mtf_df)
        
        # Daily Bias Alignment
        bias = self.get_daily_bias(
            last_close, 
            daily_data['open'], 
            daily_data['pdh'], 
            daily_data['pdl']
        )
        
        # Score Calculation
        score = 0
        if bias == htf_trend: score += 4 # Strongest alignment factor
        if bias == "BULLISH" and structure_data['bos_bullish']: score += 3
        if bias == "BEARISH" and structure_data['bos_bearish']: score += 3
        if structure_data['sweep_high'] or structure_data['sweep_low']: score += 2
        
        # Premium/Discount Alignment
        if bias == "BULLISH" and structure_data['in_discount']: score += 2
        if bias == "BEARISH" and structure_data['in_premium']: score += 2
        
        # Liquidity Pool Targets (EQH/EQL)
        if bias == "BULLISH" and structure_data['eqh']: score += 1 # Target above
        if bias == "BEARISH" and structure_data['eql']: score += 1 # Target below
        
        if phase in ["TRENDING", "EXPANSION"]: score += 2
        if in_killzone: score += 2 
        
        # Volume Validation
        vol_avg = mtf_df['volume'].rolling(20).mean().iloc[-1]
        if mtf_df['volume'].iloc[-1] > (vol_avg * 1.5): score += 2
        
        # FVG/Imbalance Check
        if structure_data.get('fvg_gap', False): score += 1
        
        side = None
        # Ultra-Strict Trigger: 
        # 1. Must be in Killzone 
        # 2. Must be aligned with HTF Trend
        # 3. Must be in the right zone (Discount for BUY, Premium for SELL)
        # 4. Min score 8
        if in_killzone and bias == htf_trend and score >= 8:
            if phase != "CONSOLIDATION":
                if bias == "BULLISH" and structure_data['in_discount']:
                    if structure_data['bos_bullish']: side = "BUY"
                elif bias == "BEARISH" and structure_data['in_premium']:
                    if structure_data['bos_bearish']: side = "SELL"
            
        return {
            'side': side,
            'score': score,
            'phase': phase,
            'bias': bias,
            'in_killzone': in_killzone,
            'fvg_ready': structure_data.get('fvg_gap', False)
        }

    def generate_signal(self, df_1m, df_5m, df_15m, df_1h):
        """Wrapper for main.py — uses ATR-based TP/SL and Order Block validation."""
        structure_data = self.struct_engine.analyze(df_15m)  # FIX: reuse from __init__

        # FIX: PDH/PDL — use actual previous session high/low, not the whole fetched window
        # df_1h has ~30 candles; iloc[0] is oldest (yesterday+), iloc[-1] is latest (today)
        # Exclude last candle (today partial) to get previous session range
        prev_candles = df_1h.iloc[:-1] if len(df_1h) > 1 else df_1h
        daily_data = {
            'open': df_1h.iloc[-1]['open'],   # Today's open (last hourly candle open)
            'pdh': prev_candles['high'].max(), # Previous session high
            'pdl': prev_candles['low'].min()   # Previous session low
        }

        eval_result = self.evaluate(df_1h, df_15m, structure_data, daily_data, {'is_valid': True})

        # FIX: Proper ATR — rolling mean of true ranges, not raw high-low range
        # The old calculation was: (rolling_max - rolling_min) which is a range, not ATR
        high_low = df_5m['high'] - df_5m['low']
        high_close = (df_5m['high'] - df_5m['close'].shift()).abs()
        low_close = (df_5m['low'] - df_5m['close'].shift()).abs()
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr_14 = true_range.rolling(14).mean().iloc[-1]
        if atr_14 != atr_14 or atr_14 == 0:  # NaN or zero fallback
            atr_14 = 30.0

        atr_multiplier_sl = 1.5
        atr_multiplier_tp = 3.0  # 2:1 RRR

        entry = df_1m['close'].iloc[-1]
        side = eval_result['side']

        if side == "BUY":
            sl = entry - (atr_14 * atr_multiplier_sl)
            tp = entry + (atr_14 * atr_multiplier_tp)
        elif side == "SELL":
            sl = entry + (atr_14 * atr_multiplier_sl)
            tp = entry - (atr_14 * atr_multiplier_tp)
        else:
            sl = entry - (atr_14 * atr_multiplier_sl)
            tp = entry + (atr_14 * atr_multiplier_tp)

        # --- Order Block Validation (Extra Confirmation) ---
        ob_valid = self.struct_engine.validate_order_block(df_5m, len(df_5m) - 1)

        return {
            'signal': side if side else 'NO TRADE',  # FIX: return string not None
            'entry': round(entry, 2),
            'sl': round(sl, 2),
            'tp': round(tp, 2),
            'atr': round(atr_14, 2),
            'score': eval_result.get('score', 0),
            'order_block_valid': self.struct_engine.validate_order_block(df_5m, len(df_5m) - 1),
            'reason': (
                f"SMC | Score: {eval_result['score']} | Phase: {eval_result['phase']} | "
                f"Killzone: {eval_result['in_killzone']} | "
                f"ATR SL: {round(atr_14 * atr_multiplier_sl, 1)} pts"
            )
        }

