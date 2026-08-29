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


def save_source_group(
    files,
    source_type,
    board=None,
    class_name=None,
    group_name=None,
    subject=None
):
    create_normalization_tables()

    if not files:
        raise ValueError("No source files were provided.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    source_directory = (
        UPLOAD_DIRECTORY /
        f"source_{timestamp}"
    )

    source_directory.mkdir(
        parents=True,
        exist_ok=True
    )

    conn = get_connection()
    cursor = conn.cursor()

    first_name = files[0].filename

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
        first_name if source_type == "PDF"
        else f"{len(files)} images",

        source_type,

        board,
        class_name,
        group_name,
        subject,

        str(source_directory),

        "UPLOADED"
    ))

    upload_id = cursor.lastrowid

    for page_number, file in enumerate(files, start=1):

        original_name = Path(file.filename).name

        destination = (
            source_directory /
            f"{page_number:04d}_{original_name}"
        )

        file.save(destination)

        cursor.execute("""
            INSERT INTO source_pages (
                upload_id,
                page_number,
                page_path,
                original_type,
                status
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            upload_id,
            page_number,
            str(destination),
            source_type,
            "UPLOADED"
        ))

    conn.commit()
    conn.close()

    return {
        "upload_id": upload_id,
        "source_type": source_type,
        "file_count": len(files),
        "status": "UPLOADED"
    }


if __name__ == "__main__":
    create_normalization_tables()
    print("Examora Source Normalizer is ready.")
