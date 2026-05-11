import requests
import json
import os

def fetch_angel_one_tokens():
    """
    Fetch the master instrument list from Angel One and filter for NIFTY/BANKNIFTY.
    """
    url = "https://margincalculator.angelbroking.com/OpenAPI_Standard/v1/Inventory/getSymbolList"
    try:
        print("Fetching Angel One Instrument List...")
        response = requests.get(url)
        data = response.json()
        
        # We want to filter for NIFTY and BANKNIFTY Indices/Futures
        # For simplicity, let's just save the whole list or filter common ones
        tokens = {}
        for item in data:
            symbol = item['symbol']
            if symbol in ['NIFTY', 'BANKNIFTY'] and item['exch_seg'] == 'NSE':
                tokens[symbol] = item['token']
            elif 'NIFTY' in symbol and 'FUT' in symbol and item['exch_seg'] == 'NFO':
                 # NIFTY Futures
                 tokens[symbol] = item['token']

        with open('backend/config/tokens.json', 'w') as f:
            json.dump(tokens, f, indent=4)
            
        print(f"Successfully saved {len(tokens)} tokens to config/tokens.json")
        return tokens
    except Exception as e:
        print(f"Error fetching tokens: {e}")
        return None

if __name__ == "__main__":
    fetch_angel_one_tokens()
