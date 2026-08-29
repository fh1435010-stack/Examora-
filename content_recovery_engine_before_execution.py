import sqlite3
import re
from datetime import datetime


DB_PATH = "examora.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_recovery_table(conn):
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recovered_page_content (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            upload_id INTEGER NOT NULL,
            page_number INTEGER NOT NULL,

            source_cleaned_content_id INTEGER,

            original_quality_status TEXT,
            suspicious_patterns TEXT,

            recovery_status TEXT NOT NULL,
            recovery_priority TEXT NOT NULL,

            original_text TEXT,
            recovered_text TEXT,

            corruption_score REAL DEFAULT 0,
            recovery_notes TEXT,

            admin_review_required INTEGER DEFAULT 0,
            admin_notification_status TEXT DEFAULT 'NONE',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(upload_id, page_number)
        )
    """)

    conn.commit()


def calculate_corruption_score(text, suspicious_patterns):
    """
    Higher score = more suspicious/corrupted content.
    This function does NOT try to invent or correct knowledge.
    It only measures how suspicious the text appears.
    """

    if not text:
        return 100.0

    total_chars = len(text)

    letters = len(re.findall(r"[A-Za-z]", text))
    digits = len(re.findall(r"\d", text))

    unusual_chars = len(re.findall(
        r"""[^A-Za-z0-9\s.,;:!?()\[\]{}'"%+\-=/\\×x²³°]""",
        text
    ))

    letter_ratio = letters / total_chars if total_chars else 0
    unusual_ratio = unusual_chars / total_chars if total_chars else 0

    short_word_matches = re.findall(r"\b[A-Za-z]{1,2}\b", text)
    short_word_ratio = (
        len(short_word_matches) / max(1, len(re.findall(r"\S+", text)))
    )

    score = 0.0

    # Too many unusual symbols
    score += unusual_ratio * 100

    # Extremely low amount of readable alphabetic content
    if letter_ratio < 0.20:
        score += 35
    elif letter_ratio < 0.40:
        score += 15

    # Too many isolated tiny fragments can indicate broken OCR
    if short_word_ratio > 0.60:
        score += 15
    elif short_word_ratio > 0.40:
        score += 8

    # Existing cleaning warnings
    if suspicious_patterns:
        if "MANY_UNUSUAL_SYMBOLS" in suspicious_patterns:
            score += 15

        if "POSSIBLE_BROKEN_WORDS" in suspicious_patterns:
            score += 25

    return round(min(score, 100), 2)


def decide_recovery_status(quality_status, corruption_score):
    """
    Decide what should happen next.

    IMPORTANT:
    This does not claim bad OCR is correct.
    It decides whether the page needs another recovery attempt
    or human/admin review.
    """

    if quality_status == "CLEAN" and corruption_score < 15:
        return (
            "CLEAN_ACCEPTED",
            "LOW",
            0,
            "NONE",
            "Content appears sufficiently clean. No recovery required."
        )

    if corruption_score >= 60:
        return (
            "REQUIRES_REVIEW",
            "CRITICAL",
            1,
            "PENDING",
            "Severe corruption detected. Do not use this content as trusted knowledge."
        )

    if corruption_score >= 30:
        return (
            "RECOVERY_REQUIRED",
            "HIGH",
            0,
            "NONE",
            "Content requires automatic source recovery and OCR comparison."
        )

    return (
        "RECOVERY_REQUIRED",
        "NORMAL",
        0,
        "NONE",
        "Minor OCR issues detected. Automatic recovery/cross-check recommended."
    )


def build_recovered_content(upload_id):
    print(f"\nExamora Content Recovery Engine started for Upload ID {upload_id}")

    conn = get_connection()
    ensure_recovery_table(conn)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            upload_id,
            page_number,
            original_characters,
            cleaned_characters,
            quality_status,
            suspicious_patterns,
            cleaned_text
        FROM cleaned_page_content
        WHERE upload_id = ?
        ORDER BY page_number
    """, (upload_id,))

    pages = cursor.fetchall()

    if not pages:
        conn.close()
        return {
            "upload_id": upload_id,
            "pages_processed": 0,
            "status": "NO_CLEANED_CONTENT_FOUND"
        }

    print(f"Pages to analyze: {len(pages)}")

    status_summary = {}

    for page in pages:
        page_id = page["id"]
        page_number = page["page_number"]
        quality_status = page["quality_status"]
        suspicious_patterns = page["suspicious_patterns"] or ""
        cleaned_text = page["cleaned_text"] or ""

        corruption_score = calculate_corruption_score(
            cleaned_text,
            suspicious_patterns
        )

        (
            recovery_status,
            recovery_priority,
            admin_review_required,
            admin_notification_status,
            recovery_notes
        ) = decide_recovery_status(
            quality_status,
            corruption_score
        )

        # IMPORTANT:
        # recovered_text is currently the same as cleaned_text.
        # We do NOT invent corrections.
        # A future recovery stage will compare multiple OCR attempts
        # and only replace it when evidence supports the new result.
        recovered_text = cleaned_text

        cursor.execute("""
            INSERT INTO recovered_page_content (
                upload_id,
                page_number,
                source_cleaned_content_id,
                original_quality_status,
                suspicious_patterns,
                recovery_status,
                recovery_priority,
                original_text,
                recovered_text,
                corruption_score,
                recovery_notes,
                admin_review_required,
                admin_notification_status,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)

            ON CONFLICT(upload_id, page_number)
            DO UPDATE SET
                source_cleaned_content_id = excluded.source_cleaned_content_id,
                original_quality_status = excluded.original_quality_status,
                suspicious_patterns = excluded.suspicious_patterns,
                recovery_status = excluded.recovery_status,
                recovery_priority = excluded.recovery_priority,
                original_text = excluded.original_text,
                recovered_text = excluded.recovered_text,
                corruption_score = excluded.corruption_score,
                recovery_notes = excluded.recovery_notes,
                admin_review_required = excluded.admin_review_required,
                admin_notification_status = excluded.admin_notification_status,
                updated_at = CURRENT_TIMESTAMP
        """, (
            upload_id,
            page_number,
            page_id,
            quality_status,
            suspicious_patterns,
            recovery_status,
            recovery_priority,
            cleaned_text,
            recovered_text,
            corruption_score,
            recovery_notes,
            admin_review_required,
            admin_notification_status
        ))

        status_summary[recovery_status] = (
            status_summary.get(recovery_status, 0) + 1
        )

        print(
            f"Page {page_number} analyzed | "
            f"corruption: {corruption_score} | "
            f"status: {recovery_status} | "
            f"priority: {recovery_priority}"
        )

    conn.commit()
    conn.close()

    print("\nExamora Content Recovery Engine completed.")

    return {
        "upload_id": upload_id,
        "pages_processed": len(pages),
        "recovery_summary": status_summary,
        "status": "RECOVERY_ANALYSIS_READY"
    }


if __name__ == "__main__":
    print("Examora Content Recovery Engine is ready.")
