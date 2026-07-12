import json
import os

cache_path = 'backend/data/OpenAPIScripMaster.json'
if os.path.exists(cache_path):
    print("File exists, reading...")
    with open(cache_path, 'r') as f:
        data = json.load(f)
    print(f"Loaded {len(data)} items.")
    
    count = 0
    for item in data:
        if item.get('name') == 'NIFTY' and item.get('exch_seg') == 'NFO' and item.get('instrumenttype') == 'OPTIDX':
            print("NIFTY OPTIDX example:")
            print(json.dumps(item, indent=4))
            count += 1
            if count >= 3:
                break
else:
    print("Scrip master not found at", cache_path)
