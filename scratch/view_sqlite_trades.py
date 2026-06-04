import sqlite3
import json

db_path = 'backend/data/trading_state.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()
cursor.execute("SELECT * FROM trades WHERE status = 'OPEN'")
rows = cursor.fetchall()
print("Open Trades count:", len(rows))
for row in rows:
    trade = dict(row)
    print("Trade ID:", trade['id'])
    print("Symbol:", trade['symbol'])
    print("Token:", trade['token'])
    print("Entry Price:", trade['entry_price'])
    print("SL:", trade['sl'])
    print("TP:", trade['tp'])
    print("Qty:", trade['qty'])
    print("Metadata:", json.loads(trade['metadata']) if trade['metadata'] else {})
    print("=" * 40)
conn.close()
