import firebase_admin
from firebase_admin import credentials
from firebase_admin import messaging
from flask import Flask, json, request, jsonify



app = Flask(__name__)

# Initialize the app only if it hasn't been initialized
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

url = "http://192.168.46.100:3000/sendNotification"

@app.route('/', methods=['GET'])
def home():
    return "Server is up and running!", 200

@app.route('/sendNotification', methods=['POST'])  
def send_notification():
    print("Received a request to /sendNotification")
    data = request.get_json()

    if not data:
        return jsonify(success = False, error='>>>>>>>>>>>>>>>>No data is received'), 400
    
    title = data.get('title')
    body = data.get('body')
    token =data.get('token')
    payload = data.get('payload')

    print('payload on the backend looks like >>>>>>>>>>>>>>>>>>.',payload)

    postdata = json.loads(payload) if payload else None
    print('payload on the backend looks like after processes >>>>>>>>>>>>>>>>>>.',postdata)
    
    
    if not title or not body or not token:
        print("Invalid data received:", data)
        return jsonify(success=False, error=">>>>>>>>>>>>>>>>>>>>>>>>Missing title, body, or token"), 400

    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body 
        ),token=token,
        data={  
                'somedata':json.dumps(postdata) if postdata else json.dumps({}),
        }
    )

    try:
        response = messaging.send(message)
        print('Successfully sent message:', response)
        return jsonify(success=True),200
    except Exception as e:
        print("Error sending message:", e)
        return jsonify(success=False, error=str(e)), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0',port=3000, debug=True)
