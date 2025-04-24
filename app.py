from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, join_room, emit, close_room
import cv2
import numpy as np
import requests
import uuid
import logging
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'f283f91a99edbc930fd3fd47c592fc33bdc1b8d7e7d0765a'
socketio = SocketIO(app, 
                   cors_allowed_origins="*", 
                   logger=True,
                   engineio_logger=True,
                   async_mode='gevent',
                   ping_timeout=60,
                   ping_interval=25)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

users = {}
meetings = set()
active_participants = {}  # Track participants by room

# Face detection setup
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
ROBOFLOW_API_KEY = "ATCth3RHKPljJdY3UmHL"
ROBOFLOW_MODEL_ID = "interview-dxisb/3"

# Routes (unchanged)
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        users[request.form['username']] = request.form['password']
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['password']
        if users.get(u) == p:
            session['username'] = u
            return redirect(url_for('dashboard'))
        return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', username=session['username'])

@app.route('/schedule')
def schedule():
    if 'username' not in session:
        return redirect(url_for('login'))
    meeting_id = str(uuid.uuid4())[:8]
    meetings.add(meeting_id)
    meeting_url = url_for('interview', meeting_id=meeting_id, _external=True)
    return render_template('schedule.html', meeting_id=meeting_id, meeting_url=meeting_url)

@app.route('/join', methods=['GET', 'POST'])
def join_meeting():
    if request.method == 'POST':
        meeting_id = request.form['meeting_id'].strip()
        if meeting_id in meetings:
            return redirect(url_for('interview', meeting_id=meeting_id))
        return render_template('join.html', error="Invalid Meeting ID")
    return render_template('join.html')

@app.route('/interview/<meeting_id>')
def interview(meeting_id):
    if 'username' not in session or meeting_id not in meetings:
        return redirect(url_for('dashboard'))
    return render_template('interview.html', meeting_id=meeting_id)

# Enhanced WebRTC Signaling
@socketio.on('join_room')
def handle_join_room(data):
    """Handle participant joining a room"""
    room = data['room']
    user_id = request.sid
    join_room(room)
    
    # Track participant
    if room not in active_participants:
        active_participants[room] = []
    active_participants[room].append(user_id)
    
    logger.info(f"User {user_id} joined room {room}")
    
    # Notify others in the room
    emit('user_connected', {'user_id': user_id}, room=room, include_self=False)
    
    # Send list of existing participants to the new joiner
    existing_users = [uid for uid in active_participants[room] if uid != user_id]
    emit('room_info', {
        'room': room,
        'existing_users': existing_users
    })

@socketio.on('offer')
def handle_offer(data):
    """Relay offer to specific target"""
    target_id = data['target_id']
    room = data['room']
    sender_id = request.sid
    
    logger.info(f"Relaying offer from {sender_id} to {target_id} in {room}")
    emit('offer', {
        'offer': data['offer'],
        'sender_id': sender_id
    }, room=target_id)

@socketio.on('answer')
def handle_answer(data):
    """Relay answer to specific target"""
    target_id = data['target_id']
    room = data['room']
    sender_id = request.sid
    
    logger.info(f"Relaying answer from {sender_id} to {target_id} in {room}")
    emit('answer', {
        'answer': data['answer'],
        'sender_id': sender_id
    }, room=target_id)

@socketio.on('ice_candidate')
def handle_ice_candidate(data):
    """Relay ICE candidate to specific target"""
    target_id = data['target_id']
    sender_id = request.sid
    
    logger.debug(f"Relaying ICE candidate from {sender_id} to {target_id}")
    emit('ice_candidate', {
        'candidate': data['candidate'],
        'sender_id': sender_id
    }, room=target_id)

@socketio.on('disconnect')
def handle_disconnect():
    """Clean up on participant disconnect"""
    user_id = request.sid
    for room, participants in active_participants.items():
        if user_id in participants:
            participants.remove(user_id)
            logger.info(f"User {user_id} disconnected from room {room}")
            emit('user_disconnected', {'user_id': user_id}, room=room)
            
            # Clean up empty rooms
            if not participants:
                del active_participants[room]
                close_room(room)
            break

# Existing detection handlers
@app.route('/detect', methods=['POST'])
def detect():
    room = request.form['room']
    frame_data = request.files['frame'].read()
    arr = np.frombuffer(frame_data, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    alert = ""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.1, 4)
    
    if len(faces) == 0:
        alert = "⚠️ No Person Detected"
    else:
        _, enc = cv2.imencode('.jpg', frame)
        try:
            response = requests.post(
                f"https://detect.roboflow.com/{'interview-dxisb/3'}",
                files={"file": enc.tobytes()},
                params={"api_key": 'ATCth3RHKPljJdY3UmHL', "confidence": 50, "overlap": 30}
            ).json()

            for obj in response.get("predictions", []):
                if obj["confidence"] >= 0.7 and obj["width"] * obj["height"] >= 2000:
                    alert = f"⚠️ Suspicious Object: {obj['class']}"
                    break
        except Exception as e:
            logger.error(f"[Detection Error] {e}")

    socketio.emit('fraud_alert', {'message': alert}, room=room)
    return ('', 204)

@socketio.on('tab_switched')
def handle_tab_switch(data):
    username = data.get('username')
    count = data.get('count')
    logger.warning(f"[ALERT] {username} switched tabs {count} times.")
    if count >= 3:
        logger.warning(f"[DISQUALIFY?] {username} exceeded tab switch limit.")
    emit('tab_switch_warning', {'message': 'Tab switch detected'}, room=request.sid)

if __name__ == '__main__':
    socketio.run(app, 
                debug=True, 
                host='0.0.0.0', 
                port=5000,
                allow_unsafe_werkzeug=True)
