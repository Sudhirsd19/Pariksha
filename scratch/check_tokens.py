import os
import json

token_file = 'backend/config/tokens.json'
print("Exists:", os.path.exists(token_file))
if os.path.exists(token_file):
    with open(token_file, 'r') as f:
        print("Content:", json.load(f))
