import asyncio
import os
import sys
import pandas as pd

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

# Set mock env vars or placeholders if needed
os.environ["FIREBASE_CREDENTIALS_PATH"] = "backend/firebase_credentials.json"

from backend.main import scan_stock_signals

async def main():
    print("Testing scan_stock_signals('RELIANCE')...")
    try:
        res = await scan_stock_signals("RELIANCE")
        print("\nSUCCESS!")
        print(res)
    except Exception as e:
        print("\nFAILED with exception:")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
