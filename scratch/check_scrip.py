import json
import os
from datetime import datetime

cache_path = 'backend/data/OpenAPIScripMaster.json'
print("File exists:", os.path.exists(cache_path))
if os.path.exists(cache_path):
    print("File size:", os.stat(cache_path).st_size)
    try:
        with open(cache_path, 'r') as f:
            data = json.load(f)
        print("Total items:", len(data))
        
        # Look at the first few items
        print("First 3 items:")
        for i in range(min(3, len(data))):
            print(data[i])
            
        # Sample items matching name="NIFTY"
        nifty_items = [item for item in data if item.get('name') == 'NIFTY'][:5]
        print("Nifty items:", nifty_items)
        
        # Check exchange segments and instrument types in data
        exch_segs = set(item.get('exch_seg') for item in data if item.get('name') == 'NIFTY')
        print("Exch segs for NIFTY:", exch_segs)
        
        instrumenttypes = set(item.get('instrumenttype') for item in data if item.get('name') == 'NIFTY')
        print("Instrument types for NIFTY:", instrumenttypes)
        
        # Filter for OPTIDX, NFO, NIFTY
        filtered = [item for item in data if item.get('name') == 'NIFTY' and item.get('exch_seg') == 'NFO' and item.get('instrumenttype') == 'OPTIDX']
        print("Number of OPTIDX NFO NIFTY:", len(filtered))
        if filtered:
            print("Sample OPTIDX contract:", filtered[0])
            print("Expiry dates found:", sorted(list(set(item.get('expiry') for item in filtered)))[:10])
            
            # Check why datetime parsing/expiry filter might fail
            today = datetime.now().date()
            print("Today's date is:", today)
            valid_expiry_count = 0
            for item in filtered:
                expiry_str = item.get('expiry')
                if not expiry_str:
                    continue
                try:
                    expiry_date = datetime.strptime(expiry_str, "%d%b%Y").date()
                    if expiry_date >= today:
                        valid_expiry_count += 1
                except Exception as e:
                    pass
            print("Valid expiry count:", valid_expiry_count)
            
    except Exception as e:
        print("Error reading json:", e)
else:
    print("No file found.")
