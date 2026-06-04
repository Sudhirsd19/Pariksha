import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.utils.token_manager import token_manager

print("Total stocks indexed:", len(token_manager.stocks_index))
# Print first 20 stocks
for i, (name, info) in enumerate(list(token_manager.stocks_index.items())[:20]):
    print(f"{name}: {info}")

# Search for "BANK"
print("\nStocks containing 'BANK':")
count = 0
for name, info in token_manager.stocks_index.items():
    if "BANK" in name or "BANK" in info.get("symbol", ""):
        print(f" - {name}: {info}")
        count += 1
        if count >= 15:
            break
