from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_socketio import SocketIO, join_room, emit
import cv2
import numpy as np
import requests
import uuid
import os
import smtplib
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = 'f283f91a99edbc930fd3fd47c592fc33bdc1b8d7e7d0765a'
socketio = SocketIO(app)

# In‑memory stores
users = {}            # username → password, otp, otp_verified
meetings = set()      # active meeting IDs

# Face cascade
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades +
    'haarcascade_frontalface_default.xml')

# ─── Send OTP Function ────────────────────────────────────────────────────────
def send_otp_email(user_email):
    otp = random.randint(10000, 99999)  # 5-digit OTP
    users[user_email]['otp'] = otp

    # Set up the email server
    sender_email = "your_email@gmail.com"  # Replace with your email
    receiver_email = user_email
    password = "your_email_password"  # Replace with your email password

    subject = "Your OTP Code"
    body = f"Your OTP code is: {otp}"

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        # Setup the SMTP server and send the email
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, password)
        text = msg.as_string()
        server.sendmail(sender_email, receiver_email, text)
        server.quit()
    except Exception as e:
        print(f"Error sending email: {e}")

# ─── Auth & Meeting Routes ───────────────────────────────────────────────────
@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        
        users[username] = {'password': password, 'email': email, 'otp_verified': False}
        send_otp_email(email)  # Send OTP email after registration
        return redirect(url_for('verify_otp', username=username))
    
    return render_template('register.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Check if username exists and password is correct
        if username in users and users[username]['password'] == password:
            # Check if OTP is verified
            if users[username].get('otp_verified', False):
                session['username'] = username
                return redirect(url_for('dashboard'))
            else:
                flash("Please verify your OTP first.", "danger")
                return redirect(url_for('verify_otp', username=username))
        else:
            flash("Invalid credentials. Please try again.", "danger")
    
    return render_template('login.html')

@app.route('/verify_otp/<username>', methods=['GET', 'POST'])
def verify_otp(username):
    if request.method == 'POST':
        otp = request.form['otp']
        
        # Check OTP validity
        if otp == str(users[username]['otp']):
            users[username]['otp_verified'] = True  # Mark OTP as verified
            flash("OTP verified successfully!", "success")
            return redirect(url_for('login'))
        else:
            flash("Invalid OTP. Please try again.", "danger")

    return render_template('verify_otp.html', username=username)

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

@app.route('/join', methods=['GET','POST'])
def join():
    if 'username' not in session:
        return redirect(url_for('login'))
    error=None
    if request.method=='POST':
        m = request.form['meeting_id']
        if m in meetings:
            return redirect(url_for('interview', meeting_id=m))
        error="Invalid Meeting ID"
    return render_template('join.html', error=error)

@app.route('/interview/<meeting_id>')
def interview(meeting_id):
    if 'username' not in session:
        return redirect(url_for('login'))
    if meeting_id not in meetings:
        return redirect(url_for('join'))
    return render_template('interview.html', meeting_id=meeting_id)

@app.route('/logout')
def logout():
    session.pop('username',None)
    return redirect(url_for('login'))

# ─── WebRTC Signaling ────────────────────────────────────────────────────────

@socketio.on('join-room')
def on_join(data):
    room = data['room']
    join_room(room)
    # notify existing peers
    emit('user-joined', {'sid': request.sid}, room=room, include_self=False)

@socketio.on('signal')
def on_signal(data):
    room = data['room']
    emit('signal', data, room=room, include_self=False)

# ─── Fraud Detection Endpoint ────────────────────────────────────────────────

@app.route('/detect', methods=['POST'])
def detect():
    room = request.form['room']
    # Read uploaded frame
    file = request.files['frame'].read()
    arr = np.frombuffer(file, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    alert = ""
    # Face absence
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray,1.1,4)
    if len(faces)==0:
        alert = "⚠️ No Person Detected"

    # Roboflow object detection
    _, enc = cv2.imencode('.jpg', frame)
    try:
        resp = requests.post(
          f"https://detect.roboflow.com/{'interview-dxisb/3'}",
          files={"file": enc.tobytes()},
          params={"api_key":'ATCth3RHKPljJdY3UmHL',"confidence":50,"overlap":30}
        ).json()
        for obj in resp.get("predictions",[]):
            c = obj["confidence"]
            area = obj["width"]*obj["height"]
            if c>=0.7 and area>=2000:
                alert = f"⚠️ Suspicious Object: {obj['class']}"
                break
    except:
        pass

    # Broadcast alert to everyone in the room
    socketio.emit('fraud-alert', {'message': alert}, room=room)
    return ('',204)

# ─── Run ────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)

