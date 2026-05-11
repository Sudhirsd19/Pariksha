import sqlite3
import os
import json
from datetime import datetime

class PersistenceManager:
    def __init__(self, db_path='backend/data/trading_state.db'):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Trades table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    symbol TEXT,
                    token TEXT,
                    side TEXT,
                    entry_price REAL,
                    sl REAL,
                    tp REAL,
                    qty INTEGER,
                    status TEXT,
                    entry_time INTEGER,
                    exit_price REAL,
                    exit_time INTEGER,
                    pnl REAL,
                    metadata TEXT
                )
            ''')
            # Positions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    avg_price REAL,
                    qty INTEGER,
                    last_update INTEGER
                )
            ''')
            # Execution Logs
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS logs (
                    timestamp INTEGER,
                    level TEXT,
                    event TEXT,
                    details TEXT
                )
            ''')
            conn.commit()

    def save_trade(self, trade_data):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO trades 
                (id, symbol, token, side, entry_price, sl, tp, qty, status, entry_time, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade_data['id'], trade_data['symbol'], trade_data['token'], 
                trade_data['signal'], trade_data['entry'], trade_data['sl'], 
                trade_data['tp'], trade_data['qty'], "OPEN", 
                trade_data['timestamp'], json.dumps(trade_data)
            ))
            conn.commit()

    def update_trade_exit(self, trade_id, exit_price, exit_time, pnl, status="CLOSED"):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE trades 
                SET exit_price = ?, exit_time = ?, pnl = ?, status = ?
                WHERE id = ?
            ''', (exit_price, exit_time, pnl, status, trade_id))
            conn.commit()

    def get_open_trades(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trades WHERE status = 'OPEN'")
            rows = cursor.fetchall()
            trades = []
            for row in rows:
                trade = dict(row)
                if trade['metadata']:
                    meta = json.loads(trade['metadata'])
                    trade.update(meta)
                trades.append(trade)
            return trades

    def log_event(self, level, event, details=""):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO logs (timestamp, level, event, details)
                VALUES (?, ?, ?, ?)
            ''', (int(datetime.now().timestamp() * 1000), level, event, details))
            conn.commit()

persistence_manager = PersistenceManager()
