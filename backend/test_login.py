from execution.broker_api import AngelOneBroker
from config.config import config

def test_login():
    print("--- Angel One Login Test ---")
    print(f"Client ID: {config.ANGEL_CLIENT_ID}")
    
    broker = AngelOneBroker()
    success = broker.login()
    
    if success:
        print("\n[SUCCESS] Login verified! Session generated.")
        print(f"Feed Token: {broker.feed_token}")
    else:
        print("\n[FAILED] Could not login. Check your credentials or TOTP key.")

if __name__ == "__main__":
    test_login()
