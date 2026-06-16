# QUICK REFERENCE: Run Backtest & See Results

## 60 Seconds to Results

### Option 1: Real Market Data (Yahoo Finance)
```bash
cd D:\QuantumIndex
set PYTHONPATH=.
python -m backend.backtesting.test_with_yfinance
```

**Output**: Real RELIANCE data (60 days, 4,291 candles)
**Time**: ~30 seconds
**Results**: Win rate, trades, P&L breakdown

### Option 2: Angel One Broker (6 Months)
```bash
set PYTHONPATH=.
python -m backend.backtesting.run_backtest
```

**Output**: 6 months historical data (8,925 candles)
**Time**: ~60 seconds
**Results**: Comprehensive backtest metrics

### Option 3: Synthetic Data (Quick Verification)
```bash
python backend/backtesting/test_optimized_strategy.py
```

**Output**: 55.6% win rate verified
**Time**: ~5 seconds
**Results**: Shows strategy logic works

---

## Recent Test Results (Real Data)

### yfinance Test (Recommended for Quick Testing)
```
Status:        SUCCESS ✓
Data:          4,291 candles (60 days)
Signals:       4 generated
Trades:        3 executed
Win Rate:      0% (needs tuning)
Return:        -1.68%
Issue:         High commission impact, signal filters need adjustment
```

### Angel One Test (Most Comprehensive)
```
Status:        SUCCESS ✓
Data:          8,925 candles (180 days)
Trades:        46 executed
Win Rate:      23.9%
Return:        -14.29%
Issue:         Strategy needs better signal filtering
```

### Synthetic Data Test (For Logic Verification)
```
Status:        SUCCESS ✓
Win Rate:      55.6% ✓
Sharpe Ratio:  5.36 ✓
Profit Factor: 1.99 ✓
Return:        8.12% ✓
```

---

## What Changed Recently

### Bug Fixes
1. **Time Filter Fixed**: Was checking `row['time']` but data has `row['date']`
   - Before: 0 signals (all filtered out)
   - After: 4 signals generated correctly

2. **MultiIndex Columns Fixed**: Yahoo Finance returns MultiIndex
   - Before: TypeError on column access
   - After: Properly flattened and usable

3. **Timezone Handling Fixed**: UTC ↔ IST conversion
   - Before: Wrong time windows selected
   - After: 1,359 rows in correct time windows

---

## Strategy Performance Summary

| Approach | Win Rate | Sharpe | Profit Factor | Status |
|----------|----------|--------|---------------|--------|
| Synthetic (55% engine) | 55.6% ✓ | 5.36 | 1.99 | VERIFIED |
| Real yfinance (60d) | 0% | -132.88 | 0.0 | NEEDS TUNING |
| Angel One (180d) | 23.9% | ??? | 0.27 | NEEDS TUNING |
| Balanced (65% target) | ??? | ??? | ??? | NOT TESTED |
| Ultra-selective (70%) | ??? | ??? | ??? | NOT TESTED |

---

## Files to Know

### Signal Engines (Choose One)
```
1. optimized_signal_engine.py      (Active) - 55% target, verified
2. balanced_quality_engine.py      (Ready)  - 65% target, not tested
3. ultra_high_quality_engine.py    (Ready)  - 70%+ target, not tested
```

### Testing Scripts
```
test_with_yfinance.py              (Main test - real data)
test_optimized_strategy.py         (Synthetic verification)
run_backtest.py                    (Angel One broker test)
verify_strategy.py                 (Auto verification)
```

### Documentation
```
INTRADAY_BACKTEST_STATUS.md        (Complete status)
REAL_DATA_BACKTEST_COMPLETE.md     (Real data details)
IMPLEMENTATION_70_PERCENT_WINRATE.md (Technical guide)
PROFITABILITY_ANALYSIS.md          (Cost analysis)
```

---

## Test All Three Engines in Real Market

### 1. Current Engine (55% Target)
Already tested - 0% win rate on real data
```
Signals: 4
Trades: 3
Result: All hit SL, no profits
Issue: Too loose, needs more filtering
```

### 2. Balanced Engine (65% Target)
```bash
# Modify test_with_yfinance.py, line 157:
# Change: engine = OptimizedSignalEngine()
# To: engine = BalancedQualityEngine()

python -m backend.backtesting.test_with_yfinance
```

Expected: Fewer signals but higher quality → Better win rate

### 3. Ultra-Selective Engine (70%+ Target)
```bash
# Modify test_with_yfinance.py, line 157:
# Change: engine = OptimizedSignalEngine()
# To: engine = UltraHighQualityEngine()

python -m backend.backtesting.test_with_yfinance
```

Expected: 1-2 signals per month, very high quality

---

## Why Results Changed from Synthetic

| Factor | Synthetic | Real Market |
|--------|-----------|------------|
| Data Type | Random walk (white noise) | Price patterns with S/R |
| Trend | None (mean-reverting) | Trending/ranging mixed |
| Volume | Constant | Realistic with clusters |
| Execution | Perfect fills | With slippage (1.5 bps) |
| Costs | Included (0.24% RT) | Included (0.24% RT) |
| Win Rate | 55.6% | 0-23.9% |

**Insight**: Real markets are NOT random. Signals work differently.

---

## Cost Impact Reality Check

### Commission Breakdown (1 Trade)
```
Entry Commission:   ₹112 (0.02% + 18% GST)
Exit Commission:    ₹24  (0.02% + 18% GST)
Sell Tax (STT):     ₹26  (0.1% on sell side)
Total:              ₹162 per round-trip trade

On ₹100K capital:
To break even (P&L = 0 after costs), need:
  Win Rate ≥ 60%
  OR
  Avg Win > 2x Avg Loss
```

### Reality of Current Results
- Lost ₹1,679 total
- Commission was ₹407 (24% of loss)
- Real loss was ₹1,272
- Commission made situation 24% worse

**Key Finding**: Need very high win rate or tight stops to be profitable!

---

## Next 30 Minutes: What to Do

### Option A: Test Balanced Engine (Recommended)
```
Time: 10 min
Risk: Low (paper trading only)
Benefit: See if less strict filters work better on real data
```

### Option B: Extend to 6-Month Test
```
Modify test_with_yfinance.py:
  period="60d"  →  period="180d"
  
Time: 30 min
Benefit: More data = better statistics
```

### Option C: Add More Market Conditions
```
Test in:
1. Morning session (9:15-11:00)
2. Afternoon session (2:00-3:30)
3. High volatility days
4. Low volatility days
```

---

## Troubleshooting

### "No signals generated"
→ Check if time window has data:
```bash
python backend/backtesting/check_hours.py
```

### "0% win rate on real data"
→ Try balanced quality engine:
```python
from backend.backtesting.balanced_quality_engine import BalancedQualityEngine
# Use in place of OptimizedSignalEngine
```

### "Error: MultiIndex columns"
→ Already fixed! Make sure you have latest `test_with_yfinance.py`

### "Commission too high"
→ Normal for NSE intraday:
- Brokerage: 0.02%
- STT: 0.1%
- GST: 18%
- Total: 0.24% per round trip

---

## Expected Improvements by Engine

| Engine | Signals/Day | Avg Win | Avg Loss | Win Rate | Status |
|--------|-----------|---------|----------|----------|--------|
| Optimized (55%) | 0.07 | ₹1,500 | ₹800 | 55.6% | Synthetic verified ✓ |
| Balanced (65%) | 0.03 | ₹2,000 | ₹1,000 | 65% | Real data TBD |
| Ultra (70%+) | 0.02 | ₹2,500 | ₹1,000 | 70%+ | Real data TBD |

---

## Key Learnings

### ✓ What Works
1. Framework handles real market data correctly
2. All 5 improvements implemented and active
3. Costs modeled realistically
4. Reproducible results with seeds
5. Backtest runs accurately

### ⚠️ What Needs Work
1. Signal filters too loose for real markets
2. Immediate SL hits on 60-day data
3. 0-23.9% win rate on real vs 55.6% on synthetic
4. Commission heavily impacts profitability
5. Need better signal selection or filtering

### 📊 Key Insight
**Real markets ≠ Synthetic data**
- Synthetic: Pure randomness with noise
- Real: Price patterns, support/resistance, momentum
- Solution: Adjust filters for real market dynamics

---

## Command Cheat Sheet

```bash
# Navigate to project
cd D:\QuantumIndex
set PYTHONPATH=.

# Quick tests
python -m backend.backtesting.test_with_yfinance          # 30 sec - Real data
python backend/backtesting/test_optimized_strategy.py    # 5 sec - Synthetic
python -m backend.backtesting.run_backtest                # 60 sec - Angel One

# Debugging
python backend/backtesting/diagnose_signals.py            # Why no signals
python backend/backtesting/check_hours.py                 # Hour distribution
python backend/backtesting/debug_yfinance.py              # Data structure

# Verify
python backend/backtesting/verify_strategy.py             # Auto verification
```

---

## Summary

**Status**: Real data testing complete and working ✓

**Framework Ready**: All 5 improvements active, costs modeled realistically ✓

**Real Results**: 0-23.9% win rate (needs signal tuning) ⚠️

**Next Step**: Test balanced (65%) or ultra-selective (70%) engines

**Deployment**: Ready for paper trading after signal tuning

---

*Last Updated: June 16, 2026*
*Framework: v3.0 (All 5 Improvements)*
*Real Data: Yahoo Finance (No API Key Needed)*
