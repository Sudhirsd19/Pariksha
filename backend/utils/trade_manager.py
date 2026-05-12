from backend.utils.persistence_manager import persistence_manager
from backend.utils.db_manager import db_manager
import time
import threading

class TradeManager:
    def __init__(self):
        self._lock = threading.Lock()
        self.active_trades = []
        self.risk_manager = None # Set from main.py
        self.realized_pnl = 0.0
        self.total_charges = 0.0
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.max_drawdown = 0.0
        self.peak_pnl = 0.0
        self.pnl_history = [0.0]
        self.gross_profit = 0.0
        self.gross_loss = 0.0

    def load_state(self):
        """Restore open trades from local SQLite on startup."""
        with self._lock:
            self.active_trades = persistence_manager.get_open_trades()
            print(f"[TradeManager] Recovered {len(self.active_trades)} open trades from local storage.")

    def add_trade(self, signal_data, doc_id):
        trade = {
            "id": doc_id,
            "symbol": signal_data.get("symbol", "NIFTY"),
            "token": signal_data.get("token"),
            "signal": signal_data["signal"],
            "entry": signal_data["actual_entry"],
            "sl": signal_data["sl"],
            "tp": signal_data["tp"],
            "qty": signal_data.get("qty", 50), 
            "status": "OPEN",
            "entry_time": signal_data["timestamp"]
        }
        with self._lock:
            self.active_trades.append(trade)
            persistence_manager.save_trade(trade)
            persistence_manager.log_event("INFO", "TRADE_OPENED", f"ID: {doc_id} | {trade['signal']} {trade['symbol']}")

    def monitor_trades(self, ltp_dict):
        """
        ltp_dict: Dictionary mapping tokens to current LTP
        """
        trades_to_close = []
        
        with self._lock:
            for trade in self.active_trades:
                token = trade.get("token")
                # If no token, we can't monitor accurately
                if not token or token not in ltp_dict:
                    continue
                    
                current_ltp = ltp_dict[token]
                
                # Check for Exit Condition
                hit_tp = False
                hit_sl = False
                exit_price = 0.0

                if trade["signal"] == "BUY":
                    if current_ltp >= trade["tp"]:
                        hit_tp = True
                        exit_price = current_ltp
                    elif current_ltp <= trade["sl"]:
                        hit_sl = True
                        exit_price = current_ltp
                elif trade["signal"] == "SELL":
                    if current_ltp <= trade["tp"]:
                        hit_tp = True
                        exit_price = current_ltp
                    elif current_ltp >= trade["sl"]:
                        hit_sl = True
                        exit_price = current_ltp

                if hit_tp or hit_sl:
                    # Calculate PnL
                    if trade["signal"] == "BUY":
                        pnl = (exit_price - trade["entry"]) * trade["qty"]
                    else:
                        pnl = (trade["entry"] - exit_price) * trade["qty"]
                    
                    # Approximate Brokerage & STT for NIFTY F&O
                    charges = 60.0 
                    net_pnl = pnl - charges

                    # Update Stats
                    self.realized_pnl += net_pnl
                    self.total_charges += charges
                    self.total_trades += 1
                    
                    if net_pnl > 0:
                        self.winning_trades += 1
                        self.gross_profit += net_pnl
                    else:
                        self.losing_trades += 1
                        self.gross_loss += abs(net_pnl)
                        
                    self.pnl_history.append(self.realized_pnl)
                    
                    # Update Max Drawdown
                    if self.realized_pnl > self.peak_pnl:
                        self.peak_pnl = self.realized_pnl
                    
                    current_dd = self.peak_pnl - self.realized_pnl
                    if self.peak_pnl > 0:
                        dd_percent = (current_dd / self.peak_pnl) * 100
                        if dd_percent > self.max_drawdown:
                            self.max_drawdown = dd_percent

                    # Update Firebase & Local Persistence
                    exit_time = int(time.time() * 1000)
                    update_data = {
                        "status": "CLOSED",
                        "exit_price": exit_price,
                        "exit_time": exit_time,
                        "pnl": net_pnl,
                        "result": "TARGET" if hit_tp else "STOPLOSS"
                    }
                    
                    # Local Update
                    persistence_manager.update_trade_exit(trade["id"], exit_price, exit_time, net_pnl, update_data['result'])
                    persistence_manager.log_event("INFO", "TRADE_CLOSED", f"ID: {trade['id']} | Result: {update_data['result']} | PnL: {net_pnl:.2f}")

                    # Remote Update
                    db_manager.update_trade(trade["id"], update_data)
                    db_manager.save_daily_pnl(net_pnl, charges, net_pnl > 0)
                    
                    # Risk Manager Exposure Sync
                    if self.risk_manager:
                        self.risk_manager.update_pnl(net_pnl, side=trade["signal"])

                    self._sync_analytics()
                    
                    trade["close_data"] = update_data
                    trades_to_close.append(trade)

            # Remove closed trades
            for t in trades_to_close:
                self.active_trades.remove(t)
            
        return trades_to_close # Return so main loop can send notifications

    def emergency_square_off(self, ltp_dict):
        trades_to_close = []
        for trade in self.active_trades:
            token = trade.get("token")
            if not token or token not in ltp_dict:
                # If we don't have LTP, we use a slightly stale entry price or skip
                # but for safety in square-off, we try to use any available data
                continue
                
            exit_price = ltp_dict[token]
            
            if trade["signal"] == "BUY":
                pnl = (exit_price - trade["entry"]) * trade["qty"]
            else:
                pnl = (trade["entry"] - exit_price) * trade["qty"]
                
            charges = 60.0 
            net_pnl = pnl - charges

            self.realized_pnl += net_pnl
            self.total_charges += charges
            self.total_trades += 1
            
            if net_pnl > 0:
                self.winning_trades += 1
                self.gross_profit += net_pnl
            else:
                self.losing_trades += 1
                self.gross_loss += abs(net_pnl)

            self.pnl_history.append(self.realized_pnl)
            
            if self.realized_pnl > self.peak_pnl:
                self.peak_pnl = self.realized_pnl
            
            current_dd = self.peak_pnl - self.realized_pnl
            if self.peak_pnl > 0:
                dd_percent = (current_dd / self.peak_pnl) * 100
                if dd_percent > self.max_drawdown:
                    self.max_drawdown = dd_percent
            
            update_data = {
                "status": "CLOSED",
                "exit_price": exit_price,
                "exit_time": int(time.time() * 1000),
                "pnl": net_pnl,
                "result": "SQUARE_OFF"
            }
            
            db_manager.update_trade(trade["id"], update_data)
            db_manager.save_daily_pnl(net_pnl, charges, net_pnl > 0)
            self._sync_analytics()
            
            trade["close_data"] = update_data
            trades_to_close.append(trade)

        for t in trades_to_close:
            self.active_trades.remove(t)
            
        return len(trades_to_close)

    def _sync_analytics(self):
        # Sync the calculated overall PnL & Analytics back to Firestore 
        # so frontend PnL Screen gets accurate metrics
        win_rate = (self.winning_trades / self.total_trades * 100) if self.total_trades > 0 else 0
        
        profit_factor = (self.gross_profit / self.gross_loss) if self.gross_loss > 0 else (self.gross_profit if self.gross_profit > 0 else 0)
        avg_winner = (self.gross_profit / self.winning_trades) if self.winning_trades > 0 else 0
        avg_loser = (self.gross_loss / self.losing_trades) if self.losing_trades > 0 else 0
        
        analytics_data = {
            "total_pnl": self.realized_pnl,
            "realized_profit": self.realized_pnl + self.total_charges,
            "charges": self.total_charges,
            "max_drawdown": self.max_drawdown,
            "win_rate": win_rate,
            "profit_factor": round(profit_factor, 2),
            "avg_winner": avg_winner,
            "avg_loser": avg_loser,
            "total_trades": self.total_trades,
            "pnl_history": self.pnl_history[-15:] # Keep last 15 points for the chart
        }
        db_manager.save_pnl_data(analytics_data)

trade_manager = TradeManager()

