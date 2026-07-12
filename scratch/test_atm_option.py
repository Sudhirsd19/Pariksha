import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from backend.utils.token_manager import token_manager

token_manager.load_scrip_master()

for symbol in ["NIFTY", "BANKNIFTY"]:
    print(f"\n--- Testing {symbol} Option Retrieval ---")
    if symbol == "NIFTY":
        test_ltps = [15000, 20000, 24150, 24180, 25000]
    else:
        test_ltps = [45000, 48000, 52000, 52100, 55000]
        
    for ltp in test_ltps:
        ce_contract = token_manager.get_atm_option(symbol, ltp, "CE")
        pe_contract = token_manager.get_atm_option(symbol, ltp, "PE")
        
        print(f"LTP: {ltp} | CE: {ce_contract['symbol'] if ce_contract else 'NOT FOUND'} ({ce_contract['token'] if ce_contract else ''}) | PE: {pe_contract['symbol'] if pe_contract else 'NOT FOUND'} ({pe_contract['token'] if pe_contract else ''})")
