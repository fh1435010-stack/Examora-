import sqlite3
import re
from datetime import datetime


DB_PATH = "examora.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_text(text):
    if not text:
        return ""

    text = text.lower()

    replacements = {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def get_words(text):
    normalized = normalize_text(text)

    if not normalized:
        return set()

    return set(
        word
        for word in normalized.split()
        if len(word) >= 2
    )


def calculate_word_agreement(text_a, text_b):
    words_a = get_words(text_a)
    words_b = get_words(text_b)

    if not words_a and not words_b:
        return 0.0

    if not words_a or not words_b:
        return 0.0

    intersection = words_a.intersection(words_b)
    union = words_a.union(words_b)

    if not union:
        return 0.0

    return round((len(intersection) / len(union)) * 100, 2)


def calculate_character_similarity(text_a, text_b):
    a = normalize_text(text_a)
    b = normalize_text(text_b)

    if not a or not b:
        return 0.0

    max_length = max(len(a), len(b))

    if max_length == 0:
        return 0.0

    matches = sum(
        1
        for char_a, char_b in zip(a, b)
        if char_a == char_b
    )

    return round((matches / max_length) * 100, 2)


def get_page_rows(cursor, upload_id):
    cursor.execute(
        """
        SELECT
            rpc.upload_id,
            rpc.page_number,
            rpc.original_text,
            rpc.recovered_text,
            rpc.recovery_status,
            rpc.recovery_priority,
            rpc.corruption_score,

            ave.verification_status,
            ave.verification_confidence,
            ave.knowledge_status,

            cpc.cleaned_text,

            pov.best_text

        FROM recovered_page_content rpc

        LEFT JOIN accuracy_verification ave
            ON ave.upload_id = rpc.upload_id
            AND ave.page_number = rpc.page_number

        LEFT JOIN cleaned_page_content cpc
            ON cpc.upload_id = rpc.upload_id
            AND cpc.page_number = rpc.page_number

        LEFT JOIN ocr_verification pov
            ON pov.upload_id = rpc.upload_id
            AND pov.page_number = rpc.page_number

        WHERE rpc.upload_id = ?

        ORDER BY rpc.page_number
        """,
        (upload_id,)
    )

    return cursor.fetchall()


def determine_source_grounded_status(
    recovery_status,
    verification_status,
    knowledge_status,
    word_agreement,
    character_similarity,
    corruption_score
):
    """
    Safety-first decision engine.

    This engine does NOT invent confidence.
    If evidence conflicts or is insufficient,
    the page is blocked or sent for review.
    """

    if verification_status == "BLOCKED":
        return (
            "BLOCKED",
            "BLOCKED",
            0,
            "Accuracy verification already blocked this page."
        )

    if knowledge_status != "READY":
        return (
            "REQUIRES_REVIEW",
            "BLOCKED",
            1,
            "Previous verification did not authorize knowledge use."
        )

    if recovery_status == "RECOVERED_UNCERTAIN":
        return (
            "REQUIRES_REVIEW",
            "BLOCKED",
            1,
            "Recovery was marked uncertain."
        )

    if word_agreement < 70:
        return (
            "SOURCE_CONFLICT",
            "BLOCKED",
            1,
            f"Low cross-version word agreement: {word_agreement}%."
        )

    if character_similarity < 50:
        return (
            "SOURCE_CONFLICT",
            "BLOCKED",
            1,
            f"Low character similarity: {character_similarity}%."
        )

    if corruption_score >= 40:
        return (
            "HIGH_RISK_REVIEW",
            "BLOCKED",
            1,
            f"High original corruption score: {corruption_score}."
        )

    if word_agreement >= 90 and character_similarity >= 75:
        return (
            "SOURCE_GROUNDED_VERIFIED",
            "READY_FOR_NEXT_STAGE",
            0,
            "Strong agreement across independently stored content versions."
        )

    return (
        "REQUIRES_REVIEW",
        "BLOCKED",
        1,
        "Evidence is insufficient for automatic approval."
    )


def create_table_if_needed(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS source_grounded_accuracy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            upload_id INTEGER NOT NULL,
            page_number INTEGER NOT NULL,

            source_word_agreement REAL DEFAULT 0,
            source_character_similarity REAL DEFAULT 0,

            verification_status TEXT NOT NULL,
            knowledge_status TEXT NOT NULL,

            admin_review_required INTEGER DEFAULT 0,
            validation_notes TEXT,

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(upload_id, page_number)
        )
        """
    )


def save_result(cursor, result):
    cursor.execute(
        """
        INSERT INTO source_grounded_accuracy (
            upload_id,
            page_number,
            source_word_agreement,
            source_character_similarity,
            verification_status,
            knowledge_status,
            admin_review_required,
            validation_notes,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(upload_id, page_number)
        DO UPDATE SET
            source_word_agreement = excluded.source_word_agreement,
            source_character_similarity = excluded.source_character_similarity,
            verification_status = excluded.verification_status,
            knowledge_status = excluded.knowledge_status,
            admin_review_required = excluded.admin_review_required,
            validation_notes = excluded.validation_notes,
            updated_at = excluded.updated_at
        """,
        (
            result["upload_id"],
            result["page_number"],
            result["word_agreement"],
            result["character_similarity"],
            result["verification_status"],
            result["knowledge_status"],
            result["admin_review_required"],
            result["notes"],
            datetime.now().isoformat(timespec="seconds")
        )
    )


def build_source_grounded_accuracy(upload_id):
    print()
    print(
        f"Examora Source-Grounded Accuracy Validation started "
        f"for Upload ID {upload_id}"
    )

    conn = get_connection()
    cursor = conn.cursor()

    create_table_if_needed(cursor)

    rows = get_page_rows(cursor, upload_id)

    print(f"Pages to validate: {len(rows)}")
    print()

    summary = {}

    for row in rows:
        page_number = row["page_number"]

        cleaned_text = row["cleaned_text"] or ""
        verified_ocr_text = row["best_text"] or ""
        recovered_text = row["recovered_text"] or ""
        original_text = row["original_text"] or ""

        # Prefer the strongest available comparison texts.
        baseline_text = cleaned_text or original_text or verified_ocr_text
        candidate_text = recovered_text or verified_ocr_text or original_text

        word_agreement = calculate_word_agreement(
            baseline_text,
            candidate_text
        )

        character_similarity = calculate_character_similarity(
            baseline_text,
            candidate_text
        )

        (
            verification_status,
            knowledge_status,
            admin_review_required,
            notes
        ) = determine_source_grounded_status(
            row["recovery_status"],
            row["verification_status"],
            row["knowledge_status"],
            word_agreement,
            character_similarity,
            row["corruption_score"]
        )

        result = {
            "upload_id": upload_id,
            "page_number": page_number,
            "word_agreement": word_agreement,
            "character_similarity": character_similarity,
            "verification_status": verification_status,
            "knowledge_status": knowledge_status,
            "admin_review_required": admin_review_required,
            "notes": notes
        }

        save_result(cursor, result)

        summary[verification_status] = (
            summary.get(verification_status, 0) + 1
        )

        print(
            f"Page {page_number} | "
            f"status: {verification_status} | "
            f"word agreement: {word_agreement}% | "
            f"knowledge: {knowledge_status}"
        )

    conn.commit()
    conn.close()

    print()
    print("Examora Source-Grounded Accuracy Validation completed.")

    return {
        "upload_id": upload_id,
        "pages_processed": len(rows),
        "validation_summary": summary,
        "status": "SOURCE_GROUNDED_VALIDATION_COMPLETED"
    }


if __name__ == "__main__":
    print(
        "Examora Source-Grounded Accuracy Engine is ready."
    )
