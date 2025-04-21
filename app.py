from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
import os
import cv2
import numpy as np

app = Flask(__name__)
app.secret_key = 'f283f91a99edbc930fd3fd47c592fc33bdc1b8d7e7d0765a'
socketio = SocketIO(app)

# Dummy user store
users = {}

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
    return render_template('dashboard.html', user=session['user'])

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

    # Placeholder fraud logic (replace with YOLO/custom)
    h, w = img.shape[:2]
    mid_x = w // 2
    left_half = img[:, :mid_x]
    right_half = img[:, mid_x:]

    left_mean = np.mean(left_half)
    right_mean = np.mean(right_half)

    fraud = left_mean - right_mean > 20  # Totally arbitrary logic rn
    status = 'fraud' if fraud else 'clear'

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
