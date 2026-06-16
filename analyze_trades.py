"""
Analyze trade logs to identify profitability issues
"""
import pandas as pd
import os

report_dir = "backend/backtesting/reports"

if os.path.exists(report_dir):
    files = [f for f in os.listdir(report_dir) if f.startswith("trade_log")]
    if files:
        latest = sorted(files)[-1]
        df = pd.read_csv(f"{report_dir}/{latest}")
        
        print("\n" + "="*80)
        print("TRADE ANALYSIS - IDENTIFYING PROBLEMS")
        print("="*80)
        
        print(f"\nTotal trades: {len(df)}")
        print(f"Winners: {len(df[df['net_pnl'] > 0])}")
        print(f"Losers: {len(df[df['net_pnl'] <= 0])}")
        
        if len(df) > 0:
            print(f"\nAverage win: Rs. {df[df['net_pnl'] > 0]['net_pnl'].mean():.0f}")
            print(f"Average loss: Rs. {df[df['net_pnl'] <= 0]['net_pnl'].mean():.0f}")
            
            print(f"\nBY EXIT REASON:")
            for reason in df['exit_reason'].unique():
                subset = df[df['exit_reason'] == reason]
                win_rate = len(subset[subset['net_pnl'] > 0]) / len(subset) * 100
                avg_pnl = subset['net_pnl'].mean()
                total_pnl = subset['net_pnl'].sum()
                print(f"  {reason:15} {len(subset):4d} trades | Win%: {win_rate:5.1f}% | Avg: Rs. {avg_pnl:7.0f} | Total: Rs. {total_pnl:8.0f}")
            
            print(f"\nBY TRADE TYPE:")
            for ttype in df['type'].unique():
                subset = df[df['type'] == ttype]
                win_rate = len(subset[subset['net_pnl'] > 0]) / len(subset) * 100
                avg_pnl = subset['net_pnl'].mean()
                total_pnl = subset['net_pnl'].sum()
                print(f"  {ttype:6} {len(subset):4d} trades | Win%: {win_rate:5.1f}% | Avg: Rs. {avg_pnl:7.0f} | Total: Rs. {total_pnl:8.0f}")
            
            print(f"\nPROFITABILITY ISSUES IDENTIFIED:")
            print(f"─" * 80)
            
            # Issue 1: Average loss > average win
            avg_win = df[df['net_pnl'] > 0]['net_pnl'].mean()
            avg_loss = abs(df[df['net_pnl'] <= 0]['net_pnl'].mean())
            print(f"\n1. Avg Win vs Avg Loss Ratio:")
            print(f"   Average Win:  Rs. {avg_win:.0f}")
            print(f"   Average Loss: Rs. {avg_loss:.0f}")
            print(f"   Ratio: 1 : {avg_loss/avg_win:.2f} (should be 1 : 0.5 or less)")
            if avg_loss > avg_win * 1.5:
                print(f"   ❌ PROBLEM: Losses are too large relative to wins!")
            
            # Issue 2: SL Hit vs TP Hit
            sl_hits = len(df[df['exit_reason'] == 'SL Hit'])
            tp_hits = len(df[df['exit_reason'] == 'TP Hit'])
            if sl_hits > 0:
                sl_win_rate = len(df[(df['exit_reason'] == 'SL Hit') & (df['net_pnl'] > 0)]) / sl_hits * 100
                print(f"\n2. Stop Loss Effectiveness:")
                print(f"   SL Hits: {sl_hits} trades")
                print(f"   Win Rate on SL: {sl_win_rate:.1f}%")
                if sl_win_rate > 0:
                    print(f"   ❌ PROBLEM: SL should never produce wins (SL = loss limit)!")
            
            # Issue 3: Commission impact
            total_commission = df['entry_commission'].sum() + df['exit_commission'].sum()
            total_gross_pnl = df['gross_pnl'].sum()
            print(f"\n3. Commission Impact:")
            print(f"   Total Commission: Rs. {total_commission:.0f}")
            print(f"   Gross PnL: Rs. {total_gross_pnl:.0f}")
            print(f"   Net PnL: Rs. {total_gross_pnl - total_commission:.0f}")
            if abs(total_commission) > abs(total_gross_pnl) * 0.3:
                print(f"   ❌ PROBLEM: Commission is eating {total_commission/abs(total_gross_pnl)*100:.0f}% of profits!")
            
            # Issue 4: Entry quality
            print(f"\n4. Entry Quality Analysis:")
            df_sort = df.sort_values('net_pnl')
            print(f"   Top 5 losers (how much are we losing per bad entry):")
            for idx, row in df_sort.head(5).iterrows():
                print(f"   {row['type']:6} {row['entry_price']:8.2f} → {row['exit_price']:8.2f} | Loss: Rs. {row['net_pnl']:7.0f} | Reason: {row['exit_reason']}")

else:
    print("No trade reports found")
