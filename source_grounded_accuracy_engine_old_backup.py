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

    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def text_similarity(text_a, text_b):
    """
    Lightweight source comparison.
    Returns a percentage based on normalized token overlap.
    """

    text_a = normalize_text(text_a).lower()
    text_b = normalize_text(text_b).lower()

    if not text_a or not text_b:
        return 0.0

    words_a = set(re.findall(r"[a-zA-Z0-9]+", text_a))
    words_b = set(re.findall(r"[a-zA-Z0-9]+", text_b))

    if not words_a or not words_b:
        return 0.0

    intersection = words_a.intersection(words_b)
    union = words_a.union(words_b)

    if not union:
        return 0.0

    return round((len(intersection) / len(union)) * 100, 2)


def get_page_rows(cursor, upload_id):
    """
    Uses ONLY columns confirmed to exist in the actual Examora schema.

    Tables:
    - accuracy_verification
    - verified_page_content
    - recovered_page_content
    """

    cursor.execute(
        """
        SELECT
            ave.upload_id,
            ave.source_page_id,
            ave.page_number,

            ave.text_source,
            ave.verification_status,
            ave.verification_confidence,
            ave.selected_text,
            ave.text_length,
            ave.unusual_symbol_ratio,
            ave.alpha_ratio,
            ave.question_structure,
            ave.numbered_questions,
            ave.question_markers,
            ave.has_numbers,
            ave.has_units,
            ave.has_scientific_notation,
            ave.has_math_symbols,
            ave.critical_content_count,
            ave.warnings,
            ave.reasons,
            ave.admin_review_required,
            ave.admin_notification_status,
            ave.knowledge_brain_status,

            vpc.verified_text,
            vpc.text_source AS verified_text_source,
            vpc.best_rotation,
            vpc.content_classification,
            vpc.verification_status AS verified_page_status,

            rpc.original_text,
            rpc.recovered_text,
            rpc.recovery_status,
            rpc.recovery_priority,
            rpc.corruption_score,
            rpc.suspicious_patterns,
            rpc.recovery_notes,
            rpc.admin_review_required AS recovery_admin_review_required,
            rpc.admin_notification_status AS recovery_admin_notification_status

        FROM accuracy_verification ave

        LEFT JOIN verified_page_content vpc
            ON ave.upload_id = vpc.upload_id
            AND ave.page_number = vpc.page_number

        LEFT JOIN recovered_page_content rpc
            ON ave.upload_id = rpc.upload_id
            AND ave.page_number = rpc.page_number

        WHERE ave.upload_id = ?

        ORDER BY ave.page_number
        """,
        (upload_id,)
    )

    return cursor.fetchall()


def choose_source_text(row):
    """
    Select the strongest available source-side text.

    Preference:
    1. verified_page_content.verified_text
    2. recovered_page_content.recovered_text
    3. recovered_page_content.original_text
    4. accuracy_verification.selected_text
    """

    candidates = [
        row["verified_text"],
        row["recovered_text"],
        row["original_text"],
        row["selected_text"],
    ]

    for text in candidates:
        text = normalize_text(text)
        if text:
            return text

    return ""


def get_critical_warnings(row):
    warnings = []

    unusual_symbol_ratio = safe_float(row["unusual_symbol_ratio"])
    critical_content_count = safe_int(row["critical_content_count"])
    corruption_score = safe_float(row["corruption_score"])

    existing_warnings = normalize_text(row["warnings"])
    suspicious_patterns = normalize_text(row["suspicious_patterns"])

    if unusual_symbol_ratio > 3.0:
        warnings.append("HIGH_UNUSUAL_SYMBOL_RATIO")

    if critical_content_count > 0:
        warnings.append("CRITICAL_CONTENT_PRESENT")

    if corruption_score >= 40:
        warnings.append("HIGH_SOURCE_CORRUPTION")

    if "TRUNCATED" in existing_warnings.upper():
        warnings.append("POSSIBLE_TRUNCATED_CONTENT")

    if "UNUSUAL_SYMBOL" in suspicious_patterns.upper():
        warnings.append("SOURCE_HAS_UNUSUAL_SYMBOLS")

    return list(dict.fromkeys(warnings))


def evaluate_source_grounded_accuracy(row):
    """
    Strict trust decision.

    Important principle:
    No page is trusted simply because an earlier engine gave it 85%.

    The page must pass source consistency checks and must not contain
    unresolved critical warnings.
    """

    selected_text = normalize_text(row["selected_text"])
    source_text = choose_source_text(row)

    verification_status = normalize_text(row["verification_status"]).upper()
    verification_confidence = safe_float(
        row["verification_confidence"]
    )

    recovery_status = normalize_text(
        row["recovery_status"]
    ).upper()

    recovery_priority = normalize_text(
        row["recovery_priority"]
    ).upper()

    warnings = get_critical_warnings(row)

    similarity = text_similarity(selected_text, source_text)

    reasons = []
    decision_warnings = list(warnings)

    if not selected_text:
        return {
            "status": "BLOCKED",
            "confidence": 0.0,
            "knowledge_status": "BLOCKED",
            "source_similarity": 0.0,
            "source_text": source_text,
            "reasons": "No selected text available for validation.",
            "warnings": ",".join(decision_warnings),
            "admin_review_required": 1,
            "admin_notification_status": "PENDING",
        }

    if not source_text:
        return {
            "status": "BLOCKED",
            "confidence": 0.0,
            "knowledge_status": "BLOCKED",
            "source_similarity": 0.0,
            "source_text": "",
            "reasons": "No source-side text available for comparison.",
            "warnings": ",".join(
                decision_warnings + ["SOURCE_TEXT_MISSING"]
            ),
            "admin_review_required": 1,
            "admin_notification_status": "PENDING",
        }

    reasons.append(
        f"Selected/source text similarity={similarity}"
    )

    reasons.append(
        f"Previous verification confidence={verification_confidence}"
    )

    if recovery_status:
        reasons.append(
            f"Recovery status={recovery_status}"
        )

    if recovery_priority:
        reasons.append(
            f"Recovery priority={recovery_priority}"
        )

    if verification_status == "BLOCKED":
        return {
            "status": "BLOCKED",
            "confidence": min(verification_confidence, 25.0),
            "knowledge_status": "BLOCKED",
            "source_similarity": similarity,
            "source_text": source_text,
            "reasons": "; ".join(
                reasons + ["Previous verification layer blocked this page."]
            ),
            "warnings": ",".join(decision_warnings),
            "admin_review_required": 1,
            "admin_notification_status": "PENDING",
        }

    if (
        "HIGH_SOURCE_CORRUPTION" in decision_warnings
        or verification_confidence < 50
    ):
        return {
            "status": "BLOCKED",
            "confidence": min(verification_confidence, similarity),
            "knowledge_status": "BLOCKED",
            "source_similarity": similarity,
            "source_text": source_text,
            "reasons": "; ".join(
                reasons + [
                    "Source quality is too weak for trusted automatic knowledge."
                ]
            ),
            "warnings": ",".join(decision_warnings),
            "admin_review_required": 1,
            "admin_notification_status": "PENDING",
        }

    critical_uncertainty = (
        "HIGH_UNUSUAL_SYMBOL_RATIO" in decision_warnings
        or "POSSIBLE_TRUNCATED_CONTENT" in decision_warnings
        or "SOURCE_HAS_UNUSUAL_SYMBOLS" in decision_warnings
        or verification_status == "UNCERTAIN"
        or recovery_status == "RECOVERED_UNCERTAIN"
    )

    if critical_uncertainty:
        return {
            "status": "SOURCE_UNCERTAIN",
            "confidence": min(
                verification_confidence,
                max(similarity, 0.0)
            ),
            "knowledge_status": "BLOCKED",
            "source_similarity": similarity,
            "source_text": source_text,
            "reasons": "; ".join(
                reasons + [
                    "Unresolved OCR or source uncertainty requires review."
                ]
            ),
            "warnings": ",".join(decision_warnings),
            "admin_review_required": 1,
            "admin_notification_status": "PENDING",
        }

    if similarity >= 95 and verification_confidence >= 85:
        return {
            "status": "SOURCE_CONFIRMED",
            "confidence": min(
                99.9,
                round(
                    (verification_confidence * 0.5)
                    + (similarity * 0.5),
                    2
                )
            ),
            "knowledge_status": "READY_FOR_KNOWLEDGE_BRAIN",
            "source_similarity": similarity,
            "source_text": source_text,
            "reasons": "; ".join(
                reasons + [
                    "Strong source agreement and no unresolved critical warnings."
                ]
            ),
            "warnings": ",".join(decision_warnings),
            "admin_review_required": 0,
            "admin_notification_status": "NONE",
        }

    return {
        "status": "SOURCE_UNCERTAIN",
        "confidence": min(
            verification_confidence,
            similarity
        ),
        "knowledge_status": "BLOCKED",
        "source_similarity": similarity,
        "source_text": source_text,
        "reasons": "; ".join(
            reasons + [
                "Automatic evidence is insufficient for source-confirmed knowledge."
            ]
        ),
        "warnings": ",".join(decision_warnings),
        "admin_review_required": 1,
        "admin_notification_status": "PENDING",
    }


def ensure_source_grounded_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS source_grounded_accuracy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id INTEGER NOT NULL,
            source_page_id INTEGER,
            page_number INTEGER NOT NULL,

            validation_status TEXT NOT NULL,
            validation_confidence REAL NOT NULL DEFAULT 0,

            source_similarity REAL NOT NULL DEFAULT 0,

            selected_text TEXT,
            source_text TEXT,

            warnings TEXT,
            reasons TEXT,

            admin_review_required INTEGER NOT NULL DEFAULT 0,
            admin_notification_status TEXT NOT NULL DEFAULT 'NONE',

            knowledge_brain_status TEXT NOT NULL DEFAULT 'BLOCKED',

            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(upload_id, page_number)
        )
        """
    )


def save_result(cursor, upload_id, row, result):
    cursor.execute(
        """
        DELETE FROM source_grounded_accuracy
        WHERE upload_id = ?
        AND page_number = ?
        """,
        (upload_id, row["page_number"])
    )

    cursor.execute(
        """
        INSERT INTO source_grounded_accuracy (
            upload_id,
            source_page_id,
            page_number,

            validation_status,
            validation_confidence,

            source_similarity,

            selected_text,
            source_text,

            warnings,
            reasons,

            admin_review_required,
            admin_notification_status,

            knowledge_brain_status,

            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            upload_id,
            row["source_page_id"],
            row["page_number"],

            result["status"],
            result["confidence"],

            result["source_similarity"],

            row["selected_text"],
            result["source_text"],

            result["warnings"],
            result["reasons"],

            result["admin_review_required"],
            result["admin_notification_status"],

            result["knowledge_status"],

            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
    )


def build_source_grounded_accuracy(upload_id):
    print()
    print(
        f"Examora Source-Grounded Accuracy Validation started for Upload ID {upload_id}"
    )

    conn = get_connection()
    cursor = conn.cursor()

    try:
        ensure_source_grounded_table(cursor)

        rows = get_page_rows(cursor, upload_id)

        if not rows:
            return {
                "upload_id": upload_id,
                "pages_processed": 0,
                "validation_summary": {},
                "status": "NO_PAGES_FOUND",
            }

        print(f"Pages to validate: {len(rows)}")
        print()

        summary = {}

        for row in rows:
            result = evaluate_source_grounded_accuracy(row)

            save_result(
                cursor,
                upload_id,
                row,
                result
            )

            status = result["status"]

            summary[status] = summary.get(status, 0) + 1

            print(
                f"Page {row['page_number']} | "
                f"status: {status} | "
                f"confidence: {result['confidence']} | "
                f"similarity: {result['source_similarity']} | "
                f"knowledge: {result['knowledge_status']}"
            )

        conn.commit()

        print()
        print(
            "Examora Source-Grounded Accuracy Validation completed."
        )

        return {
            "upload_id": upload_id,
            "pages_processed": len(rows),
            "validation_summary": summary,
            "status": "SOURCE_GROUNDED_ACCURACY_COMPLETED",
        }

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == "__main__":
    print(
        "Examora Source-Grounded Accuracy Engine is ready."
    )
