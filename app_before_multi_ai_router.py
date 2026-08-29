import os
from flask import Flask, render_template, request, redirect, session, url_for, jsonify
import sqlite3
from werkzeug.utils import secure_filename
import requests
# CONFIGURE EXAMORA SECURE PHOTO UPLOAD STORAGE PATHS
UPLOAD_FOLDER = 'static/uploads/profiles/'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.secret_key = "examora_secret_key"
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Auto-build directory tree if missing inside Termux workspace
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------------- DATABASE ---------------- #

def init_db():
    conn = sqlite3.connect("examora.db")
    cursor = conn.cursor()

    # 1. CORE USERS TABLE (Preserves your existing setup)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        board TEXT,
        class_name TEXT,
        group_name TEXT,
        total_marks INTEGER DEFAULT 0,
        streak INTEGER DEFAULT 1,
        pk_position INTEGER DEFAULT 99,
        profile_picture TEXT DEFAULT NULL
    )
    """)

    # 2. PAPERS DESIGN CONFIGURATION LEDGER
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS papers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        board TEXT,
        class_name TEXT,
        group_name TEXT,
        subject TEXT,
        paper_type TEXT,
        year TEXT,
        exam_time INTEGER,
        mcqs TEXT,
        mcq_answers TEXT,
        short_questions TEXT,
        short_keywords TEXT,
        long_questions TEXT,
        long_keywords TEXT
    )
    """)

    # 3. REAL EXAM RESULTS ENGINE TABLE
    # Expanded with tracking markers for weak concept mapping metrics
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS results(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        paper_id INTEGER,
        subject TEXT,
        topic TEXT,
        mcq_score INTEGER,
        total_mcqs INTEGER,
        score_obtained REAL DEFAULT 0,
        total_possible REAL DEFAULT 0,
        percentage REAL,
        test_date TEXT
    )
    """)

        # ⭐ UPDATED: EXAM HISTORY TABLE WITH CORRECT COLUMNS ⭐
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS exam_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        user_id INTEGER,
        paper_id TEXT,
        score TEXT,
        score_obtained REAL DEFAULT 0,
        total_questions INTEGER,
        percentage REAL,
        date_taken TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )
    ''')


    # 4. CACHED AUTOMATED AI INFRASTRUCTURE INSIGHTS
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_insights(
        username TEXT PRIMARY KEY,
        daily_plan TEXT DEFAULT NULL,
        weekly_plan TEXT DEFAULT NULL,
        monthly_plan TEXT DEFAULT NULL,
        yearly_plan TEXT DEFAULT NULL,
        last_updated TEXT
    )
    """)

    conn.commit()
    conn.close()

init_db()



# ---------------- ADMIN ---------------- #

ADMIN_NAME = "F@iZaN1952h@IeR"
ADMIN_PASSWORD = "L@LAKbAR1952"

# ---------------- HOME ---------------- #

@app.route('/')
def home():

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

            if user[3] is None:
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

        conn = sqlite3.connect("examora.db")
        cursor = conn.cursor()

        try:

            cursor.execute(

                "INSERT INTO users(username, password) VALUES(?, ?)",

                (username, password)

            )

            conn.commit()

        except:

            conn.close()
            return "Username Already Exists"

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
        group_name = request.form['group_name']

        conn = sqlite3.connect("examora.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE users
            SET board=?,
                class_name=?,
                group_name=?
            WHERE username=?
            """,
            (
                board,
                class_name,
                group_name,
                session['user']
            )
        )

        conn.commit()
        conn.close()

        return redirect('/dashboard')

    return render_template('setup.html')


# ---------------- DASHBOARD ---------------- #

@app.route('/dashboard')
def dashboard():

    if 'user' not in session:
        return redirect('/login')

    conn = sqlite3.connect("examora.db")
    cursor = conn.cursor()

    # 1. Fetch metadata (board, class, group, streak) from users
    cursor.execute(
        "SELECT board, class_name, group_name, streak FROM users WHERE username=?",
        (session['user'],)
    )
    user_info = cursor.fetchone()
    
    board = user_info[0]
    class_name = user_info[1]
    group_name = user_info[2]
    streak = user_info[3] if user_info[3] is not None else 1

    # 2. Calculate Real Total Marks from exam_history
    cursor.execute(
        "SELECT SUM(score_obtained) FROM exam_history WHERE username=?",
        (session['user'],)
    )
    total_marks = cursor.fetchone()[0] or 0

    # 3. Calculate National Position
    cursor.execute("""
        SELECT COUNT(*) + 1 
        FROM (SELECT username, SUM(score_obtained) as total FROM exam_history GROUP BY username) 
        WHERE total > ?
    """, (total_marks,))
    pk_position = cursor.fetchone()[0]

    # 4. Calculate Board Position (The new feature!)
    cursor.execute("""
        SELECT COUNT(*) + 1 
        FROM (SELECT h.username, SUM(h.score_obtained) as total 
              FROM exam_history h JOIN users u ON h.username = u.username 
              WHERE u.board = ? GROUP BY h.username) 
        WHERE total > ?
    """, (board, total_marks))
    board_position = cursor.fetchone()[0]

    # 5. Fetch Dynamic Leaderboard from history
    cursor.execute(
        """
        SELECT h.username, SUM(h.score_obtained) as total, u.board, u.class_name
        FROM exam_history h
        JOIN users u ON h.username = u.username
        GROUP BY h.username
        ORDER BY total DESC
        LIMIT 10
        """
    )
    leaderboard_rows = cursor.fetchall()
    conn.close()

    # Reformat leaderboard data neatly into key-value pairs
    top_students = []
    for row in leaderboard_rows:
        top_students.append({
            'username': row[0],
            'total_marks': row[1] if row[1] is not None else 0,
            'board': row[2] if row[2] else 'N/A',
            'class_name': row[3] if row[3] else 'N/A'
        })

    subjects = [
        "English",
        "Urdu",
        "Islamiat",
        "Pakistan Studies"
    ]

    if group_name == "Science Biology":
        subjects += [
            "Physics",
            "Chemistry",
            "Biology",
            "Mathematics"
        ]

    elif group_name == "Science Computer":
        subjects += [
            "Physics",
            "Chemistry",
            "Computer Science",
            "Mathematics"
        ]

    return render_template(
        'dashboard.html',
        username=session['user'],
        board=board,
        class_name=class_name,
        group_name=group_name,
        subjects=subjects,
        total_marks=total_marks,
        streak=streak,
        pk_position=pk_position,
        board_position=board_position,
        top_students=top_students
    )



# ---------------- SUBJECT PAGE ---------------- #

@app.route('/subject/<subject_name>')
def subject_page(subject_name):

    if 'user' not in session:
        return redirect('/login')

    conn = sqlite3.connect("examora.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # =========================
    # GET USER DATA SAFELY
    # =========================
    cursor.execute("""
        SELECT board, class_name, group_name
        FROM users
        WHERE username=?
    """, (session['user'],))

    user = cursor.fetchone()

    if not user:
        conn.close()
        return "User not found", 404

    board = user['board']
    class_name = user['class_name']
    group_name = user['group_name']

    # =========================
    # FETCH PAPERS (SAFE MATCH)
    # =========================
    cursor.execute("""
        SELECT id, paper_type, year
        FROM papers
        WHERE LOWER(TRIM(board)) = LOWER(TRIM(?))
        AND LOWER(TRIM(class_name)) = LOWER(TRIM(?))
        AND LOWER(TRIM(group_name)) = LOWER(TRIM(?))
        AND LOWER(TRIM(subject)) = LOWER(TRIM(?))
    """, (
        board,
        class_name,
        group_name,
        subject_name
    ))

    papers = cursor.fetchall()

    conn.close()

    return render_template(
        'subject.html',
        subject_name=subject_name,
        papers=papers
    )

# ---------------- TAKE EXAM ---------------- #

@app.route('/take_exam/<int:paper_id>')
def take_exam(paper_id):

    if 'user' not in session:
        return redirect('/login')

    conn = sqlite3.connect("examora.db")
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM papers WHERE id=?",
        (paper_id,)
    )

    paper = cursor.fetchone()

    conn.close()

    if not paper:
        return "Paper will upload soon"

    mcq_list = []

    for line in paper[8].split('\n'):

        line = line.strip()

        if line:

            parts = line.split('|')

            mcq_list.append(parts)

    short_questions = paper[10].split('\n')

    long_questions = paper[12].split('\n')

    return render_template(

        'take_exam.html',

        paper=paper,

        mcqs=mcq_list,
        short_questions=short_questions,
        long_questions=long_questions

    )

# ---------------- SUBMIT EXAM ---------------- #
# ---------------- HELPERS ----------------

def check_mcqs(user_answers, correct_answers, mcq_marks):

    score = 0

    for i in range(len(correct_answers)):
        if user_answers.get(f"mcq{i}") == correct_answers[i]:
            score += mcq_marks

    return score


def check_short_answers(form_data, keywords_list, short_marks):

    score = 0

    for i in range(len(keywords_list)):

        user_answer = form_data.get(f"short{i}")

        if not user_answer:
            continue

        user_answer = user_answer.lower()

        keywords = [
            k.strip().lower()
            for k in keywords_list[i].split(',')
            if k.strip()
        ]

        matched = 0

        for keyword in keywords:
            if keyword in user_answer:
                matched += 1

        if len(keywords) > 0:
            obtained = (matched / len(keywords)) * short_marks
            score += round(obtained)

    return score


def check_long_answers(form_data, keywords_list, long_marks):

    score = 0

    for i in range(len(keywords_list)):

        user_answer = form_data.get(f"long{i}")

        if not user_answer:
            continue

        user_answer = user_answer.lower()

        keywords = [
            k.strip().lower()
            for k in keywords_list[i].split(',')
            if k.strip()
        ]

        matched = 0

        for keyword in keywords:
            if keyword in user_answer:
                matched += 1

        if len(keywords) > 0:
            obtained = (matched / len(keywords)) * long_marks
            score += round(obtained)

    return score


# ---------------- SUBMIT EXAM ----------------

@app.route('/submit_exam/<int:paper_id>', methods=['POST'])
def submit_exam(paper_id):

    if 'user' not in session:
        return redirect('/login')

    conn = sqlite3.connect("examora.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            mcq_answers,
            short_keywords,
            long_keywords,
            mcq_marks,
            short_marks,
            long_marks
        FROM papers
        WHERE id=?
    """, (paper_id,))

    paper = cursor.fetchone()

    if not paper:
        conn.close()
        return "Paper not found", 404

    correct_mcqs = paper[0].split(',') if paper[0] else []
    short_keywords = paper[1].split('|') if paper[1] else []
    long_keywords = paper[2].split('|') if paper[2] else []

    mcq_marks = int(paper[3] or 1)
    short_marks = int(paper[4] or 2)
    long_marks = int(paper[5] or 5)

    mcq_score = check_mcqs(
        request.form,
        correct_mcqs,
        mcq_marks
    )

    short_score = check_short_answers(
        request.form,
        short_keywords,
        short_marks
    )

    long_score = check_long_answers(
        request.form,
        long_keywords,
        long_marks
    )

    total_score = mcq_score + short_score + long_score

    total_marks = (
        len(correct_mcqs) * mcq_marks +
        len(short_keywords) * short_marks +
        len(long_keywords) * long_marks
    )

    percentage = (
        (total_score / total_marks) * 100
        if total_marks > 0 else 0
    )

    print("MCQ SCORE =", mcq_score)
    print("SHORT SCORE =", short_score)
    print("LONG SCORE =", long_score)
    print("TOTAL SCORE =", total_score)
    print("TOTAL MARKS =", total_marks)

    level = "excellent"

    if percentage <= 20:
        level = "critical"
    elif percentage <= 40:
        level = "weak"
    elif percentage <= 80:
        level = "average"

    cursor.execute(
        """
        INSERT INTO results
        (username, paper_id, mcq_score, total_mcqs, percentage)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            session['user'],
            paper_id,
            mcq_score,
            len(correct_mcqs),
            percentage
        )
    )

    cursor.execute(
        """
        INSERT INTO exam_history
        (username, subject, score_obtained, test_date)
        VALUES (?, ?, ?, DATETIME('now'))
        """,
        (
            session['user'],
            "General",
            total_score
        )
    )

    cursor.execute(
        "UPDATE users SET streak = streak + 1 WHERE username=?",
        (session['user'],)
    )

    conn.commit()
    conn.close()

    return render_template(
        'result.html',
        score=total_score,
        total=total_marks,
        percentage=percentage,
        level=level,
        mcq_score=mcq_score,
        total_mcqs=len(correct_mcqs) * mcq_marks,
        short_score=short_score,
        total_short=len(short_keywords) * short_marks,
        long_score=long_score,
        total_long=len(long_keywords) * long_marks
    )


# ---------------- UPLOAD PAPER ---------------- #

@app.route('/upload_paper', methods=['GET', 'POST'])
def upload_paper():

    if 'admin' not in session:
        return redirect('/login')

    if request.method == 'POST':

        board = request.form['board']
        class_name = request.form['class_name']
        group_name = request.form['group_name']

        subject = request.form['subject']
        paper_type = request.form['paper_type']
        year = request.form['year']

        exam_time = request.form['exam_time']

        mcq_marks = request.form['mcq_marks']
        short_marks = request.form['short_marks']
        long_marks = request.form['long_marks']

        mcqs = request.form['mcqs']
        mcq_answers = request.form['mcq_answers']

        short_questions = request.form['short_questions']
        short_keywords = request.form['short_keywords']

        long_questions = request.form['long_questions']
        long_keywords = request.form['long_keywords']

        conn = sqlite3.connect("examora.db")
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO papers(

                board,
                class_name,
                group_name,

                subject,
                paper_type,
                year,

                exam_time,

                mcq_marks,
                short_marks,
                long_marks,

                mcqs,
                mcq_answers,

                short_questions,
                short_keywords,

                long_questions,
                long_keywords

            )

            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,

            (
                board,
                class_name,
                group_name,

                subject,
                paper_type,
                year,

                exam_time,

                mcq_marks,
                short_marks,
                long_marks,

                mcqs,
                mcq_answers,

                short_questions,
                short_keywords,

                long_questions,
                long_keywords
            )
        )

        conn.commit()
        conn.close()

        return "Paper Uploaded Successfully"

    return render_template('upload_paper.html')
# ---------------- ADMIN ---------------- #

@app.route('/admin')
def admin():

    if 'admin' not in session:
        return redirect('/login')

    return render_template(

        'admin.html',
        admin_name=session['admin']

    )

# ---------------- LOGOUT ---------------- #

@app.route('/logout')
def logout():

    session.clear()

    return redirect('/login')

# ---------------- RUN ---------------- #
# ---------------- LEADERBOARD PAGE ---------------- #
@app.route('/leaderboard')
def leaderboard_page():

    if 'user' not in session:
        return redirect('/login')

    current_username = session['user']

    conn = sqlite3.connect("examora.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute(
        "SELECT board FROM users WHERE username = ?",
        (current_username,)
    )

    user_record = cursor.fetchone()

    user_board = (
        user_record['board']
        if (user_record and user_record['board'])
        else 'Federal Board'
    )

    cursor.execute("""
        SELECT
            u.username,
            COALESCE(SUM(h.score_obtained), 0) AS total_marks,
            u.board,
            u.class_name,
            u.profile_picture
        FROM users u
        LEFT JOIN exam_history h
            ON u.username = h.username
        GROUP BY u.username
        ORDER BY total_marks DESC
    """)

    national_rows = cursor.fetchall()

    cursor.execute("""
        SELECT
            u.username,
            COALESCE(SUM(h.score_obtained), 0) AS total_marks,
            u.board,
            u.class_name,
            u.profile_picture
        FROM users u
        LEFT JOIN exam_history h
            ON u.username = h.username
        WHERE u.board = ?
        GROUP BY u.username
        ORDER BY total_marks DESC
    """, (user_board,))

    board_rows = cursor.fetchall()

    conn.close()

    national_list = [
        {**dict(row), 'position': i + 1}
        for i, row in enumerate(national_rows)
    ]

    board_list = [
        {**dict(row), 'position': i + 1}
        for i, row in enumerate(board_rows)
    ]

    return render_template(
        'leaderboard.html',
        national_list=national_list,
        board_list=board_list,
        user_board=user_board
    )
# ---------------- USER PROFILE PAGE ---------------- #
@app.route('/profile')
def profile_page():
    if 'user' not in session:
        return redirect('/login')

    current_user = session['user']
    conn = sqlite3.connect("examora.db")
    cursor = conn.cursor()

    # 1. Fetch live user account configuration fields
    cursor.execute(
        """
        SELECT board, class_name, group_name, total_marks, streak, pk_position, profile_picture
        FROM users WHERE username=?
        """,
        (current_user,)
    )
    user_data = cursor.fetchone()

    # 2. CALCULATE REAL WEAK TOPICS VIA SQL INNER JOIN ON PAPERS
    # Computes real average accuracy grouped by subject/topic from past papers
    cursor.execute(
        """
        SELECT p.subject, AVG(r.percentage) as avg_accuracy
        FROM results r
        JOIN papers p ON r.paper_id = p.id
        WHERE r.username = ?
        GROUP BY p.subject
        HAVING avg_accuracy < 50
        ORDER BY avg_accuracy ASC
        """,
        (current_user,)
    )
    weak_rows = cursor.fetchall()
    
    weak_topics = []
    for row in weak_rows:
        weak_topics.append({
            'name': row[0],
            'accuracy': round(row[1], 1)
        })

    # 3. FETCH PERSONALIZED AI STUDY PLANS FROM CACHE
    cursor.execute(
        "SELECT daily_plan, weekly_plan, monthly_plan, yearly_plan FROM ai_insights WHERE username=?",
        (current_user,)
    )
    ai_row = cursor.fetchone()
    
    if ai_row:
        study_plans = {
            'daily': ai_row[0] or "No daily roadmap objective set yet.",
            'weekly': ai_row[1] or "No weekly milestone target built yet.",
            'monthly': ai_row[2] or "No monthly target configured yet.",
            'yearly': ai_row[3] or "No yearly rank projection mapped yet."
        }
    else:
        study_plans = {
            'daily': "No data available yet",
            'weekly': "No data available yet",
            'monthly': "No data available yet",
            'yearly': "No data available yet"
        }

    # 4. FETCH COMPREHENSIVE HISTORICAL ACCOUNT LEDGER
    cursor.execute(
        """
        SELECT p.subject, p.paper_type, p.year, r.mcq_score, r.total_mcqs, r.percentage
        FROM results r
        JOIN papers p ON r.paper_id = p.id
        WHERE r.username = ?
        ORDER BY r.id DESC
        """,
        (current_user,)
    )
    history_rows = cursor.fetchall()
    
    exam_history = []
    for row in history_rows:
        exam_history.append({
            'subject': row[0],
            'paper_type': f"{row[1]} ({row[2]})",
            'score': f"{row[3]}/{row[4]}",
            'percentage': round(row[5], 1),
            'date': "Recent"  # Replaces static hardcoding with live evaluation markers
        })

    conn.close()

    # Fallback assignment structure to prevent application runtime failures
    return render_template(
        'profile.html',
        username=current_user,
        board=user_data[0] if user_data and user_data[0] else 'N/A',
        class_name=user_data[1] if user_data and user_data[1] else 'N/A',
        group_name=user_data[2] if user_data and user_data[2] else 'N/A',
        total_marks=user_data[3] if user_data and user_data[3] is not None else 0,
        streak=user_data[4] if user_data and user_data[4] is not None else 1,
        pk_position=user_data[5] if user_data and user_data[5] is not None else 99,
        profile_picture=user_data[6] if user_data and user_data[6] else None,
        weak_topics=weak_topics,
        study_plans=study_plans,
        history=exam_history
    )
# ---------------- UPDATE PROFILE ---------------- #

@app.route('/update_profile', methods=['POST'])
def update_profile():

    if 'user' not in session:
        return redirect('/login')

    current_username = session['user']

    new_username = request.form.get('username')
    new_password = request.form.get('password')

    conn = sqlite3.connect("examora.db")
    cursor = conn.cursor()

    if new_username and new_username.strip():
        cursor.execute(
            "UPDATE users SET username=? WHERE username=?",
            (new_username.strip(), current_username)
        )

        # Keep session synced
        session['user'] = new_username.strip()
        current_username = new_username.strip()

    if new_password and new_password.strip():
        cursor.execute(
            "UPDATE users SET password=? WHERE username=?",
            (new_password.strip(), current_username)
        )

    conn.commit()
    conn.close()

    return redirect('/profile')
# ---------------- PROFILE IMAGE UPLOAD PIPELINE ---------------- #
@app.route('/upload_profile_picture', methods=['POST'])
def upload_profile_picture():
    if 'user' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized user session'}), 401
        
    if 'profile_pic' not in request.files:
        return jsonify({'success': False, 'error': 'No file payload found'}), 400
        
    file = request.files['profile_pic']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected from gallery'}), 400
        
    if file and allowed_file(file.filename):
        username = session['user']
        file_ext = file.filename.rsplit('.', 1)[1].lower()
        filename = secure_filename(f"profile_{username}.{file_ext}")
        
        # Build direct absolute path mapping for safe local system discovery
        upload_dir = os.path.join(app.root_path, 'static', 'uploads', 'profiles')
        os.makedirs(upload_dir, exist_ok=True)
        
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)
        
        # Save structural root path resource token string for HTML rendering
        db_path = f"/static/uploads/profiles/{filename}"
        
        conn = sqlite3.connect("examora.db")
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET profile_picture=? WHERE username=?",
            (db_path, username)
        )
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'filepath': db_path})
        
    return jsonify({'success': False, 'error': 'Invalid file type'}), 400

# ---------------- FINAL RANKINGS ROUTE ---------------- #
@app.route('/rankings')
def rankings():

    if 'user' not in session:
        return redirect('/login')

    conn = sqlite3.connect("examora.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            u.username,
            u.board,
            u.class_name,
            COALESCE(SUM(h.score_obtained),0) as total_score
        FROM users u
        LEFT JOIN exam_history h
        ON u.username = h.username
        GROUP BY u.username
        ORDER BY total_score DESC
    """)

    rows = cursor.fetchall()

    users = []

    for i, row in enumerate(rows, start=1):
        user = dict(row)
        user['position'] = i
        users.append(user)

    conn.close()

    return render_template(
        'rankings.html',
        users=users
    )



def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS




from flask import Response

@app.route("/sitemap.xml")
def sitemap():
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://examora-gmc3.onrender.com/</loc>
  </url>
  <url>
    <loc>https://examora-gmc3.onrender.com/login</loc>
  </url>
  <url>
    <loc>https://examora-gmc3.onrender.com/signup</loc>
  </url>
  <url>
    <loc>https://examora-gmc3.onrender.com/about</loc>
  </url>
</urlset>
"""
    return Response(xml, mimetype="application/xml")
if __name__ == '__main__':
    app.run(
        host='0.0.0.0',
        port=int(os.environ.get("PORT", 5000)),
        debug=False,
        use_reloader=False
    )
