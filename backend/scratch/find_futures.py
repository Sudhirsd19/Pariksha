import requests
import json
from datetime import datetime

def find_current_futures():
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    print("Fetching master list...")
    response = requests.get(url)
    data = response.json()
    
    # NIFTY expiry usually last Thursday. Let's look for May 2026.
    targets = ['NIFTY', 'BANKNIFTY']
    results = {}
    
    for item in data:
        if item['name'] in targets and item['exch_seg'] == 'NFO' and item['instrumenttype'] == 'FUTIDX':
            # We want the nearest expiry. For simplicity, let's find the one with 'MAY' and '2026'
            if 'MAY26' in item['symbol']:
                results[item['name']] = {
                    'symbol': item['symbol'],
                    'token': item['token'],
                    'lotsize': item['lotsize']
                }
    
    print(json.dumps(results, indent=4))

if __name__ == "__main__":
    find_current_futures()
