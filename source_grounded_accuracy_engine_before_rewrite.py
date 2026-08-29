import sqlite3
import re
from difflib import SequenceMatcher


DB_PATH = "examora.db"


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):
    if text is None:
        return ""

    text = str(text)

    # Normalize whitespace only.
    # We deliberately DO NOT "correct" words, numbers, formulas,
    # symbols, punctuation, or scientific notation.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def character_similarity(a, b):
    a = normalize_text(a)
    b = normalize_text(b)

    if not a and not b:
        return 1.0

    if not a or not b:
        return 0.0

    return SequenceMatcher(None, a, b).ratio()


def word_agreement(a, b):
    a = normalize_text(a).lower()
    b = normalize_text(b).lower()

    words_a = re.findall(r"\S+", a)
    words_b = re.findall(r"\S+", b)

    if not words_a and not words_b:
        return 1.0

    if not words_a or not words_b:
        return 0.0

    # Multiset-like comparison using word counts.
    from collections import Counter

    ca = Counter(words_a)
    cb = Counter(words_b)

    common = sum((ca & cb).values())
    total = max(len(words_a), len(words_b))

    return common / total if total else 0.0


# ============================================================
# CRITICAL CONTENT DETECTION
# ============================================================

def extract_numbers(text):
    if not text:
        return []

    return re.findall(
        r"""
        (?<!\w)
        [-+]?
        (?:
            \d+(?:\.\d+)?
            |
            \.\d+
        )
        (?:[eE][-+]?\d+)?
        %?
        """,
        text,
        re.VERBOSE,
    )


def extract_question_markers(text):
    if not text:
        return []

    return re.findall(
        r"(?:^|\n)\s*(?:Q(?:uestion)?\.?\s*)?\d{1,3}[\.\):\-]",
        text,
        re.IGNORECASE,
    )


def extract_option_markers(text):
    if not text:
        return []

    return re.findall(
        r"(?:^|\n)\s*(?:[A-Da-d])[\.\):\-]\s+",
        text,
    )


def critical_content_signature(text):
    return {
        "numbers": extract_numbers(text),
        "questions": extract_question_markers(text),
        "options": extract_option_markers(text),
    }


def critical_content_matches(source_text, verified_text):
    source = critical_content_signature(source_text)
    verified = critical_content_signature(verified_text)

    return {
        "numbers_match": source["numbers"] == verified["numbers"],
        "questions_match": source["questions"] == verified["questions"],
        "options_match": source["options"] == verified["options"],
    }


# ============================================================
# SCHEMA SAFETY
# ============================================================

def get_columns(cursor, table_name):
    rows = cursor.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {row["name"] for row in rows}


def require_columns(cursor, table_name, required):
    columns = get_columns(cursor, table_name)

    missing = sorted(set(required) - columns)

    if missing:
        raise RuntimeError(
            f"Required columns missing from {table_name}: "
            + ", ".join(missing)
        )

    return columns


# ============================================================
# SOURCE DATA
# ============================================================

def get_page_rows(cursor, upload_id):
    require_columns(
        cursor,
        "source_pages",
        [
            "id",
            "upload_id",
            "page_number",
        ],
    )

    require_columns(
        cursor,
        "page_contents",
        [
            "id",
            "upload_id",
            "source_page_id",
            "page_number",
            "content_text",
        ],
    )

    require_columns(
        cursor,
        "accuracy_verification",
        [
            "upload_id",
            "source_page_id",
            "page_number",
            "verification_status",
            "verification_confidence",
            "selected_text",
            "knowledge_brain_status",
        ],
    )

    require_columns(
        cursor,
        "verified_page_content",
        [
            "upload_id",
            "source_page_id",
            "page_number",
            "verified_text",
            "verification_status",
        ],
    )

    return cursor.execute(
        """
        SELECT
            sp.id AS source_page_id,
            sp.page_number,

            pc.id AS page_content_id,
            pc.content_text AS extracted_text,

            av.verification_status AS accuracy_status,
            av.verification_confidence AS accuracy_confidence,
            av.selected_text AS selected_text,
            av.knowledge_brain_status AS previous_knowledge_status,

            vp.verified_text AS verified_text,
            vp.verification_status AS verified_content_status

        FROM source_pages sp

        LEFT JOIN page_contents pc
            ON pc.upload_id = sp.upload_id
           AND pc.source_page_id = sp.id
           AND pc.page_number = sp.page_number

        LEFT JOIN accuracy_verification av
            ON av.upload_id = sp.upload_id
           AND av.source_page_id = sp.id
           AND av.page_number = sp.page_number

        LEFT JOIN verified_page_content vp
            ON vp.upload_id = sp.upload_id
           AND vp.source_page_id = sp.id
           AND vp.page_number = sp.page_number

        WHERE sp.upload_id = ?

        ORDER BY sp.page_number
        """,
        (upload_id,),
    ).fetchall()


# ============================================================
# STRICT DECISION ENGINE
# ============================================================

def evaluate_page(row):
    source_text = normalize_text(row["extracted_text"])
    selected_text = normalize_text(row["selected_text"])
    verified_text = normalize_text(row["verified_text"])

    reasons = []
    notes = []

    # --------------------------------------------------------
    # Required source chain
    # --------------------------------------------------------

    if not row["source_page_id"]:
        reasons.append("MISSING_SOURCE_PAGE")

    if not source_text:
        reasons.append("MISSING_SOURCE_TEXT")

    if not selected_text:
        reasons.append("MISSING_SELECTED_TEXT")

    if not verified_text:
        reasons.append("MISSING_VERIFIED_TEXT")

    # --------------------------------------------------------
    # Existing verification states
    # --------------------------------------------------------

    accuracy_status = (
        str(row["accuracy_status"])
        if row["accuracy_status"] is not None
        else ""
    ).upper()

    verified_status = (
        str(row["verified_content_status"])
        if row["verified_content_status"] is not None
        else ""
    ).upper()

    confidence = float(
        row["accuracy_confidence"]
        if row["accuracy_confidence"] is not None
        else 0
    )

    if accuracy_status != "VERIFIED":
        reasons.append(
            f"ACCURACY_VERIFICATION_STATUS_{accuracy_status or 'MISSING'}"
        )

    if verified_status != "VERIFIED":
        reasons.append(
            f"VERIFIED_CONTENT_STATUS_{verified_status or 'MISSING'}"
        )

    # --------------------------------------------------------
    # Similarity measurements
    # --------------------------------------------------------

    source_word = word_agreement(source_text, verified_text)
    source_char = character_similarity(source_text, verified_text)

    selected_char = character_similarity(source_text, selected_text)

    # --------------------------------------------------------
    # Critical content
    # --------------------------------------------------------

    critical = critical_content_matches(
        source_text,
        verified_text,
    )

    if not critical["numbers_match"]:
        reasons.append("CRITICAL_NUMBERS_CHANGED")

    if not critical["questions_match"]:
        reasons.append("QUESTION_STRUCTURE_CHANGED")

    if not critical["options_match"]:
        reasons.append("MCQ_OPTION_STRUCTURE_CHANGED")

    # --------------------------------------------------------
    # STRICT THRESHOLDS
    # --------------------------------------------------------

    # These are deliberately strict.
    #
    # IMPORTANT:
    # Passing these thresholds does NOT mathematically prove that
    # OCR is perfect. It means the page satisfies Examora's
    # source-grounding acceptance policy.

    if source_char < 0.98:
        reasons.append(
            f"SOURCE_CHARACTER_SIMILARITY_TOO_LOW:{source_char:.4f}"
        )

    if source_word < 0.98:
        reasons.append(
            f"SOURCE_WORD_AGREEMENT_TOO_LOW:{source_word:.4f}"
        )

    if selected_char < 0.98:
        reasons.append(
            f"SELECTED_TEXT_SIMILARITY_TOO_LOW:{selected_char:.4f}"
        )

    if confidence < 95.0:
        reasons.append(
            f"VERIFICATION_CONFIDENCE_TOO_LOW:{confidence:.2f}"
        )

    # --------------------------------------------------------
    # Final gate
    # --------------------------------------------------------

    if reasons:
        verification_status = "BLOCKED"
        knowledge_status = "BLOCKED"
        admin_review_required = 1

        notes.append(
            "Content failed one or more strict source-grounding "
            "requirements. Knowledge Brain entry is blocked."
        )

    else:
        verification_status = "SOURCE_GROUNDED_VERIFIED"
        knowledge_status = "READY_FOR_KNOWLEDGE_BRAIN"
        admin_review_required = 0

        notes.append(
            "Content passed all configured source-grounding gates."
        )

    return {
        "upload_id": row["upload_id"] if "upload_id" in row.keys() else None,
        "source_page_id": row["source_page_id"],
        "page_number": row["page_number"],
        "source_word_agreement": round(source_word * 100, 4),
        "source_character_similarity": round(source_char * 100, 4),
        "verification_status": verification_status,
        "knowledge_status": knowledge_status,
        "admin_review_required": admin_review_required,
        "validation_notes": (
            " ".join(notes)
            + (
                " Reasons: "
                + "; ".join(reasons)
                if reasons
                else ""
            )
        ),
    }


# ============================================================
# DATABASE SAVE
# ============================================================

def save_result(cursor, result):
    cursor.execute(
        """
        DELETE FROM source_grounded_accuracy
        WHERE upload_id = ?
          AND page_number = ?
        """,
        (
            result["upload_id"],
            result["page_number"],
        ),
    )

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
            validation_notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            result["upload_id"],
            result["page_number"],
            result["source_word_agreement"],
            result["source_character_similarity"],
            result["verification_status"],
            result["knowledge_status"],
            result["admin_review_required"],
            result["validation_notes"],
        ),
    )


# ============================================================
# MAIN ENGINE
# ============================================================

def build_source_grounded_accuracy(upload_id):
    print(
        f"\nExamora Source-Grounded Accuracy Gate "
        f"started for Upload ID {upload_id}"
    )

    conn = get_connection()
    cursor = conn.cursor()

    try:
        rows = get_page_rows(cursor, upload_id)

        print(f"Pages to validate: {len(rows)}")
        print()

        summary = {
            "SOURCE_GROUNDED_VERIFIED": 0,
            "BLOCKED": 0,
        }

        for row in rows:
            result = evaluate_page(row)

            result["upload_id"] = upload_id

            save_result(cursor, result)

            status = result["verification_status"]
            knowledge = result["knowledge_status"]

            summary[status] = summary.get(status, 0) + 1

            print(
                f"Page {result['page_number']} | "
                f"status: {status} | "
                f"knowledge: {knowledge}"
            )

            print(
                f"  Word agreement: "
                f"{result['source_word_agreement']:.2f}%"
            )

            print(
                f"  Character similarity: "
                f"{result['source_character_similarity']:.2f}%"
            )

            if result["admin_review_required"]:
                print("  ADMIN REVIEW: REQUIRED")

            print()

        conn.commit()

        print(
            "Examora Source-Grounded Accuracy Gate completed."
        )

        final_result = {
            "upload_id": upload_id,
            "pages_processed": len(rows),
            "verification_summary": summary,
            "status": "SOURCE_GROUNDED_ACCURACY_COMPLETED",
        }

        print("\nFINAL RESULT:")
        print(final_result)

        return final_result

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":
    print(
        "Examora Source-Grounded Accuracy Gate is ready."
    )
