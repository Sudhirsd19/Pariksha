import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))
from backend.utils.token_manager import token_manager

token_manager.load_scrip_master()
print("NIFTY CE strikes in options_index:")
nifty_ce = token_manager.options_index.get("NIFTY", {}).get("CE", {})
print("Number of strikes:", len(nifty_ce))
print("First 10 strikes:", sorted(list(nifty_ce.keys()))[:10])
print("First strike contracts count:", len(nifty_ce[sorted(list(nifty_ce.keys()))[0]]) if nifty_ce else 0)

print("\nBANKNIFTY CE strikes in options_index:")
bn_ce = token_manager.options_index.get("BANKNIFTY", {}).get("CE", {})
print("Number of strikes:", len(bn_ce))
print("First 10 strikes:", sorted(list(bn_ce.keys()))[:10])
