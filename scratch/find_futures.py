import json
from datetime import datetime

cache_path = 'backend/data/OpenAPIScripMaster.json'
with open(cache_path, 'r') as f:
    data = json.load(f)

today = datetime.now().date()
print("Today's date is:", today)

nifty_futs = []
banknifty_futs = []

for item in data:
    if item.get('exch_seg') == 'NFO' and item.get('instrumenttype') == 'FUTIDX':
        name = item.get('name')
        expiry_str = item.get('expiry')
        if not expiry_str:
            continue
        try:
            expiry_date = datetime.strptime(expiry_str, "%d%b%Y").date()
        except Exception:
            continue
            
        if expiry_date >= today:
            entry = {
                "token": item.get("token"),
                "symbol": item.get("symbol"),
                "expiry": expiry_date,
                "lotsize": int(item.get("lotsize", 1))
            }
            if name == "NIFTY":
                nifty_futs.append(entry)
            elif name == "BANKNIFTY":
                banknifty_futs.append(entry)

# Sort by expiry (nearest first)
nifty_futs.sort(key=lambda x: x["expiry"])
banknifty_futs.sort(key=lambda x: x["expiry"])

print("Active NIFTY Futures contracts:")
for fut in nifty_futs[:3]:
    print(fut)

print("\nActive BANKNIFTY Futures contracts:")
for fut in banknifty_futs[:3]:
    print(fut)
