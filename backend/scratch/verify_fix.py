import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

import asyncio
from backend.utils.db_manager import db_manager
from backend.execution.broker_api import AngelOneBroker
from backend.config.firebase_config import init_firebase, get_db

async def run_verification():
    init_firebase()
    db = get_db()
    
    # 1. Verify get_system_status
    print("--- Verifying System Status ---")
    status = db_manager.get_system_status()
    print(f"System Status: {status}")
    
    # 2. Verify Open Trades Firestore Query
    print("\n--- Verifying Open Trades Firestore Query ---")
    from datetime import datetime, timezone, timedelta
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    start_of_day_ist = datetime.now(ist_tz).replace(hour=0, minute=0, second=0, microsecond=0)
    start_of_day_ms = int(start_of_day_ist.timestamp() * 1000)
    open_trades_query = db.collection("quantum_trades").where("status", "==", "OPEN").stream()
    open_trades = []
    for doc in open_trades_query:
        d = doc.to_dict()
        d['id'] = doc.id
        if d.get('timestamp', 0) >= start_of_day_ms:
            open_trades.append(d)
    print(f"Found {len(open_trades)} open trades in Firestore.")
    for ot in open_trades:
        print(f"  Trade ID: {ot['id']}, Symbol: {ot.get('symbol')}, Status: {ot.get('status')}")
        
    # 3. Verify Broker Positions Exchange Segment Keys
    print("\n--- Verifying Broker Positions & Exchange ---")
    broker = AngelOneBroker()
    if broker.login():
        print("Logged into Angel One broker successfully.")
        try:
            positions = broker.smart_api.position()
            if positions and positions.get('status') and positions.get('data'):
                print(f"Found {len(positions['data'])} positions on broker:")
                for pos in positions['data']:
                    net_qty = int(pos.get('netqty', 0))
                    print(f"  Symbol: {pos.get('tradingsymbol')}, Token: {pos.get('symboltoken')}, Qty: {net_qty}, Exchange: {pos.get('exchange')}")
            else:
                print("No positions found or error fetching positions.")
        except Exception as e:
            print(f"Error fetching positions: {e}")
    else:
        print("Failed to login to broker.")

    # 4. Verify Sectoral trends parallel fetch and StockAnalyzer upgrades
    print("\n--- Verifying Sectoral Trend Lookup and StockAnalyzer Upgrades ---")
    from backend.engines.stock_analyzer import stock_analyzer, STOCK_SECTOR_MAP
    import yfinance as yf
    
    # Let's fetch index trends in parallel
    index_tickers = ["^NSEI", "^NSEBANK", "^CNXIT", "^CNXENERGY", "^CNXFIN", "^CNXMETAL", "^CNXPHARMA", "^CNXFMCG", "^CNXAUTO", "^CNXINFRA", "^CNXREALTY"]
    
    async def fetch_index_trend(ticker):
        try:
            t_obj = yf.Ticker(ticker)
            fast_info = await asyncio.to_thread(lambda: t_obj.fast_info)
            last_price = float(getattr(fast_info, "last_price", 0))
            prev_close = float(getattr(fast_info, "previous_close", 0))
            if last_price > 0 and prev_close > 0:
                return ticker, ("Bullish" if last_price > prev_close else "Bearish")
        except Exception as ex:
            print(f"[IndexTrend] Failed to fetch {ticker}: {ex}")
        return ticker, "Neutral"

    tasks = [fetch_index_trend(t) for t in index_tickers]
    index_trends = dict(await asyncio.gather(*tasks))
    print(f"Index Trends Fetched: {index_trends}")

    # Analyze a few test stocks
    test_symbols = ["SBIN", "TCS", "RELIANCE"]
    for sym in test_symbols:
        print(f"\nAnalyzing stock: {sym}")
        res = await stock_analyzer.analyze_stock(sym, index_trends=index_trends)
        print(f"  Symbol: {res.get('symbol')}")
        print(f"  Score: {res.get('score')}")
        print(f"  Actionable: {res.get('actionable')}")
        print(f"  ATR (5M): {res.get('atr')}")
        print(f"  Sector Index: {STOCK_SECTOR_MAP.get(sym, '^NSEI')}")
        print(f"  Checklist:")
        for item in res.get('checklist', []):
            print(f"    - {item['item']}: {item['status']} ({item['detail']}) - Points: {item['points']}")

if __name__ == '__main__':
    asyncio.run(run_verification())
