import time
from backend.engines.structure_engine import StructureEngine
from backend.engines.signal_engine import SignalEngine
from backend.engines.risk_engine import RiskEngine
from backend.engines.execution_engine import ExecutionEngine
from backend.engines.analytics_engine import AnalyticsEngine

class QuantumIndexMain:
    def __init__(self):
        self.structure = StructureEngine()
        self.signal = SignalEngine()
        self.risk = RiskEngine()
        self.execution = ExecutionEngine()
        self.analytics = AnalyticsEngine()
        
        self.state = "SCANNING" # SCANNING, WAITING_FOR_RETEST, IN_TRADE
        self.current_signal = None

    def run_iteration(self, htf_df, mtf_df, ltf_df, daily_data, session_info):
        """Single loop iteration for real-time trading."""
        
        # 1. Check if trading is allowed today
        can_trade, reason = self.risk.can_trade()
        if not can_trade:
            print(f"Risk Block: {reason}")
            return

        # 2. State-based Logic
        if self.state == "SCANNING":
            # Detect Structure & Signal
            struct_data = self.structure.analyze(mtf_df)
            eval_data = self.signal.evaluate(htf_df, mtf_df, struct_data, daily_data, session_info)
            
            if eval_data['side']:
                print(f"Signal Found: {eval_data['side']} | Score: {eval_data['score']}")
                self.current_signal = eval_data
                self.state = "WAITING_FOR_RETEST"

        elif self.state == "WAITING_FOR_RETEST":
            # Check for FVG Retest on 1M (LTF)
            current_price = ltf_df['close'].iloc[-1]
            struct_data = self.structure.analyze(mtf_df) # Refresh FVG
            
            if self.execution.check_fvg_retest(current_price, struct_data['fvgs'], self.current_signal['side']):
                print("FVG Retest Confirmed. Entering Trade.")
                self.enter_trade(current_price)
                self.state = "IN_TRADE"

        elif self.state == "IN_TRADE":
            # Manage Exit
            if self.execution.check_time_exit():
                self.exit_trade("Time-based Exit")
            # Additional logic for Trailing SL and Targets would go here

    def enter_trade(self, price):
        # Calculate Qty based on dynamic risk (₹100 or ₹50)
        risk_amt = self.risk.get_current_risk()
        # In real life, call Broker API here
        self.execution.entry_time = time.time()
        print(f"Entered Trade at {price} with risk ₹{risk_amt}")

    def exit_trade(self, reason):
        pnl = 0 # Calculate actual PnL here
        self.risk.update_pnl(pnl)
        self.analytics.log_trade({
            "setup": self.current_signal,
            "pnl": pnl,
            "reason": reason,
            "timestamp": time.time()
        })
        self.execution.reset()
        self.state = "SCANNING"
        print(f"Trade Closed: {reason}")

if __name__ == "__main__":
    # Example initialization
    engine = QuantumIndexMain()
    # In production, this would be inside a WebSocket or polling loop
    print("QuantumIndex Main Engine Initialized.")

