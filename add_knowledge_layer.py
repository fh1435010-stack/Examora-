import sqlite3

DB_NAME = "examora.db"

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

# =========================================================
# 1. TRUSTED KNOWLEDGE SOURCES
# =========================================================
cursor.execute("""
CREATE TABLE IF NOT EXISTS knowledge_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    source_type TEXT NOT NULL,
    board TEXT,
    class_name TEXT,
    subject TEXT,
    source_url TEXT,
    trust_level TEXT NOT NULL DEFAULT 'PENDING',
    status TEXT NOT NULL DEFAULT 'PENDING',
    added_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# =========================================================
# 2. VERIFIED KNOWLEDGE CHUNKS
# Only approved content should be used as trusted knowledge
# =========================================================
cursor.execute("""
CREATE TABLE IF NOT EXISTS knowledge_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id INTEGER NOT NULL,
    board TEXT,
    class_name TEXT,
    subject TEXT,
    topic TEXT,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    approved_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (source_id) REFERENCES knowledge_sources(id)
)
""")

# =========================================================
# 3. AI-DISCOVERED IMPROVEMENT CANDIDATES
# Student messages can suggest improvements,
# but NEVER automatically become trusted facts.
# =========================================================
cursor.execute("""
CREATE TABLE IF NOT EXISTS knowledge_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT,
    subject TEXT,
    topic TEXT,
    candidate_type TEXT NOT NULL,
    evidence TEXT,
    suggested_content TEXT,
    confidence REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# =========================================================
# 4. ADMIN REVIEW HISTORY
# =========================================================
cursor.execute("""
CREATE TABLE IF NOT EXISTS knowledge_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER,
    reviewer TEXT NOT NULL,
    decision TEXT NOT NULL,
    review_notes TEXT,
    reviewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (candidate_id)
        REFERENCES knowledge_candidates(id)
)
""")

# =========================================================
# INDEXES FOR FASTER AI KNOWLEDGE SEARCH
# =========================================================
cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_knowledge_chunks_search
ON knowledge_chunks(board, class_name, subject, topic, status)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_knowledge_sources_search
ON knowledge_sources(board, class_name, subject, status)
""")

cursor.execute("""
CREATE INDEX IF NOT EXISTS idx_knowledge_candidates_status
ON knowledge_candidates(status, subject, topic)
""")

conn.commit()

print("SUCCESS: Examora Knowledge Safety Layer created.")

tables = [
    "knowledge_sources",
    "knowledge_chunks",
    "knowledge_candidates",
    "knowledge_reviews"
]

print("\nChecking tables...")

for table in tables:
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    )

    if cursor.fetchone():
        print(f"OK: {table}")
    else:
        print(f"ERROR: {table}")

conn.close()
