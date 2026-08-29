import sqlite3
from pathlib import Path

import fitz


DATABASE = "examora.db"


def get_connection():
    return sqlite3.connect(DATABASE)


def create_content_extraction_tables():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS page_contents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            upload_id INTEGER NOT NULL,
            source_page_id INTEGER NOT NULL,
            page_number INTEGER NOT NULL,

            content_type TEXT NOT NULL,

            content_text TEXT,

            extraction_method TEXT NOT NULL,

            status TEXT NOT NULL DEFAULT 'EXTRACTED',

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (upload_id)
                REFERENCES knowledge_uploads(id),

            FOREIGN KEY (source_page_id)
                REFERENCES source_pages(id)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_page_contents_upload_page
        ON page_contents(upload_id, page_number)
    """)

    conn.commit()
    conn.close()


def get_upload(upload_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            original_name,
            source_type,
            upload_path,
            status
        FROM knowledge_uploads
        WHERE id=?
    """, (upload_id,))

    upload = cursor.fetchone()

    conn.close()

    return upload


def get_source_pages(upload_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            page_number,
            page_path,
            original_type
        FROM source_pages
        WHERE upload_id=?
        ORDER BY page_number
    """, (upload_id,))

    pages = cursor.fetchall()

    conn.close()

    return pages


def find_original_pdf(upload_path):

    upload_directory = Path(upload_path)

    pdf_files = list(upload_directory.glob("*.pdf"))

    if not pdf_files:
        pdf_files = list(upload_directory.glob("*.PDF"))

    if not pdf_files:
        raise FileNotFoundError(
            "Original PDF file was not found."
        )

    return pdf_files[0]


def clear_previous_text(upload_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM page_contents
        WHERE upload_id=?
        AND content_type='TEXT'
    """, (upload_id,))

    conn.commit()
    conn.close()


def save_page_text(
    upload_id,
    source_page_id,
    page_number,
    text
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO page_contents (
            upload_id,
            source_page_id,
            page_number,
            content_type,
            content_text,
            extraction_method,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        upload_id,
        source_page_id,
        page_number,
        "TEXT",
        text,
        "PYMUPDF_NATIVE_TEXT",
        "EXTRACTED"
    ))

    conn.commit()
    conn.close()


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


def extract_pdf_content(upload_id):

    create_content_extraction_tables()

    upload = get_upload(upload_id)

    if not upload:
        raise ValueError(
            f"Upload ID {upload_id} was not found."
        )

    (
        source_id,
        original_name,
        source_type,
        upload_path,
        status
    ) = upload

    if source_type != "PDF":

        raise ValueError(
            "This extraction function currently "
            "handles PDF sources only."
        )

    source_pages = get_source_pages(upload_id)

    if not source_pages:

        raise ValueError(
            "No normalized pages were found for "
            f"Upload ID {upload_id}."
        )

    original_pdf = find_original_pdf(upload_path)

    document = fitz.open(original_pdf)

    clear_previous_text(upload_id)

    total_pages = len(document)

    extracted_pages = 0
    empty_pages = 0

    for page_index in range(total_pages):

        page = document.load_page(page_index)

        page_number = page_index + 1

        text = page.get_text(
            "text",
            sort=True
        )

        text = text.strip()

        matching_source_page = None

        for source_page in source_pages:

            if source_page[1] == page_number:
                matching_source_page = source_page
                break

        if matching_source_page is None:

            print(
                f"WARNING: Source page {page_number} "
                "was not found in source_pages."
            )

            continue

        source_page_id = matching_source_page[0]

        if not text:

            empty_pages += 1

            text = ""

        else:

            extracted_pages += 1

        save_page_text(
            upload_id=upload_id,
            source_page_id=source_page_id,
            page_number=page_number,
            text=text
        )

        print(
            f"Page {page_number}/{total_pages} extracted "
            f"| characters: {len(text)}"
        )

    document.close()

    if empty_pages > 0:

        final_status = "TEXT_EXTRACTION_PARTIAL"

    else:

        final_status = "TEXT_EXTRACTED"

    update_upload_status(
        upload_id,
        final_status
    )

    return {
        "upload_id": upload_id,
        "original_name": original_name,
        "source_type": source_type,
        "total_pdf_pages": total_pages,
        "pages_with_text": extracted_pages,
        "pages_without_text": empty_pages,
        "status": final_status
    }


if __name__ == "__main__":

    create_content_extraction_tables()

    print(
        "Examora Content Extractor is ready."
    )
