import pandas as pd

class BacktestEngine:
    def __init__(self, initial_capital=10000):
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.equity_curve = [initial_capital]
        self.trades = []
        
        # Costs (Approx for Nifty Options)
        self.brokerage_per_order = 20
        self.slippage_pct = 0.001 # 0.1% slippage
        self.stt_pct = 0.0005    # 0.05% on sell
        
    def calculate_costs(self, price, qty, is_buy=True):
        brokerage = self.brokerage_per_order
        slippage = price * qty * self.slippage_pct
        stt = 0
        if not is_buy:
            stt = price * qty * self.stt_pct
        
        return brokerage + slippage + stt

    def execute_trade(self, entry_price, exit_price, qty, side="BUY"):
        # Entry Costs
        entry_costs = self.calculate_costs(entry_price, qty, is_buy=(side=="BUY"))
        
        # Exit Costs
        exit_costs = self.calculate_costs(exit_price, qty, is_buy=(side=="SELL"))
        
        # Gross PnL
        if side == "BUY":
            gross_pnl = (exit_price - entry_price) * qty
        else:
            gross_pnl = (entry_price - exit_price) * qty
            
        # Net PnL
        net_pnl = gross_pnl - entry_costs - exit_costs
        
        self.balance += net_pnl
        self.equity_curve.append(self.balance)
        
        self.trades.append({
            'side': side,
            'entry': entry_price,
            'exit': exit_price,
            'qty': qty,
            'net_pnl': net_pnl,
            'costs': entry_costs + exit_costs
        })
        
        return net_pnl

    def get_metrics(self):
        if not self.trades:
            return "No trades executed."
            
        df = pd.DataFrame(self.trades)
        win_rate = (len(df[df['net_pnl'] > 0]) / len(df)) * 100
        total_pnl = df['net_pnl'].sum()
        max_drawdown = self.calculate_max_drawdown()
        
        return {
            'Total PnL': total_pnl,
            'Win Rate (%)': win_rate,
            'Max Drawdown (%)': max_drawdown,
            'Total Trades': len(df),
            'Avg PnL per Trade': total_pnl / len(df)
        }

    def calculate_max_drawdown(self):
        equity_series = pd.Series(self.equity_curve)
        rolling_max = equity_series.cummax()
        drawdown = (equity_series - rolling_max) / rolling_max
        return drawdown.min() * 100
