import sys
import os
import time
import socket

# Monkey-patch socket.getaddrinfo to force IPv4
original_getaddrinfo = socket.getaddrinfo

def ipv4_only_getaddrinfo(*args, **kwargs):
    args = list(args)
    # Ensure family is socket.AF_INET (index 2 in positional args)
    if len(args) > 2:
        args[2] = socket.AF_INET
    else:
        kwargs['family'] = socket.AF_INET
    return original_getaddrinfo(*args, **kwargs)

socket.getaddrinfo = ipv4_only_getaddrinfo

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config.firebase_config import init_firebase, get_db
from firebase_admin import messaging

print("Initializing Firebase...")
success = init_firebase()
print(f"Firebase initialized: {success}")

db = get_db()
if db:
    print("Testing Firestore write...")
    try:
        t0 = time.time()
        doc_ref = db.collection("test_connection").document("test_doc")
        doc_ref.set({"timestamp": int(time.time()), "status": "ok"})
        print(f"SUCCESS: Firestore write completed in {time.time() - t0:.2f} seconds!")
    except Exception as e:
        print(f"FAILED: Firestore write: {e}")
else:
    print("Firestore client is None!")

print("Testing FCM send...")
try:
    t0 = time.time()
    message = messaging.Message(
        notification=messaging.Notification(
            title="Test Title",
            body="Test Body",
        ),
        topic='trading_alerts',
    )
    print("Sending message via FCM...")
    response = messaging.send(message)
    print(f"SUCCESS: FCM send completed in {time.time() - t0:.2f} seconds! Response: {response}")
except Exception as e:
    print(f"FAILED: FCM send: {e}")
