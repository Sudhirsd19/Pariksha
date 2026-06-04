from backend.config.firebase_config import init_firebase, get_db

init_firebase()
db = get_db()
if db:
    doc_ref = db.collection("quantum_system").document("settings")
    doc = doc_ref.get()
    if doc.exists:
        print("Current Firestore settings:")
        print(doc.to_dict())
    else:
        print("No settings document found in Firestore.")
else:
    print("Could not initialize Firebase database.")
