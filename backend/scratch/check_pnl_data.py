import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.append(r"d:\QuantumIndex")

from backend.config.firebase_config import init_firebase, get_db

init_firebase()
db = get_db()

if db:
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    start_of_day_ist = datetime.now(ist_tz).replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_ms = int(start_of_day_ist.timestamp() * 1000)
    
    print("--- TODAY'S TRADES ---")
    trades_query = db.collection("quantum_trades").where("timestamp", ">=", start_of_day_ms).order_by("timestamp").stream()
    total_pnl_calc = 0.0
    for doc in trades_query:
        d = doc.to_dict()
        pnl = d.get('pnl', 0.0)
        status = d.get('status')
        symbol = d.get('symbol')
        timestamp = d.get('timestamp')
        dt = datetime.fromMillisecondsSinceEpoch(timestamp) if hasattr(datetime, 'fromMillisecondsSinceEpoch') else datetime.fromtimestamp(timestamp/1000, tz=ist_tz)
        print(f"Symbol: {symbol} | Status: {status} | PnL: {pnl} | Time: {dt.strftime('%H:%M:%S')}")
        if status == 'CLOSED':
            total_pnl_calc += pnl
            
    print(f"\nCalculated sum of CLOSED trades PnL: {total_pnl_calc}")
    
    print("\n--- DAILY PNL DOCS ---")
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_ist = datetime.now(ist_tz).strftime("%Y-%m-%d")
    
    doc_utc = db.collection("pnl_daily").document(today_utc).get()
    if doc_utc.exists:
        print(f"Doc UTC ({today_utc}): {doc_utc.to_dict()}")
    else:
        print(f"Doc UTC ({today_utc}) does not exist.")
        
    if today_ist != today_utc:
        doc_ist = db.collection("pnl_daily").document(today_ist).get()
        if doc_ist.exists:
            print(f"Doc IST ({today_ist}): {doc_ist.to_dict()}")
        else:
            print(f"Doc IST ({today_ist}) does not exist.")
else:
    print("Could not initialize DB.")
