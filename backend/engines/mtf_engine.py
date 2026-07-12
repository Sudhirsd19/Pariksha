import pandas as pd
from backend.indicators.technical_indicators import TechnicalIndicators

class MTFEngine:
    """HTF = Direction, LTF = Entry (Smart Money Concepts).

    Higher Timeframe (15m / 1h) determines the TREND DIRECTION.
    Lower Timeframe (1m / 5m) determines the precise ENTRY TIMING.
    Only enter on LTF when HTF confirms the direction.
    """

    def _ensure_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Apply indicators if not already present."""
        if df is None or df.empty:
            return df
        df = df.copy()
        df.columns = [c.lower() for c in df.columns]
        needed = {'ema_20', 'ema_50', 'adx', 'rsi', 'vwap', 'macd', 'macd_signal'}
        if not needed.issubset(set(df.columns)):
            try:
                df = TechnicalIndicators.apply_all(df)
            except Exception:
                pass
        return df

    def analyze_htf(self, df_15m: pd.DataFrame, df_1h: pd.DataFrame) -> str:
        """Determine overall trend direction from higher timeframes.

        Uses EMA 20/50 alignment + ADX strength + MACD confirmation on both 15m and 1h.
        Scoring: each timeframe can contribute 0-3 points per direction.
        Needs 3+ bull or bear points to confirm.

        Returns:
            'Bullish', 'Bearish', or 'Neutral'
        """
        bull = 0
        bear = 0

        for label, df in [('15m', df_15m), ('1h', df_1h)]:
            if df is None or df.empty or len(df) < 50:
                continue

            df = self._ensure_indicators(df)
            last = df.iloc[-1]

            ema20 = last.get('ema_20', 0)
            ema50 = last.get('ema_50', 0)
            adx = last.get('adx', 0)
            macd = last.get('macd', 0)
            macd_sig = last.get('macd_signal', 0)

            # EMA alignment
            if ema20 > ema50:
                bull += 1
            elif ema20 < ema50:
                bear += 1

            # ADX confirms a strong trend (> 20)
            if adx > 20:
                if ema20 > ema50:
                    bull += 1
                elif ema20 < ema50:
                    bear += 1

            # MACD confirmation
            if macd and macd_sig:
                if macd > macd_sig:
                    bull += 1
                elif macd < macd_sig:
                    bear += 1

        if bull >= 3:
            return "Bullish"
        elif bear >= 3:
            return "Bearish"
        return "Neutral"

    def get_htf_confidence(self, df_15m: pd.DataFrame, df_1h: pd.DataFrame) -> int:
        """Calculate HTF trend confidence (0 to 100)."""
        score = 0
        for df in [df_15m, df_1h]:
            if df is None or df.empty or len(df) < 50:
                continue

            df = self._ensure_indicators(df)
            last = df.iloc[-1]

            ema20 = last.get('ema_20', 0)
            ema50 = last.get('ema_50', 0)
            adx = last.get('adx', 0)
            macd = last.get('macd', 0)
            macd_sig = last.get('macd_signal', 0)
            rsi = last.get('rsi', 50)

            # EMA 20/50: +15/-15
            if ema20 > ema50:
                score += 15
            elif ema20 < ema50:
                score -= 15

            # ADX > 20: +10 (sign matches EMA direction)
            if adx > 20:
                if ema20 > ema50:
                    score += 10
                elif ema20 < ema50:
                    score -= 10

            # MACD > Signal: +10/-10
            if macd and macd_sig:
                if macd > macd_sig:
                    score += 10
                elif macd < macd_sig:
                    score -= 10

            # RSI: +5/-5
            if rsi > 50:
                score += 5
            elif rsi < 50:
                score -= 5

        # Return absolute value clamped to 0-100
        return min(100, max(0, abs(score)))

    def analyze_ltf(self, df_1m: pd.DataFrame, df_5m: pd.DataFrame,
                    htf_trend: str) -> bool:
        """Check if lower timeframe supports entry in HTF direction.

        Conditions for valid LTF entry:
        1. EMA 9 > EMA 20 for bullish (or < for bearish) on 5m
        2. RSI supports direction (>50 for bull, <50 for bear) on 5m
        3. Price above VWAP for bull (below for bear) on 5m
        At least 2 of 3 must agree.

        Returns:
            True if LTF structure aligns with HTF, else False.
        """
        if htf_trend == "Neutral":
            return False

        # Prefer 5m; fallback to 1m
        df = df_5m if (df_5m is not None and not df_5m.empty) else df_1m
        if df is None or df.empty or len(df) < 25:
            return False

        df = self._ensure_indicators(df)
        last = df.iloc[-1]

        ema9 = last.get('ema_9', 0)
        ema20 = last.get('ema_20', 0)
        rsi = last.get('rsi', 50)
        vwap = last.get('vwap', 0)
        price = last.get('close', 0)

        score = 0

        if htf_trend == "Bullish":
            if ema9 > ema20:
                score += 1
            if rsi > 50:
                score += 1
            if vwap > 0 and price > vwap:
                score += 1
        elif htf_trend == "Bearish":
            if ema9 < ema20:
                score += 1
            if rsi < 50:
                score += 1
            if vwap > 0 and price < vwap:
                score += 1

        return score >= 2

    def analyze(self, df_1m: pd.DataFrame, df_5m: pd.DataFrame,
                df_15m: pd.DataFrame, df_1h: pd.DataFrame) -> dict:
        """Full multi-timeframe analysis."""
        htf_trend = self.analyze_htf(df_15m, df_1h)
        ltf_valid = self.analyze_ltf(df_1m, df_5m, htf_trend)
        htf_confidence = self.get_htf_confidence(df_15m, df_1h)

        # Alignment score (0-100)
        alignment = 0
        if htf_trend != "Neutral":
            alignment += 40  # HTF has a direction

            # Check how many LTF conditions match
            df = df_5m if (df_5m is not None and not df_5m.empty) else df_1m
            if df is not None and not df.empty and len(df) >= 25:
                df = self._ensure_indicators(df)
                last = df.iloc[-1]
                ema9 = last.get('ema_9', 0)
                ema20 = last.get('ema_20', 0)
                rsi = last.get('rsi', 50)
                vwap = last.get('vwap', 0)
                price = last.get('close', 0)

                if htf_trend == "Bullish":
                    if ema9 > ema20: alignment += 20
                    if rsi > 50: alignment += 20
                    if vwap > 0 and price > vwap: alignment += 20
                else:
                    if ema9 < ema20: alignment += 20
                    if rsi < 50: alignment += 20
                    if vwap > 0 and price < vwap: alignment += 20

        # Supporting flags
        htf_ema_bullish = False
        ltf_momentum = False
        if df_15m is not None and not df_15m.empty and len(df_15m) >= 50:
            df_15 = self._ensure_indicators(df_15m)
            htf_ema_bullish = df_15.iloc[-1].get('ema_20', 0) > df_15.iloc[-1].get('ema_50', 0)

        if df_5m is not None and not df_5m.empty and len(df_5m) >= 20:
            df_5 = self._ensure_indicators(df_5m)
            rsi_5 = df_5.iloc[-1].get('rsi', 50)
            if htf_trend == "Bullish":
                ltf_momentum = rsi_5 > 50
            elif htf_trend == "Bearish":
                ltf_momentum = rsi_5 < 50

        return {
            'htf_trend': htf_trend,
            'ltf_entry_valid': ltf_valid,
            'alignment_score': min(alignment, 100),
            'htf_confidence': htf_confidence,
            'htf_ema_bullish': htf_ema_bullish,
            'ltf_momentum_aligned': ltf_momentum,
        }

mtf_engine = MTFEngine()
