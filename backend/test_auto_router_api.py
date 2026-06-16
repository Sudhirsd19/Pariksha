import sys
import os
import json

# Ensure project root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def run_test():
    print("Testing /api/scanner/scan with RELIANCE.NS...")
    response = client.get("/api/scanner/scan?symbol=RELIANCE")
    
    print(f"Status Code: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print("\n=== SUCCESS ===")
        print(f"Symbol: {data.get('symbol')}")
        print(f"ADX Score: {data.get('adx_score')}")
        print(f"Engine Used: {data.get('engine_used')}")
        print(f"Total Signals Today: {data.get('total_signals_today')}")
        
        if data.get('signals'):
            print("\nLatest Signal:")
            print(json.dumps(data['signals'][0], indent=2))
        else:
            print("\nNo signals generated today.")
    else:
        print("FAILED!")
        print(response.text)

if __name__ == "__main__":
    run_test()
