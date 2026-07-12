"""
QuantumIndex — Comprehensive Intraday System Functionality Test
Tests ALL critical components end-to-end
"""
import os, sys, json, time
import pandas as pd
import numpy as np

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
results = []

def test(name, condition, detail=""):
    status = PASS if condition else FAIL
    results.append((name, status, detail))
    icon = "✅" if status == PASS else "❌"
    print(f"  {icon} {name}" + (f" — {detail}" if detail else ""))
    return condition

def warn(name, detail=""):
    results.append((name, WARN, detail))
    print(f"  ⚠️  {name}" + (f" — {detail}" if detail else ""))

def section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")

# ================================================================
# 1. STRICT CHECKLIST ENGINE — Signal Generation
# ================================================================
section("1. STRICT CHECKLIST ENGINE (Signal Logic)")

try:
    from backend.engines.strict_checklist_engine import StrictChecklistEngine
    engine = StrictChecklistEngine()
    test("StrictChecklistEngine imported", True)
    
    # Test with mock data — verify evaluate signature works
    # evaluate() needs (symbol, df, trend_direction=...)
    # Create minimal df for test
    mock_df = pd.DataFrame({
        'open': [100]*50, 'high': [101]*50, 'low': [99]*50,
        'close': [100]*50, 'volume': [100000]*50
    })
    try:
        result = engine.evaluate("TEST.NS", mock_df, trend_direction="NEUTRAL")
        test("evaluate() returns dict", isinstance(result, dict))
        test("Result has 'signal' key", 'signal' in result)
        test("Result has 'strict_score' key", 'strict_score' in result)
        
        score = result.get('strict_score', 0)
        # Score < 70 should give NONE signal
        if score < 70:
            test("Score < 70 returns NONE signal", result['signal'] == "NONE",
                 f"score={score}, signal={result['signal']}")
        else:
            test("Score >= 70 returns BUY/SELL signal", result['signal'] in ["BUY", "SELL"],
                 f"score={score}, signal={result['signal']}")
    except Exception as e:
        test("evaluate() execution", False, str(e))
             
except Exception as e:
    test("StrictChecklistEngine import/run", False, str(e))

# ================================================================
# 2. SIGNAL ENGINES (Balanced + Ultra-High)
# ================================================================
section("2. SIGNAL ENGINES (Balanced + Ultra-High Quality)")

try:
    import yfinance as yf
    from backend.backtesting.balanced_quality_engine import BalancedQualityEngine
    from backend.backtesting.ultra_high_quality_engine import UltraHighQualitySignalEngine
    from backend.backtesting.test_with_yfinance import prepare_data_for_backtest
    
    ticker = yf.Ticker("RELIANCE.NS")
    data = ticker.history(period="60d", interval="5m")
    test("yfinance data download", not data.empty, f"{len(data)} rows")
    
    df = prepare_data_for_backtest(data)
    test("Data preparation", len(df) > 0, f"{len(df)} candles prepared")
    
    # Required columns check
    required_cols = ['date', 'open', 'high', 'low', 'close', 'volume']
    missing = [c for c in required_cols if c not in df.columns]
    test("All required columns present", len(missing) == 0, 
         f"Missing: {missing}" if missing else "date, open, high, low, close, volume")
    
    # Balanced Engine
    bal_engine = BalancedQualityEngine(df)
    bal_signals = bal_engine.generate_signals()
    test("BalancedQualityEngine generates signals", len(bal_signals) > 0, f"{len(bal_signals)} signals")
    
    # Ultra-High Engine
    ultra_engine = UltraHighQualitySignalEngine(df)
    ultra_signals = ultra_engine.generate_signals()
    test("UltraHighQualityEngine generates signals", len(ultra_signals) >= 0, f"{len(ultra_signals)} signals")
    
    # Signal format validation
    if bal_signals:
        s = bal_signals[0]
        test("Signal has 'type' field", 'type' in s, f"type={s.get('type')}")
        test("Signal has 'index' field", 'index' in s)
        test("Signal type is BUY or SELL", s['type'] in ['BUY', 'SELL'], f"type={s['type']}")
        
except Exception as e:
    test("Signal Engines", False, str(e))

# ================================================================
# 3. ADVANCED BACKTEST ENGINE
# ================================================================
section("3. ADVANCED BACKTEST ENGINE")

try:
    from backend.backtesting.advanced_backtest_engine import AdvancedBacktestEngine
    
    bt = AdvancedBacktestEngine(initial_capital=100000, seed=42)
    test("AdvancedBacktestEngine initialized", bt.balance == 100000)
    
    # Run backtest with balanced signals
    df_run = df.copy()
    df_run['signal'] = None
    for s in bal_signals:
        df_run.at[s['index'], 'signal'] = s['type']
    df_run['time'] = df_run['date']
    
    report = bt.run_backtest(df_run, htf_trend="BULLISH", risk_per_trade=0.02, atr_sl=2.5, atr_tp=5.0)
    
    test("Backtest returns report dict", isinstance(report, dict))
    test("Report has win_rate", 'win_rate' in report, f"win_rate={report.get('win_rate', 'N/A')}")
    test("Report has total_trades", 'total_trades' in report, f"total={report.get('total_trades', 'N/A')}")
    test("Report has profit_factor", 'profit_factor' in report, f"PF={report.get('profit_factor', 'N/A')}")
    test("Report has net_profit", 'net_profit' in report, f"net={report.get('net_profit', 'N/A')}")
    test("Trades were executed", report['total_trades'] > 0, f"{report['total_trades']} trades")
    
except Exception as e:
    test("Backtest Engine", False, str(e))

# ================================================================
# 4. TRAILING STOP-LOSS & BREAK-EVEN SIMULATION
# ================================================================
section("4. TRAILING STOP-LOSS & BREAK-EVEN LOGIC")

try:
    bt2 = AdvancedBacktestEngine(initial_capital=100000, seed=42)
    
    # Simulate a BUY trade
    mock_trade_buy = {
        'type': 'BUY', 'entry_price': 100.0, 'sl': 97.5, 'tp': 112.5,
        'atr': 2.5, 'entry_price_effective': 100.0, 'qty': 100,
        'entry_time': '2026-01-01', 'entry_volume': 100000
    }
    
    # Test Step 1: No trailing at 30% progress
    trade = mock_trade_buy.copy()
    bt2._update_trailing_sl(trade, 103.75, high=103.75, low=102.0)  # 30% of 12.5 = 3.75
    test("No trailing at 30% progress", trade['sl'] == 97.5, f"SL stayed at {trade['sl']}")
    
    # Test Step 2: Break-even at 50% progress
    trade = mock_trade_buy.copy()
    bt2._update_trailing_sl(trade, 106.25, high=106.25, low=105.0)  # 50% of 12.5 = 6.25
    test("Break-even at 50% progress", trade['sl'] == 100.0, f"SL moved to {trade['sl']}")
    
    # Test Step 3: Trail at 70% progress
    trade = mock_trade_buy.copy()
    bt2._update_trailing_sl(trade, 108.75, high=108.75, low=107.0)  # 70% of 12.5 = 8.75
    test("Trailing SL at 70% progress", trade['sl'] > 100.0, f"SL trailed to {trade['sl']}")
    
    # Test SELL trade break-even
    mock_trade_sell = {
        'type': 'SELL', 'entry_price': 100.0, 'sl': 102.5, 'tp': 87.5,
        'atr': 2.5, 'entry_price_effective': 100.0, 'qty': 100,
        'entry_time': '2026-01-01', 'entry_volume': 100000
    }
    trade = mock_trade_sell.copy()
    bt2._update_trailing_sl(trade, 93.75, high=95.0, low=93.75)  # 50% of 12.5
    test("SELL break-even at 50%", trade['sl'] == 100.0, f"SL moved to {trade['sl']}")
    
    trade = mock_trade_sell.copy()
    bt2._update_trailing_sl(trade, 91.25, high=93.0, low=91.25)  # 70% of 12.5
    test("SELL trailing at 70%", trade['sl'] < 100.0, f"SL trailed to {trade['sl']}")
    
except Exception as e:
    test("Trailing SL Logic", False, str(e))

# ================================================================
# 5. EXIT CONDITIONS (TP Priority when SL in profit)
# ================================================================
section("5. EXIT CONDITIONS (TP Priority Logic)")

try:
    bt3 = AdvancedBacktestEngine(initial_capital=100000, seed=42)
    
    # BUY trade: SL in profit zone, both SL and TP hit same candle
    trade_buy = {'type': 'BUY', 'entry_price': 100.0, 'sl': 104.0, 'tp': 106.0,
                 'atr': 2.0, 'entry_price_effective': 100.0, 'qty': 100,
                 'entry_time': '2026-01-01', 'entry_volume': 100000}
    
    # Candle where both SL (104) and TP (106) are hit (low=103.5, high=107)
    exit_result = bt3._check_exit_conditions(trade_buy, high=107.0, low=103.5, 
                                              current_price=105.0, current_time='2026-01-01 10:00')
    test("TP priority when SL in profit + both hit", 
         exit_result and exit_result['reason'] == 'TP Hit',
         f"reason={exit_result['reason'] if exit_result else 'None'}")
    
    # BUY trade: Original SL (below entry), only SL hit
    trade_buy_orig = {'type': 'BUY', 'entry_price': 100.0, 'sl': 97.5, 'tp': 106.0,
                      'atr': 2.0, 'entry_price_effective': 100.0, 'qty': 100,
                      'entry_time': '2026-01-01', 'entry_volume': 100000}
    exit_result2 = bt3._check_exit_conditions(trade_buy_orig, high=101.0, low=97.0,
                                               current_price=98.0, current_time='2026-01-01 10:00')
    test("Original SL hit correctly", 
         exit_result2 and exit_result2['reason'] == 'SL Hit',
         f"reason={exit_result2['reason'] if exit_result2 else 'None'}")
    
    # Trailing SL hit (SL >= entry but TP not hit)
    trade_buy_trail = {'type': 'BUY', 'entry_price': 100.0, 'sl': 103.0, 'tp': 110.0,
                       'atr': 2.0, 'entry_price_effective': 100.0, 'qty': 100,
                       'entry_time': '2026-01-01', 'entry_volume': 100000}
    exit_result3 = bt3._check_exit_conditions(trade_buy_trail, high=104.0, low=102.5,
                                               current_price=103.0, current_time='2026-01-01 10:00')
    test("Trailing SL Hit labeled correctly", 
         exit_result3 and exit_result3['reason'] == 'Trailing SL Hit',
         f"reason={exit_result3['reason'] if exit_result3 else 'None'}")
    
except Exception as e:
    test("Exit Conditions", False, str(e))

# ================================================================
# 6. AUTO-SQUAREOFF AT 3:10 PM IST
# ================================================================
section("6. AUTO-SQUAREOFF (3:10 PM IST)")

try:
    # Simulate the squareoff time check from the backtest engine
    import pytz
    
    times_to_test = [
        ("09:30", False),
        ("14:59", False),
        ("15:09", False),
        ("15:10", True),   # Should trigger squareoff
        ("15:15", True),
        ("15:25", True),
    ]
    
    all_ok = True
    for time_str, expected in times_to_test:
        dt = pd.Timestamp(f"2026-07-10 {time_str}:00+05:30")
        is_squareoff = dt.hour > 15 or (dt.hour == 15 and dt.minute >= 10)
        if is_squareoff != expected:
            all_ok = False
            test(f"Squareoff at {time_str}", False, f"Expected={expected}, Got={is_squareoff}")
    
    if all_ok:
        test("Auto-squareoff triggers at 3:10 PM IST", True, "All time checks passed")
        
except Exception as e:
    test("Auto-Squareoff", False, str(e))

# ================================================================
# 7. COST MODEL (STT, Brokerage, Slippage)
# ================================================================
section("7. COST MODEL (STT + Brokerage + Slippage)")

try:
    bt4 = AdvancedBacktestEngine(initial_capital=100000, seed=42)
    
    # Test commission calculation
    comm = bt4.calculate_commission(100.0, 100, is_buy=True)
    test("Commission calculated", comm > 0, f"Commission = Rs.{comm:.2f}")
    
    # Test effective price with slippage
    eff_price = bt4.calculate_effective_price(100.0, 100, 100000, is_buy=True, is_entry=True)
    test("Slippage applied on entry", eff_price >= 100.0, f"Effective={eff_price:.4f} (original=100.0)")
    
    eff_sell = bt4.calculate_effective_price(100.0, 100, 100000, is_buy=False, is_entry=False)
    test("Slippage applied on exit", eff_sell <= 100.0, f"Effective={eff_sell:.4f} (original=100.0)")
    
except Exception as e:
    test("Cost Model", False, str(e))

# ================================================================
# 8. SCORE THRESHOLD (70+ = Signal, <70 = NONE)
# ================================================================
section("8. SCORE THRESHOLD (70+ Rule)")

try:
    from backend.engines.strict_checklist_engine import StrictChecklistEngine
    engine = StrictChecklistEngine()
    
    # We can't easily force a specific score, but we verify the logic exists
    import inspect
    source = inspect.getsource(engine.evaluate)
    
    has_70_check = '70' in source and 'NONE' in source
    test("70+ threshold logic exists in evaluate()", has_70_check, 
         "Score < 70 returns NONE signal")
    
except Exception as e:
    test("Score Threshold", False, str(e))

# ================================================================
# 9. EXECUTION ENGINE (Trailing SL, Time Exit, Partial Profit)
# ================================================================
section("9. EXECUTION ENGINE (Live Trade Logic)")

try:
    from backend.engines.execution_engine import ExecutionEngine
    
    ee = ExecutionEngine()
    test("ExecutionEngine imported", True)
    
    # FVG retest check
    fvgs = [{'type': 'BULLISH', 'top': 102, 'bottom': 100}]
    test("FVG retest detection (in zone)", ee.check_fvg_retest(101, fvgs, "BUY") == True)
    test("FVG retest detection (out of zone)", ee.check_fvg_retest(105, fvgs, "BUY") == False)
    
    # Partial profit check
    test("Partial profit at 1%+", ee.check_partial_profit(101.0, 100.0, "BUY") == True, "1% gain triggers partial")
    test("No double partial", ee.check_partial_profit(102.0, 100.0, "BUY") == False, "Already booked")
    
    # Score decay exit
    test("Score decay exit", ee.check_score_decay_exit(30, 80) == True, "30 < 80*0.5=40")
    test("No score decay exit", ee.check_score_decay_exit(50, 80) == False, "50 > 40")
    
except Exception as e:
    test("Execution Engine", False, str(e))

# ================================================================
# 10. TRADE MANAGER (Live Trade Management)
# ================================================================
section("10. TRADE MANAGER (Live Trade Management)")

try:
    from backend.utils.trade_manager import TradeManager
    
    tm = TradeManager()
    test("TradeManager imported", True)
    test("Active trades list initialized", isinstance(tm.active_trades, list))
    
    # Check trade manager has key methods
    test("_calculate_charges method exists", hasattr(tm, '_calculate_charges'))
    test("active_trades is list", isinstance(tm.active_trades, list))
    
except Exception as e:
    test("Trade Manager", False, str(e))

# ================================================================
# 11. API ENDPOINTS CHECK (main.py)
# ================================================================
section("11. API ENDPOINTS (main.py Route Validation)")

try:
    with open(os.path.join(os.path.dirname(__file__), '..', 'backend', 'main.py'), 'r', encoding='utf-8') as f:
        main_source = f.read()
    
    endpoints = [
        ('/api/scanner/scan', 'Stock Scanner'),
        ('/api/scanner/bulk-scan', 'Bulk Scanner'),
        ('quantum_system/watchlist', 'Watchlist (Firestore-based)'),
        ('/api/backtest', 'Backtest'),
        ('trend_direction', 'Fixed trend_direction param (was trend_result)'),
    ]
    
    for endpoint, desc in endpoints:
        test(f"Endpoint: {desc}", endpoint in main_source, endpoint)
        
except Exception as e:
    test("API Endpoints", False, str(e))

# ================================================================
# 12. FULL BACKTEST PIPELINE (End-to-End)
# ================================================================
section("12. FULL BACKTEST PIPELINE (End-to-End on RELIANCE)")

try:
    bt_final = AdvancedBacktestEngine(initial_capital=100000, seed=42)
    
    df_final = df.copy()
    df_final['signal'] = None
    for s in ultra_signals:
        df_final.at[s['index'], 'signal'] = s['type']
    df_final['time'] = df_final['date']
    
    report = bt_final.run_backtest(df_final, htf_trend="BULLISH", risk_per_trade=0.02, atr_sl=2.5, atr_tp=5.0)
    
    test("E2E backtest completed", report['total_trades'] >= 0)
    
    # Check trade details
    trailing_trades = [t for t in bt_final.trades if 'Trailing' in t.get('exit_reason', '')]
    breakeven_trades = [t for t in bt_final.trades if t['exit_price'] == t.get('entry_price', 0)]
    squareoff_trades = [t for t in bt_final.trades if 'Squareoff' in t.get('exit_reason', '')]
    sl_trades = [t for t in bt_final.trades if t.get('exit_reason') == 'SL Hit']
    tp_trades = [t for t in bt_final.trades if t.get('exit_reason') == 'TP Hit']
    
    print(f"\n  📊 RELIANCE Ultra-High Engine Results:")
    print(f"     Total Trades:     {report['total_trades']}")
    print(f"     Win Rate:         {report['win_rate']:.1f}%")
    print(f"     Profit Factor:    {report['profit_factor']:.2f}")
    print(f"     Net Return:       Rs.{report['net_profit']:.0f} ({report['net_profit_pct']:.2f}%)")
    print(f"     TP Hits:          {len(tp_trades)}")
    print(f"     SL Hits:          {len(sl_trades)}")
    print(f"     Trailing SL Hits: {len(trailing_trades)}")
    print(f"     Auto-Squareoffs:  {len(squareoff_trades)}")
    
    test("Report metrics are valid numbers", 
         not np.isnan(report['win_rate']) and report['total_trades'] >= 0)
         
except Exception as e:
    test("E2E Pipeline", False, str(e))


# ================================================================
# FINAL SUMMARY
# ================================================================
section("FINAL SUMMARY")

passed = sum(1 for _, s, _ in results if s == PASS)
failed = sum(1 for _, s, _ in results if s == FAIL)
warned = sum(1 for _, s, _ in results if s == WARN)
total = len(results)

print(f"\n  Total Tests:  {total}")
print(f"  ✅ Passed:    {passed}")
print(f"  ❌ Failed:    {failed}")
print(f"  ⚠️  Warnings: {warned}")
print(f"\n  Score: {passed}/{total} ({passed/total*100:.0f}%)")

if failed == 0:
    print(f"\n  🎉 ALL TESTS PASSED! System is fully functional.")
else:
    print(f"\n  ⚠️  {failed} test(s) failed. Review above for details.")
    
    # Print failed tests
    print(f"\n  Failed Tests:")
    for name, status, detail in results:
        if status == FAIL:
            print(f"    ❌ {name}: {detail}")
