from abc import ABC, abstractmethod
import logging

class BrokerBase(ABC):
    @abstractmethod
    def get_positions(self): pass
    @abstractmethod
    def place_order(self, order_data): pass
    @abstractmethod
    def cancel_all_orders(self): pass

class ReconciliationEngine:
    def __init__(self, broker: BrokerBase):
        self.broker = broker
        self.last_sync_status = True

    def reconcile(self, local_positions):
        """Phase 1: Compare local engine state vs actual broker state."""
        try:
            broker_positions = self.broker.get_positions()
            
            for symbol, local_qty in local_positions.items():
                broker_qty = broker_positions.get(symbol, 0)
                
                if local_qty != broker_qty:
                    logging.critical(f"RECONCILIATION MISMATCH: {symbol} | Local: {local_qty} | Broker: {broker_qty}")
                    return False, f"Mismatch in {symbol}"
            
            # Detect Ghost Orders (Positions on broker not in local)
            for symbol in broker_positions:
                if symbol not in local_positions and broker_positions[symbol] != 0:
                    logging.critical(f"GHOST ORDER DETECTED: {symbol} on Broker")
                    return False, "Ghost Position Found"
            
            return True, "Reconciled"
            
        except Exception as e:
            logging.error(f"Reconciliation Failed: {str(e)}")
            return False, "API Error"

    def emergency_recovery(self):
        """Hard Stop: Close all broker positions and cancel orders."""
        logging.warning("TRIGGERING EMERGENCY BROKER RECOVERY...")
        self.broker.cancel_all_orders()
        # In a real scenario, this would also flatten all positions
