import sqlite3
import subprocess
from pathlib import Path


DATABASE = "examora.db"


def get_connection():
    return sqlite3.connect(DATABASE)


def create_ocr_tables():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS page_ocr (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            upload_id INTEGER NOT NULL,
            source_page_id INTEGER NOT NULL,
            page_number INTEGER NOT NULL,

            page_path TEXT NOT NULL,

            ocr_text TEXT,

            ocr_engine TEXT NOT NULL,

            status TEXT NOT NULL DEFAULT 'OCR_EXTRACTED',

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (upload_id)
                REFERENCES knowledge_uploads(id),

            FOREIGN KEY (source_page_id)
                REFERENCES source_pages(id)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_page_ocr_upload_page
        ON page_ocr(upload_id, page_number)
    """)

    conn.commit()
    conn.close()


def get_pages_requiring_ocr(upload_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            sp.id,
            sp.page_number,
            sp.page_path
        FROM source_pages sp

        LEFT JOIN page_contents pc
        ON sp.id = pc.source_page_id
        AND pc.content_type = 'TEXT'

        WHERE sp.upload_id = ?

        GROUP BY
            sp.id,
            sp.page_number,
            sp.page_path

        HAVING
            COALESCE(MAX(LENGTH(TRIM(pc.content_text))), 0) = 0

        ORDER BY sp.page_number
    """, (upload_id,))

    pages = cursor.fetchall()

    conn.close()

    return pages


def clear_previous_ocr(upload_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM page_ocr
        WHERE upload_id=?
    """, (upload_id,))

    conn.commit()
    conn.close()


def save_ocr_result(
    upload_id,
    source_page_id,
    page_number,
    page_path,
    ocr_text,
    status
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO page_ocr (
            upload_id,
            source_page_id,
            page_number,
            page_path,
            ocr_text,
            ocr_engine,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        upload_id,
        source_page_id,
        page_number,
        page_path,
        ocr_text,
        "TESSERACT",
        status
    ))

    conn.commit()
    conn.close()


def run_tesseract(page_path):

    result = subprocess.run(
        [
            "tesseract",
            str(page_path),
            "stdout",
            "--psm",
            "3"
        ],
        capture_output=True,
        text=True,
        timeout=120
    )

    if result.returncode != 0:

        error_message = result.stderr.strip()

        raise RuntimeError(
            f"Tesseract OCR failed: {error_message}"
        )

    return result.stdout.strip()


def update_upload_status(
    upload_id,
    status
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE knowledge_uploads
        SET status=?
        WHERE id=?
    """, (
        status,
        upload_id
    ))

    conn.commit()
    conn.close()


def process_ocr(upload_id):

    create_ocr_tables()

    pages = get_pages_requiring_ocr(upload_id)

    if not pages:

        return {
            "upload_id": upload_id,
            "pages_processed": 0,
            "pages_with_text": 0,
            "pages_without_text": 0,
            "status": "OCR_NOT_REQUIRED"
        }

    clear_previous_ocr(upload_id)

    pages_processed = 0
    pages_with_text = 0
    pages_without_text = 0

    total_pages = len(pages)

    print()
    print(
        f"Examora OCR started for Upload ID {upload_id}"
    )

    print(
        f"Pages requiring OCR: {total_pages}"
    )

    print()

    for index, page in enumerate(pages, start=1):

        source_page_id = page[0]
        page_number = page[1]
        page_path = page[2]

        page_file = Path(page_path)

        if not page_file.exists():

            print(
                f"Page {page_number}: FILE NOT FOUND"
            )

            save_ocr_result(
                upload_id=upload_id,
                source_page_id=source_page_id,
                page_number=page_number,
                page_path=page_path,
                ocr_text="",
                status="OCR_FILE_NOT_FOUND"
            )

            pages_processed += 1
            pages_without_text += 1

            continue

        try:

            print(
                f"OCR {index}/{total_pages} "
                f"| Page {page_number}"
            )

            text = run_tesseract(page_file)

            if text:

                status = "OCR_EXTRACTED"

                pages_with_text += 1

            else:

                status = "OCR_EMPTY"

                pages_without_text += 1

            save_ocr_result(
                upload_id=upload_id,
                source_page_id=source_page_id,
                page_number=page_number,
                page_path=page_path,
                ocr_text=text,
                status=status
            )

            print(
                f"Page {page_number} completed "
                f"| characters: {len(text)}"
            )

        except Exception as error:

            print(
                f"Page {page_number} OCR ERROR: {error}"
            )

            save_ocr_result(
                upload_id=upload_id,
                source_page_id=source_page_id,
                page_number=page_number,
                page_path=page_path,
                ocr_text="",
                status="OCR_ERROR"
            )

            pages_without_text += 1

        pages_processed += 1

    if pages_without_text == 0:

        final_status = "OCR_COMPLETED"

    elif pages_with_text > 0:

        final_status = "OCR_PARTIAL"

    else:

        final_status = "OCR_FAILED_OR_EMPTY"

    update_upload_status(
        upload_id,
        final_status
    )

    print()
    print(
        "Examora OCR processing completed."
    )

    return {
        "upload_id": upload_id,
        "pages_processed": pages_processed,
        "pages_with_text": pages_with_text,
        "pages_without_text": pages_without_text,
        "status": final_status
    }


if __name__ == "__main__":

    create_ocr_tables()

    print(
        "Examora OCR Engine is ready."
    )
