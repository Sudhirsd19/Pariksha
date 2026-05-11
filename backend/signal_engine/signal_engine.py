from engines.trend_engine import TrendEngine
from engines.structure_engine import StructureEngine
from engines.liquidity_engine import LiquidityEngine
from engines.volume_engine import VolumeEngine
from engines.momentum_engine import MomentumEngine
from engines.regime_engine import RegimeEngine
from filters.filters import SessionFilter, VolatilityFilter

class SignalEngine:
    def __init__(self):
        self.trend_engine = TrendEngine()
        self.structure_engine = StructureEngine()
        self.liquidity_engine = LiquidityEngine()
        self.volume_engine = VolumeEngine()
        self.momentum_engine = MomentumEngine()
        self.regime_engine = RegimeEngine()

    def generate_signal(self, df_1m, df_5m, df_15m, df_1h):
        """
        INSTITUTIONAL GRADE SCORING SYSTEM (v2.0)
        Target Score: >= 6/9
        """
        
        # 1. HARD FILTERS (Non-negotiable)
        if not SessionFilter.is_within_session():
            return {"signal": "NO TRADE", "score": 0, "reason": "Outside strict session hours"}
            
        regime = self.regime_engine.analyze(df_5m)
        if not regime['trending']:
            return {"signal": "NO TRADE", "score": 0, "reason": "Choppy Market (ADX < 20)"}

        # 2. DATA EXTRACTION
        trend_1h = self.trend_engine.analyze(df_1h)
        trend_15m = self.trend_engine.analyze(df_15m)
        trend_5m = self.trend_engine.analyze(df_5m)
        structure_5m = self.structure_engine.analyze(df_5m)
        momentum_1m = self.momentum_engine.analyze(df_1m)
        volume_5m = self.volume_engine.analyze(df_5m)
        liquidity_5m = self.liquidity_engine.analyze(df_5m)
        
        price = df_1m['close'].iloc[-1]
        atr_5m = df_5m['ATR'].iloc[-1] if 'ATR' in df_5m.columns else 30

        # --- MANDATORY PRODUCTION SAFETY: BOS Confirmation ---
        if structure_5m.get('bos', 'None') == "None":
            return {"signal": "NO TRADE", "score": 0, "reason": "Awaiting BOS Confirmation"}

        # 3. SCORING ENGINE
        score = 0
        
        # Factor 1: 1H Trend Alignment (+2)
        is_bullish_trend = (trend_1h == "Bullish" and trend_15m == "Bullish")
        is_bearish_trend = (trend_1h == "Bearish" and trend_15m == "Bearish")
        if is_bullish_trend or is_bearish_trend: score += 2
        
        # Factor 2: Liquidity Sweep (+2)
        if liquidity_5m['sweep'] in ["Bullish Sweep", "Bearish Sweep"]: score += 2
        
        # Factor 3: BOS Confirmation (Body Close) (+2)
        # Note: structure_engine now uses body close in v2.0
        if structure_5m['bos'] in ["Bullish", "Bearish"]: score += 2
        
        # Factor 4: VWAP Alignment (+1)
        # Assuming VolumeEngine provides vwap_status
        if volume_5m['vwap_status'] == "Above" and is_bullish_trend: score += 1
        elif volume_5m['vwap_status'] == "Below" and is_bearish_trend: score += 1
        
        # Factor 5: Volume Spike (+1)
        if volume_5m['strength'] == "Strong": score += 1
        
        # Factor 6: Momentum Filter (+1)
        if is_bullish_trend and momentum_1m['rsi'] > 50 and momentum_1m['rising']: score += 1
        elif is_bearish_trend and momentum_1m['rsi'] < 50 and not momentum_1m['rising']: score += 1

        # 4. DECISION LOGIC
        final_signal = "NO TRADE"
        if score >= 6:
            if is_bullish_trend and liquidity_5m['sweep'] == "Bullish Sweep":
                final_signal = "BUY"
            elif is_bearish_trend and liquidity_5m['sweep'] == "Bearish Sweep":
                final_signal = "SELL"

        if final_signal != "NO TRADE":
            return {
                "signal": final_signal,
                "score": score,
                "entry": price,
                "sl": price - (atr_5m * 1.5) if final_signal == "BUY" else price + (atr_5m * 1.5),
                "tp": price + (atr_5m * 3.0) if final_signal == "BUY" else price - (atr_5m * 3.0),
                "reason": f"INSTITUTIONAL CONFIRMED (Score: {score}/9)"
            }
        
        return {"signal": "NO TRADE", "score": score, "reason": f"Low Quality Setup (Score: {score}/9)"}

