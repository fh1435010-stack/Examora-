import sqlite3
from datetime import datetime


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
    # We deliberately DO NOT aggressively rewrite characters,
    # because source fidelity is more important than appearance.
    return " ".join(text.split())


def compact_text(text):
    return "".join(normalize_text(text).lower().split())


# ============================================================
# BASIC SOURCE-GROUNDING METRICS
# ============================================================

def character_similarity(source_text, candidate_text):
    """
    Conservative character-level similarity.

    This is NOT a claim that the text is factually correct.
    It only measures textual agreement.
    """

    source = compact_text(source_text)
    candidate = compact_text(candidate_text)

    if not source and not candidate:
        return 1.0

    if not source or not candidate:
        return 0.0

    max_len = max(len(source), len(candidate))

    if max_len == 0:
        return 1.0

    # Longest common subsequence.
    previous = [0] * (len(candidate) + 1)

    for a in source:
        current = [0]

        for j, b in enumerate(candidate, start=1):
            if a == b:
                current.append(previous[j - 1] + 1)
            else:
                current.append(
                    max(previous[j], current[-1])
                )

        previous = current

    lcs = previous[-1]

    return round(
        (2.0 * lcs) / (len(source) + len(candidate)),
        6
    )


def word_agreement(source_text, candidate_text):
    """
    Measures how many source words survive in the candidate.

    Again, this is source agreement, not factual truth.
    """

    source_words = normalize_text(source_text).lower().split()
    candidate_words = normalize_text(candidate_text).lower().split()

    if not source_words:
        return 1.0 if not candidate_words else 0.0

    if not candidate_words:
        return 0.0

    candidate_set = set(candidate_words)

    matched = sum(
        1 for word in source_words
        if word in candidate_set
    )

    return round(
        matched / len(source_words),
        6
    )


# ============================================================
# STRUCTURAL CHECKS
# ============================================================

def count_question_markers(text):
    text = text or ""

    return (
        text.count("?")
        + text.count("Q.")
        + text.count("Q)")
    )


def count_numbered_questions(text):
    import re

    text = text or ""

    patterns = [
        r"\b\d+\.",
        r"\b\d+\)",
        r"\bQ\d+\b",
        r"\bQ\.\s*\d+",
    ]

    total = 0

    for pattern in patterns:
        total += len(re.findall(pattern, text, flags=re.IGNORECASE))

    return total


def unusual_symbol_ratio(text):
    """
    Conservative indicator only.
    Mathematical symbols are NOT automatically treated as errors.
    """

    if not text:
        return 0.0

    allowed = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        " .,;:!?()[]{}+-=*/%<>"
        "'\"-_/\n\t"
    )

    unusual = sum(
        1 for char in text
        if char not in allowed
    )

    return round(
        unusual / max(len(text), 1),
        6
    )


# ============================================================
# SOURCE DATA
# ============================================================

def get_page_rows(cursor, upload_id):
    """
    Uses ONLY confirmed schema:

        source_pages
        page_contents
        accuracy_verification
        verified_page_content
    """

    cursor.execute(
        """
        SELECT
            sp.id AS source_page_id,
            sp.upload_id,
            sp.page_number,
            sp.page_path,
            sp.original_type,

            pc.id AS page_content_id,
            pc.content_text,
            pc.content_type,
            pc.extraction_method,
            pc.status AS content_status,

            av.verification_status,
            av.verification_confidence,
            av.knowledge_brain_status,
            av.admin_review_required,
            av.warnings,
            av.reasons,

            vpc.verified_text,
            vpc.text_source AS verified_text_source,
            vpc.verification_status AS verified_page_status

        FROM source_pages sp

        LEFT JOIN page_contents pc
            ON pc.source_page_id = sp.id
           AND pc.upload_id = sp.upload_id

        LEFT JOIN accuracy_verification av
            ON av.source_page_id = sp.id
           AND av.upload_id = sp.upload_id

        LEFT JOIN verified_page_content vpc
            ON vpc.source_page_id = sp.id
           AND vpc.upload_id = sp.upload_id

        WHERE sp.upload_id = ?

        ORDER BY sp.page_number
        """,
        (upload_id,)
    )

    return cursor.fetchall()


# ============================================================
# DECISION ENGINE
# ============================================================

def validate_page(row):
    source_text = normalize_text(row["content_text"])
    verified_text = normalize_text(row["verified_text"])

    accuracy_status = (
        row["verification_status"]
        or "UNKNOWN"
    )

    knowledge_status = (
        row["knowledge_brain_status"]
        or "BLOCKED"
    )

    confidence = float(
        row["verification_confidence"]
        or 0
    )

    admin_review = int(
        row["admin_review_required"]
        or 0
    )

    # --------------------------------------------------------
    # Select the strongest available candidate.
    #
    # IMPORTANT:
    # We do not manufacture text.
    # --------------------------------------------------------

    if verified_text:
        candidate = verified_text
        candidate_source = "VERIFIED_PAGE_CONTENT"
    else:
        candidate = source_text
        candidate_source = "PAGE_CONTENTS"

    candidate = normalize_text(candidate)

    # --------------------------------------------------------
    # Empty content = immediate block.
    # --------------------------------------------------------

    if not candidate:
        return {
            "source_word_agreement": 0.0,
            "source_character_similarity": 0.0,
            "verification_status": "BLOCKED",
            "knowledge_status": "BLOCKED",
            "admin_review_required": 1,
            "validation_notes": (
                "No usable extracted content was available. "
                "Knowledge Brain ingestion blocked."
            )
        }

    # --------------------------------------------------------
    # Compare candidate with source extraction.
    # --------------------------------------------------------

    word_score = word_agreement(
        source_text,
        candidate
    )

    character_score = character_similarity(
        source_text,
        candidate
    )

    symbol_ratio = unusual_symbol_ratio(candidate)

    question_count = count_numbered_questions(candidate)
    question_markers = count_question_markers(candidate)

    # --------------------------------------------------------
    # HARD SAFETY GATES
    # --------------------------------------------------------

    reasons = []

    # Existing accuracy verification must not be blocked.
    if accuracy_status in {
        "BLOCKED",
        "UNCERTAIN",
        "UNKNOWN"
    }:
        reasons.append(
            f"Existing verification status={accuracy_status}"
        )

    if confidence < 85.0:
        reasons.append(
            f"Verification confidence below 85 ({confidence:.2f})"
        )

    if admin_review:
        reasons.append(
            "Existing system requires administrator review"
        )

    if not source_text:
        reasons.append(
            "Original page content is unavailable"
        )

    if source_text and word_score < 0.98:
        reasons.append(
            f"Source word agreement below 98% ({word_score:.4f})"
        )

    if source_text and character_score < 0.98:
        reasons.append(
            "Source character similarity below 98%"
        )

    # Very high unusual-character concentration is suspicious.
    if symbol_ratio > 0.08:
        reasons.append(
            f"High unusual-symbol ratio ({symbol_ratio:.4f})"
        )

    # --------------------------------------------------------
    # FINAL DECISION
    # --------------------------------------------------------

    if reasons:
        status = "UNCERTAIN"

        # Severe source disagreement becomes BLOCKED.
        if (
            word_score < 0.90
            or character_score < 0.90
            or not source_text
            or accuracy_status == "BLOCKED"
        ):
            status = "BLOCKED"

        final_knowledge_status = "BLOCKED"
        final_admin_review = 1

        notes = (
            "SOURCE-GROUNDED VALIDATION FAILED. "
            "Knowledge Brain ingestion blocked. "
            + " | ".join(reasons)
        )

    else:
        status = "VERIFIED"
        final_knowledge_status = "READY_FOR_KNOWLEDGE_BRAIN"
        final_admin_review = 0

        notes = (
            "Source-grounded validation passed. "
            "Candidate text agrees with the available "
            "source extraction and passed all safety gates. "
            f"Candidate source={candidate_source}; "
            f"word_agreement={word_score:.4f}; "
            f"character_similarity={character_score:.4f}; "
            f"confidence={confidence:.2f}."
        )

    return {
        "source_word_agreement": word_score,
        "source_character_similarity": character_score,
        "verification_status": status,
        "knowledge_status": final_knowledge_status,
        "admin_review_required": final_admin_review,
        "validation_notes": notes
    }


# ============================================================
# SAVE RESULT
# ============================================================

def save_result(cursor, row, result):
    """
    Uses the ACTUAL confirmed schema of source_grounded_accuracy.

    No source_page_id column is assumed.
    """

    cursor.execute(
        """
        SELECT id
        FROM source_grounded_accuracy
        WHERE upload_id = ?
          AND page_number = ?
        LIMIT 1
        """,
        (
            row["upload_id"],
            row["page_number"]
        )
    )

    existing = cursor.fetchone()

    now = datetime.utcnow().isoformat()

    if existing:
        cursor.execute(
            """
            UPDATE source_grounded_accuracy
            SET
                source_word_agreement = ?,
                source_character_similarity = ?,
                verification_status = ?,
                knowledge_status = ?,
                admin_review_required = ?,
                validation_notes = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                result["source_word_agreement"],
                result["source_character_similarity"],
                result["verification_status"],
                result["knowledge_status"],
                result["admin_review_required"],
                result["validation_notes"],
                now,
                existing["id"]
            )
        )

    else:
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
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["upload_id"],
                row["page_number"],
                result["source_word_agreement"],
                result["source_character_similarity"],
                result["verification_status"],
                result["knowledge_status"],
                result["admin_review_required"],
                result["validation_notes"],
                now,
                now
            )
        )


# ============================================================
# MAIN ENGINE
# ============================================================

def build_source_grounded_accuracy(upload_id):
    print(
        f"\nExamora Source-Grounded Accuracy Validation "
        f"started for Upload ID {upload_id}"
    )

    conn = get_connection()

    try:
        cursor = conn.cursor()

        rows = get_page_rows(
            cursor,
            upload_id
        )

        print(
            f"Pages to validate: {len(rows)}\n"
        )

        summary = {
            "VERIFIED": 0,
            "UNCERTAIN": 0,
            "BLOCKED": 0
        }

        for row in rows:

            page_number = row["page_number"]

            result = validate_page(row)

            save_result(
                cursor,
                row,
                result
            )

            status = result["verification_status"]

            summary.setdefault(
                status,
                0
            )

            summary[status] += 1

            print(
                f"Page {page_number} validated | "
                f"status: {status} | "
                f"word agreement: "
                f"{result['source_word_agreement']:.4f} | "
                f"character similarity: "
                f"{result['source_character_similarity']:.4f} | "
                f"knowledge: "
                f"{result['knowledge_status']}"
            )

        conn.commit()

        print(
            "\nExamora Source-Grounded Accuracy Validation "
            "completed."
        )

        print(
            f"Summary: {summary}"
        )

        return {
            "upload_id": upload_id,
            "pages_processed": len(rows),
            "validation_summary": summary,
            "status": "SOURCE_GROUNDED_VALIDATION_COMPLETED"
        }

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
        "Examora Source-Grounded Accuracy Engine is ready."
    )
