import requests
try:
    response = requests.post("http://localhost:8000/toggle-trading?active=true")
    print(f"Response: {response.json()}")
except Exception as e:
    print(f"Error: {e}")
