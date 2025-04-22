from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
import requests
import cv2
import numpy as np

app = Flask(__name__)
app.secret_key = 'f283f91a99edbc930fd3fd47c592fc33bdc1b8d7e7d0765a'
socketio = SocketIO(app)

# Dummy user store
users = {}

# Roboflow API settings
ROBOFLOW_MODEL_ENDPOINT = "https://detect.roboflow.com/fraud-detection/1"
ROBOFLOW_API_KEY = "ATCth3RHKPljJdY3UmHL"  # Get your API key from the deploy tab

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users:
            return 'User already exists'
        users[username] = password
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if users.get(username) == password:
            session['user'] = username
            return redirect(url_for('dashboard'))
        return 'Invalid credentials'
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', username=session['user'])

@app.route('/schedule')
def schedule():
    return render_template('schedule.html')

@app.route('/join')
def join():
    return render_template('join.html')

@app.route('/interview')
def interview():
    return render_template('interview.html')

@app.route('/video')
def video():
    return render_template('video.html')

# ------------------- FRAUD DETECTION -------------------

@app.route('/detect', methods=['POST'])
def detect():
    if 'image' not in request.files:
        return jsonify({'error': 'No image uploaded'}), 400

    file = request.files['image']
    npimg = np.frombuffer(file.read(), np.uint8)
    img = cv2.imdecode(npimg, cv2.IMREAD_COLOR)

    # Prepare image for sending to Roboflow
    _, img_encoded = cv2.imencode('.jpg', img)
    img_bytes = img_encoded.tobytes()

    # Send image to Roboflow API for prediction
    headers = {
        "Authorization": f"Bearer {ROBOFLOW_API_KEY}",
    }

    # POST request to the Roboflow endpoint
    response = requests.post(
        ROBOFLOW_MODEL_ENDPOINT, 
        files={"file": img_bytes}, 
        headers=headers
    )

    if response.status_code == 200:
        data = response.json()
        # Assuming the result contains a "predictions" field
        predictions = data.get('predictions', [])
        if predictions:
            # Assuming fraud detection based on a class label (you can adjust based on your model's output)
            status = "fraud" if "fraud" in [pred["class"] for pred in predictions] else "clear"
        else:
            status = "clear"
    else:
        return jsonify({'error': 'Failed to process image with Roboflow API'}), 500

    return jsonify({'status': status})

# ------------------- SOCKET.IO EVENTS -------------------

@socketio.on('join-room')
def handle_join_room(data):
    room = data['room']
    join_room(room)
    emit('user-connected', {'user': request.sid}, to=room)

@socketio.on('signal')
def handle_signal(data):
    emit('signal', data, to=data['target'])

@socketio.on('disconnect')
def handle_disconnect():
    print(f'User {request.sid} disconnected')

# ------------------- RUN APP -------------------

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
