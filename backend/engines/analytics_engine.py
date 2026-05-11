import pandas as pd
import json
import os

class AnalyticsEngine:
    def __init__(self, log_path="d:/QuantumIndex/logs/trade_journal.json"):
        self.log_path = log_path
        self.journal = self.load_journal()

    def load_journal(self):
        if os.path.exists(self.log_path):
            with open(self.log_path, 'r') as f:
                return json.load(f)
        return []

    def log_trade(self, trade_data):
        """Store detailed trade metrics."""
        self.journal.append(trade_data)
        with open(self.log_path, 'w') as f:
            json.dump(self.journal, f, indent=4)

    def generate_report(self):
        if not self.journal: return "No trades logged."
        
        df = pd.DataFrame(self.journal)
        
        # Calculate Stats
        total_trades = len(df)
        win_rate = (len(df[df['net_pnl'] > 0]) / total_trades) * 100
        profit_factor = abs(df[df['net_pnl'] > 0]['net_pnl'].sum() / df[df['net_pnl'] < 0]['net_pnl'].sum())
        
        best_setup = df.groupby('setup_type')['net_pnl'].sum().idxmax()
        worst_session = df.groupby('session')['net_pnl'].sum().idxmin()
        
        return {
            'Win Rate (%)': round(win_rate, 2),
            'Profit Factor': round(profit_factor, 2),
            'Total PnL': round(df['net_pnl'].sum(), 2),
            'Best Setup': best_setup,
            'Worst Session': worst_session,
            'Avg RR': round(df['rr'].mean(), 2)
        }
