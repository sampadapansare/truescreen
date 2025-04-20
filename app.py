from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO, join_room, emit
import cv2
import numpy as np
import requests
import uuid
import os
from datetime import timedelta

app = Flask(__name__)
app.secret_key = 'f283f91a99edbc930fd3fd47c592fc33bdc1b8d7e7d0765a'
app.permanent_session_lifetime = timedelta(days=7)
socketio = SocketIO(app)

# In‑memory user store
users = {}            # username → password
meetings = set()      # active meeting IDs

# Face detection
face_cascade = cv2.CascadeClassifier(
    cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
)

# Roboflow Config
ROBOFLOW_API_KEY = "ATCth3RHKPljJdY3UmHL"
ROBOFLOW_MODEL_ID = "interview-dxisb/3"

# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['password']
        if u in users:
            flash("Username already exists!", "error")
            return redirect(url_for('login'))
        users[u] = p
        flash("Registered! Please log in.", "success")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = request.form['username']
        p = request.form['password']
        remember = request.form.get('remember')
        if users.get(u) == p:
            session.permanent = bool(remember)
            session['username'] = u
            flash("Login successful!", "success")
            return redirect(url_for('dashboard'))
        flash("Invalid credentials.", "error")
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', username=session['username'])

@app.route('/schedule')
def schedule():
    if 'username' not in session:
        return redirect(url_for('login'))
    m = str(uuid.uuid4())[:8]
    meetings.add(m)
    return render_template('schedule.html', meeting_id=m)

@app.route('/join', methods=['GET', 'POST'])
def join():
    if 'username' not in session:
        return redirect(url_for('login'))
    error = None
    if request.method == 'POST':
        m = request.form['meeting_id']
        if m in meetings:
            return redirect(url_for('interview', meeting_id=m))
        error = "Invalid Meeting ID"
    return render_template('join.html', error=error)

@app.route('/interview/<meeting_id>')
def interview(meeting_id):
    if 'username' not in session or meeting_id not in meetings:
        return redirect(url_for('login'))
    return render_template('interview.html', meeting_id=meeting_id)

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash("Logged out successfully.", "info")
    return redirect(url_for('login'))

# ─── WebRTC Signaling ────────────────────────────────────────────────────────

@socketio.on('join-room')
def on_join(data):
    room = data['room']
    join_room(room)
    emit('user-joined', {'sid': request.sid}, room=room, include_self=False)

@socketio.on('signal')
def on_signal(data):
    emit('signal', data, room=data['room'], include_self=False)

# ─── Fraud Detection ─────────────────────────────────────────────────────────

@app.route('/detect', methods=['POST'])
def detect():
    room = request.form['room']
    file = request.files['frame'].read()
    arr = np.frombuffer(file, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    alert = ""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, 1.1, 4)
    if len(faces) == 0:
        alert = "⚠️ No Person Detected"

    _, enc = cv2.imencode('.jpg', frame)
    try:
        resp = requests.post(
            f"https://detect.roboflow.com/{ROBOFLOW_MODEL_ID}",
            files={"file": enc.tobytes()},
            params={"api_key": ROBOFLOW_API_KEY, "confidence": 50, "overlap": 30}
        ).json()
        for obj in resp.get("predictions", []):
            if obj["confidence"] >= 0.7 and obj["width"] * obj["height"] >= 2000:
                alert = f"⚠️ Suspicious Object: {obj['class']}"
                break
    except:
        pass

    socketio.emit('fraud-alert', {'message': alert}, room=room)
    return ('', 204)

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
