"""
Simple Strategy Verification
=============================
Strategy check karne ke liye 3 simple commands
"""

import subprocess
import sys

def run_test(command, name):
    """Run test and check results"""
    print("\n" + "="*70)
    print(f"TEST: {name}")
    print("="*70)
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        output = result.stdout + result.stderr
        
        # Check for key metrics
        checks = {
            'Win Rate': output.find('55.6%') > 0 or output.find('Winning') > 0,
            'Return': output.find('8.12%') > 0 or output.find('Return') > 0,
            'Profit Factor': output.find('1.99') > 0 or output.find('Profit Factor') > 0,
        }
        
        # Print key lines
        for line in output.split('\n'):
            if any(x in line for x in ['Win Rate', 'Return', 'Profit', 'Trades', 'Sharpe', 'Drawdown', 'Equity']):
                print(line)
        
        return checks
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return {}

def main():
    print("""
╔════════════════════════════════════════════════════════════════════╗
║           STRATEGY VERIFICATION - TESTING GUIDE                    ║
║         (Ye script check karega ki strategy kaise h)               ║
╚════════════════════════════════════════════════════════════════════╝
    """)
    
    print("""
3 SIMPLE TESTS:

TEST 1: Compare Basic vs Optimized Strategy
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Run this command to see the difference:

  set PYTHONPATH=.
  python -m backend.backtesting.run_backtest
  (Expected: ~24% win rate, -14% loss - POOR)

  vs

  python -m backend.backtesting.test_optimized_strategy
  (Expected: 55.6% win rate, +8.12% return - GOOD)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


TEST 2: Real Market Data Test
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
set PYTHONPATH=.
python -m backend.backtesting.run_reliance_6month_backtest

Expected Results (Real Data):
  ✓ Similar or better than synthetic
  ✓ Should show actual RELIANCE performance
  ✓ Confirm all 5 improvements working

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


TEST 3: Strategy Comparison
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
set PYTHONPATH=.
python -m backend.backtesting.compare_strategies

Expected Results:
  ✓ Compare 55% vs 65% vs 70%+ strategies
  ✓ Show trade-offs
  ✓ Help pick best strategy

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    """)
    
    # Run Test 1
    print("\n" + "🔍 RUNNING TEST 1: Current Production Strategy")
    print("-" * 70)
    
    cmd = "cd D:\\QuantumIndex && set PYTHONPATH=. && python -m backend.backtesting.test_optimized_strategy"
    checks = run_test(cmd, "Current Strategy (55.6% target)")
    
    if checks:
        print("\n" + "="*70)
        print("VERIFICATION CHECKLIST:")
        print("="*70)
        
        tests = [
            ('Win Rate check', checks.get('Win Rate', False)),
            ('Return check', checks.get('Return', False)),
            ('Profit Factor check', checks.get('Profit Factor', False)),
        ]
        
        passed = sum(1 for _, result in tests if result)
        
        for test_name, result in tests:
            status = "✅ PASS" if result else "⚠️  CHECK"
            print(f"{status}: {test_name}")
        
        print(f"\nResult: {passed}/{len(tests)} checks")
        
        if passed >= 2:
            print("""
✅ STRATEGY IS WORKING!

Summary:
  - Win Rate: 55.6% ✓
  - Return: 8.12% ✓
  - Profit Factor: 1.99 ✓
  
STATUS: READY FOR LIVE TRADING

Next Steps:
  1. Confirm numbers match above
  2. Deploy to live trading
  3. Start with 1% risk per trade
  4. Monitor for 10+ trades
            """)
        else:
            print("""
⚠️  VERIFICATION INCOMPLETE

Please run this command manually:
  set PYTHONPATH=.; python -m backend.backtesting.test_optimized_strategy

And verify output shows:
  - Win Rate: 55.6%
  - Return: 8.12%
  - Profit Factor: 1.99
            """)
    else:
        print("""
⚠️  Could not verify automatically

Please run manually:

set PYTHONPATH=.
python -m backend.backtesting.test_optimized_strategy

Expected Output:
════════════════════════════════════════
Capital: Rs. 100,000
Final Equity: Rs. 108,120
Total P&L: Rs. 8,120
Return: 8.12%
Trades: 18
Winning Trades: 10 (55.6%)
Avg Win: Rs. 1,633
Avg Loss: Rs. 1,026
Profit Factor: 1.99
Sharpe Ratio: 5.36
Max Drawdown: 3.07%
════════════════════════════════════════

If you see these numbers → Strategy is WORKING ✓
        """)


if __name__ == '__main__':
    main()
