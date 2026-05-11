import logging
import os
from datetime import datetime

class QuantumLogger:
    def __init__(self, name="QuantumIndex"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        if not os.path.exists("logs"):
            os.makedirs("logs")
            
        today = datetime.now().strftime("%Y-%m-%d")
        file_handler = logging.FileHandler(f"logs/trade_log_{today}.log")
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        
        if not self.logger.handlers:
            self.logger.addHandler(file_handler)
            console_handler = logging.StreamHandler()
            console_handler.setFormatter(formatter)
            self.logger.addHandler(console_handler)

    def log_trade(self, trade_data):
        self.logger.info(f"TRADE: {trade_data}")

    def log_signal(self, signal_data):
        self.logger.info(f"SIGNAL: {signal_data}")

    def log_error(self, error_msg):
        self.logger.error(f"ERROR: {error_msg}")

logger = QuantumLogger()
