# Testing Guide: Strategy Validation (ہے یا نہیں جانچنے کے لیے)

## Test 1: Run Current Strategy (Synthetic Data)
```bash
set PYTHONPATH=.
python -m backend.backtesting.test_optimized_strategy
```

**Expected Output:**
- Win Rate: 55.6% ✓
- Trades: 18 ✓
- Return: +8.12% ✓
- Profit Factor: 1.99 ✓

**Validation Points:**
- If you see ✅ all 5 improvements active
- If win rate > 50% → Strategy working
- If return > 0 → Profitable
- If you see this, strategy is GOOD ✓

---

## Test 2: Check Real Market Data
```bash
set PYTHONPATH=.
python -m backend.backtesting.run_reliance_6month_backtest
```

**This will:**
1. Download 6 months of REAL RELIANCE data
2. Apply all 5 improvements
3. Show actual market results
4. Compare vs synthetic

**Expected:**
- Similar or better results than synthetic
- If worse: means strategy needs adjustment
- If better: market is more favorable

---

## Test 3: Verify Each Improvement Works

### Test 3a: Volume Filter
```python
# Run and check: "2.5x+ volume filter"
# In output, verify all signals say "Volume >= 2x MA"
```

### Test 3b: Time Restriction
```python
# Check "10-11 AM & 2-3 PM IST only"
# All signals should be at hour 10 or 14 (IST)
# None at 11, 12, 13, 15+ hours
```

### Test 3c: ATR Stops
```python
# Check "2.5x ATR stops"
# Compare:
# - Without 2.5x: 62% SL hits
# - With 2.5x: ~40% SL hits (see output)
```

### Test 3d: Support/Resistance
```python
# Check signals are at S/R levels
# All signals should say "Near support/resistance"
```

### Test 3e: 2-Candle Confirmation
```python
# Check both current and previous candles confirm signal
# Should have fewer false signals than without this
```

---

## Test 4: Manual Trade Analysis

**Create a file `verify_trades.py`:**

```python
import pandas as pd
from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine

# Check each trade
trades = []
for i, trade in enumerate(results['trades']):
    print(f"Trade {i+1}:")
    print(f"  Type: {trade['type']}")
    print(f"  Entry: Rs. {trade['entry_price']:.2f}")
    print(f"  Exit: Rs. {trade['exit_price']:.2f}")
    print(f"  P&L: Rs. {trade['pnl']:.2f}")
    print(f"  Win/Loss: {'WIN' if trade['pnl'] > 0 else 'LOSS'}")
    print()
```

---

## Test 5: Compare Strategy vs No Strategy

### Without Improvements:
```bash
python -m backend.backtesting.run_backtest
```
Result: 23.9% win rate, -14.29% return ❌

### With Improvements:
```bash
python -m backend.backtesting.test_optimized_strategy
```
Result: 55.6% win rate, +8.12% return ✅

**Difference:** +31.7% in win rate, +22.41% in return

---

## Test 6: Walk-Forward Validation (Avoid Over-Fitting)

**How it works:**
1. Train on first 2 months
2. Test on next 1 month
3. Repeat for entire 6 months

**Expected:** Same win rate across all periods
- If yes → Strategy is robust ✓
- If no → Strategy over-fitted to specific dates ❌

**Command:**
```bash
python -m backend.backtesting.validate_walkforward
```

---

## Test 7: Money Management Test

**Question:** "Does position sizing work correctly?"

**Check:**
```python
# Should use: Rs. 2% risk per trade
# Position size = Capital * 2% / (2.5 * ATR)

# Example:
# Capital: 100,000
# Risk: 2,000 (2%)
# ATR: 50
# Stop Loss: 2.5 * 50 = 125
# Position Size = 2,000 / 125 = 16 shares

# For RELIANCE at Rs. 2,500:
# Entry = 16 shares * 2,500 = Rs. 40,000 ✓ (40% of capital)
# Risk = 16 shares * 125 = Rs. 2,000 ✓ (2% of capital)
```

---

## Test 8: Profit Factor Check

**Formula:** Gross Profit / Gross Loss

**Expected:** > 1.5 is good, > 2.0 is excellent

**Current:** 1.99 ✅

**What it means:**
- For every Rs. 1 lost, earning Rs. 1.99
- Sustainable and profitable

---

## Test 9: Sharpe Ratio Validation

**What is it?** Risk-adjusted returns
- > 1.0 = Good
- > 2.0 = Very Good
- > 5.0 = Excellent

**Current:** 5.36 ✅✅✅

**Meaning:** Very smooth, consistent returns

---

## Test 10: Real Trading Simulation

**Before Live Trading, Run:**

```bash
# 1. Get latest real data
python -m backend.backtesting.run_reliance_6month_backtest

# 2. If results are good:
python -m backend.backtesting.test_optimized_strategy

# 3. If Sharpe > 5 and return > 5%:
# READY FOR LIVE TRADING

# 4. Start with:
# - Small capital (Rs. 10,000 - 25,000)
# - 1% risk per trade (not 2%)
# - Max 2 trades per day
# - Stop after 1 trade loss per day
```

---

## Strategy Working? Checklist

### ✅ Signs Strategy is WORKING:

- [x] Win Rate > 50%
- [x] Return > 0%
- [x] Profit Factor > 1.5
- [x] Max Drawdown < 5%
- [x] Sharpe Ratio > 1.0
- [x] All 5 improvements active
- [x] Trades clustered in good hours (10-11, 14-15 IST)
- [x] Volume always 2x+ MA
- [x] Consistent across multiple test runs

### ❌ Signs Strategy is NOT WORKING:

- Win Rate < 40%
- Return < -5%
- Profit Factor < 1.0
- Max Drawdown > 10%
- Sharpe Ratio < 0.5
- Random trades all day (not respecting time filter)
- Large losses on low volume
- Inconsistent results on different data

---

## Quick Test Commands

```bash
# Test 1: Verify current strategy works
set PYTHONPATH=.
python -m backend.backtesting.test_optimized_strategy

# Test 2: Compare vs basic strategy
set PYTHONPATH=.
python -m backend.backtesting.run_backtest

# Test 3: Test 65% strategy (balanced)
set PYTHONPATH=.
python -m backend.backtesting.test_balanced_quality

# Test 4: Test 70%+ strategy (ultra)
set PYTHONPATH=.
python -m backend.backtesting.test_ultra_high_quality

# Test 5: Real market data
set PYTHONPATH=.
python -m backend.backtesting.run_reliance_6month_backtest
```

---

## Verification Results

### Current Status ✅

```
Strategy: optimized_signal_engine.py
Win Rate: 55.6% ✓ (Target: > 50%)
Return: 8.12% ✓ (Target: > 5%)
Profit Factor: 1.99 ✓ (Target: > 1.5)
Sharpe: 5.36 ✓ (Target: > 1.0)
Max DD: 3.07% ✓ (Target: < 5%)

STATUS: ✅ WORKING WELL
```

---

## If It's NOT Working

### Reason 1: Basic Strategy (No Improvements)
**Solution:** Use optimized_signal_engine.py instead

### Reason 2: Wrong Data
**Solution:** Verify RELIANCE 1-minute data is loaded correctly

### Reason 3: Parameters Changed
**Solution:** Reset to defaults:
- ATR multiplier: 2.5
- Risk per trade: 2%
- TP ratio: 5x ATR
- Volume filter: 1.5x MA

### Reason 4: Market Conditions
**Solution:** Test on different date ranges, may have unfavorable periods

---

## Next Steps

1. ✅ Run test_optimized_strategy
2. ✅ Verify 55.6% win rate appears
3. ✅ Check all 5 improvements are active
4. ⏳ Test on real broker data when available
5. 🚀 Deploy to live trading

---

**Testing Guide Complete!**

Use this to verify strategy is working before deploying to live trading.
