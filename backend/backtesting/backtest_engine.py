import pandas as pd

class BacktestEngine:
    def __init__(self, initial_capital=10000):
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.equity_curve = [initial_capital]
        self.trades = []
        
        # Costs (Approx for Nifty Options)
        self.brokerage_per_order = 20
        self.stt_pct = 0.0005    # 0.05% on sell
        # BE-2 Fix: Asymmetric slippage
        self.entry_slippage_pct = 0.008  # 0.8% on options entry (wide spread at open)
        self.exit_slippage_pct  = 0.003  # 0.3% on options exit
        
    def calculate_costs(self, price, qty, is_buy=True):
        brokerage = self.brokerage_per_order
        slippage = price * qty * (self.entry_slippage_pct if is_buy else self.exit_slippage_pct)
        stt = 0
        if not is_buy:
            stt = price * qty * self.stt_pct
        
        return brokerage + slippage + stt

    def execute_trade(self, entry_price, exit_price, qty, side="BUY", is_expiry=False, underlying_price=0):
        # Entry Costs
        entry_costs = self.calculate_costs(entry_price, qty, is_buy=(side=="BUY"))
        
        # Exit Costs
        exit_costs = self.calculate_costs(exit_price, qty, is_buy=(side=="SELL"))
        
        # BE-1 Fix: ITM expiry STT trap
        if is_expiry and exit_price > 0 and underlying_price > 0:
            stt_trap = underlying_price * qty * 0.00125
            exit_costs += stt_trap
        
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
        
        # BE-3 Fix: Add Profit Factor, Expectancy, Sharpe Ratio
        winners = df[df['net_pnl'] > 0]
        losers  = df[df['net_pnl'] <= 0]
        
        avg_win  = winners['net_pnl'].mean() if not winners.empty else 0
        avg_loss = abs(losers['net_pnl'].mean()) if not losers.empty else 0
        win_rate_decimal = len(winners) / len(df)
        
        expectancy = (win_rate_decimal * avg_win) - ((1 - win_rate_decimal) * avg_loss)
        profit_factor = winners['net_pnl'].sum() / abs(losers['net_pnl'].sum()) if not losers.empty else float('inf')
        
        # Sharpe (simplified, assumes daily trades)
        daily_pnl = df['net_pnl']
        sharpe = (daily_pnl.mean() / daily_pnl.std() * (252 ** 0.5)) if daily_pnl.std() > 0 else 0
        
        return {
            'Total PnL': total_pnl,
            'Win Rate (%)': win_rate,
            'Profit Factor': round(profit_factor, 2),
            'Expectancy (Rs.)': round(expectancy, 2),
            'Sharpe Ratio': round(sharpe, 2),
            'Max Drawdown (%)': max_drawdown,
            'Total Trades': len(df),
            'Avg PnL per Trade': total_pnl / len(df)
        }

    def export_trades_csv(self, path):
        """Export executed trades to a CSV file at `path`. Overwrites if exists."""
        import csv
        if not self.trades:
            return False
        keys = list(self.trades[0].keys())
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=keys)
                writer.writeheader()
                for t in self.trades:
                    writer.writerow(t)
            return True
        except Exception:
            return False

    def export_metrics_csv(self, path):
        """Export summarized metrics to CSV (single-row)."""
        import csv
        metrics = self.get_metrics()
        if isinstance(metrics, str):
            return False
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['metric', 'value'])
                for k, v in metrics.items():
                    writer.writerow([k, v])
            return True
        except Exception:
            return False

    def calculate_max_drawdown(self):
        equity_series = pd.Series(self.equity_curve)
        rolling_max = equity_series.cummax()
        drawdown = (equity_series - rolling_max) / rolling_max
        return drawdown.min() * 100
