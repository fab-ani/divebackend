import os
from dotenv import load_dotenv
import firebase_admin
from flask import Flask, request, jsonify
from firebase_admin import credentials, firestore, messaging  
from datetime import datetime, timezone
  
app = Flask(__name__)

load_dotenv() 
if not firebase_admin._apps:
    cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if cred_path  and os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)

db = firestore.client()
          
SEND_INTERVAL_SECONDS = 120  # 2 minutes


# === Add to Buffer ===
@app.route("/add_to_buffer", methods=["POST"])
def add_to_buffer():
    data = request.get_json()
    community_id = data.get("communityId")
    sender_id = data.get("senderId")
    sender_name = data.get("senderName")
    text = data.get("text")

    if not all([community_id, sender_id, sender_name, text]):
        return jsonify({"error": "Missing required fields"}), 400

    buffer_ref = db.collection("notification_buffer").document(community_id)
    buffer_doc = buffer_ref.get()

    if buffer_doc.exists:
        buffer_data = buffer_doc.to_dict()
        pending_messages = buffer_data.get("pendingMessages", [])
        pending_messages.append({
            "senderId": sender_id,
            "senderName": sender_name,
            "text": text,
            "timestamp": datetime.now(timezone.utc)
        })
        buffer_ref.update({"pendingMessages": pending_messages})
    else:
        buffer_ref.set({
            "pendingMessages": [{
                "senderId": sender_id,
                "senderName": sender_name,
                "text": text,
                "timestamp": datetime.now(timezone.utc)
            }],
            "lastSentAt": None
        })

    return jsonify({"status": "added"}), 200


# === Send Notifications ===
@app.route("/send_notifications", methods=["GET"])
def send_grouped_notifications():
    print("WE ON BACKEND >>>>>>>>>>>>>>>>>")
    buffers = db.collection("notification_buffer").stream()
    now = datetime.now(timezone.utc)

    for doc in buffers:
        buffer_data = doc.to_dict()
        last_sent_at = buffer_data.get("lastSentAt")
        pending_messages = buffer_data.get("pendingMessages", [])

        if not pending_messages:
            continue

        if last_sent_at and (now - last_sent_at).total_seconds() < SEND_INTERVAL_SECONDS:
            continue

        if len(pending_messages) == 1:
            body = f"{pending_messages[0]['senderName']}: {pending_messages[0]['text']}"
        else:
            body = f"{len(pending_messages)} new messages from {len(set(m['senderName'] for m in pending_messages))} people"

        community_ref = db.collection("communities").document(doc.id).get()
        if not community_ref.exists:
            continue

        community_data = community_ref.to_dict()
        members = community_data.get("members", [])
        if not members:
            continue

        tokens = []
        for user_id in members:
            user_doc = db.collection("users").document(user_id).get()
            if user_doc.exists:
                token = user_doc.to_dict().get("fcmToken")
                if token:
                    tokens.append(token)

        if tokens:
            message = messaging.MulticastMessage(
                tokens=tokens,
                notification=messaging.Notification(
                    title=f"New activity in {community_data.get('name', 'your community')}",
                    body=body
                )
            )
            response = messaging.send_multicast(message)
            print(f"Sent to {len(tokens)} users, success: {response.success_count}")

        db.collection("notification_buffer").document(doc.id).update({
            "pendingMessages": [],
            "lastSentAt": now
        })

    return {"status": "done"}, 200

@app.route("/send_notification", methods=["POST"])
def send_notification():
    try:
        data = request.get_json()
        community_id = data.get('communityId')
        sender_id = data.get('senderId')
        sender_name = data.get('senderName')
        text = data.get('text')
        
        # Get community members and their tokens
        community_doc = db.collection('communities').document(community_id).get()
        print(repr(community_id))
        print("Exists:", community_doc.exists)
        print("Backend Firebase Project:", db.project)

        if not community_doc.exists:

            return {"error": "Community not found",
                        "data": data
                    }, 404
            
        members = community_doc.to_dict().get('members', [])
        
        # Get FCM tokens (exclude sender)
        tokens = []   
        for user_id in members:
            # if user_id != sender_id:  # Don't send to sender
                user_doc = db.collection('users').document(user_id).get()
                if user_doc.exists:
                    token = user_doc.to_dict().get('fcmToken')
                    print("Here the tokens>>>>>>>>>>>>>>>>>>>>>>>>>",token)
                    if token:
                        tokens.append(token)
        
        if tokens:
            # Create notification message
            message = messaging.MulticastMessage(
                tokens=tokens,
                notification=messaging.Notification(
                    title=f"New message in {community_doc.to_dict().get('name', 'Community')}",
                    body=f"{sender_name}: {text[:100]}..." if len(text) > 100 else f"{sender_name}: {text}"
                ),
                data={
                    'communityId': community_id,
                    'senderId': sender_id,
                    'type': 'message'
                }
            )
            
            # Send notification
            response = messaging.send_each_for_multicast(message)
            print(f"Sent notifications: {response.success_count} successful, {response.failure_count} failed")
            if response.failure_count >0:
                failed_tokens = []
                for idx, resp in enumerate(response.responses):
                    if not resp.success:
                        failed_tokens.append(tokens[idx])
                print(f'List of tokens that caused failures:{failed_tokens}')
            return {
                "success": True,
                "sent_count": response.success_count,  
                "failed_count": response.failure_count
            }, 200
        else:
            return {"message": "No tokens found"}, 200
            
    except Exception as e:
        print(f"Error sending notification: {e}")
        return {"error": str(e)}, 500
    
if __name__ == "__main__":
    app.run(port=5000, debug=True)
                                       