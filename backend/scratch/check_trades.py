import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone

def check_today_trades():
    try:
        cred = credentials.Certificate('d:/QuantumIndex/backend/firebase_credentials.json')
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # Check daily PnL
        daily_doc = db.collection("pnl_daily").document(today).get()
        if daily_doc.exists:
            data = daily_doc.to_dict()
            print(f"--- Summary for {today} ---")
            print(f"Total Trades: {data.get('total_trades', 0)}")
            print(f"Wins: {data.get('wins', 0)}")
            print(f"Losses: {data.get('losses', 0)}")
            print(f"Net PnL: Rs. {data.get('total_pnl', 0.0):.2f}")
            print(f"Charges: Rs. {data.get('charges', 0.0):.2f}")
        else:
            print(f"No summary found for {today}")

        # List individual trades
        print("\n--- Recent Individual Trades ---")
        trades_ref = db.collection("quantum_trades")
        
        # Get start of day as a string prefix for doc_id (which is ms timestamp)
        start_of_day_ms = int(datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
        
        # Query last 20 trades to see what's there
        query = trades_ref.order_by("id", direction=firestore.Query.DESCENDING).limit(20).stream()
        count = 0
        for doc in query:
            t = doc.to_dict()
            try:
                doc_id_ms = int(doc.id)
                if doc_id_ms >= start_of_day_ms:
                    count += 1
                    time_str = datetime.fromtimestamp(doc_id_ms/1000).strftime('%H:%M:%S')
                    print(f"[{time_str}] {t.get('symbol', 'N/A')} {t.get('signal')} @ {t.get('entry')} | Status: {t.get('status')} | PnL: Rs. {t.get('pnl', 0)}")
            except:
                continue
        
        if count == 0:
            print("No individual trades found for today in the last 20 records.")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_today_trades()
