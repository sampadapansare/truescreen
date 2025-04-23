from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_socketio import SocketIO, join_room, emit
import cv2
import numpy as np
import requests
import uuid

app = Flask(__name__)
app.secret_key = 'f283f91a99edbc930fd3fd47c592fc33bdc1b8d7e7d0765a'
socketio = SocketIO(app)

# In-memory stores
users = {}            # username → password
meetings = set()      # active meeting IDs

# Face detection model
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# Roboflow API setup
ROBOFLOW_API_KEY = "ATCth3RHKPljJdY3UmHL"
ROBOFLOW_MODEL_ID = "interview-dxisb/3"

# ─── Auth Routes ─────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['password']
        users[u] = p
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

# ─── Dashboard & Meeting Routes ──────────────────────────────────────────────

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    meeting_id = str(uuid.uuid4())[:8]
    return render_template('dashboard.html', username=session['username'], meeting_id=meeting_id)

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
    if 'username' not in session:
        return redirect(url_for('login'))
    if meeting_id not in meetings:
        return redirect(url_for('dashboard'))
    return render_template('interview.html', meeting_id=meeting_id)

# ─── WebRTC Signaling ────────────────────────────────────────────────────────

@socketio.on('join-room')
def on_join(data):
    room = data['room']
    join_room(room)
    emit('user-joined', {'sid': request.sid}, room=room, include_self=False)

@socketio.on('signal')
def on_signal(data):
    room = data['room']
    emit('signal', data, room=room, include_self=False)

# ─── Fraud Detection ─────────────────────────────────────────────────────────

@app.route('/detect', methods=['POST'])
def detect():
    room = request.form['room']
    file = request.files['frame'].read()
    arr = np.frombuffer(file, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    alert = ""

    # Face detection
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.1, 4)
    if len(faces) == 0:
        alert = "⚠️ No Person Detected"

    # Roboflow detection
    _, enc = cv2.imencode('.jpg', frame)
    try:
        resp = requests.post(
            f"https://detect.roboflow.com/{'interview-dxisb/3'}",
            files={"file": enc.tobytes()},
            params={"api_key": 'ATCth3RHKPljJdY3UmHL', "confidence": 50, "overlap": 30}
        ).json()

        for obj in resp.get("predictions", []):
            c = obj["confidence"]
            area = obj["width"] * obj["height"]
            if c >= 0.7 and area >= 2000:
                alert = f"⚠️ Suspicious Object: {obj['class']}"
                break
    except Exception as e:
        print(f"Detection error: {e}")

    socketio.emit('fraud-alert', {'message': alert}, room=room)
    return ('', 204)

# ─── Tab Switch Monitoring ───────────────────────────────────────────────────

@socketio.on('tab_switched')
def handle_tab_switch(data):
    username = data.get('username')
    count = data.get('count')
    print(f"[ALERT] {username} switched tabs! Total count: {count}")
    if count >= 3:
        print(f"{username} switched tabs more than 3 times! Consider disqualification.")
    emit('tab_switch_warning', {'message': 'Tab switch detected'}, room=request.sid)

# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    socketio.run(app, debug=True)
