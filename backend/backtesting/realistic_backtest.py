import pandas as pd
import numpy as np

class RealisticBacktestEngine:
    def __init__(self, initial_capital=10000):
        self.balance = initial_capital
        self.queue_delay_ms = 50 # 50ms simulated network latency
        self.exchange_freeze_prob = 0.001 # 0.1% chance of broker rejection
        self.trades = []

    def simulate_execution(self, price, qty, atr, current_time):
        """Simulate realistic execution with slippage and delay."""
        
        # 1. Queue Delay Simulation
        # In a real move, price might change during the 50ms delay
        # (Simplified as a small random price shift)
        execution_price = price + (np.random.normal(0, 0.0002) * price)
        
        # 2. Slippage Spikes (ATR Based)
        # If ATR is high, slippage increases exponentially
        vol_mult = (atr / price) * 100
        slippage = execution_price * (vol_mult * 0.05) 
        
        final_price = execution_price + slippage
        
        # 3. Broker Rejection Simulation
        if np.random.random() < self.exchange_freeze_prob:
            return None, "Broker Rejection / Exchange Freeze"
            
        return final_price, "Success"

    def run_backtest(self, signals_df):
        """Main backtest loop with realism injected."""
        for i, row in signals_df.iterrows():
            # Add logic to call simulate_execution here
            pass
        return self.trades
