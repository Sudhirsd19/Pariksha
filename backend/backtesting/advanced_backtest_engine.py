"""
Advanced Backtesting Engine v2.0
With realistic slippage, commission, risk management, and comprehensive metrics
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

class AdvancedBacktestEngine:
    """
    Enhanced backtest engine with:
    1. Realistic slippage & commission modeling
    2. Risk-per-trade & position-sizing rules
    3. Comprehensive metrics (Sharpe, Sortino, Profit Factor)
    4. Trade logs & detailed reporting
    5. Seed-based reproducibility
    """
    
    def __init__(self, initial_capital=100000, seed=42):
        np.random.seed(seed)
        self.seed = seed
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.equity_curve = [initial_capital]
        self.trades = []
        self.daily_pnl = {}
        
        # Realistic costs for intraday equity trading (NSE)
        self.brokerage_pct = 0.0003  # 0.03% (capped at ₹20)
        self.brokerage_max = 20      # Capped at ₹20 per executed order
        self.stt_pct = 0.00025  # 0.025% on sell (NSE intraday equity)
        self.gst_pct = 0.18  # 18% GST on brokerage
        
        # Slippage (depends on liquidity - RELIANCE has good liquidity)
        self.entry_slippage_bps = 1.5  # 1.5 bps (0.015%) for entry
        self.exit_slippage_bps = 1.5   # 1.5 bps for exit
        self.slippage_volatility_multiplier = 1.2  # Increase in low-volume candles
        
        # Risk management parameters (will be optimized)
        self.risk_per_trade_pct = 0.02  # Default 2% risk per trade
        self.atr_multiplier_sl = 1.5
        self.atr_multiplier_tp = 3.0
        self.max_daily_loss_pct = 0.05  # 5% daily loss limit
        self.max_open_positions = 1
        
    def calculate_slippage(self, price, qty, volume_context, is_entry=True):
        """
        Calculate realistic slippage based on:
        - Order size relative to volume
        - Bid-ask spread (estimated from volatility)
        - Time of day (morning vs afternoon)
        """
        if volume_context is None or volume_context == 0:
            volume_context = 100000  # Default safe estimate
        
        # Base slippage
        slippage_bps = self.entry_slippage_bps if is_entry else self.exit_slippage_bps
        
        # Adjust for order size relative to volume
        order_size_ratio = (price * qty) / volume_context
        if order_size_ratio > 0.1:  # Large relative order
            slippage_bps *= 2
        elif order_size_ratio > 0.05:
            slippage_bps *= 1.5
        
        slippage_amount = price * qty * (slippage_bps / 10000)
        return slippage_amount
    
    def calculate_commission(self, price, qty, is_buy=True):
        """Calculate realistic commission (brokerage + STT + GST)"""
        trade_value = price * qty
        
        # Brokerage (0.03% or ₹20, whichever is lower)
        brokerage = min(trade_value * self.brokerage_pct, self.brokerage_max)
        
        # GST on brokerage
        gst = brokerage * self.gst_pct
        
        # STT (only on sell)
        stt = trade_value * self.stt_pct if not is_buy else 0
        
        total_commission = brokerage + gst + stt
        return total_commission
    
    def calculate_effective_price(self, price, qty, volume_context, is_buy=True, is_entry=True):
        """Calculate entry/exit price after slippage"""
        slippage = self.calculate_slippage(price, qty, volume_context, is_entry)
        
        if is_buy:
            return price + (slippage / qty)
        else:
            return price - (slippage / qty)
    
    def run_backtest(self, df, htf_trend="BULLISH", risk_per_trade=0.02, atr_sl=1.5, atr_tp=3.0):
        """
        Run backtest with all improvements
        
        Args:
            df: DataFrame with OHLCV data + 'signal' column
            htf_trend: "BULLISH", "BEARISH", or "NEUTRAL"
            risk_per_trade: Risk as % of capital (0.02 = 2%)
            atr_sl: ATR multiplier for stop loss
            atr_tp: ATR multiplier for take profit
        """
        print(f"Running advanced backtest on {len(df)} candles...")
        print(f"Risk per trade: {risk_per_trade*100:.1f}% | SL: {atr_sl}x ATR | TP: {atr_tp}x ATR")
        
        self.balance = self.initial_capital
        self.equity_curve = [self.initial_capital]
        self.trades = []
        self.daily_pnl = {}
        self.risk_per_trade_pct = risk_per_trade
        self.atr_multiplier_sl = atr_sl
        self.atr_multiplier_tp = atr_tp
        
        open_trade = None
        last_date = None
        daily_loss = 0
        trades_today = 0
        warmup_period = 100
        
        for i in range(warmup_period, len(df)):
            current_row = df.iloc[i]
            current_price = float(current_row['close'])
            current_high = float(current_row['high'])
            current_low = float(current_row['low'])
            current_volume = float(current_row.get('volume', 100000))
            current_time = current_row['time']
            
            # Reset daily metrics
            current_date = str(current_time).split(' ')[0]
            if current_date != last_date:
                daily_loss = 0
                trades_today = 0
                last_date = current_date
            
            # Check for intraday auto-squareoff (3:10 PM IST to match live system)
            is_squareoff_time = False
            try:
                dt = pd.to_datetime(current_time)
                if dt.hour > 15 or (dt.hour == 15 and dt.minute >= 10):
                    is_squareoff_time = True
            except:
                pass
            
            # ========== MANAGE EXISTING TRADE ==========
            if open_trade:
                # Force exit if it is end of day (auto-squareoff)
                if is_squareoff_time:
                    prev_balance = self.balance
                    self._close_trade(
                        open_trade, current_price, current_time, 
                        "Intraday Auto-Squareoff", current_volume
                    )
                    daily_loss += (self.balance - prev_balance)
                    open_trade = None
                    continue

                self._update_trailing_sl(open_trade, current_price)

                exit_signal = self._check_exit_conditions(
                    open_trade, current_high, current_low, current_price, current_time
                )
                
                if exit_signal:
                    prev_balance = self.balance
                    self._close_trade(
                        open_trade, exit_signal['price'], current_time, 
                        exit_signal['reason'], current_volume
                    )
                    daily_loss += (self.balance - prev_balance)
                    open_trade = None
                    continue
            
            # ========== LOOK FOR NEW ENTRY ==========
            if not open_trade and trades_today < self.max_open_positions:
                # Skip opening new trades if we are in squareoff window
                if is_squareoff_time:
                    continue

                # Check daily loss limit
                if daily_loss < -self.initial_capital * self.max_daily_loss_pct:
                    continue  # Skip trading for rest of day
                
                # Check if signal exists
                signal = current_row.get('signal', None)
                if not signal or signal not in ["BUY", "SELL"]:
                    continue
                
                # Calculate position size with ATR-based risk
                history_df = df.iloc[max(0, i-300):i+1].copy()
                atr = self._calculate_atr(history_df, period=14)
                
                if atr == 0 or pd.isna(atr):
                    atr = current_price * 0.01  # Fallback to 1%
                
                # Risk-based position sizing
                risk_amount = self.balance * self.risk_per_trade_pct
                sl_dist = atr * self.atr_multiplier_sl
                qty = int(risk_amount / sl_dist)
                
                # Capital constraint
                entry_price_effective = self.calculate_effective_price(
                    current_price, qty, current_volume, 
                    is_buy=(signal == "BUY"), is_entry=True
                )
                required_capital = entry_price_effective * qty
                
                if required_capital > self.balance * 0.9:  # Use max 90% of capital
                    qty = int(self.balance * 0.9 / entry_price_effective)
                
                if qty <= 0:
                    continue
                
                # Calculate SL & TP
                sl = current_price - (atr * self.atr_multiplier_sl) if signal == "BUY" else current_price + (atr * self.atr_multiplier_sl)
                tp = current_price + (atr * self.atr_multiplier_tp) if signal == "BUY" else current_price - (atr * self.atr_multiplier_tp)
                
                # Open trade
                open_trade = {
                    "type": signal,
                    "entry_time": current_time,
                    "entry_price": current_price,
                    "entry_price_effective": entry_price_effective,
                    "qty": qty,
                    "sl": sl,
                    "tp": tp,
                    "atr": atr,
                    "entry_volume": current_volume
                }
                trades_today += 1
        
        # Close any remaining open trade
        if open_trade:
            last_price = df.iloc[-1]['close']
            last_volume = df.iloc[-1].get('volume', 100000)
            self._close_trade(open_trade, last_price, df.iloc[-1]['time'], "End of backtest", last_volume)
        
        return self._generate_comprehensive_report()
    
    def _update_trailing_sl(self, trade, current_price):
        """Implement the exact trailing stop-loss and break-even logic from trade_manager.py"""
        entry = trade['entry_price']
        sl = trade['sl']
        tp = trade['tp']
        atr = trade.get('atr', 0)
        
        if trade['type'] == 'BUY':
            tp_distance = tp - entry
            current_profit = current_price - entry
            
            # Step 1: Move SL to exact break-even at 50% target progress (1:1 RR)
            if current_profit >= (tp_distance * 0.5) and sl < entry:
                trade['sl'] = entry
                
            # Step 2: Trail SL at 70% target progress
            if current_profit >= (tp_distance * 0.7):
                atr_trail = atr if atr > 0 else (tp_distance * 0.3)
                new_sl = current_price - (atr_trail * 0.5)
                if new_sl > trade['sl']:
                    trade['sl'] = round(new_sl, 2)
                    
        elif trade['type'] == 'SELL':
            tp_distance = entry - tp
            current_profit = entry - current_price
            
            # Step 1: Move SL to exact break-even at 50% target progress (1:1 RR)
            if current_profit >= (tp_distance * 0.5) and sl > entry:
                trade['sl'] = entry
                
            # Step 2: Trail SL at 70% target progress
            if current_profit >= (tp_distance * 0.7):
                atr_trail = atr if atr > 0 else (tp_distance * 0.3)
                new_sl = current_price + (atr_trail * 0.5)
                if new_sl < trade['sl']:
                    trade['sl'] = round(new_sl, 2)

    def _calculate_atr(self, df, period=14):
        """Calculate Average True Range"""
        try:
            high_low = df['high'] - df['low']
            high_close = (df['high'] - df['close'].shift()).abs()
            low_close = (df['low'] - df['close'].shift()).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(period).mean().iloc[-1]
            return atr if not pd.isna(atr) else 0
        except:
            return 0
    
    def _check_exit_conditions(self, trade, high, low, current_price, current_time):
        """Check if SL or TP is hit"""
        if trade['type'] == "BUY":
            if low <= trade['sl']:
                return {
                    'price': trade['sl'],
                    'reason': 'SL Hit'
                }
            elif high >= trade['tp']:
                return {
                    'price': trade['tp'],
                    'reason': 'TP Hit'
                }
        else:  # SELL
            if high >= trade['sl']:
                return {
                    'price': trade['sl'],
                    'reason': 'SL Hit'
                }
            elif low <= trade['tp']:
                return {
                    'price': trade['tp'],
                    'reason': 'TP Hit'
                }
        
        return None
    
    def _close_trade(self, trade, exit_price, exit_time, exit_reason, exit_volume):
        """Close a trade and record it"""
        # Calculate costs
        entry_commission = self.calculate_commission(
            trade['entry_price_effective'], trade['qty'], is_buy=(trade['type'] == "BUY")
        )
        
        # Exit price with slippage
        exit_price_effective = self.calculate_effective_price(
            exit_price, trade['qty'], exit_volume,
            is_buy=(trade['type'] == "SELL"), is_entry=False
        )
        
        exit_commission = self.calculate_commission(
            exit_price_effective, trade['qty'], is_buy=(trade['type'] == "SELL")
        )
        
        # Calculate gross PnL
        if trade['type'] == "BUY":
            gross_pnl = (exit_price_effective - trade['entry_price_effective']) * trade['qty']
        else:
            gross_pnl = (trade['entry_price_effective'] - exit_price_effective) * trade['qty']
        
        # Net PnL after all costs
        net_pnl = gross_pnl - entry_commission - exit_commission
        
        # Record trade
        trade_record = {
            'entry_time': trade['entry_time'],
            'exit_time': exit_time,
            'type': trade['type'],
            'entry_price': trade['entry_price'],
            'entry_price_effective': trade['entry_price_effective'],
            'exit_price': exit_price,
            'exit_price_effective': exit_price_effective,
            'qty': trade['qty'],
            'sl': trade['sl'],
            'tp': trade['tp'],
            'gross_pnl': gross_pnl,
            'entry_commission': entry_commission,
            'exit_commission': exit_commission,
            'net_pnl': net_pnl,
            'exit_reason': exit_reason,
            'atr': trade['atr'],
            'duration_candles': 0  # To be calculated
        }
        
        self.balance += net_pnl
        self.equity_curve.append(self.balance)
        self.trades.append(trade_record)
    
    def _generate_comprehensive_report(self):
        """Generate detailed backtest report with advanced metrics"""
        if not self.trades:
            return self._empty_report()
        
        df_trades = pd.DataFrame(self.trades)
        
        # Basic metrics
        total_trades = len(df_trades)
        winning_trades = df_trades[df_trades['net_pnl'] > 0]
        losing_trades = df_trades[df_trades['net_pnl'] <= 0]
        
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
        gross_profit = winning_trades['net_pnl'].sum()
        gross_loss = losing_trades['net_pnl'].sum()
        net_profit = self.balance - self.initial_capital
        
        # Advanced metrics
        avg_win = winning_trades['net_pnl'].mean() if not winning_trades.empty else 0
        avg_loss = abs(losing_trades['net_pnl'].mean()) if not losing_trades.empty else 0
        
        # Profit factor
        profit_factor = gross_profit / abs(gross_loss) if gross_loss != 0 else float('inf')
        
        # Expectancy
        win_rate_decimal = len(winning_trades) / total_trades if total_trades > 0 else 0
        expectancy = (win_rate_decimal * avg_win) - ((1 - win_rate_decimal) * avg_loss)
        
        # Sharpe ratio (simplified)
        returns = df_trades['net_pnl'].values
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252)
        else:
            sharpe = 0
        
        # Sortino ratio (downside deviation)
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0 and np.std(downside_returns) > 0:
            sortino = (np.mean(returns) / np.std(downside_returns)) * np.sqrt(252)
        else:
            sortino = sharpe  # Fallback to Sharpe if no losing trades
        
        # Max drawdown
        peak = self.initial_capital
        max_dd = 0
        for balance in self.equity_curve:
            if balance > peak:
                peak = balance
            dd = (peak - balance) / peak * 100
            if dd > max_dd:
                max_dd = dd
        
        # Recovery factor
        recovery_factor = net_profit / abs(max_dd * self.initial_capital / 100) if max_dd > 0 else float('inf')
        
        # Consecutive wins/losses
        pnl_series = df_trades['net_pnl'].values
        win_streak = max_loss_streak = current_streak = 0
        for pnl in pnl_series:
            if pnl > 0:
                current_streak = current_streak + 1 if current_streak >= 0 else 1
            else:
                current_streak = current_streak - 1 if current_streak <= 0 else -1
            
            win_streak = max(win_streak, current_streak)
            max_loss_streak = max(max_loss_streak, abs(current_streak))
        
        return {
            "initial_capital": self.initial_capital,
            "final_balance": self.balance,
            "net_profit": net_profit,
            "net_profit_pct": (net_profit / self.initial_capital) * 100,
            "total_trades": total_trades,
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "expectancy": expectancy,
            "sharpe_ratio": sharpe,
            "sortino_ratio": sortino,
            "max_drawdown_pct": max_dd,
            "recovery_factor": recovery_factor,
            "longest_win_streak": win_streak,
            "longest_loss_streak": max_loss_streak,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "total_commission": df_trades['entry_commission'].sum() + df_trades['exit_commission'].sum(),
            "seed": self.seed,
            "trades": self.trades
        }
    
    def _empty_report(self):
        """Return empty report if no trades"""
        return {
            "initial_capital": self.initial_capital,
            "final_balance": self.initial_capital,
            "net_profit": 0,
            "net_profit_pct": 0,
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "profit_factor": 0,
            "expectancy": 0,
            "sharpe_ratio": 0,
            "sortino_ratio": 0,
            "max_drawdown_pct": 0,
            "recovery_factor": 0,
            "longest_win_streak": 0,
            "longest_loss_streak": 0,
            "gross_profit": 0,
            "gross_loss": 0,
            "total_commission": 0,
            "seed": self.seed,
            "trades": []
        }
    
    def export_trade_log(self, filepath):
        """Export detailed trade log to CSV"""
        if not self.trades:
            return False
        
        df = pd.DataFrame(self.trades)
        df.to_csv(filepath, index=False)
        return True
    
    def export_equity_curve(self, filepath):
        """Export equity curve"""
        df = pd.DataFrame({
            'candle': range(len(self.equity_curve)),
            'balance': self.equity_curve
        })
        df.to_csv(filepath, index=False)
        return True
