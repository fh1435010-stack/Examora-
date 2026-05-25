from flask import Flask, render_template, request, redirect, session
import sqlite3

app = Flask(__name__)
app.secret_key = "examora_secret_key"

# ---------------- DATABASE ---------------- #

def init_db():

    conn = sqlite3.connect("examora.db")
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        board TEXT,
        class_name TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()

# ---------------- ADMIN ---------------- #

ADMIN_NAME = "F@iZaN1952h@IeR"
ADMIN_PASSWORD = "L@LAKbAR1952"

# ---------------- SPLASH ---------------- #

@app.route('/')
def splash():

    if "user" in session:
        return redirect('/dashboard')

    if "admin" in session:
        return redirect('/admin')

    return render_template('splash.html')

# ---------------- LOGIN ---------------- #

@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        # ADMIN LOGIN
        if username == ADMIN_NAME and password == ADMIN_PASSWORD:

            session['admin'] = username
            return redirect('/admin')

        # USER LOGIN
        conn = sqlite3.connect("examora.db")
        cursor = conn.cursor()

        cursor.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password)
        )

        user = cursor.fetchone()

        conn.close()

        if user:

            session['user'] = username

            # CHECK FIRST TIME SETUP
            if user[3] is None or user[4] is None:
                return redirect('/setup')

            return redirect('/dashboard')

        return "Invalid Username or Password"

    return render_template('login.html')

# ---------------- SIGNUP ---------------- #

@app.route('/signup', methods=['GET', 'POST'])
def signup():

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']
        confirm = request.form['confirm']

        if password != confirm:
            return "Passwords do not match"

        conn = sqlite3.connect("examora.db")
        cursor = conn.cursor()

        try:

            cursor.execute(
                "INSERT INTO users(username, password) VALUES(?, ?)",
                (username, password)
            )

            conn.commit()

        except:
            return "Username already exists"

        conn.close()

        session['user'] = username

        return redirect('/setup')

    return render_template('signup.html')

# ---------------- SETUP ---------------- #

@app.route('/setup', methods=['GET', 'POST'])
def setup():

    if 'user' not in session:
        return redirect('/login')

    if request.method == 'POST':

        board = request.form['board']
        class_name = request.form['class_name']

        conn = sqlite3.connect("examora.db")
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE users SET board=?, class_name=? WHERE username=?",
            (board, class_name, session['user'])
        )

        conn.commit()
        conn.close()

        return redirect('/dashboard')

    return render_template('setup.html')

# ---------------- USER DASHBOARD ---------------- #

@app.route('/dashboard')
def dashboard():

    if 'user' not in session:
        return redirect('/login')

    return render_template(
        'dashboard.html',
        username=session['user']
    )

# ---------------- ADMIN DASHBOARD ---------------- #

@app.route('/admin')
def admin():

    if 'admin' not in session:
        return redirect('/login')

    return render_template('admin.html')

# ---------------- LOGOUT ---------------- #

@app.route('/logout')
def logout():

    session.clear()

    return redirect('/login')

# ---------------- RUN ---------------- #

if __name__ == '__main__':
    app.run(debug=True)
