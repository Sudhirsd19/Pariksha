import json
from datetime import datetime

cache_path = 'backend/data/OpenAPIScripMaster.json'
with open(cache_path, 'r') as f:
    data = json.load(f)

today = datetime.now().date()
options_index = {"NIFTY": {"CE": {}, "PE": {}}, "BANKNIFTY": {"CE": {}, "PE": {}}}
count = 0

for item in data:
    if (item.get('name') in ["NIFTY", "BANKNIFTY"] and 
        item.get('exch_seg') == 'NFO' and 
        item.get('instrumenttype') == 'OPTIDX'):
        
        symbol = item.get('name')
        raw_strike = float(item.get('strike', 0))
        strike = int(raw_strike / 100.0)  # Convert from e.g. 2415000.0 to 24150
        
        expiry_str = item.get('expiry')
        if not expiry_str:
            continue
        try:
            expiry_date = datetime.strptime(expiry_str, "%d%b%Y").date()
        except Exception:
            continue
            
        if expiry_date < today:
            continue
            
        trading_symbol = item.get('symbol', '')
        if trading_symbol.endswith("CE"):
            opt_type = "CE"
        elif trading_symbol.endswith("PE"):
            opt_type = "PE"
        else:
            continue
            
        if strike not in options_index[symbol][opt_type]:
            options_index[symbol][opt_type][strike] = []
            
        options_index[symbol][opt_type][strike].append({
            "token": item.get("token"),
            "symbol": trading_symbol,
            "lotsize": int(item.get("lotsize", 25)),
            "expiry": expiry_date
        })
        count += 1

print("Successfully indexed", count, "contracts")
# Test get_atm_option logic
index_ltp = 24150.0
strike = int(round(index_ltp / 50.0) * 50)
print(f"LTP: {index_ltp}, Strike: {strike}")
contracts = options_index["NIFTY"]["CE"].get(strike, [])
print("Contracts for strike CE:", contracts[:2])

# Test get_atm_option logic for BANKNIFTY
bn_ltp = 48500.0
bn_strike = int(round(bn_ltp / 100.0) * 100)
print(f"BANKNIFTY LTP: {bn_ltp}, Strike: {bn_strike}")
bn_contracts = options_index["BANKNIFTY"]["CE"].get(bn_strike, [])
print("BANKNIFTY Contracts for strike CE:", bn_contracts[:2])
