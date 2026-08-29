import re
import sqlite3
import subprocess
from pathlib import Path


DATABASE = "examora.db"

ROTATIONS = [0, 90, 180, 270]


def get_connection():
    return sqlite3.connect(DATABASE)


def create_ocr_verification_table():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ocr_verification (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            upload_id INTEGER NOT NULL,
            source_page_id INTEGER NOT NULL,
            page_number INTEGER NOT NULL,

            original_rotation INTEGER NOT NULL DEFAULT 0,
            best_rotation INTEGER NOT NULL DEFAULT 0,

            original_text_length INTEGER NOT NULL DEFAULT 0,
            best_text_length INTEGER NOT NULL DEFAULT 0,

            readability_score REAL NOT NULL DEFAULT 0,
            alphabetic_ratio REAL NOT NULL DEFAULT 0,
            meaningful_word_count INTEGER NOT NULL DEFAULT 0,

            page_classification TEXT,
            verification_status TEXT NOT NULL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (upload_id)
                REFERENCES knowledge_uploads(id),

            FOREIGN KEY (source_page_id)
                REFERENCES source_pages(id)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_ocr_verification_upload_page
        ON ocr_verification(upload_id, page_number)
    """)

    conn.commit()
    conn.close()


def get_pages_for_verification(upload_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            sp.id,
            sp.page_number,
            sp.page_path,
            COALESCE(po.ocr_text, '')
        FROM source_pages sp
        LEFT JOIN page_ocr po
            ON sp.id = po.source_page_id
        WHERE sp.upload_id=?
        ORDER BY sp.page_number
    """, (upload_id,))

    pages = cursor.fetchall()

    conn.close()

    return pages


def rotate_image(input_path, output_path, rotation):

    if rotation == 0:
        return input_path

    command = [
        "magick",
        input_path,
        "-rotate",
        str(rotation),
        output_path
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:

        raise RuntimeError(
            f"Image rotation failed: {result.stderr}"
        )

    return output_path


def run_tesseract(image_path):

    command = [
        "tesseract",
        image_path,
        "stdout",
        "--psm",
        "6"
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True
    )

    if result.returncode != 0:

        raise RuntimeError(
            f"OCR failed: {result.stderr}"
        )

    return result.stdout.strip()


def calculate_text_quality(text):

    if not text:
        return {
            "score": 0.0,
            "alphabetic_ratio": 0.0,
            "meaningful_words": 0
        }

    total_characters = len(text)

    alphabetic_characters = sum(
        1
        for character in text
        if character.isalpha()
    )

    alphabetic_ratio = (
        alphabetic_characters
        / max(total_characters, 1)
    )

    words = re.findall(
        r"[A-Za-z]{3,}",
        text
    )

    meaningful_words = len(words)

    length_score = min(
        total_characters / 1000,
        1.0
    )

    word_score = min(
        meaningful_words / 150,
        1.0
    )

    readability_score = (
        alphabetic_ratio * 40
        + length_score * 25
        + word_score * 35
    )

    return {
        "score": round(readability_score, 2),
        "alphabetic_ratio": round(
            alphabetic_ratio,
            4
        ),
        "meaningful_words": meaningful_words
    }


def classify_page(
    text_length,
    quality_score
):

    if text_length <= 20:
        return "VISUAL_OR_LOW_TEXT"

    if quality_score < 20:
        return "LOW_QUALITY_TEXT"

    if text_length < 150:
        return "MIXED_OR_LOW_TEXT"

    return "TEXT_HEAVY"


def clear_previous_verification(upload_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM ocr_verification
        WHERE upload_id=?
    """, (upload_id,))

    conn.commit()
    conn.close()


def save_verification(
    upload_id,
    source_page_id,
    page_number,
    best_rotation,
    original_text_length,
    best_text,
    best_text_length,
    readability_score,
    alphabetic_ratio,
    meaningful_word_count,
    page_classification,
    verification_status
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO ocr_verification (
            upload_id,
            source_page_id,
            page_number,

            original_rotation,
            best_rotation,

            original_text_length,
            best_text_length,

            readability_score,
            alphabetic_ratio,
            meaningful_word_count,

            page_classification,
            verification_status,

            best_text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        upload_id,
        source_page_id,
        page_number,

        0,
        best_rotation,

        original_text_length,
        best_text_length,

        readability_score,
        alphabetic_ratio,
        meaningful_word_count,

        page_classification,
        verification_status,

        best_text
    ))

    conn.commit()
    conn.close()


def verify_ocr(upload_id):

    create_ocr_verification_table()

    pages = get_pages_for_verification(
        upload_id
    )

    if not pages:

        raise ValueError(
            f"No pages found for Upload ID {upload_id}."
        )

    clear_previous_verification(upload_id)

    print()

    print(
        f"Examora OCR Verification started "
        f"for Upload ID {upload_id}"
    )

    print(
        f"Pages to verify: {len(pages)}"
    )

    for page_data in pages:

        (
            source_page_id,
            page_number,
            page_path,
            original_text
        ) = page_data

        print()

        print(
            f"VERIFYING PAGE "
            f"{page_number}/{len(pages)}"
        )

        original_text = (
            original_text or ""
        ).strip()

        original_text_length = len(
            original_text
        )

        best_rotation = 0

        best_text = original_text

        best_quality = calculate_text_quality(
            original_text
        )

        image_path = Path(page_path)

        if not image_path.exists():

            print(
                f"WARNING: Image not found: "
                f"{page_path}"
            )

            continue

        for rotation in ROTATIONS:

            if rotation == 0:

                text = original_text

            else:

                rotated_path = (
                    image_path.parent
                    / (
                        f"verify_page_"
                        f"{page_number:04d}_"
                        f"{rotation}.png"
                    )
                )

                try:

                    rotated_image = rotate_image(
                        str(image_path),
                        str(rotated_path),
                        rotation
                    )

                    text = run_tesseract(
                        str(rotated_image)
                    )

                except Exception as error:

                    print(
                        f"Rotation {rotation} failed: "
                        f"{error}"
                    )

                    continue

            quality = calculate_text_quality(
                text
            )

            print(
                f"Rotation {rotation}° "
                f"| chars: {len(text)} "
                f"| score: {quality['score']}"
            )

            if (
                quality["score"]
                > best_quality["score"]
            ):

                best_rotation = rotation

                best_text = text

                best_quality = quality

        best_text = (
            best_text or ""
        ).strip()

        best_text_length = len(
            best_text
        )

        classification = classify_page(
            best_text_length,
            best_quality["score"]
        )

        if best_quality["score"] >= 40:

            verification_status = "VERIFIED"

        else:

            verification_status = "LOW_CONFIDENCE"

        save_verification(
            upload_id=upload_id,
            source_page_id=source_page_id,
            page_number=page_number,
            best_rotation=best_rotation,
            original_text_length=original_text_length,
            best_text=best_text,
            best_text_length=best_text_length,
            readability_score=best_quality[
                "score"
            ],
            alphabetic_ratio=best_quality[
                "alphabetic_ratio"
            ],
            meaningful_word_count=best_quality[
                "meaningful_words"
            ],
            page_classification=classification,
            verification_status=verification_status
        )

        print(
            f"BEST RESULT → "
            f"Rotation: {best_rotation}° "
            f"| Characters: {best_text_length} "
            f"| Classification: {classification} "
            f"| Status: {verification_status}"
        )

    print()

    print(
        "Examora OCR Verification completed."
    )

    return {
        "upload_id": upload_id,
        "pages_verified": len(pages),
        "status": "OCR_VERIFICATION_COMPLETED"
    }


if __name__ == "__main__":

    create_ocr_verification_table()

    print(
        "Examora OCR Verification Engine is ready."
    )
