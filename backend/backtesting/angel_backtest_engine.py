import asyncio
import pandas as pd
from datetime import datetime, timedelta, timezone
from backend.utils.historical_data import fetch_historical_data
from backend.engines.signal_engine import SignalEngine
from backend.engines.structure_engine import StructureEngine

IST = timezone(timedelta(hours=5, minutes=30))

async def fetch_long_history(smart_api, token, interval="FIVE_MINUTE", total_days=180, exchange="NSE"):
    """
    Fetch up to 180 days of intraday data by requesting it in 30-day chunks to bypass broker limits.
    """
    df_list = []
    end_date = datetime.now(IST)
    
    # AngelOne typically limits 5-min historical data to max 30-40 days per request
    chunk_size_days = 30 
    
    remaining_days = total_days
    
    print(f"Fetching {total_days} days of {interval} data for token {token}...")
    
    while remaining_days > 0:
        days_to_fetch = min(chunk_size_days, remaining_days)
        start_date = end_date - timedelta(days=days_to_fetch)
        
        params = {
            "exchange": exchange,
            "symboltoken": token,
            "interval": interval,
            "fromdate": start_date.strftime('%Y-%m-%d %H:%M'),
            "todate": end_date.strftime('%Y-%m-%d %H:%M')
        }
        
        try:
            data = await asyncio.to_thread(smart_api.getCandleData, params)
            if data and data.get('status') and data.get('data'):
                chunk_df = pd.DataFrame(data['data'], columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                if not chunk_df.empty:
                    df_list.append(chunk_df)
        except Exception as e:
            print(f"Failed to fetch chunk {start_date} to {end_date}: {e}")
            
        end_date = start_date
        remaining_days -= days_to_fetch
        
        # Prevent rate limit hit (3 req/sec limit)
        await asyncio.sleep(0.4)
        
    if not df_list:
        return None
        
    # Concatenate and sort
    full_df = pd.concat(df_list, ignore_index=True)
    full_df['time'] = pd.to_datetime(full_df['time'])
    full_df.sort_values('time', inplace=True)
    full_df.drop_duplicates(subset=['time'], keep='last', inplace=True)
    full_df.reset_index(drop=True, inplace=True)
    
    print(f"Successfully fetched {len(full_df)} candles over {total_days} days.")
    return full_df

class AngelBacktestEngine:
    def __init__(self, initial_capital=100000):
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.trades = []
        self.signal_engine = SignalEngine()
        self.struct_engine = StructureEngine()
        
    def simulate_slippage(self, price, is_buy):
        # Add 0.05% slippage
        slippage = price * 0.0005
        return price + slippage if is_buy else price - slippage
        
    def run_backtest(self, df, htf_trend="BULLISH", risk_per_trade=0.02):
        print(f"Running simulation on {len(df)} candles. This might take a moment...")
        self.balance = self.initial_capital
        self.trades = []
        
        open_trade = None
        last_date = None
        trades_today = 0
        
        # We need at least 100 candles of history for EMAs and ATRs to warm up
        warmup_period = 100
        
        for i in range(warmup_period, len(df)):
            # Slice the dataframe to simulate real-time arrival of data up to index `i`
            current_df = df.iloc[max(0, i - 300) : i+1].copy() # Keep last 300 candles for context
            current_row = current_df.iloc[-1]
            current_price = float(current_row['close'])
            current_time = current_row['time']
            
            import pandas as pd
            # Safely get the date string
            current_date_str = str(current_time).split(' ')[0]
            if current_date_str != last_date:
                trades_today = 0
                last_date = current_date_str
            
            # 1. Manage existing open trade
            if open_trade:
                trade_type = open_trade['type']
                sl = open_trade['sl']
                tp = open_trade['tp']
                qty = open_trade['qty']
                
                # Check SL/TP Hits
                if trade_type == "BUY":
                    if current_row['low'] <= sl: # Stop Loss Hit
                        exit_price = self.simulate_slippage(sl, is_buy=False)
                        pnl = (exit_price - open_trade['entry_price']) * qty
                        self._close_trade(open_trade, exit_price, current_time, "SL Hit", pnl)
                        open_trade = None
                        continue
                    elif current_row['high'] >= tp: # Take Profit Hit
                        exit_price = self.simulate_slippage(tp, is_buy=False)
                        pnl = (exit_price - open_trade['entry_price']) * qty
                        self._close_trade(open_trade, exit_price, current_time, "TP Hit", pnl)
                        open_trade = None
                        continue
                        
                elif trade_type == "SELL":
                    if current_row['high'] >= sl: # Stop Loss Hit
                        exit_price = self.simulate_slippage(sl, is_buy=True)
                        pnl = (open_trade['entry_price'] - exit_price) * qty
                        self._close_trade(open_trade, exit_price, current_time, "SL Hit", pnl)
                        open_trade = None
                        continue
                    elif current_row['low'] <= tp: # Take Profit Hit
                        exit_price = self.simulate_slippage(tp, is_buy=True)
                        pnl = (open_trade['entry_price'] - exit_price) * qty
                        self._close_trade(open_trade, exit_price, current_time, "TP Hit", pnl)
                        open_trade = None
                        continue
                        
            # 2. Look for new entries if no open trade
            if not open_trade and trades_today < 1:
                # Check killzone
                try:
                    time_str = str(current_time).split(' ')[1][:8] # Extract HH:MM:SS
                    import datetime as dt
                    t = dt.datetime.strptime(time_str, "%H:%M:%S").time()
                    kz_1_start, kz_1_end = dt.time(9, 30), dt.time(11, 0)
                    kz_2_start, kz_2_end = dt.time(13, 30), dt.time(15, 0)
                    if not ((kz_1_start <= t <= kz_1_end) or (kz_2_start <= t <= kz_2_end)):
                        continue
                except Exception:
                    pass # Fallback if time parse fails
                    
                # Resample for HTF data
                current_df.set_index('time', inplace=True)
                df_1d = current_df.resample('1D').agg({'open':'first', 'high':'max', 'low':'min', 'close':'last', 'volume':'sum'}).dropna().reset_index()
                current_df.reset_index(inplace=True)
                
                # --- APPLY 100-POINT FORMULA ---
                # Default fundamental points for Reliance (Mocked as they are constant)
                # Inst. Holding, Promoter Pledge, Piotroski, PE, Event, Beta, Sector, PCR = ~40 points
                score = 40
                
                # Tech points
                last_close = current_price
                
                # Spread (Mocked pass)
                score += 5
                
                # EMA Strong Trend Filter (using 5-min candles instead of 1D since context is only 300 candles)
                if len(current_df) >= 200:
                    ema50 = current_df['close'].ewm(span=50, adjust=False).mean().iloc[-1]
                    ema200 = current_df['close'].ewm(span=200, adjust=False).mean().iloc[-1]
                    
                    if current_df['close'].iloc[-1] > ema50 and ema50 > ema200:
                        htf_trend = "Bullish"
                    elif current_df['close'].iloc[-1] < ema50 and ema50 < ema200:
                        htf_trend = "Bearish"
                    else:
                        htf_trend = "Neutral"
                else:
                    htf_trend = "Neutral"
                    
                if htf_trend == "Bullish": score += 5
                
                # Structure Points
                struct_res = self.struct_engine.analyze(current_df)
                if struct_res.get("bos_bullish") or struct_res.get("fvg_gap"):
                    score += 5
                if struct_res.get("in_discount"):
                    score += 5
                    
                # Volume breakout
                score += 5 # Mocking OI / volume buildup
                
                signal_side = None
                if score >= 60 and htf_trend == "Bullish":
                    signal_side = "BUY"
                elif score <= 40 and htf_trend == "Bearish":
                    signal_side = "SELL"
                    
                if signal_side:
                    # Calculate ATR for SL/TP
                    high_low = current_df['high'] - current_df['low']
                    high_close = (current_df['high'] - current_df['close'].shift()).abs()
                    low_close = (current_df['low'] - current_df['close'].shift()).abs()
                    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                    atr = true_range.rolling(14).mean().iloc[-1]
                    if pd.isna(atr) or atr == 0: atr = current_price * 0.005
                    
                    sl = current_price - (atr * 1.5) if signal_side == "BUY" else current_price + (atr * 1.5)
                    tp = current_price + (atr * 3.0) if signal_side == "BUY" else current_price - (atr * 3.0)
                    
                    signal = {
                        'signal': signal_side,
                        'sl': sl,
                        'tp': tp,
                        'reason': f"Score {score}/100"
                    }
                else:
                    signal = None
                
                if signal and signal.get('signal') in ["BUY", "SELL"]:
                    entry_price = self.simulate_slippage(current_price, signal['signal'] == "BUY")
                    risk_amount = self.balance * risk_per_trade
                    sl_dist = abs(entry_price - signal['sl'])
                    if sl_dist == 0:
                        continue
                        
                    qty = int(risk_amount / sl_dist)
                    if qty <= 0:
                        continue
                        
                    # Enforce capital limit
                    required_margin = entry_price * qty
                    if required_margin > self.balance:
                        qty = int(self.balance / entry_price)
                        if qty <= 0:
                            continue
                            
                    open_trade = {
                        "type": signal['signal'],
                        "entry_time": current_time,
                        "entry_price": entry_price,
                        "qty": qty,
                        "sl": signal['sl'],
                        "tp": signal['tp'],
                        "atr": atr,
                        "reason": signal['reason']
                    }
                    trades_today += 1
                    
        # Close any open trade at end of backtest
        if open_trade:
            exit_price = df.iloc[-1]['close']
            pnl = (exit_price - open_trade['entry_price']) * open_trade['qty'] if open_trade['type'] == "BUY" else (open_trade['entry_price'] - exit_price) * open_trade['qty']
            self._close_trade(open_trade, exit_price, df.iloc[-1]['time'], "End of Test", pnl)
            
        return self._generate_report()
        
    def _close_trade(self, trade, exit_price, exit_time, exit_reason, pnl):
        trade['exit_time'] = exit_time
        trade['exit_price'] = exit_price
        trade['exit_reason'] = exit_reason
        trade['pnl'] = pnl
        
        # Deduct minimal brokerage/charges per trade (e.g., ₹20 per order + STT)
        brokerage = 40 + (trade['entry_price'] * trade['qty'] * 0.0003)
        trade['net_pnl'] = pnl - brokerage
        
        self.balance += trade['net_pnl']
        self.trades.append(trade)
        
    def _generate_report(self):
        winning_trades = [t for t in self.trades if t['net_pnl'] > 0]
        losing_trades = [t for t in self.trades if t['net_pnl'] <= 0]
        
        total_trades = len(self.trades)
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
        
        gross_profit = sum(t['net_pnl'] for t in winning_trades)
        gross_loss = sum(t['net_pnl'] for t in losing_trades)
        net_profit = self.balance - self.initial_capital
        
        # Calculate Max Drawdown
        peak = self.initial_capital
        max_dd = 0
        current_bal = self.initial_capital
        for t in self.trades:
            current_bal += t['net_pnl']
            if current_bal > peak:
                peak = current_bal
            dd = (peak - current_bal) / peak * 100
            if dd > max_dd:
                max_dd = dd
                
        return {
            "initial_capital": self.initial_capital,
            "final_balance": self.balance,
            "net_profit": net_profit,
            "total_trades": total_trades,
            "win_rate": win_rate,
            "max_drawdown_pct": max_dd,
            "gross_profit": gross_profit,
            "gross_loss": gross_loss,
            "trades": self.trades
        }
