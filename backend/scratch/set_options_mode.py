import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.config.firebase_config import init_firebase, get_db
from backend.utils.db_manager import db_manager

def configure_settings():
    init_firebase()
    db = get_db()
    if not db:
        print("Could not connect to database")
        return
        
    settings = {
        "risk_percent": 1.5,
        "take_profit_points": 60,
        "stop_loss_points": 30,
        "max_daily_trades": 5,
        "paper_trading": True,
        "instrument_type": "OPTIONS",
        "capital_limit": 10000.0
    }
    
    print("Updating Firestore settings doc...")
    db.collection("quantum_system").document("settings").set(settings, merge=True)
    
    # Reset today's PnL aggregation doc to release hard lock
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"Resetting daily PnL stats doc for {today}...")
    db.collection("pnl_daily").document(today).delete()
    
    print("Settings and daily stats reset successfully!")

if __name__ == "__main__":
    configure_settings()
