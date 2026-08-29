import sqlite3

DB_NAME = "examora.db"

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# 1. AI CONVERSATIONS
cursor.execute("""
CREATE TABLE IF NOT EXISTS ai_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    title TEXT,
    subject TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# 2. EVERY MESSAGE IN A CONVERSATION
cursor.execute("""
CREATE TABLE IF NOT EXISTS ai_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    subject TEXT,
    topic TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES ai_conversations(id)
)
""")

# 3. LONG-TERM STUDENT AI LEARNING PROFILE
cursor.execute("""
CREATE TABLE IF NOT EXISTS student_ai_profile (
    username TEXT PRIMARY KEY,
    preferred_language TEXT DEFAULT 'English',
    explanation_level TEXT DEFAULT 'student',
    preferred_style TEXT DEFAULT NULL,
    strong_topics TEXT DEFAULT NULL,
    weak_topics TEXT DEFAULT NULL,
    common_mistakes TEXT DEFAULT NULL,
    learning_notes TEXT DEFAULT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# 4. STUDENT FEEDBACK ON AI ANSWERS
cursor.execute("""
CREATE TABLE IF NOT EXISTS ai_feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    rating INTEGER,
    feedback_text TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (message_id) REFERENCES ai_messages(id)
)
""")

# Performance indexes
cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_ai_conversations_username
ON ai_conversations(username)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_ai_messages_conversation
ON ai_messages(conversation_id)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_ai_messages_subject_topic
ON ai_messages(subject, topic)
""")

conn.commit()

print("SUCCESS: AI memory tables created safely.")

tables = [
    "ai_conversations",
    "ai_messages",
    "student_ai_profile",
    "ai_feedback"
]

for table in tables:
    cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table}'")
    result = cursor.fetchone()

    if result:
        print(f"OK: {table}")
    else:
        print(f"ERROR: {table} was not created")

conn.close()
