import os
import sys
import time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from config.firebase_config import init_firebase
from utils.db_manager import db_manager

# Initialize firebase for this script
init_firebase()

mock_signal = {
    "signal": "BUY",
    "symbol": "NIFTY",
    "entry": 24050.25,
    "actual_entry": 24052.10,
    "sl": 23990.00,
    "tp": 24200.00,
    "reason": "TEST SIGNAL - User Verification",
    "is_paper": True,
    "timestamp": int(time.time() * 1000)
}

print("Pushing test signal to Firestore...")
db_manager.save_signal(mock_signal)
print("Done!")
