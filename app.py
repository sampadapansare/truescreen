from flask import Flask, render_template, request, redirect, url_for, session
from flask_socketio import SocketIO, emit, join_room
import os

app = Flask(__name__)
app.secret_key = "supersecret"
socketio = SocketIO(app)

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        session['username'] = request.form['username']
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Store user data in a real app
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/verify')
def verify():
    return render_template('verify.html')

@app.route('/dashboard')
def dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html', username=session['username'])

@app.route('/schedule')
def schedule():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('schedule.html', username=session['username'])

@app.route('/interview')
def interview():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('interview.html', username=session['username'])

@app.route('/join')
def join():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('join.html', username=session['username'])

@app.route('/video')
def video():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('video.html', username=session['username'])

# SocketIO Events
@socketio.on('join_room')
def handle_join(data):
    room = data['room']
    join_room(room)
    emit('user_joined', {'username': session.get('username', 'Anonymous')}, room=room)

@socketio.on('offer')
def handle_offer(data):
    emit('offer', data, room=data['room'])

@socketio.on('answer')
def handle_answer(data):
    emit('answer', data, room=data['room'])

@socketio.on('ice-candidate')
def handle_ice_candidate(data):
    emit('ice-candidate', data, room=data['room'])

@socketio.on('fraud_event')
def handle_fraud(data):
    emit('fraud_alert', data, room=data['room'])

# No __main__ block needed! Gunicorn will launch the app.
# This is intentionally left out for Render deployment.
