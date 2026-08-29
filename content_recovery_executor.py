import os
import re
import sqlite3

from PIL import Image, ImageEnhance, ImageFilter
import pytesseract


DB_PATH = "examora.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def calculate_text_quality(text):
    """
    Conservative OCR quality score.

    This score does NOT decide that content is educationally correct.
    It only compares OCR candidates and helps detect obvious corruption.
    """

    if not text:
        return 0.0

    total_chars = len(text)

    letters = sum(ch.isalpha() for ch in text)
    digits = sum(ch.isdigit() for ch in text)

    allowed_symbols = set(
        " \n\t.,;:!?()[]{}+-=*/%^_<>"
        "\"'\\|&@#$~`"
    )

    unusual = sum(
        1
        for ch in text
        if not ch.isalnum()
        and not ch.isspace()
        and ch not in allowed_symbols
    )

    words = re.findall(r"[A-Za-z]{2,}", text)

    if not words:
        return 0.0

    alphabetic_ratio = letters / max(total_chars, 1)

    meaningful_words = sum(
        1
        for word in words
        if len(word) >= 3
    )

    word_ratio = meaningful_words / max(len(words), 1)

    unusual_ratio = unusual / max(total_chars, 1)

    score = (
        alphabetic_ratio * 45
        + word_ratio * 35
        + min(len(words) / 100, 1) * 20
        - unusual_ratio * 100
    )

    return round(max(0.0, min(score, 100.0)), 2)


def rotate_image(image, rotation):
    """
    Rotate image according to verified best rotation.
    """

    if rotation == 0:
        return image

    return image.rotate(
        rotation,
        expand=True
    )


def prepare_recovery_versions(image):
    """
    Create several conservative versions of the original image.

    Original image is NEVER modified on disk.
    """

    versions = {}

    versions["ROTATED_ORIGINAL"] = image

    grayscale = image.convert("L")
    versions["GRAYSCALE"] = grayscale

    contrast = ImageEnhance.Contrast(grayscale).enhance(2.0)
    versions["HIGH_CONTRAST"] = contrast

    sharpened = grayscale.filter(
        ImageFilter.SHARPEN
    )
    versions["SHARPENED"] = sharpened

    enhanced = ImageEnhance.Contrast(
        ImageEnhance.Sharpness(
            grayscale
        ).enhance(2.0)
    ).enhance(1.5)

    versions["ENHANCED"] = enhanced

    return versions


def run_ocr_candidates(image_versions):
    """
    Run multiple conservative OCR attempts.

    Different page segmentation modes may perform differently
    depending on page layout.
    """

    candidates = []

    psm_modes = [
        3,
        6,
        11
    ]

    for version_name, image in image_versions.items():

        for psm in psm_modes:

            config = f"--psm {psm}"

            try:
                text = pytesseract.image_to_string(
                    image,
                    config=config
                )

                quality_score = calculate_text_quality(text)

                candidates.append({
                    "version": version_name,
                    "psm": psm,
                    "text": text,
                    "quality_score": quality_score
                })

            except Exception as error:

                candidates.append({
                    "version": version_name,
                    "psm": psm,
                    "text": "",
                    "quality_score": 0.0,
                    "error": str(error)
                })

    return candidates


def select_best_candidate(candidates):
    """
    Select best OCR candidate based on quality score.

    This selects the best OCR output,
    NOT automatically verified educational truth.
    """

    valid_candidates = [
        candidate
        for candidate in candidates
        if candidate.get("text", "").strip()
    ]

    if not valid_candidates:
        return None

    valid_candidates.sort(
        key=lambda candidate: candidate["quality_score"],
        reverse=True
    )

    return valid_candidates[0]


def get_recovery_rows(cursor, upload_id):
    """
    Get pages that need actual recovery.
    """

    cursor.execute(
        """
        SELECT
            recovered.id,
            recovered.upload_id,
            recovered.page_number,
            recovered.source_cleaned_content_id,
            recovered.original_quality_status,
            recovered.suspicious_patterns,
            recovered.recovery_status,
            recovered.recovery_priority,
            recovered.original_text,
            recovered.corruption_score,

            cleaned.source_page_id,
            cleaned.cleaned_text,

            source.page_path,

            verification.best_rotation,
            verification.verification_status

        FROM recovered_page_content AS recovered

        JOIN cleaned_page_content AS cleaned
            ON cleaned.id =
            recovered.source_cleaned_content_id

        JOIN source_pages AS source
            ON source.id =
            cleaned.source_page_id

        LEFT JOIN ocr_verification AS verification
            ON verification.upload_id =
            recovered.upload_id
            AND verification.page_number =
            recovered.page_number

        WHERE recovered.upload_id = ?

        AND recovered.recovery_status
        IN (
            'RECOVERY_REQUIRED',
            'REQUIRES_REVIEW'
        )

        ORDER BY
            CASE recovered.recovery_priority
                WHEN 'CRITICAL' THEN 1
                WHEN 'HIGH' THEN 2
                WHEN 'NORMAL' THEN 3
                ELSE 4
            END,
            recovered.page_number
        """,
        (upload_id,)
    )

    return cursor.fetchall()


def execute_recovery_for_page(row):
    """
    Perform recovery attempts for one page.
    """

    (
        recovery_id,
        upload_id,
        page_number,
        source_cleaned_content_id,
        original_quality_status,
        suspicious_patterns,
        recovery_status,
        recovery_priority,
        original_text,
        corruption_score,
        source_page_id,
        cleaned_text,
        page_path,
        best_rotation,
        verification_status
    ) = row

    if not os.path.exists(page_path):
        return {
            "success": False,
            "recovery_id": recovery_id,
            "page_number": page_number,
            "recovered_text": None,
            "recovery_status": "SOURCE_FILE_MISSING",
            "admin_review_required": 1,
            "notes": f"Original page file not found: {page_path}"
        }

    try:

        original_image = Image.open(page_path)

        rotation = best_rotation or 0

        rotated_image = rotate_image(
            original_image,
            rotation
        )

        image_versions = prepare_recovery_versions(
            rotated_image
        )

        candidates = run_ocr_candidates(
            image_versions
        )

        best_candidate = select_best_candidate(
            candidates
        )

        if not best_candidate:

            return {
                "success": False,
                "recovery_id": recovery_id,
                "page_number": page_number,
                "recovered_text": None,
                "recovery_status": "RECOVERY_FAILED",
                "admin_review_required": 1,
                "notes": "No usable OCR candidate produced."
            }

        recovered_text = best_candidate["text"]
        recovered_score = best_candidate["quality_score"]

        existing_score = calculate_text_quality(
            cleaned_text
        )

        # Conservative decision:
        # Only replace existing content if the new candidate
        # is meaningfully better.

        improvement = round(
            recovered_score - existing_score,
            2
        )

        if improvement >= 5:

            final_text = recovered_text

            if recovered_score >= 70:
                final_status = "RECOVERED"
                admin_review_required = 0
            else:
                final_status = "RECOVERED_UNCERTAIN"
                admin_review_required = 1

            notes = (
                f"Recovery selected. "
                f"Method={best_candidate['version']}, "
                f"PSM={best_candidate['psm']}, "
                f"OldScore={existing_score}, "
                f"NewScore={recovered_score}, "
                f"Improvement={improvement}"
            )

        else:

            final_text = cleaned_text

            final_status = "RECOVERY_NOT_IMPROVED"

            # Critical pages must remain visible
            # for human review.

            if recovery_priority in ("HIGH", "CRITICAL"):
                admin_review_required = 1
            else:
                admin_review_required = 0

            notes = (
                f"Recovery candidate was not sufficiently "
                f"better. "
                f"Method={best_candidate['version']}, "
                f"PSM={best_candidate['psm']}, "
                f"OldScore={existing_score}, "
                f"NewScore={recovered_score}, "
                f"Improvement={improvement}. "
                f"Existing cleaned text preserved."
            )

        return {
            "success": True,
            "recovery_id": recovery_id,
            "page_number": page_number,
            "recovered_text": final_text,
            "recovery_status": final_status,
            "admin_review_required": admin_review_required,
            "notes": notes,
            "existing_score": existing_score,
            "recovered_score": recovered_score,
            "improvement": improvement
        }

    except Exception as error:

        return {
            "success": False,
            "recovery_id": recovery_id,
            "page_number": page_number,
            "recovered_text": None,
            "recovery_status": "RECOVERY_ERROR",
            "admin_review_required": 1,
            "notes": str(error)
        }


def save_recovery_result(cursor, result):

    notification_status = (
        "PENDING"
        if result["admin_review_required"]
        else "NONE"
    )

    cursor.execute(
        """
        UPDATE recovered_page_content

        SET
            recovered_text = ?,
            recovery_status = ?,
            recovery_notes = ?,
            admin_review_required = ?,
            admin_notification_status = ?,
            updated_at = CURRENT_TIMESTAMP

        WHERE id = ?
        """,
        (
            result["recovered_text"],
            result["recovery_status"],
            result["notes"],
            result["admin_review_required"],
            notification_status,
            result["recovery_id"]
        )
    )


def build_recovery_execution(upload_id):

    print(
        f"\nExamora Recovery Execution started "
        f"for Upload ID {upload_id}"
    )

    conn = get_connection()
    cursor = conn.cursor()

    rows = get_recovery_rows(
        cursor,
        upload_id
    )

    print(
        f"Pages queued for recovery: {len(rows)}"
    )

    summary = {}

    for row in rows:

        page_number = row[2]
        priority = row[7]

        print(
            f"\nRECOVERING PAGE {page_number} "
            f"| priority: {priority}"
        )

        result = execute_recovery_for_page(row)

        save_recovery_result(
            cursor,
            result
        )

        conn.commit()

        status = result["recovery_status"]

        summary[status] = (
            summary.get(status, 0) + 1
        )

        if result["success"]:

            print(
                f"Page {page_number} completed "
                f"| status: {status}"
            )

            if "existing_score" in result:

                print(
                    f"  Existing score: "
                    f"{result['existing_score']}"
                )

                print(
                    f"  Recovery score: "
                    f"{result['recovered_score']}"
                )

                print(
                    f"  Improvement: "
                    f"{result['improvement']}"
                )

        else:

            print(
                f"Page {page_number} failed "
                f"| status: {status}"
            )

    conn.close()

    print(
        "\nExamora Recovery Execution completed."
    )

    return {
        "upload_id": upload_id,
        "pages_processed": len(rows),
        "recovery_summary": summary,
        "status": "RECOVERY_EXECUTION_COMPLETED"
    }


if __name__ == "__main__":

    print(
        "Examora Content Recovery Executor is ready."
    )
