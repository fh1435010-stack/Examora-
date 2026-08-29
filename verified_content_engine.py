import sqlite3


DATABASE = "examora.db"


def get_connection():

    conn = sqlite3.connect(DATABASE)

    conn.row_factory = sqlite3.Row

    return conn


def create_verified_content_table():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS verified_page_content (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            upload_id INTEGER NOT NULL,

            source_page_id INTEGER NOT NULL,

            page_number INTEGER NOT NULL,

            verified_text TEXT,

            text_source TEXT NOT NULL,

            best_rotation INTEGER,

            content_classification TEXT,

            verification_status TEXT NOT NULL,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (upload_id)
                REFERENCES knowledge_uploads(id),

            FOREIGN KEY (source_page_id)
                REFERENCES source_pages(id)
        )
    """)

    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_verified_page_content_unique

        ON verified_page_content(
            upload_id,
            source_page_id
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_verified_page_content_upload_page

        ON verified_page_content(
            upload_id,
            page_number
        )
    """)

    conn.commit()
    conn.close()


def get_source_pages(upload_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            page_number,
            page_path
        FROM source_pages
        WHERE upload_id=?
        ORDER BY page_number
    """, (upload_id,))

    pages = cursor.fetchall()

    conn.close()

    return pages


def get_native_text(
    upload_id,
    source_page_id
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            content_text
        FROM page_contents
        WHERE upload_id=?
        AND source_page_id=?
        AND content_type='TEXT'
        ORDER BY id DESC
        LIMIT 1
    """, (
        upload_id,
        source_page_id
    ))

    row = cursor.fetchone()

    conn.close()

    if row:

        return row["content_text"] or ""

    return ""


def get_ocr_text(
    upload_id,
    source_page_id
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            ocr_text
        FROM page_ocr
        WHERE upload_id=?
        AND source_page_id=?
        ORDER BY id DESC
        LIMIT 1
    """, (
        upload_id,
        source_page_id
    ))

    row = cursor.fetchone()

    conn.close()

    if row:

        return row["ocr_text"] or ""

    return ""


def get_verification_result(
    upload_id,
    source_page_id
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            best_rotation,
            best_text,
            readability_score,
            alphabetic_ratio,
            meaningful_word_count,
            page_classification,
            verification_status
        FROM ocr_verification
        WHERE upload_id=?
        AND source_page_id=?
        ORDER BY id DESC
        LIMIT 1
    """, (
        upload_id,
        source_page_id
    ))

    row = cursor.fetchone()

    conn.close()

    return row


def classify_text_content(text):

    clean_text = (text or "").strip()

    characters = len(clean_text)

    words = len(clean_text.split())

    if characters == 0:

        return "NO_TEXT"

    if characters < 100 or words < 20:

        return "VISUAL_HEAVY"

    if characters < 500 or words < 80:

        return "MIXED"

    return "TEXT_HEAVY"


def choose_best_text(
    native_text,
    ocr_text,
    verification
):

    native_text = (native_text or "").strip()

    ocr_text = (ocr_text or "").strip()

    verified_ocr_text = ""

    best_rotation = None

    verification_status = "UNVERIFIED"

    verified_classification = None

    if verification:

        verified_ocr_text = (
            verification["best_text"] or ""
        ).strip()

        best_rotation = (
            verification["best_rotation"]
        )

        verification_status = (
            verification["verification_status"]
            or "UNVERIFIED"
        )

        verified_classification = (
            verification["page_classification"]
        )

    native_length = len(native_text)

    verified_ocr_length = len(
        verified_ocr_text
    )

    original_ocr_length = len(
        ocr_text
    )

    # Native PDF text is preferred when
    # meaningful native text exists.
    if native_length >= 100:

        return {
            "verified_text": native_text,
            "text_source": "NATIVE_PDF",
            "best_rotation": best_rotation,
            "verification_status":
                verification_status,
            "content_classification":
                verified_classification
                or classify_text_content(
                    native_text
                )
        }

    # Prefer the OCR text selected by the
    # OCR verification engine.
    if verified_ocr_length > 0:

        return {
            "verified_text":
                verified_ocr_text,
            "text_source":
                "OCR_VERIFIED",
            "best_rotation":
                best_rotation,
            "verification_status":
                verification_status,
            "content_classification":
                verified_classification
                or classify_text_content(
                    verified_ocr_text
                )
        }

    # Fall back to original OCR only when
    # verified OCR text is unavailable.
    if original_ocr_length > 0:

        return {
            "verified_text": ocr_text,
            "text_source":
                "OCR_UNVERIFIED_FALLBACK",
            "best_rotation":
                best_rotation,
            "verification_status":
                verification_status,
            "content_classification":
                classify_text_content(
                    ocr_text
                )
        }

    return {
        "verified_text": "",
        "text_source": "NONE",
        "best_rotation":
            best_rotation,
        "verification_status":
            verification_status,
        "content_classification":
            verified_classification
            or "NO_TEXT"
    }


def save_verified_content(
    upload_id,
    source_page_id,
    page_number,
    verified_text,
    text_source,
    best_rotation,
    content_classification,
    verification_status
):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO verified_page_content (

            upload_id,
            source_page_id,
            page_number,

            verified_text,
            text_source,
            best_rotation,
            content_classification,
            verification_status,

            updated_at
        )

        VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)

        ON CONFLICT(upload_id, source_page_id)

        DO UPDATE SET

            page_number=excluded.page_number,

            verified_text=excluded.verified_text,

            text_source=excluded.text_source,

            best_rotation=excluded.best_rotation,

            content_classification=
                excluded.content_classification,

            verification_status=
                excluded.verification_status,

            updated_at=CURRENT_TIMESTAMP
    """, (
        upload_id,
        source_page_id,
        page_number,

        verified_text,
        text_source,
        best_rotation,
        content_classification,
        verification_status
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


def build_verified_content(upload_id):

    create_verified_content_table()

    source_pages = get_source_pages(
        upload_id
    )

    if not source_pages:

        raise ValueError(
            f"No source pages found for "
            f"Upload ID {upload_id}."
        )

    print(
        f"Examora Verified Content Engine "
        f"started for Upload ID {upload_id}"
    )

    print(
        f"Pages to process: "
        f"{len(source_pages)}"
    )

    processed_pages = 0

    source_counts = {}

    classification_counts = {}

    for source_page in source_pages:

        source_page_id = source_page["id"]

        page_number = source_page[
            "page_number"
        ]

        native_text = get_native_text(
            upload_id,
            source_page_id
        )

        ocr_text = get_ocr_text(
            upload_id,
            source_page_id
        )

        verification = get_verification_result(
            upload_id,
            source_page_id
        )

        result = choose_best_text(
            native_text=native_text,
            ocr_text=ocr_text,
            verification=verification
        )

        save_verified_content(
            upload_id=upload_id,
            source_page_id=source_page_id,
            page_number=page_number,
            verified_text=
                result["verified_text"],
            text_source=
                result["text_source"],
            best_rotation=
                result["best_rotation"],
            content_classification=
                result[
                    "content_classification"
                ],
            verification_status=
                result[
                    "verification_status"
                ]
        )

        processed_pages += 1

        text_source = result[
            "text_source"
        ]

        classification = result[
            "content_classification"
        ]

        source_counts[text_source] = (
            source_counts.get(
                text_source,
                0
            ) + 1
        )

        classification_counts[
            classification
        ] = (
            classification_counts.get(
                classification,
                0
            ) + 1
        )

        print(
            f"Page {page_number} completed "
            f"| source: {text_source} "
            f"| rotation: "
            f"{result['best_rotation']} "
            f"| class: {classification} "
            f"| characters: "
            f"{len(result['verified_text'])}"
        )

    update_upload_status(
        upload_id,
        "VERIFIED_CONTENT_READY"
    )

    print()

    print(
        "Examora Verified Content Engine "
        "completed."
    )

    return {
        "upload_id": upload_id,
        "pages_processed": processed_pages,
        "text_sources": source_counts,
        "content_classifications":
            classification_counts,
        "status":
            "VERIFIED_CONTENT_READY"
    }


if __name__ == "__main__":

    create_verified_content_table()

    print(
        "Examora Verified Content Engine "
        "is ready."
    )
