import pandas as pd
import numpy as np
import datetime

class SignalEngine:
    def __init__(self):
        self.min_score = 8   # Must match the hardcoded threshold in evaluate()
        self._struct_engine = None  # FIX: Lazy init once, not on every signal call

    @property
    def struct_engine(self):
        if self._struct_engine is None:
            from backend.engines.structure_engine import StructureEngine
            self._struct_engine = StructureEngine()
        return self._struct_engine

    def detect_market_phase(self, df):
        """Classify market phase: Trending, Expansion, Consolidation."""
        # True ATR: max(H-L, |H-prev_C|, |L-prev_C|) — NOT rolling range
        import pandas as pd
        hl       = df['high'] - df['low']
        hc       = (df['high'] - df['close'].shift(1)).abs()
        lc       = (df['low']  - df['close'].shift(1)).abs()
        true_range = pd.concat([hl, hc, lc], axis=1).max(axis=1)
        atr_14   = true_range.rolling(14).mean()
        atr_avg  = atr_14.rolling(50).mean().iloc[-1]
        current_atr = atr_14.iloc[-1]

        if pd.isna(current_atr) or pd.isna(atr_avg) or atr_avg == 0:
            return "NEUTRAL"

        # Consolidation: ATR significantly below its own average
        if current_atr < (atr_avg * 0.7):
            return "CONSOLIDATION"

        # Trending vs Expansion
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

    def calculate_adx(self, df, period=14):
        """Calculate Average Directional Index (ADX) to determine trend strength."""
        try:
            high = df['high']
            low = df['low']
            close = df['close']
            
            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs()
            ], axis=1).max(axis=1)
            
            up_move = high - high.shift()
            down_move = low.shift() - low
            
            plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=df.index)
            minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=df.index)
            
            tr_smooth = tr.rolling(period).mean()
            plus_di = 100 * (plus_dm.rolling(period).mean() / tr_smooth)
            minus_di = 100 * (minus_dm.rolling(period).mean() / tr_smooth)
            
            dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
            adx = dx.rolling(period).mean()
            
            val = adx.iloc[-1]
            if pd.isna(val):
                return 25.0
            return float(val)
        except Exception:
            return 25.0

    def evaluate(self, htf_df, mtf_df, structure_data, daily_data, session_info, symbol="NIFTY"):
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
        
        # FVG/Imbalance Check — only score if FVG direction matches trade bias
        if bias == "BULLISH" and structure_data.get('bullish_fvg', False): score += 1
        if bias == "BEARISH" and structure_data.get('bearish_fvg', False): score += 1
        
        # Allow backtest override to relax strict live filters for bulk historical testing
        backtest_override = False
        try:
            backtest_override = bool(session_info.get('backtest_override', False))
        except Exception:
            backtest_override = False

        # 1. ADX Trend Strength Check
        adx_val = self.calculate_adx(mtf_df)
        adx_ok = adx_val >= 20
        if adx_ok:
            score += 2
        else:
            score -= 2 # Deduct points for rangebound chop
            
        # 2. PCR Supportive Check
        from backend.engines.oi_engine import oi_engine
        oi_supportive = True
        if bias == "BULLISH":
            oi_supportive = oi_engine.is_oi_supportive(symbol, "BUY")
        elif bias == "BEARISH":
            oi_supportive = oi_engine.is_oi_supportive(symbol, "SELL")

        # 3. 15-Min ORB Filter
        orb_passed = True
        try:
            if 'time' in mtf_df.columns and not mtf_df.empty:
                latest_time = pd.to_datetime(mtf_df['time'].iloc[-1])
                today_str = latest_time.strftime("%Y-%m-%d")
                # Normalize time column to string safely (handles both str and datetime types)
                time_col_str = mtf_df['time'].astype(str)
                today_candles = mtf_df[time_col_str.str.startswith(today_str)]
            else:
                today_candles = pd.DataFrame()

            if not today_candles.empty:
                first_candle = today_candles.iloc[0]
                orb_high = first_candle['high']
                orb_low  = first_candle['low']
                if bias == "BULLISH" and last_close <= orb_high:
                    orb_passed = False
                elif bias == "BEARISH" and last_close >= orb_low:
                    orb_passed = False
            # else: no today candles found → bypass ORB (don't block trade due to missing data)
        except Exception as e:
            print(f"[SignalEngine] ORB filter error: {e}")  # log instead of silent swallow

        side = None
        # Ultra-Strict Trigger for live trading. For backtests we optionally relax these.
        required_score = 8
        if backtest_override:
            # In backtest mode, be more permissive to gather signal behavior
            in_killzone = True
            oi_supportive = True
            orb_passed = True
            required_score = 4

        if in_killzone and bias == htf_trend and score >= required_score and oi_supportive and orb_passed:
            if phase != "CONSOLIDATION":
                if bias == "BULLISH" and structure_data.get('in_discount', False):
                    if structure_data.get('bos_bullish', False):
                        side = "BUY"
                elif bias == "BEARISH" and structure_data.get('in_premium', False):
                    if structure_data.get('bos_bearish', False):
                        side = "SELL"
            
        return {
            'side': side,
            'score': score,
            'phase': phase,
            'bias': bias,
            'in_killzone': in_killzone,
            'fvg_ready': structure_data.get('fvg_gap', False)
        }

    def generate_signal(self, df_1m, df_5m, df_15m, df_1h, symbol=None, ltp=None, backtest_override=False):
        """Wrapper for main.py — uses ATR-based TP/SL and Order Block validation."""
        if not symbol:
            # Guess symbol based on current price
            entry = df_1m['close'].iloc[-1]
            symbol = "BANKNIFTY" if entry > 35000 else "NIFTY"

        structure_data = self.struct_engine.analyze(df_15m)  # FIX: reuse from __init__

        # PDH/PDL: filter df_1h to only yesterday's candles using the 'time' column
        if 'time' in df_1h.columns and not df_1h.empty:
            _latest_time = pd.to_datetime(df_1h['time'].iloc[-1])
            _today_str = _latest_time.strftime("%Y-%m-%d")
        else:
            from datetime import timezone, timedelta, datetime as _dt
            _ist = timezone(timedelta(hours=5, minutes=30))
            _today_str = _dt.now(_ist).strftime("%Y-%m-%d")

        if 'time' in df_1h.columns:
            # Normalize to string in case column is datetime type
            time_col = df_1h['time'].astype(str)
            today_candles_1h  = df_1h[time_col.str.startswith(_today_str)]
            prev_day_candles  = df_1h[~time_col.str.startswith(_today_str)]
        else:
            # Fallback: last 8 candles = roughly yesterday's NSE session (9 hourly bars)
            prev_day_candles  = df_1h.iloc[-9:-1]
            today_candles_1h  = df_1h.iloc[-1:]

        daily_data = {
            'open': today_candles_1h.iloc[0]['open'] if not today_candles_1h.empty else df_1h.iloc[-1]['open'],
            'pdh':  prev_day_candles['high'].max() if not prev_day_candles.empty else df_1h['high'].iloc[-2],
            'pdl':  prev_day_candles['low'].min()  if not prev_day_candles.empty else df_1h['low'].iloc[-2],
        }

        # Pass a backtest_override flag via session_info when running historical backtests
        # Pass backtest_override through session_info when requested by callers
        eval_result = self.evaluate(df_1h, df_15m, structure_data, daily_data, {'is_valid': True, 'backtest_override': bool(backtest_override)}, symbol=symbol)

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

        entry = ltp if ltp and ltp > 0 else df_1m['close'].iloc[-1]
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

        # --- Order Block Validation (Extra Confirmation) --- FIX H-2: Called only once, result reused
        ob_valid = self.struct_engine.validate_order_block(df_5m, len(df_5m) - 1)

        return {
            'signal': side if side else 'NO TRADE',  # FIX: return string not None
            'entry': round(entry, 2),
            'sl': round(sl, 2),
            'tp': round(tp, 2),
            'atr': round(atr_14, 2),
            'score': eval_result.get('score', 0),
            'order_block_valid': ob_valid,  # FIX H-2: Reuse computed result
            'reason': (
                f"SMC | Score: {eval_result['score']} | Phase: {eval_result['phase']} | "
                f"Killzone: {eval_result['in_killzone']} | "
                f"ATR SL: {round(atr_14 * atr_multiplier_sl, 1)} pts"
            )
        }


