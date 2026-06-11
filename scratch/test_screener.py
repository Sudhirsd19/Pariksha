import asyncio
import sys
import os

# Set environment variables so the app config doesn't throw errors
os.environ["ANGEL_API_KEY"] = "2sromxA0"
os.environ["ANGEL_CLIENT_ID"] = "S50050133"
os.environ["ANGEL_PIN"] = "9109"
os.environ["ANGEL_TOTP_KEY"] = "KSHZS7LMQZCCUCFAJVAE35O3II"
os.environ["FIREBASE_SERVICE_ACCOUNT_JSON"] = "{}"

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.main import smart_screener

async def main():
    try:
        res = await smart_screener(max_price=500.0, min_score=70)
        print("Success!")
        print("Results count:", len(res.get("results", [])))
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
