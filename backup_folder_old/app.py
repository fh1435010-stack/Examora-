from flask import Flask, render_template, request, redirect, session
import sqlite3

app = Flask(__name__)
app.secret_key = "examora_secret_key"

# ---------------- DATABASE ---------------- #

def init_db():

    conn = sqlite3.connect("examora.db")
    cursor = conn.cursor()

    # USERS TABLE

    cursor.execute("""

    CREATE TABLE IF NOT EXISTS users(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        username TEXT UNIQUE,
        password TEXT,

        board TEXT,
        class_name TEXT,
        group_name TEXT

    )

    """)

    # PAPERS TABLE

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

    # RESULTS TABLE

    cursor.execute("""

    CREATE TABLE IF NOT EXISTS results(

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        username TEXT,
        paper_id INTEGER,

        mcq_score INTEGER,
        total_mcqs INTEGER,

        percentage REAL

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

    return redirect('/login')

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

    cursor.execute(

        """

        SELECT board, class_name, group_name

        FROM users

        WHERE username=?

        """,

        (session['user'],)

    )

    data = cursor.fetchone()

    conn.close()

    board = data[0]
    class_name = data[1]
    group_name = data[2]

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

    return render_template(

        'dashboard.html',

        username=session['user'],
        board=board,
        class_name=class_name,
        group_name=group_name,
        subjects=subjects

    )

# ---------------- SUBJECT PAGE ---------------- #

@app.route('/subject/<subject_name>')
def subject_page(subject_name):

    if 'user' not in session:
        return redirect('/login')

    conn = sqlite3.connect("examora.db")
    cursor = conn.cursor()

    cursor.execute(

        """

        SELECT board, class_name, group_name

        FROM users

        WHERE username=?

        """,

        (session['user'],)

    )

    user = cursor.fetchone()

    board = user[0]
    class_name = user[1]
    group_name = user[2]

    cursor.execute(

        """

        SELECT id, paper_type, year

        FROM papers

        WHERE board=?
        AND class_name=?
        AND group_name=?
        AND subject=?

        """,

        (

            board,
            class_name,
            group_name,
            subject_name

        )

    )

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
        return "Paper Not Found"

    mcqs = paper[8].split('\n')

    short_questions = paper[10].split('\n')

    long_questions = paper[12].split('\n')

    return render_template(

        'take_exam.html',

        paper=paper,

        mcqs=mcqs,
        short_questions=short_questions,
        long_questions=long_questions

    )

# ---------------- SUBMIT EXAM ---------------- #

@app.route('/submit_exam/<int:paper_id>', methods=['POST'])
def submit_exam(paper_id):

    if 'user' not in session:
        return redirect('/login')

    conn = sqlite3.connect("examora.db")
    cursor = conn.cursor()

    cursor.execute(

        "SELECT mcq_answers FROM papers WHERE id=?",

        (paper_id,)

    )

    data = cursor.fetchone()

    correct_answers = data[0].split(',')

    total = len(correct_answers)

    score = 0

    for i in range(total):

        student_answer = request.form.get(f"mcq{i}")

        if student_answer:

            if student_answer.strip().lower() == correct_answers[i].strip().lower():

                score += 1

    percentage = (score / total) * 100

    cursor.execute(

        """

        INSERT INTO results(

            username,
            paper_id,

            mcq_score,
            total_mcqs,

            percentage

        )

        VALUES(?, ?, ?, ?, ?)

        """,

        (

            session['user'],
            paper_id,

            score,
            total,

            percentage

        )

    )

    conn.commit()
    conn.close()

    return render_template(

        'result.html',

        score=score,
        total=total,
        percentage=percentage

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

                mcqs,
                mcq_answers,

                short_questions,
                short_keywords,

                long_questions,
                long_keywords

            )

            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

            """,

            (

                board,
                class_name,
                group_name,

                subject,
                paper_type,
                year,

                exam_time,

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

if __name__ == '__main__':

    app.run(debug=True)
