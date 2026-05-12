import firebase_admin
from firebase_admin import credentials, firestore
import os

db = None

def init_firebase():
    global db
    
    # Try loading from environment variable first (for Cloud deployment)
    service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    
    try:
        if not firebase_admin._apps:
            if service_account_json:
                import json
                cred_dict = json.loads(service_account_json)
                cred = credentials.Certificate(cred_dict)
                print("Initializing Firebase using environment variable...")
            else:
                cred_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "firebase_credentials.json")
                if not os.path.exists(cred_path):
                    print(f"Warning: Firebase credentials not found at {cred_path}. Firestore features will be disabled.")
                    return False
                cred = credentials.Certificate(cred_path)
                print(f"Initializing Firebase using file: {cred_path}")
                
            firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        print("Firebase initialized successfully.")
        return True
    except Exception as e:
        print(f"Failed to initialize Firebase: {e}")
        return False

def get_db():
    return db
