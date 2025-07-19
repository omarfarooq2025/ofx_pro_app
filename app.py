
from flask import Flask, render_template, request, redirect, url_for, session, g, flash
from functools import wraps
import sqlite3
import os
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key'
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# =========================
# Database Setup
# =========================
DATABASE = 'ofx_app.db'

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# =========================
# Helper Functions
# =========================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# =========================
# Routes
# =========================
@app.route('/')
@login_required
def dashboard():
    db = get_db()
    cur = db.execute('SELECT name FROM users WHERE id = ?', (session['user_id'],))
    user = cur.fetchone()

    cur = db.execute('SELECT COUNT(*) as count FROM users WHERE referral_id = ?', (session['user_id'],))
    referrals = cur.fetchone()['count']

    cur = db.execute('SELECT SUM(amount) as total FROM earnings WHERE user_id = ?', (session['user_id'],))
    earnings = cur.fetchone()['total'] or 0

    return render_template('dashboard.html', name=user['name'], referrals=referrals, earnings=f'₦{earnings:,}')

@app.route('/training')
@login_required
def training():
    db = get_db()
    cur = db.execute('SELECT * FROM videos')
    videos = cur.fetchall()
    return render_template('training.html', videos=videos)

@app.route('/referral')
@login_required
def referral():
    db = get_db()
    cur = db.execute('SELECT COUNT(*) as count FROM users WHERE referral_id = ?', (session['user_id'],))
    referrals = cur.fetchone()['count']
    earnings = referrals * 200
    bonus_unlocked = earnings >= 2500
    return render_template('referral.html', referrals=referrals, earnings=f'₦{earnings:,}', bonus_unlocked=bonus_unlocked)

@app.route('/wallet')
@login_required
def wallet():
    db = get_db()
    cur = db.execute('SELECT amount, type FROM earnings WHERE user_id = ?', (session['user_id'],))
    history = cur.fetchall()
    cur = db.execute('SELECT SUM(amount) as balance FROM earnings WHERE user_id = ?', (session['user_id'],))
    balance = cur.fetchone()['balance'] or 0
    return render_template('wallet.html', balance=f'₦{balance:,}', history=history)

@app.route('/withdraw', methods=['POST'])
@login_required
def withdraw():
    db = get_db()
    amount = request.form.get('amount')
    if amount:
        db.execute('INSERT INTO withdrawals (user_id, amount, status, requested_at) VALUES (?, ?, ?, ?)',
                   (session['user_id'], amount, 'pending', datetime.now()))
        db.commit()
        flash('Withdrawal request sent. Please wait 3–4 hours for admin approval.', 'info')
    return redirect(url_for('wallet'))

@app.route('/account')
@login_required
def account():
    db = get_db()
    cur = db.execute('SELECT name, email FROM users WHERE id = ?', (session['user_id'],))
    user = cur.fetchone()
    return render_template('account.html', name=user['name'], email=user['email'])

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        db = get_db()
        cur = db.execute('SELECT * FROM users WHERE email = ? AND password = ?', (email, password))
        user = cur.fetchone()
        if user:
            session['user_id'] = user['id']
            session['email'] = user['email']
            session['is_admin'] = bool(user['is_admin'])
            if user['is_admin']:
                return redirect(url_for('admin_panel'))
            else:
                return redirect(url_for('dashboard'))
        else:
            return "Invalid credentials"
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        db = get_db()
        db.execute('INSERT INTO users (name, email, password) VALUES (?, ?, ?)', (name, email, password))
        db.commit()
        cur = db.execute('SELECT id FROM users WHERE email = ?', (email,))
        user = cur.fetchone()
        session['user_id'] = user['id']
        session['email'] = email
        session['is_admin'] = False
        return redirect(url_for('dashboard'))
    return render_template('signup.html')

@app.route('/admin', methods=['GET', 'POST'])
@admin_required
def admin_panel():
    db = get_db()
    cur = db.execute('SELECT COUNT(*) as total_users FROM users')
    total_users = cur.fetchone()['total_users']

    cur = db.execute('SELECT COUNT(*) as total_referrals FROM users WHERE referral_id IS NOT NULL')
    total_referrals = cur.fetchone()['total_referrals']

    cur = db.execute("SELECT SUM(amount) as total_earnings FROM earnings")
    total_earnings = cur.fetchone()['total_earnings'] or 0

    cur = db.execute("SELECT SUM(amount) as total_payouts FROM withdrawals WHERE status = 'approved'")
    total_payouts = cur.fetchone()['total_payouts'] or 0

    cur = db.execute("SELECT SUM(amount) as cpa_income FROM earnings WHERE type = 'CPA'")
    cpa_income = cur.fetchone()['cpa_income'] or 0

    cur = db.execute("SELECT SUM(amount) as referral_income FROM earnings WHERE type = 'Referral Overflow'")
    referral_income = cur.fetchone()['referral_income'] or 0

    cur = db.execute('SELECT * FROM videos')
    videos = cur.fetchall()

    cur = db.execute('SELECT * FROM users')
    users = cur.fetchall()

    return render_template('admin.html', users=users, videos=videos, total_users=total_users,
                           total_referrals=total_referrals, total_earnings=total_earnings,
                           total_payouts=total_payouts, cpa_income=cpa_income,
                           referral_income=referral_income)

import os  # Make sure this is at the top of your file
from werkzeug.utils import secure_filename  # also at the top

@app.route('/admin/upload_video', methods=['POST'])
@admin_required
def upload_video():
    title = request.form['title']
    duration = request.form['duration']
    amount = request.form['amount']
    file = request.files['file']

    if file:
        # Ensure the uploads folder exists
        upload_dir = os.path.join('static', 'uploads')
        os.makedirs(upload_dir, exist_ok=True)

        filename = secure_filename(file.filename)
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)

        # Save to database
        db = get_db()
        db.execute('INSERT INTO videos (title, duration, amount) VALUES (?, ?, ?)',
                   (title, duration, amount))
        db.commit()

    return redirect(url_for('admin_panel'))

# =========================
# Start Server
# =========================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)