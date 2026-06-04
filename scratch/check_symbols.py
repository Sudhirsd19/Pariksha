import json
from datetime import datetime

cache_path = 'backend/data/OpenAPIScripMaster.json'
with open(cache_path, 'r') as f:
    data = json.load(f)

filtered = [item for item in data if item.get('name') == 'NIFTY' and item.get('exch_seg') == 'NFO' and item.get('instrumenttype') == 'OPTIDX']
for item in filtered[:20]:
    symbol = item.get('symbol')
    strike = item.get('strike')
    expiry = item.get('expiry')
    print(f"Symbol: {symbol:25} Strike: {strike:15} Expiry: {expiry:10}")
