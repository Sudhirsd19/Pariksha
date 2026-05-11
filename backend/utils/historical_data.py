from datetime import datetime, timedelta

def fetch_historical_data(smart_api, symbol_token, interval="FIVE_MINUTE", days=5, exchange="NSE"):
    """
    Fetch historical candle data.
    exchange: "NSE" for index (99926000), "NFO" for futures (66071)
    """
    to_date = datetime.now().strftime('%Y-%m-%d %H:%M')
    from_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M')
    
    params = {
        "exchange": exchange,
        "symboltoken": symbol_token,
        "interval": interval,
        "fromdate": from_date,
        "todate": to_date
    }
    
    try:
        data = smart_api.getCandleData(params)
        if data and data['status']:
            import pandas as pd
            df = pd.DataFrame(data['data'], columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            if df.empty:
                print(f"[historical_data] Empty data returned for token {symbol_token} on {exchange}")
                return None
            return df
        else:
            msg = data.get('message', 'Unknown error') if data else 'No response'
            print(f"[historical_data] Error for token {symbol_token}: {msg}")
            return None
    except Exception as e:
        print(f"[historical_data] Exception for token {symbol_token}: {e}")
        return None
