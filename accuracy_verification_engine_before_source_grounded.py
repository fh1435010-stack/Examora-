import sqlite3
import re
from collections import Counter


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


def calculate_unusual_symbol_ratio(text):
    """
    Measures suspicious symbols while allowing common
    educational punctuation and mathematical symbols.
    """

    if not text:
        return 100.0

    allowed = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        " \n\t"
        ".,;:!?()[]{}"
        "'\""
        "+-=*/<>"
        "%°"
        "×÷"
        "^_"
        "₹$£"
        "₀₁₂₃₄₅₆₇₈₉"
        "⁰¹²³⁴⁵⁶⁷⁸⁹"
        "√πλμΔΩθ"
        "–—-"
    )

    suspicious = 0

    for char in text:
        if char not in allowed:
            if char.isalnum():
                continue
            suspicious += 1

    return round((suspicious / max(len(text), 1)) * 100, 2)


def calculate_alpha_ratio(text):
    if not text:
        return 0.0

    meaningful_chars = [
        char for char in text
        if not char.isspace()
    ]

    if not meaningful_chars:
        return 0.0

    alpha_count = sum(
        1 for char in meaningful_chars
        if char.isalpha()
    )

    return round(
        (alpha_count / len(meaningful_chars)) * 100,
        2
    )


def detect_broken_words(text):
    """
    Detects likely OCR fragments such as:
    scientitic
    cal
    prefi

    This is intentionally conservative.
    It creates a warning rather than silently changing content.
    """

    if not text:
        return []

    warnings = []

    words = re.findall(r"\b[A-Za-z]+\b", text)

    short_words = []

    for word in words:
        if len(word) <= 2:
            if word.lower() not in {
                "a", "i", "an", "am", "as", "at",
                "be", "by", "do", "go", "he",
                "if", "in", "is", "it", "me",
                "my", "no", "of", "on", "or",
                "so", "to", "up", "us", "we"
            }:
                short_words.append(word)

    if len(short_words) >= 8:
        warnings.append("MANY_SHORT_OCR_FRAGMENTS")

    suspicious_fragments = []

    for word in words:
        if len(word) >= 4:
            if word.endswith(("iti", "tic", "cal", "pre", "fi")):
                suspicious_fragments.append(word)

    if len(suspicious_fragments) >= 3:
        warnings.append("POSSIBLE_TRUNCATED_WORDS")

    return warnings


def detect_question_structure(text):
    """
    Checks whether educational question numbering exists.
    """

    if not text:
        return {
            "question_markers": 0,
            "numbered_questions": 0,
            "status": "NO_STRUCTURE"
        }

    numbered = re.findall(
        r"(?m)^\s*(\d{1,3})[\.\)]\s+",
        text
    )

    question_words = re.findall(
        r"\b(what|why|how|when|where|which|define|write|express|determine|calculate|find|explain|describe|state|look)\b",
        text,
        re.IGNORECASE
    )

    question_markers = len(question_words)
    numbered_questions = len(numbered)

    if numbered_questions >= 2:
        status = "QUESTION_STRUCTURE_DETECTED"
    elif question_markers >= 2:
        status = "POSSIBLE_QUESTION_STRUCTURE"
    else:
        status = "STRUCTURE_NOT_CONFIRMED"

    return {
        "question_markers": question_markers,
        "numbered_questions": numbered_questions,
        "status": status
    }


def detect_critical_educational_content(text):
    """
    Detects content requiring stricter verification.

    Numbers, units, scientific notation and mathematical
    expressions are critical because a small OCR mistake
    can change the meaning.
    """

    if not text:
        return {
            "has_numbers": False,
            "has_units": False,
            "has_scientific_notation": False,
            "has_math_symbols": False,
            "critical_count": 0
        }

    has_numbers = bool(
        re.search(r"\d", text)
    )

    unit_pattern = (
        r"\b("
        r"m|cm|mm|km|kg|g|mg|s|min|h|"
        r"N|J|W|Pa|V|A|Hz|K|°C|"
        r"m/s|km/h"
        r")\b"
    )

    has_units = bool(
        re.search(unit_pattern, text)
    )

    scientific_pattern = (
        r"\d+(?:\.\d+)?\s*"
        r"(?:x|×|\*)\s*10"
    )

    has_scientific_notation = bool(
        re.search(
            scientific_pattern,
            text,
            re.IGNORECASE
        )
    )

    math_symbols = [
        "=", "+", "-", "×", "÷",
        "√", "^", "²", "³"
    ]

    math_symbol_count = sum(
        text.count(symbol)
        for symbol in math_symbols
    )

    has_math_symbols = math_symbol_count > 0

    critical_count = sum([
        has_numbers,
        has_units,
        has_scientific_notation,
        has_math_symbols
    ])

    return {
        "has_numbers": has_numbers,
        "has_units": has_units,
        "has_scientific_notation": has_scientific_notation,
        "has_math_symbols": has_math_symbols,
        "critical_count": critical_count
    }


def select_source_text(row):
    """
    Selects the best currently available text.

    IMPORTANT:
    This does not mean the text is trusted.
    It only selects the candidate that will be verified.
    """

    recovery_status = row["recovery_status"]

    recovered_text = normalize_text(
        row["recovered_text"]
    )

    original_text = normalize_text(
        row["original_text"]
    )

    if recovery_status in {
        "RECOVERED",
        "RECOVERED_UNCERTAIN"
    }:
        if recovered_text:
            return recovered_text, "RECOVERED_TEXT"

    return original_text, "ORIGINAL_TEXT"


def get_recovery_rows(cursor, upload_id):
    cursor.execute("""
        SELECT
            r.id,
            r.upload_id,
            r.page_number,
            r.recovery_status,
            r.recovery_priority,
            r.original_text,
            r.recovered_text,
            r.corruption_score,
            r.suspicious_patterns,
            r.admin_review_required,
            r.admin_notification_status,
            s.id AS source_page_id,
            s.page_path
        FROM recovered_page_content r
        LEFT JOIN source_pages s
            ON s.upload_id = r.upload_id
            AND s.page_number = r.page_number
        WHERE r.upload_id = ?
        ORDER BY r.page_number
    """, (upload_id,))

    return cursor.fetchall()


def calculate_verification(
    row,
    text,
    text_source
):
    """
    Main accuracy decision.

    The score is a verification-confidence score,
    NOT a claim of literal OCR percentage accuracy.
    """

    reasons = []
    warnings = []

    confidence = 100.0

    text = normalize_text(text)

    if not row["source_page_id"]:
        confidence -= 100
        reasons.append("SOURCE_PAGE_MISSING")

    if not row["page_path"]:
        confidence -= 100
        reasons.append("SOURCE_PATH_MISSING")

    if not text:
        confidence -= 100
        reasons.append("TEXT_MISSING")

    text_length = len(text)

    if 0 < text_length < 30:
        confidence -= 40
        warnings.append("VERY_SHORT_TEXT")

    unusual_symbol_ratio = (
        calculate_unusual_symbol_ratio(text)
    )

    if unusual_symbol_ratio > 20:
        confidence -= 40
        warnings.append("SEVERE_SYMBOL_CORRUPTION")
    elif unusual_symbol_ratio > 10:
        confidence -= 20
        warnings.append("HIGH_SYMBOL_CORRUPTION")
    elif unusual_symbol_ratio > 5:
        confidence -= 10
        warnings.append("MODERATE_SYMBOL_CORRUPTION")

    alpha_ratio = calculate_alpha_ratio(text)

    if text_length > 100:
        if alpha_ratio < 25:
            confidence -= 40
            warnings.append("VERY_LOW_READABILITY")
        elif alpha_ratio < 40:
            confidence -= 20
            warnings.append("LOW_READABILITY")

    broken_word_warnings = detect_broken_words(text)
    warnings.extend(broken_word_warnings)

    if "MANY_SHORT_OCR_FRAGMENTS" in broken_word_warnings:
        confidence -= 15

    if "POSSIBLE_TRUNCATED_WORDS" in broken_word_warnings:
        confidence -= 15

    question_info = detect_question_structure(text)

    critical_info = (
        detect_critical_educational_content(text)
    )

    if (
        critical_info["critical_count"] >= 2
        and unusual_symbol_ratio > 5
    ):
        warnings.append(
            "CRITICAL_EDUCATIONAL_CONTENT_NEEDS_STRICT_VERIFICATION"
        )
        confidence -= 10

    recovery_status = row["recovery_status"]

    if recovery_status == "RECOVERED_UNCERTAIN":
        confidence -= 20
        warnings.append(
            "RECOVERY_RESULT_MARKED_UNCERTAIN"
        )

    if row["admin_review_required"] == 1:
        confidence -= 20
        warnings.append(
            "ADMIN_REVIEW_ALREADY_REQUIRED"
        )

    if recovery_status == "RECOVERED":
        reasons.append(
            "TEXT_SELECTED_FROM_RECOVERY"
        )

    if recovery_status == "CLEAN_ACCEPTED":
        reasons.append(
            "CLEANED_CONTENT_ACCEPTED"
        )

    confidence = max(
        0.0,
        min(100.0, confidence)
    )

    # Safety-first decision rules.

    if (
        "SOURCE_PAGE_MISSING" in reasons
        or "SOURCE_PATH_MISSING" in reasons
        or "TEXT_MISSING" in reasons
        or confidence < 45
    ):
        verification_status = "BLOCKED"
        admin_review_required = 1

    elif (
        confidence < 85
        or recovery_status == "RECOVERED_UNCERTAIN"
        or row["admin_review_required"] == 1
        or "SEVERE_SYMBOL_CORRUPTION" in warnings
        or "VERY_LOW_READABILITY" in warnings
    ):
        verification_status = "UNCERTAIN"
        admin_review_required = 1

    else:
        verification_status = "VERIFIED"
        admin_review_required = 0

    return {
        "upload_id": row["upload_id"],
        "page_number": row["page_number"],
        "source_page_id": row["source_page_id"],
        "text_source": text_source,
        "verification_status": verification_status,
        "verification_confidence": round(confidence, 2),
        "selected_text": text,
        "text_length": text_length,
        "unusual_symbol_ratio": unusual_symbol_ratio,
        "alpha_ratio": alpha_ratio,
        "question_structure": question_info["status"],
        "numbered_questions": question_info["numbered_questions"],
        "question_markers": question_info["question_markers"],
        "has_numbers": int(
            critical_info["has_numbers"]
        ),
        "has_units": int(
            critical_info["has_units"]
        ),
        "has_scientific_notation": int(
            critical_info["has_scientific_notation"]
        ),
        "has_math_symbols": int(
            critical_info["has_math_symbols"]
        ),
        "critical_content_count": (
            critical_info["critical_count"]
        ),
        "warnings": ",".join(
            sorted(set(warnings))
        ),
        "reasons": ",".join(
            sorted(set(reasons))
        ),
        "admin_review_required": (
            admin_review_required
        )
    }


def ensure_accuracy_table(cursor):
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accuracy_verification (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            upload_id INTEGER NOT NULL,
            source_page_id INTEGER,

            page_number INTEGER NOT NULL,

            text_source TEXT NOT NULL,

            verification_status TEXT NOT NULL,

            verification_confidence REAL NOT NULL DEFAULT 0,

            selected_text TEXT,

            text_length INTEGER NOT NULL DEFAULT 0,

            unusual_symbol_ratio REAL NOT NULL DEFAULT 0,

            alpha_ratio REAL NOT NULL DEFAULT 0,

            question_structure TEXT,

            numbered_questions INTEGER NOT NULL DEFAULT 0,

            question_markers INTEGER NOT NULL DEFAULT 0,

            has_numbers INTEGER NOT NULL DEFAULT 0,

            has_units INTEGER NOT NULL DEFAULT 0,

            has_scientific_notation INTEGER NOT NULL DEFAULT 0,

            has_math_symbols INTEGER NOT NULL DEFAULT 0,

            critical_content_count INTEGER NOT NULL DEFAULT 0,

            warnings TEXT,

            reasons TEXT,

            admin_review_required INTEGER NOT NULL DEFAULT 0,

            admin_notification_status TEXT
                NOT NULL DEFAULT 'NONE',

            knowledge_brain_status TEXT
                NOT NULL DEFAULT 'BLOCKED',

            created_at TEXT
                DEFAULT CURRENT_TIMESTAMP,

            updated_at TEXT
                DEFAULT CURRENT_TIMESTAMP,

            UNIQUE(upload_id, page_number)
        )
    """)


def save_verification_result(
    cursor,
    result
):
    knowledge_brain_status = "BLOCKED"

    if (
        result["verification_status"] == "VERIFIED"
        and result["admin_review_required"] == 0
    ):
        knowledge_brain_status = "READY_FOR_KNOWLEDGE_BRAIN"

    notification_status = "NONE"

    if result["admin_review_required"] == 1:
        notification_status = "PENDING"

    cursor.execute("""
        INSERT INTO accuracy_verification (
            upload_id,
            source_page_id,
            page_number,
            text_source,
            verification_status,
            verification_confidence,
            selected_text,
            text_length,
            unusual_symbol_ratio,
            alpha_ratio,
            question_structure,
            numbered_questions,
            question_markers,
            has_numbers,
            has_units,
            has_scientific_notation,
            has_math_symbols,
            critical_content_count,
            warnings,
            reasons,
            admin_review_required,
            admin_notification_status,
            knowledge_brain_status,
            updated_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP
        )
        ON CONFLICT(upload_id, page_number)
        DO UPDATE SET

            source_page_id = excluded.source_page_id,

            text_source = excluded.text_source,

            verification_status =
                excluded.verification_status,

            verification_confidence =
                excluded.verification_confidence,

            selected_text =
                excluded.selected_text,

            text_length =
                excluded.text_length,

            unusual_symbol_ratio =
                excluded.unusual_symbol_ratio,

            alpha_ratio =
                excluded.alpha_ratio,

            question_structure =
                excluded.question_structure,

            numbered_questions =
                excluded.numbered_questions,

            question_markers =
                excluded.question_markers,

            has_numbers =
                excluded.has_numbers,

            has_units =
                excluded.has_units,

            has_scientific_notation =
                excluded.has_scientific_notation,

            has_math_symbols =
                excluded.has_math_symbols,

            critical_content_count =
                excluded.critical_content_count,

            warnings =
                excluded.warnings,

            reasons =
                excluded.reasons,

            admin_review_required =
                excluded.admin_review_required,

            admin_notification_status =
                excluded.admin_notification_status,

            knowledge_brain_status =
                excluded.knowledge_brain_status,

            updated_at =
                CURRENT_TIMESTAMP
    """, (
        result["upload_id"],
        result["source_page_id"],
        result["page_number"],
        result["text_source"],
        result["verification_status"],
        result["verification_confidence"],
        result["selected_text"],
        result["text_length"],
        result["unusual_symbol_ratio"],
        result["alpha_ratio"],
        result["question_structure"],
        result["numbered_questions"],
        result["question_markers"],
        result["has_numbers"],
        result["has_units"],
        result["has_scientific_notation"],
        result["has_math_symbols"],
        result["critical_content_count"],
        result["warnings"],
        result["reasons"],
        result["admin_review_required"],
        (
            "PENDING"
            if result["admin_review_required"] == 1
            else "NONE"
        ),
        knowledge_brain_status
    ))


def build_accuracy_verification(upload_id):
    conn = get_connection()
    cursor = conn.cursor()

    ensure_accuracy_table(cursor)

    rows = get_recovery_rows(
        cursor,
        upload_id
    )

    if not rows:
        conn.close()

        return {
            "upload_id": upload_id,
            "pages_processed": 0,
            "status": "NO_RECOVERED_CONTENT_FOUND"
        }

    print()
    print(
        f"Examora Accuracy Verification started "
        f"for Upload ID {upload_id}"
    )

    print(
        f"Pages to verify: {len(rows)}"
    )

    summary = Counter()

    for row in rows:
        text, text_source = select_source_text(row)

        result = calculate_verification(
            row,
            text,
            text_source
        )

        save_verification_result(
            cursor,
            result
        )

        summary[
            result["verification_status"]
        ] += 1

        print(
            f"Page {result['page_number']} verified | "
            f"status: {result['verification_status']} | "
            f"confidence: "
            f"{result['verification_confidence']} | "
            f"knowledge: "
            f"{'READY' if result['admin_review_required'] == 0 and result['verification_status'] == 'VERIFIED' else 'BLOCKED'}"
        )

    conn.commit()
    conn.close()

    print()
    print(
        "Examora Accuracy Verification completed."
    )

    return {
        "upload_id": upload_id,
        "pages_processed": len(rows),
        "verification_summary": dict(summary),
        "status": "ACCURACY_VERIFICATION_COMPLETED"
    }


if __name__ == "__main__":
    print(
        "Examora Accuracy Verification Engine is ready."
    )
