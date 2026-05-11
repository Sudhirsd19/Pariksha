import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Angel One
    ANGEL_API_KEY = os.getenv("ANGEL_API_KEY")
    ANGEL_CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
    ANGEL_PIN = os.getenv("ANGEL_PIN")
    ANGEL_TOTP_KEY = os.getenv("ANGEL_TOTP_KEY")

    # App
    DEBUG = os.getenv("DEBUG", "True") == "True"
    SECRET_KEY = os.getenv("SECRET_KEY", "supersecret")
    PAPER_TRADING = os.getenv("PAPER_TRADING", "True") == "True"
    
    # Trading
    RISK_PER_TRADE = float(os.getenv("RISK_PER_TRADE", 0.01))
    DAILY_LOSS_LIMIT = float(os.getenv("DAILY_LOSS_LIMIT", 0.03))
    MAX_TRADES_PER_DAY = int(os.getenv("MAX_TRADES_PER_DAY", 5))

    # Market Timings (India) - Optimized for continuous trading
    MARKET_OPEN = "09:15"
    MARKET_CLOSE = "15:30"
    SESSION_1_START = "09:15"
    SESSION_1_END = "15:25"
    SESSION_2_START = "09:15" # redundant but safe
    SESSION_2_END = "15:25"

config = Config()
