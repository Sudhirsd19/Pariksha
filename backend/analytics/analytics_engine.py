import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd
import pandas as pd
from datetime import datetime, timedelta, timezone

class AnalyticsEngine:
    def __init__(self):
        try:
            self.db = firestore.client()
        except ValueError:
            print("[AnalyticsEngine] Firebase not initialized. Analytics will not run.")
            self.db = None

    def fetch_recent_trades(self, days=30):
        if not self.db:
            return pd.DataFrame()
            
        IST = timezone(timedelta(hours=5, minutes=30))
        start_time = int((datetime.now(IST) - timedelta(days=days)).timestamp() * 1000)
        trades_ref = self.db.collection("quantum_trades").where("timestamp", ">=", start_time).stream()
        
        trades = []
        for doc in trades_ref:
            trades.append(doc.to_dict())
            
        return pd.DataFrame(trades)

    def analyze_score_impact(self, df: pd.DataFrame):
        """Analyzes how specific conditions inside `score_breakdown` affect win rate."""
        if df.empty or 'score_breakdown' not in df.columns:
            return {}

        condition_stats = {}
        
        for _, row in df.iterrows():
            if 'score_breakdown' not in row or not isinstance(row['score_breakdown'], list):
                continue
                
            is_win = 1 if row.get('pnl', 0) > 0 else 0
            
            for condition in row['score_breakdown']:
                item_name = condition.get('item', 'Unknown')
                status = condition.get('status', 'Unknown')
                key = f"{item_name}: {status}"
                
                if key not in condition_stats:
                    condition_stats[key] = {'trades': 0, 'wins': 0}
                    
                condition_stats[key]['trades'] += 1
                condition_stats[key]['wins'] += is_win
                
        # Calculate Win Rates
        report = {}
        MIN_TRADES = 5  # AE-2 Fix: Only report conditions with at least 5 trades
        for key, stats in condition_stats.items():
            if stats['trades'] < MIN_TRADES:
                continue
            win_rate = (stats['wins'] / stats['trades']) * 100
            report[key] = {
                "trades": stats['trades'],
                "win_rate": round(win_rate, 2)
            }
            
        return report
        
if __name__ == "__main__":
    engine = AnalyticsEngine()
    df = engine.fetch_recent_trades(days=30)
    print("Fetched Trades:", len(df))
    if not df.empty:
        stats = engine.analyze_score_impact(df)
        print("--- Condition Analysis ---")
        for condition, metrics in sorted(stats.items(), key=lambda x: x[1]['win_rate'], reverse=True):
            print(f"{condition} -> {metrics['win_rate']}% Win Rate (Trades: {metrics['trades']})")
