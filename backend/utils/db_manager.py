from config.firebase_config import get_db
import time
from datetime import datetime, timezone

class DatabaseManager:
    @staticmethod
    def save_signal(signal_data):
        db = get_db()
        if not db: return None
        
        try:
            doc_id = str(int(time.time() * 1000))
            signal_data['id'] = doc_id
            db.collection("quantum_trades").document(doc_id).set(signal_data)
            return doc_id
        except Exception as e:
            print(f"Error saving signal to DB: {e}")
            return None

    @staticmethod
    def update_trade(doc_id, update_data):
        db = get_db()
        if not db: return
        
        try:
            db.collection("quantum_trades").document(doc_id).update(update_data)
        except Exception as e:
            print(f"Error updating trade in DB: {e}")

    @staticmethod
    def update_system_status(status_data):
        db = get_db()
        if not db: return
        
        try:
            db.collection("quantum_system").document("live_status").set(status_data, merge=True)
        except Exception as e:
            print(f"Error updating status to DB: {e}")
            
    @staticmethod
    def get_settings():
        db = get_db()
        if not db: 
            return None
            
        try:
            doc = db.collection("quantum_system").document("settings").get()
            if doc.exists:
                return doc.to_dict()
            return None
        except Exception as e:
            print(f"Error getting settings from DB: {e}")
            return None
            
    @staticmethod
    def save_pnl_data(pnl_data):
        db = get_db()
        if not db: return
        
        try:
            db.collection("quantum_system").document("pnl_data").set(pnl_data, merge=True)
        except Exception as e:
            print(f"Error saving PnL to DB: {e}")

    @staticmethod
    def save_daily_pnl(net_pnl: float, charges: float, is_win: bool):
        """
        Aggregates today's PnL into pnl_daily/{YYYY-MM-DD} document.
        Uses Firestore incremental update so multiple trades accumulate correctly.
        """
        db = get_db()
        if not db: return
        
        try:
            from google.cloud.firestore_v1 import Increment
            
            # IST = UTC+5:30
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            # Also calculate week key (ISO week) and month key
            now = datetime.now(timezone.utc)
            week_key  = f"{now.year}-W{now.strftime('%V')}"
            month_key = now.strftime("%Y-%m")

            daily_ref = db.collection("pnl_daily").document(today)
            
            # Atomic increments — safe even if multiple trades close simultaneously
            daily_ref.set({
                "date": today,
                "week": week_key,
                "month": month_key,
                "total_pnl":   Increment(net_pnl),
                "charges":     Increment(charges),
                "total_trades": Increment(1),
                "wins":        Increment(1 if is_win else 0),
                "losses":      Increment(0 if is_win else 1),
            }, merge=True)

        except Exception as e:
            print(f"Error saving daily PnL to DB: {e}")

db_manager = DatabaseManager()

