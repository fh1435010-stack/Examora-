import shutil
import sqlite3
from pathlib import Path
from datetime import datetime


DATABASE = "examora.db"

UPLOAD_DIRECTORY = Path("knowledge_uploads")
NORMALIZED_DIRECTORY = Path("normalized_pages")

UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
NORMALIZED_DIRECTORY.mkdir(parents=True, exist_ok=True)


def get_connection():
    return sqlite3.connect(DATABASE)


def create_normalization_tables():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            board TEXT,
            class_name TEXT,
            group_name TEXT,
            subject TEXT,
            upload_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'UPLOADED',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS source_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id INTEGER NOT NULL,
            page_number INTEGER NOT NULL,
            page_path TEXT NOT NULL,
            original_type TEXT,
            width INTEGER,
            height INTEGER,
            status TEXT NOT NULL DEFAULT 'NORMALIZED',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (upload_id)
                REFERENCES knowledge_uploads(id)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_source_pages_upload_page
        ON source_pages(upload_id, page_number)
    """)

    conn.commit()
    conn.close()


def save_uploaded_source(
    source_file,
    board=None,
    class_name=None,
    group_name=None,
    subject=None
):
    create_normalization_tables()

    source_path = Path(source_file)

    if not source_path.exists():
        raise FileNotFoundError(
            f"Source file not found: {source_file}"
        )

    suffix = source_path.suffix.lower()

    if suffix == ".pdf":
        source_type = "PDF"

    elif suffix in [".jpg", ".jpeg", ".png", ".webp"]:
        source_type = "IMAGE"

    else:
        raise ValueError(
            "Unsupported source type. "
            "Only PDF and image files are currently supported."
        )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    stored_name = f"{timestamp}_{source_path.name}"

    destination = UPLOAD_DIRECTORY / stored_name

    shutil.copy2(
        source_path,
        destination
    )

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO knowledge_uploads (
            original_name,
            source_type,
            board,
            class_name,
            group_name,
            subject,
            upload_path,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        source_path.name,
        source_type,
        board,
        class_name,
        group_name,
        subject,
        str(destination),
        "UPLOADED"
    ))

    upload_id = cursor.lastrowid

    conn.commit()
    conn.close()

    return {
        "upload_id": upload_id,
        "source_type": source_type,
        "upload_path": str(destination),
        "status": "UPLOADED"
    }


if __name__ == "__main__":
    create_normalization_tables()

    print(
        "Examora Source Normalizer foundation is ready."
    )
