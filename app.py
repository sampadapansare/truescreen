from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import timedelta
import uuid

app = Flask(__name__)
app.secret_key = 'f283f91a99edbc930fd3fd47c592fc33bdc1b8d7e7d0765a'
app.permanent_session_lifetime = timedelta(days=7)

# In‑memory user store
users = {}  # username → password

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
            session.permanent = bool(remember)  # This ensures "remember me" functionality
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

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash("Logged out successfully.", "info")
    return redirect(url_for('login'))

# ─── Main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    app.run(debug=True)
