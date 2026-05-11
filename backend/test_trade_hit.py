import os
import sys
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.firebase_config import init_firebase
from utils.db_manager import db_manager

init_firebase()

# The base LTP in main.py is ~23997.55
# We set very tight SL and TP so the random +/- 2.0 jitter hits it quickly
mock_signal = {
    "signal": "BUY",
    "symbol": "NIFTY",
    "entry": 23997.55,
    "actual_entry": 23998.00,
    "sl": 23995.00,
    "tp": 24001.00,
    "reason": "TEST - PnL Accuracy Verification",
    "is_paper": True,
    "timestamp": int(time.time() * 1000)
}

print("Pushing tight-range trade to Firestore...")
doc_id = db_manager.save_signal(mock_signal)
print(f"Trade added with ID: {doc_id}")
print("Please check your Flutter App's Dashboard. It will move to PnL screen once it hits SL/TP.")
