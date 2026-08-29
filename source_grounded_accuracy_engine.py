import sqlite3
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path


# ============================================================
# EXAMORA
# SOURCE-GROUNDED ACCURACY GATE
#
# Purpose:
#   Decide whether already-verified source content is safe to
#   enter the Knowledge Brain.
#
# Important:
#   This module does NOT perform OCR.
#   This module does NOT modify source extraction.
#   This module does NOT rewrite verified content.
#   This module only evaluates and records the gate decision.
# ============================================================


DB_PATH = Path("examora.db")

# A verified page must have very strong agreement between the
# selected text and the final verified text.
TEXT_SIMILARITY_THRESHOLD = 0.98

# Critical content must remain identical.
CRITICAL_CONTENT_MUST_MATCH = True


# ============================================================
# DATABASE
# ============================================================

def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(cursor, table_name):
    row = cursor.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?
        LIMIT 1
        """,
        (table_name,),
    ).fetchone()

    return row is not None


def get_columns(cursor, table_name):
    if not table_exists(cursor, table_name):
        raise RuntimeError(
            f"Required table does not exist: {table_name}"
        )

    rows = cursor.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    return {row["name"] for row in rows}


def require_columns(cursor, table_name, required_columns):
    columns = get_columns(cursor, table_name)

    missing = sorted(
        set(required_columns) - columns
    )

    if missing:
        raise RuntimeError(
            f"Required columns missing from {table_name}: "
            + ", ".join(missing)
        )

    return columns


# ============================================================
# TEXT NORMALIZATION
#
# Only formatting whitespace is normalized.
#
# We deliberately do NOT:
#   - correct spelling
#   - change numbers
#   - change formulas
#   - change scientific notation
#   - change symbols
#   - change question wording
#   - change MCQ options
# ============================================================

def normalize_text(text):
    if text is None:
        return ""

    text = str(text)

    text = (
        text
        .replace("\r\n", "\n")
        .replace("\r", "\n")
    )

    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


# ============================================================
# SIMILARITY
# ============================================================

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

    counts_a = Counter(words_a)
    counts_b = Counter(words_b)

    common = sum(
        (counts_a & counts_b).values()
    )

    total = max(
        len(words_a),
        len(words_b),
    )

    return (
        common / total
        if total
        else 0.0
    )


# ============================================================
# CRITICAL CONTENT
#
# These checks are intentionally conservative.
#
# A text can have a high overall similarity while still
# changing one important number or question structure.
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
        r"""
        (?:^|\n)
        \s*
        (?:
            Q(?:uestion)?
            \.?
            \s*
        )?
        \d{1,3}
        [\.\):\-]
        """,
        text,
        re.IGNORECASE | re.VERBOSE,
    )


def extract_option_markers(text):
    if not text:
        return []

    return re.findall(
        r"""
        (?:^|\n)
        \s*
        [A-Da-d]
        [\.\):\-]
        \s+
        """,
        text,
    )


def critical_content_signature(text):
    return {
        "numbers": extract_numbers(text),
        "questions": extract_question_markers(text),
        "options": extract_option_markers(text),
    }


def critical_content_matches(a, b):
    signature_a = critical_content_signature(a)
    signature_b = critical_content_signature(b)

    return {
        "numbers_match": (
            signature_a["numbers"]
            == signature_b["numbers"]
        ),
        "questions_match": (
            signature_a["questions"]
            == signature_b["questions"]
        ),
        "options_match": (
            signature_a["options"]
            == signature_b["options"]
        ),
    }


# ============================================================
# SOURCE PAGE VALIDATION
# ============================================================

def validate_source_page(cursor, row):
    reasons = []

    source_page_id = row["source_page_id"]
    page_path = row["page_path"]

    if not source_page_id:
        reasons.append("MISSING_SOURCE_PAGE_ID")

    if not page_path:
        reasons.append("MISSING_SOURCE_PAGE_PATH")

    return reasons


# ============================================================
# LOAD ACTUAL DATABASE CHAIN
#
# IMPORTANT:
#
# page_contents.content_text is currently empty in Upload 1.
# Therefore it is NOT used as the comparison source here.
#
# The current usable verification chain is:
#
# source_pages
#       ↓
# accuracy_verification.selected_text
#       ↓
# verified_page_content.verified_text
#
# Existing verification status is respected.
# ============================================================

def get_page_rows(cursor, upload_id):
    require_columns(
        cursor,
        "source_pages",
        [
            "id",
            "upload_id",
            "page_number",
            "page_path",
        ],
    )

    require_columns(
        cursor,
        "accuracy_verification",
        [
            "upload_id",
            "source_page_id",
            "page_number",
            "selected_text",
            "verification_status",
            "verification_confidence",
            "text_source",
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

    require_columns(
        cursor,
        "source_grounded_accuracy",
        [
            "upload_id",
            "page_number",
            "source_word_agreement",
            "source_character_similarity",
            "verification_status",
            "knowledge_status",
            "admin_review_required",
            "validation_notes",
        ],
    )

    return cursor.execute(
        """
        SELECT
            sp.id AS source_page_id,
            sp.upload_id,
            sp.page_number,
            sp.page_path,

            av.selected_text,
            av.verification_status
                AS accuracy_verification_status,
            av.verification_confidence
                AS accuracy_verification_confidence,
            av.text_source,

            vp.verified_text,
            vp.verification_status
                AS verified_page_status

        FROM source_pages sp

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
# PAGE EVALUATION
# ============================================================

def evaluate_page(row):
    reasons = []

    selected_text = normalize_text(
        row["selected_text"]
    )

    verified_text = normalize_text(
        row["verified_text"]
    )

    accuracy_status = (
        str(
            row["accuracy_verification_status"]
            or ""
        )
        .strip()
        .upper()
    )

    verified_status = (
        str(
            row["verified_page_status"]
            or ""
        )
        .strip()
        .upper()
    )

    text_source = (
        str(
            row["text_source"]
            or ""
        )
        .strip()
        .upper()
    )

    confidence = float(
        row["accuracy_verification_confidence"]
        or 0
    )

    # --------------------------------------------------------
    # SOURCE CHAIN
    # --------------------------------------------------------

    if not row["source_page_id"]:
        reasons.append(
            "MISSING_SOURCE_PAGE"
        )

    if not row["page_path"]:
        reasons.append(
            "MISSING_SOURCE_PAGE_PATH"
        )

    # --------------------------------------------------------
    # TEXT AVAILABILITY
    # --------------------------------------------------------

    if not selected_text:
        reasons.append(
            "MISSING_SELECTED_TEXT"
        )

    if not verified_text:
        reasons.append(
            "MISSING_VERIFIED_TEXT"
        )

    # --------------------------------------------------------
    # EXISTING VERIFICATION STATES
    #
    # UNCERTAIN is a hard block.
    # Only explicitly VERIFIED content can pass.
    # --------------------------------------------------------

    if accuracy_status != "VERIFIED":
        reasons.append(
            "ACCURACY_VERIFICATION_NOT_VERIFIED:"
            + (
                accuracy_status
                if accuracy_status
                else "MISSING"
            )
        )

    if verified_status != "VERIFIED":
        reasons.append(
            "VERIFIED_PAGE_CONTENT_NOT_VERIFIED:"
            + (
                verified_status
                if verified_status
                else "MISSING"
            )
        )

    # --------------------------------------------------------
    # TEXT COMPARISON
    # --------------------------------------------------------

    selected_verified_character_similarity = (
        character_similarity(
            selected_text,
            verified_text,
        )
    )

    selected_verified_word_agreement = (
        word_agreement(
            selected_text,
            verified_text,
        )
    )

    if (
        selected_verified_character_similarity
        < TEXT_SIMILARITY_THRESHOLD
    ):
        reasons.append(
            "SELECTED_VERIFIED_CHARACTER_SIMILARITY_TOO_LOW:"
            f"{selected_verified_character_similarity:.4f}"
        )

    if (
        selected_verified_word_agreement
        < TEXT_SIMILARITY_THRESHOLD
    ):
        reasons.append(
            "SELECTED_VERIFIED_WORD_AGREEMENT_TOO_LOW:"
            f"{selected_verified_word_agreement:.4f}"
        )

    # --------------------------------------------------------
    # CRITICAL CONTENT
    # --------------------------------------------------------

    critical = critical_content_matches(
        selected_text,
        verified_text,
    )

    if CRITICAL_CONTENT_MUST_MATCH:
        if not critical["numbers_match"]:
            reasons.append(
                "CRITICAL_NUMBERS_CHANGED"
            )

        if not critical["questions_match"]:
            reasons.append(
                "QUESTION_STRUCTURE_CHANGED"
            )

        if not critical["options_match"]:
            reasons.append(
                "MCQ_OPTION_STRUCTURE_CHANGED"
            )

    # --------------------------------------------------------
    # CONFIDENCE
    #
    # IMPORTANT DESIGN DECISION:
    #
    # We do NOT independently block a page just because the
    # confidence number is below 95.
    #
    # Why?
    #
    # Your actual Upload 1 data contains pages marked VERIFIED
    # with confidence 85.0.
    #
    # The authoritative existing verification state is therefore
    # respected, while confidence is retained as audit metadata.
    # --------------------------------------------------------

    confidence_note = (
        f"Existing verification confidence: "
        f"{confidence:.2f}"
    )

    if text_source:
        confidence_note += (
            f"; text source: {text_source}"
        )

    # --------------------------------------------------------
    # FINAL GATE
    # --------------------------------------------------------

    if reasons:
        verification_status = "BLOCKED"
        knowledge_status = "BLOCKED"
        admin_review_required = 1

        validation_notes = (
            "Knowledge Brain entry BLOCKED. "
            + confidence_note
            + ". Reasons: "
            + "; ".join(reasons)
        )

    else:
        verification_status = (
            "SOURCE_GROUNDED_VERIFIED"
        )
        knowledge_status = (
            "READY_FOR_KNOWLEDGE_BRAIN"
        )
        admin_review_required = 0

        validation_notes = (
            "Page passed the source-grounded accuracy gate. "
            + confidence_note
            + ". Existing verified text agrees with the "
              "selected verified source content and critical "
              "content is unchanged."
        )

    return {
        "upload_id": row["upload_id"],
        "source_page_id": row["source_page_id"],
        "page_number": row["page_number"],
        "source_word_agreement": round(
            selected_verified_word_agreement * 100,
            4,
        ),
        "source_character_similarity": round(
            selected_verified_character_similarity * 100,
            4,
        ),
        "verification_status": verification_status,
        "knowledge_status": knowledge_status,
        "admin_review_required": (
            admin_review_required
        ),
        "validation_notes": validation_notes,
    }


# ============================================================
# SAVE RESULT
#
# Actual source_grounded_accuracy schema does NOT contain
# source_page_id.
#
# Therefore we only insert columns that actually exist.
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
# MAIN GATE
# ============================================================

def build_source_grounded_accuracy(upload_id):
    print()
    print(
        "Examora Source-Grounded Accuracy Gate "
        f"started for Upload ID {upload_id}"
    )

    conn = get_connection()
    cursor = conn.cursor()

    try:
        rows = get_page_rows(
            cursor,
            upload_id,
        )

        if not rows:
            raise RuntimeError(
                f"No source pages found for Upload ID {upload_id}"
            )

        print(
            f"Pages to validate: {len(rows)}"
        )
        print()

        summary = {
            "SOURCE_GROUNDED_VERIFIED": 0,
            "BLOCKED": 0,
        }

        for row in rows:
            result = evaluate_page(row)

            save_result(
                cursor,
                result,
            )

            status = result[
                "verification_status"
            ]

            knowledge = result[
                "knowledge_status"
            ]

            summary[status] = (
                summary.get(status, 0) + 1
            )

            print(
                f"Page {result['page_number']} | "
                f"status: {status} | "
                f"knowledge: {knowledge}"
            )

            print(
                "  Word agreement: "
                f"{result['source_word_agreement']:.2f}%"
            )

            print(
                "  Character similarity: "
                f"{result['source_character_similarity']:.2f}%"
            )

            if result[
                "admin_review_required"
            ]:
                print(
                    "  ADMIN REVIEW: REQUIRED"
                )

            print()

        conn.commit()

        final_result = {
            "upload_id": upload_id,
            "pages_processed": len(rows),
            "verification_summary": summary,
            "status": (
                "SOURCE_GROUNDED_ACCURACY_COMPLETED"
            ),
        }

        print(
            "Examora Source-Grounded Accuracy Gate "
            "completed."
        )

        print()
        print("FINAL RESULT:")
        print(final_result)

        return final_result

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


# ============================================================
# DATABASE SCHEMA SELF-CHECK
# ============================================================

def schema_check():
    conn = get_connection()
    cursor = conn.cursor()

    try:
        print(
            "Examora Source-Grounded Accuracy "
            "schema check started."
        )

        require_columns(
            cursor,
            "source_pages",
            [
                "id",
                "upload_id",
                "page_number",
                "page_path",
            ],
        )

        print("source_pages OK")

        require_columns(
            cursor,
            "accuracy_verification",
            [
                "upload_id",
                "source_page_id",
                "page_number",
                "selected_text",
                "verification_status",
                "verification_confidence",
                "text_source",
            ],
        )

        print(
            "accuracy_verification OK"
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

        print(
            "verified_page_content OK"
        )

        require_columns(
            cursor,
            "source_grounded_accuracy",
            [
                "upload_id",
                "page_number",
                "source_word_agreement",
                "source_character_similarity",
                "verification_status",
                "knowledge_status",
                "admin_review_required",
                "validation_notes",
            ],
        )

        print(
            "source_grounded_accuracy OK"
        )

        print(
            "SCHEMA CHECK COMPLETED"
        )

    finally:
        conn.close()


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":
    print(
        "Examora Source-Grounded Accuracy Gate is ready."
    )
