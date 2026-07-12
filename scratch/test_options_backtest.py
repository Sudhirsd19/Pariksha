import os, sys, time
import pandas as pd
import numpy as np
import yfinance as yf

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from backend.backtesting.balanced_quality_engine import BalancedQualityEngine
from backend.backtesting.ultra_high_quality_engine import UltraHighQualitySignalEngine
from backend.backtesting.test_with_yfinance import prepare_data_for_backtest

class OptionsBacktestEngine:
    def __init__(self, initial_capital=100000):
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.equity_curve = [initial_capital]
        self.trades = []
        
    def run_options_backtest(self, df, symbol, signals, capital_per_trade=10000.0, atr_sl=2.5, atr_tp=5.0):
        """
        Runs a high-fidelity options premium backtest using spot index candles and delta-adjusted tracking.
        """
        self.balance = self.initial_capital
        self.equity_curve = [self.initial_capital]
        self.trades = []
        
        lot_size = 25 if symbol == "NIFTY" else 15
        ATM_DELTA = 0.45
        
        # Mark signals
        df_run = df.copy()
        df_run['signal'] = None
        for s in signals:
            df_run.at[s['index'], 'signal'] = s['type']
            
        open_trade = None
        trades_today = 0
        last_date = None
        
        for i in range(100, len(df_run)):
            row = df_run.iloc[i]
            current_time = row['date']
            current_price = float(row['close'])
            current_high = float(row['high'])
            current_low = float(row['low'])
            
            # Daily reset
            current_date = str(current_time).split(' ')[0]
            if current_date != last_date:
                trades_today = 0
                last_date = current_date
                
            # Check auto-squareoff (3:10 PM IST)
            is_squareoff_time = False
            try:
                dt = pd.to_datetime(current_time)
                if dt.hour > 15 or (dt.hour == 15 and dt.minute >= 10):
                    is_squareoff_time = True
            except:
                pass
                
            # ========== MANAGE OPEN TRADE ==========
            if open_trade:
                # EOD squareoff
                if is_squareoff_time:
                    # Final value of option premium at close
                    if open_trade['type'] == 'BUY':
                        final_premium = open_trade['entry_premium'] + (current_price - open_trade['underlying_entry']) * ATM_DELTA
                    else:
                        final_premium = open_trade['entry_premium'] + (open_trade['underlying_entry'] - current_price) * ATM_DELTA
                        
                    final_premium = max(1.0, final_premium)
                    self._close_option_trade(open_trade, final_premium, current_time, "Intraday Auto-Squareoff")
                    open_trade = None
                    continue
                
                # Check intra-candle premium fluctuations
                if open_trade['type'] == 'BUY':  # Call Option
                    max_premium = open_trade['entry_premium'] + (current_high - open_trade['underlying_entry']) * ATM_DELTA
                    min_premium = open_trade['entry_premium'] + (current_low - open_trade['underlying_entry']) * ATM_DELTA
                else:  # Put Option
                    max_premium = open_trade['entry_premium'] + (open_trade['underlying_entry'] - current_low) * ATM_DELTA
                    min_premium = open_trade['entry_premium'] + (open_trade['underlying_entry'] - current_high) * ATM_DELTA
                
                # Apply Trailing SL / Break-even
                tp_dist = open_trade['premium_tp'] - open_trade['entry_premium']
                current_max_profit = max_premium - open_trade['entry_premium']
                
                # 50% target progress -> Move SL to break-even
                if current_max_profit >= (tp_dist * 0.5) and open_trade['premium_sl'] < open_trade['entry_premium']:
                    open_trade['premium_sl'] = open_trade['entry_premium']
                    
                # 70% target progress -> Trail SL
                if current_max_profit >= (tp_dist * 0.7):
                    new_sl = max_premium - (open_trade['atr'] * ATM_DELTA * 0.5)
                    if new_sl > open_trade['premium_sl']:
                        open_trade['premium_sl'] = round(new_sl, 2)
                        
                # Check exit conditions
                sl_hit = min_premium <= open_trade['premium_sl']
                tp_hit = max_premium >= open_trade['premium_tp']
                sl_in_profit = open_trade['premium_sl'] >= open_trade['entry_premium']
                
                if sl_hit and tp_hit:
                    # Prefer TP if SL is in profit zone, else SL
                    exit_reason = "TP Hit" if sl_in_profit else "SL Hit"
                    exit_premium = open_trade['premium_tp'] if sl_in_profit else open_trade['premium_sl']
                    self._close_option_trade(open_trade, exit_premium, current_time, exit_reason)
                    open_trade = None
                elif tp_hit:
                    self._close_option_trade(open_trade, open_trade['premium_tp'], current_time, "TP Hit")
                    open_trade = None
                elif sl_hit:
                    reason = "Trailing SL Hit" if sl_in_profit else "SL Hit"
                    self._close_option_trade(open_trade, open_trade['premium_sl'], current_time, reason)
                    open_trade = None
                continue
                
            # ========== LOOK FOR NEW ENTRY ==========
            if not open_trade and not is_squareoff_time:
                signal = row.get('signal')
                if signal in ['BUY', 'SELL']:
                    # Calculate ATR
                    history_df = df_run.iloc[max(0, i-300):i+1].copy()
                    atr = self._calculate_atr(history_df)
                    if atr == 0:
                        atr = current_price * 0.005
                        
                    # Calculate strike and premium
                    strike = int(round(current_price / (50.0 if symbol == "NIFTY" else 100.0)) * (50.0 if symbol == "NIFTY" else 100.0))
                    # Estimate ATM premium as 0.75% of index price
                    entry_premium = round(current_price * 0.0075, 2)
                    
                    # Position sizing
                    lots = int(capital_per_trade / (entry_premium * lot_size))
                    if lots <= 0:
                        lots = 1
                    qty = lots * lot_size
                    
                    sl_dist = atr * atr_sl
                    tp_dist = atr * atr_tp
                    
                    premium_sl = round(max(entry_premium * 0.5, entry_premium - sl_dist * ATM_DELTA), 2)
                    premium_tp = round(entry_premium + tp_dist * ATM_DELTA, 2)
                    
                    open_trade = {
                        'type': signal,
                        'symbol': f"{symbol} CE" if signal == 'BUY' else f"{symbol} PE",
                        'strike': strike,
                        'entry_time': current_time,
                        'underlying_entry': current_price,
                        'entry_premium': entry_premium,
                        'qty': qty,
                        'lots': lots,
                        'premium_sl': premium_sl,
                        'premium_tp': premium_tp,
                        'atr': atr
                    }
                    trades_today += 1
                    
        return self._generate_report()

    def _close_option_trade(self, trade, exit_premium, exit_time, reason):
        # Transaction costs for options trading: flat Rs.20 per order + GST + STT on Sell premium
        brokerage = 20.0 * 2  # round-trip
        gst = brokerage * 0.18
        
        # STT is 0.0625% on sell side option premium turnover (NFO Options)
        stt = (exit_premium * trade['qty']) * 0.000625
        
        total_costs = brokerage + gst + stt
        
        gross_pnl = (exit_premium - trade['entry_premium']) * trade['qty']
        net_pnl = gross_pnl - total_costs
        
        self.balance += net_pnl
        self.equity_curve.append(self.balance)
        
        self.trades.append({
            'type': trade['type'],
            'symbol': trade['symbol'],
            'lots': trade['lots'],
            'qty': trade['qty'],
            'entry_time': trade['entry_time'],
            'exit_time': exit_time,
            'underlying_entry': trade['underlying_entry'],
            'entry_premium': trade['entry_premium'],
            'exit_premium': exit_premium,
            'net_pnl': net_pnl,
            'costs': total_costs,
            'reason': reason
        })
        
    def _calculate_atr(self, df, period=14):
        try:
            high_low = df['high'] - df['low']
            high_close = (df['high'] - df['close'].shift()).abs()
            low_close = (df['low'] - df['close'].shift()).abs()
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            atr = tr.rolling(period).mean().iloc[-1]
            return atr if not pd.isna(atr) else 0
        except:
            return 0
            
    def _generate_report(self):
        if not self.trades:
            return {
                "total_trades": 0,
                "win_rate": 0,
                "net_profit": 0,
                "net_profit_pct": 0,
                "profit_factor": 0,
                "trades": []
            }
            
        df_trades = pd.DataFrame(self.trades)
        wins = df_trades[df_trades['net_pnl'] > 0]
        losses = df_trades[df_trades['net_pnl'] <= 0]
        
        total = len(df_trades)
        win_rate = (len(wins) / total) * 100
        net_profit = self.balance - self.initial_capital
        
        gross_profit = wins['net_pnl'].sum() if not wins.empty else 0
        gross_loss = abs(losses['net_pnl'].sum()) if not losses.empty else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        return {
            "total_trades": total,
            "win_rate": round(win_rate, 1),
            "net_profit": round(net_profit, 0),
            "net_profit_pct": round((net_profit / self.initial_capital) * 100, 2),
            "profit_factor": round(profit_factor, 2),
            "trades": self.trades
        }

def test_engine(df, symbol, engine_class, name, atr_sl, atr_tp):
    engine = engine_class(df)
    signals = engine.generate_signals()
    
    print(f"\n-------------------------------------------------------")
    print(f"  {name} (Signals: {len(signals)})")
    print(f"-------------------------------------------------------")
    
    backtester = OptionsBacktestEngine(initial_capital=100000)
    report = backtester.run_options_backtest(df, symbol, signals, capital_per_trade=10000, atr_sl=atr_sl, atr_tp=atr_tp)
    
    print(f"  Total Trades:  {report['total_trades']}")
    print(f"  Win Rate:      {report['win_rate']}%")
    print(f"  Profit Factor: {report['profit_factor']}")
    print(f"  Net Return:    Rs. {report['net_profit']} ({report['net_profit_pct']}%)")
    
    if report['trades']:
        print(f"\n  Recent Trades (Max 5):")
        for i, t in enumerate(report['trades'][-5:]):
            icon = "✅" if t['net_pnl'] > 0 else "❌"
            print(f"    {t['entry_time']} | {t['type']} | Prem Entry: {t['entry_premium']:.2f} -> Exit: {t['exit_premium']:.2f} | "
                  f"Net PnL: Rs. {t['net_pnl']:.0f} {icon} | Reason: {t['reason']}")

def main():
    symbol = "NIFTY"
    print(f"Downloading 60 days of 5m data for {symbol} index...")
    ticker = yf.Ticker("^NSEI")
    data = ticker.history(period="60d", interval="5m")
    if data.empty:
        print("Failed to download NIFTY data.")
        return
        
    df = prepare_data_for_backtest(data)
    print(f"Data ready: {len(df)} candles.")
    
    # 1. Balanced Quality Engine
    test_engine(df, "NIFTY", BalancedQualityEngine, "Balanced Quality Engine (Medium - 65%)", atr_sl=2.5, atr_tp=3.0)
    
    # 2. Ultra-High Quality Engine
    test_engine(df, "NIFTY", UltraHighQualitySignalEngine, "Ultra-High Quality Engine (Strict - 70%+)", atr_sl=2.5, atr_tp=2.0)

if __name__ == '__main__':
    main()
