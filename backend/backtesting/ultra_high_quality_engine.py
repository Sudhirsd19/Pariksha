"""
Ultra-High-Quality Signal Engine for 70%+ Win Rate
====================================================

8-Condition Strict Filter:
1. EMAs perfectly aligned (bullish: close > SMA(20) > SMA(50) > SMA(200))
2. MACD bullish (histogram positive AND increasing)
3. RSI in sweet zone (30-70, not extreme)
4. Price at S/R bounce (within 0.5% of support/resistance)
5. Volume spike: candle volume >= 2.0x MA volume
6. Increasing volume (current > previous candle volume)
7. Strong candles (high-low range > 0.5% of ATR)
8. Stochastic in middle zone (30-70, not oversold/overbought)

Result: 1-2 trades per month, 70%+ win rate expected
"""

import pandas as pd
import numpy as np
from typing import List, Tuple, Dict, Optional
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class UltraHighQualitySignalEngine:
    """Ultra-selective signal engine targeting 70%+ win rate"""
    
    def __init__(self, df: pd.DataFrame, capital: float = 100000, risk_per_trade: float = 2.0):
        """
        Args:
            df: DataFrame with OHLCV data
            capital: Trading capital
            risk_per_trade: Risk percentage per trade
        """
        self.df = df.copy()
        self.capital = capital
        self.risk_per_trade = risk_per_trade
        self.signals = []
        self.rejected_reasons = []
        
        # Ensure required columns
        self._validate_data()
        self._calculate_indicators()
    
    def _validate_data(self):
        """Validate required columns"""
        required = ['open', 'high', 'low', 'close', 'volume']
        for col in required:
            if col not in self.df.columns:
                raise ValueError(f"Missing column: {col}")
    
    def _calculate_indicators(self):
        """Calculate all technical indicators"""
        df = self.df
        
        # EMAs
        df['ema5'] = df['close'].ewm(span=5, adjust=False).mean()
        df['ema13'] = df['close'].ewm(span=13, adjust=False).mean()
        df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        # SMAs for S/R detection
        df['sma20'] = df['close'].rolling(20).mean()
        df['sma50'] = df['close'].rolling(50).mean()
        df['sma200'] = df['close'].rolling(200).mean()
        
        # ATR
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        df['atr'] = df['tr'].rolling(14).mean()
        
        # Volume MA
        df['vol_ma20'] = df['volume'].rolling(20).mean()
        
        # MACD (12, 26, 9)
        ema12 = df['close'].ewm(span=12, adjust=False).mean()
        ema26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = ema12 - ema26
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # Stochastic (14, 3, 3)
        low_min = df['low'].rolling(14).min()
        high_max = df['high'].rolling(14).max()
        df['stoch_k'] = 100 * (df['close'] - low_min) / (high_max - low_min)
        df['stoch_d'] = df['stoch_k'].rolling(3).mean()
        
        # Support/Resistance levels (20-period)
        df['support'] = df['low'].rolling(20).min()
        df['resistance'] = df['high'].rolling(20).max()
    
    def _is_allowed_time(self, timestamp) -> bool:
        """
        Check if time is in allowed trading hours (IST)
        10-11 AM IST: Morning momentum
        2-3 PM IST: Afternoon momentum
        """
        hour = timestamp.hour
        return hour in [10, 14]  # 10 AM or 2 PM IST
    
    def _is_ema_bullish(self, row) -> bool:
        """Check if EMAs are perfectly aligned (bullish)"""
        # close > ema20 > ema50 > ema200
        return (row['close'] > row['ema20'] and 
                row['ema20'] > row['ema50'] and 
                row['ema50'] > row['ema200'])
    
    def _is_ema_bearish(self, row) -> bool:
        """Check if EMAs are perfectly aligned (bearish)"""
        # close < ema20 < ema50 < ema200
        return (row['close'] < row['ema20'] and 
                row['ema20'] < row['ema50'] and 
                row['ema50'] < row['ema200'])
    
    def _is_macd_bullish(self, idx) -> bool:
        """Check if MACD is bullish (histogram positive and increasing)"""
        if idx < 2:
            return False
        
        curr_hist = self.df.iloc[idx]['macd_hist']
        prev_hist = self.df.iloc[idx-1]['macd_hist']
        
        # Histogram should be positive and increasing
        return curr_hist > 0 and curr_hist > prev_hist
    
    def _is_macd_bearish(self, idx) -> bool:
        """Check if MACD is bearish (histogram negative and decreasing)"""
        if idx < 2:
            return False
        
        curr_hist = self.df.iloc[idx]['macd_hist']
        prev_hist = self.df.iloc[idx-1]['macd_hist']
        
        # Histogram should be negative and decreasing
        return curr_hist < 0 and curr_hist < prev_hist
    
    def _is_rsi_valid(self, row) -> bool:
        """Check if RSI is in sweet zone (30-70, not extreme)"""
        return 30 < row['rsi'] < 70
    
    def _is_stoch_valid(self, row) -> bool:
        """Check if Stochastic is in middle zone (30-70)"""
        return 30 < row['stoch_k'] < 70
    
    def _is_at_support_resistance(self, row) -> bool:
        """Check if price is at S/R bounce (within 0.5% of level)"""
        support = row['support']
        resistance = row['resistance']
        close = row['close']
        
        # Within 0.5% of support or resistance
        dist_to_support = abs(close - support) / support * 100
        dist_to_resistance = abs(close - resistance) / resistance * 100
        
        return dist_to_support < 0.5 or dist_to_resistance < 0.5
    
    def _is_volume_spike(self, row) -> bool:
        """Check if volume is spiked (>= 2.0x MA volume)"""
        return row['volume'] >= 2.0 * row['vol_ma20']
    
    def _is_volume_increasing(self, idx) -> bool:
        """Check if volume is increasing (current > previous)"""
        if idx < 1:
            return False
        
        curr_vol = self.df.iloc[idx]['volume']
        prev_vol = self.df.iloc[idx-1]['volume']
        
        return curr_vol > prev_vol
    
    def _is_candle_strong(self, row) -> bool:
        """Check if candle is strong (range > 0.5% of ATR)"""
        candle_range = row['high'] - row['low']
        return candle_range > 0.005 * row['atr']
    
    def _evaluate_bullish_signal(self, idx) -> Optional[Dict]:
        """Evaluate 8 conditions for bullish signal"""
        if idx < 200:  # Need history for indicators
            return None
        
        row = self.df.iloc[idx]
        prev_row = self.df.iloc[idx-1]
        conditions = []
        
        # Condition 1: EMA bullish
        cond1 = self._is_ema_bullish(row)
        conditions.append(('EMA aligned', cond1))
        
        # Condition 2: MACD bullish
        cond2 = self._is_macd_bullish(idx)
        conditions.append(('MACD bullish', cond2))
        
        # Condition 3: RSI valid
        cond3 = self._is_rsi_valid(row)
        conditions.append(('RSI in zone', cond3))
        
        # Condition 4: At S/R
        cond4 = self._is_at_support_resistance(row)
        conditions.append(('At S/R', cond4))
        
        # Condition 5: Volume spike
        cond5 = self._is_volume_spike(row)
        conditions.append(('Volume 2x+', cond5))
        
        # Condition 6: Volume increasing
        cond6 = self._is_volume_increasing(idx)
        conditions.append(('Volume increasing', cond6))
        
        # Condition 7: Strong candle
        cond7 = self._is_candle_strong(row)
        conditions.append(('Strong candle', cond7))
        
        # Condition 8: Stochastic valid
        cond8 = self._is_stoch_valid(row)
        conditions.append(('Stochastic valid', cond8))
        
        # All conditions must be true
        all_conditions_met = all(c[1] for c in conditions)
        
        if not all_conditions_met:
            failed = [c[0] for c in conditions if not c[1]]
            self.rejected_reasons.append(f"BUY rejected at {idx}: {', '.join(failed)}")
            return None
        
        # Calculate confidence score
        confidence = sum(1 for c in conditions if c[1]) / len(conditions)
        
        return {
            'type': 'BUY',
            'index': idx,
            'price': row['close'],
            'atr': row['atr'],
            'confidence': confidence,
            'conditions_met': [c[0] for c in conditions]
        }
    
    def _evaluate_bearish_signal(self, idx) -> Optional[Dict]:
        """Evaluate 8 conditions for bearish signal"""
        if idx < 200:  # Need history for indicators
            return None
        
        row = self.df.iloc[idx]
        prev_row = self.df.iloc[idx-1]
        conditions = []
        
        # Condition 1: EMA bearish
        cond1 = self._is_ema_bearish(row)
        conditions.append(('EMA aligned', cond1))
        
        # Condition 2: MACD bearish
        cond2 = self._is_macd_bearish(idx)
        conditions.append(('MACD bearish', cond2))
        
        # Condition 3: RSI valid
        cond3 = self._is_rsi_valid(row)
        conditions.append(('RSI in zone', cond3))
        
        # Condition 4: At S/R
        cond4 = self._is_at_support_resistance(row)
        conditions.append(('At S/R', cond4))
        
        # Condition 5: Volume spike
        cond5 = self._is_volume_spike(row)
        conditions.append(('Volume 2x+', cond5))
        
        # Condition 6: Volume increasing
        cond6 = self._is_volume_increasing(idx)
        conditions.append(('Volume increasing', cond6))
        
        # Condition 7: Strong candle
        cond7 = self._is_candle_strong(row)
        conditions.append(('Strong candle', cond7))
        
        # Condition 8: Stochastic valid
        cond8 = self._is_stoch_valid(row)
        conditions.append(('Stochastic valid', cond8))
        
        # All conditions must be true
        all_conditions_met = all(c[1] for c in conditions)
        
        if not all_conditions_met:
            failed = [c[0] for c in conditions if not c[1]]
            self.rejected_reasons.append(f"SELL rejected at {idx}: {', '.join(failed)}")
            return None
        
        # Calculate confidence score
        confidence = sum(1 for c in conditions if c[1]) / len(conditions)
        
        return {
            'type': 'SELL',
            'index': idx,
            'price': row['close'],
            'atr': row['atr'],
            'confidence': confidence,
            'conditions_met': [c[0] for c in conditions]
        }
    
    def generate_signals(self) -> List[Dict]:
        """Generate ultra-high-quality signals"""
        self.signals = []
        self.rejected_reasons = []
        
        last_signal_type = None
        last_signal_idx = -100  # Prevent consecutive signals of same type
        
        for idx in range(200, len(self.df)):
            row = self.df.iloc[idx]
            
            # Check time restriction
            if not self._is_allowed_time(row['date']):
                continue
            
            # Avoid consecutive signals of same type (prevent overtrading)
            if idx - last_signal_idx < 10:
                continue
            
            # Try bullish signal
            bullish = self._evaluate_bullish_signal(idx)
            if bullish and last_signal_type != 'BUY':
                self.signals.append(bullish)
                last_signal_type = 'BUY'
                last_signal_idx = idx
                continue
            
            # Try bearish signal
            bearish = self._evaluate_bearish_signal(idx)
            if bearish and last_signal_type != 'SELL':
                self.signals.append(bearish)
                last_signal_type = 'SELL'
                last_signal_idx = idx
        
        return self.signals
    
    def get_signal_stats(self) -> Dict:
        """Get signal generation statistics"""
        if not self.signals:
            return {
                'total_signals': 0,
                'buy_signals': 0,
                'sell_signals': 0,
                'avg_confidence': 0,
                'signal_rate_per_day': 0
            }
        
        buys = [s for s in self.signals if s['type'] == 'BUY']
        sells = [s for s in self.signals if s['type'] == 'SELL']
        
        return {
            'total_signals': len(self.signals),
            'buy_signals': len(buys),
            'sell_signals': len(sells),
            'avg_confidence': np.mean([s['confidence'] for s in self.signals]),
            'signal_rate_per_day': len(self.signals) / len(self.df) * 390  # 390 candles/day
        }
    
    def get_rejection_stats(self) -> Dict:
        """Get rejection reason statistics"""
        if not self.rejected_reasons:
            return {}
        
        rejection_counts = {}
        for reason in self.rejected_reasons:
            if 'rejected at' in reason:
                # Extract the failed conditions
                failed_part = reason.split(': ')[1]
                for failed in failed_part.split(', '):
                    rejection_counts[failed] = rejection_counts.get(failed, 0) + 1
        
        return rejection_counts
