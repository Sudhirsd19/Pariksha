import firebase_admin
from firebase_admin import credentials, firestore
import os

db = None

def init_firebase():
    global db
    cred_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "firebase_credentials.json")
    
    if not os.path.exists(cred_path):
        print(f"Warning: Firebase credentials not found at {cred_path}. Firestore features will be disabled.")
        return False
        
    try:
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("Firebase initialized successfully.")
        return True
    except Exception as e:
        print(f"Failed to initialize Firebase: {e}")
        return False

def get_db():
    return db
