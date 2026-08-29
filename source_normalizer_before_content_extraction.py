import sqlite3
from pathlib import Path
from datetime import datetime

import fitz
from PIL import Image


DATABASE = "examora.db"

UPLOAD_DIRECTORY = Path("knowledge_uploads")
NORMALIZED_DIRECTORY = Path("normalized_pages")

UPLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
NORMALIZED_DIRECTORY.mkdir(parents=True, exist_ok=True)


def get_connection():
    return sqlite3.connect(DATABASE)


def create_normalization_tables():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_name TEXT NOT NULL,
            source_type TEXT NOT NULL,
            board TEXT,
            class_name TEXT,
            group_name TEXT,
            subject TEXT,
            upload_path TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'UPLOADED',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS source_pages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            upload_id INTEGER NOT NULL,
            page_number INTEGER NOT NULL,
            page_path TEXT NOT NULL,
            original_type TEXT,
            width INTEGER,
            height INTEGER,
            status TEXT NOT NULL DEFAULT 'NORMALIZED',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (upload_id)
                REFERENCES knowledge_uploads(id)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_source_pages_upload_page
        ON source_pages(upload_id, page_number)
    """)

    conn.commit()
    conn.close()


def save_source_group(
    files,
    source_type,
    board=None,
    class_name=None,
    group_name=None,
    subject=None
):
    create_normalization_tables()

    if not files:
        raise ValueError("No source files were provided.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

    source_directory = (
        UPLOAD_DIRECTORY /
        f"source_{timestamp}"
    )

    source_directory.mkdir(
        parents=True,
        exist_ok=True
    )

    conn = get_connection()
    cursor = conn.cursor()

    first_name = files[0].filename

    cursor.execute("""
        INSERT INTO knowledge_uploads (
            original_name,
            source_type,
            board,
            class_name,
            group_name,
            subject,
            upload_path,
            status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        first_name if source_type == "PDF"
        else f"{len(files)} images",

        source_type,

        board,
        class_name,
        group_name,
        subject,

        str(source_directory),

        "UPLOADED"
    ))

    upload_id = cursor.lastrowid

    for page_number, file in enumerate(files, start=1):

        original_name = Path(file.filename).name

        destination = (
            source_directory /
            f"{page_number:04d}_{original_name}"
        )

        file.save(destination)

        cursor.execute("""
            INSERT INTO source_pages (
                upload_id,
                page_number,
                page_path,
                original_type,
                status
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            upload_id,
            page_number,
            str(destination),
            source_type,
            "UPLOADED"
        ))

    conn.commit()
    conn.close()

    return {
        "upload_id": upload_id,
        "source_type": source_type,
        "file_count": len(files),
        "status": "UPLOADED"
    }


def update_source_page(
    upload_id,
    page_number,
    page_path,
    width,
    height,
    status="NORMALIZED"
):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE source_pages
        SET
            page_path=?,
            width=?,
            height=?,
            status=?
        WHERE upload_id=?
        AND page_number=?
    """, (
        str(page_path),
        width,
        height,
        status,
        upload_id,
        page_number
    ))

    conn.commit()
    conn.close()


def set_upload_status(upload_id, status):
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


def normalize_image(
    input_path,
    output_path
):
    output_path = Path(output_path)
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with Image.open(input_path) as image:

        image = image.convert("RGB")

        image.save(
            output_path,
            format="PNG",
            optimize=True
        )

        width, height = image.size

    return width, height


def normalize_pdf(
    upload_id,
    pdf_path
):
    output_directory = (
        NORMALIZED_DIRECTORY /
        f"source_{upload_id}"
    )

    output_directory.mkdir(
        parents=True,
        exist_ok=True
    )

    document = fitz.open(pdf_path)

    normalized_pages = []

    for page_index in range(len(document)):

        page_number = page_index + 1

        page = document.load_page(page_index)

        matrix = fitz.Matrix(2, 2)

        pixmap = page.get_pixmap(
            matrix=matrix,
            alpha=False
        )

        output_path = (
            output_directory /
            f"page_{page_number:04d}.png"
        )

        pixmap.save(str(output_path))

        with Image.open(output_path) as image:
            width, height = image.size

        normalized_pages.append({
            "page_number": page_number,
            "page_path": output_path,
            "width": width,
            "height": height
        })

    document.close()

    return normalized_pages


def process_uploaded_source(upload_id):
    create_normalization_tables()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            source_type,
            upload_path
        FROM knowledge_uploads
        WHERE id=?
    """, (upload_id,))

    upload = cursor.fetchone()

    conn.close()

    if not upload:
        raise ValueError(
            f"Knowledge upload ID {upload_id} was not found."
        )

    source_type = upload[0]
    upload_path = Path(upload[1])

    if not upload_path.exists():
        raise FileNotFoundError(
            f"Upload directory does not exist: {upload_path}"
        )

    set_upload_status(
        upload_id,
        "PROCESSING"
    )

    try:

        if source_type == "PDF":

            pdf_files = sorted(
                upload_path.glob("*.pdf")
            )

            if not pdf_files:
                raise FileNotFoundError(
                    "No PDF file found in upload directory."
                )

            pdf_path = pdf_files[0]

            normalized_pages = normalize_pdf(
                upload_id,
                pdf_path
            )

            conn = get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                DELETE FROM source_pages
                WHERE upload_id=?
            """, (upload_id,))

            for page_data in normalized_pages:

                cursor.execute("""
                    INSERT INTO source_pages (
                        upload_id,
                        page_number,
                        page_path,
                        original_type,
                        width,
                        height,
                        status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    upload_id,
                    page_data["page_number"],
                    str(page_data["page_path"]),
                    "PDF",
                    page_data["width"],
                    page_data["height"],
                    "NORMALIZED"
                ))

            conn.commit()
            conn.close()

            set_upload_status(
                upload_id,
                "NORMALIZED"
            )

            return {
                "upload_id": upload_id,
                "source_type": "PDF",
                "page_count": len(normalized_pages),
                "status": "NORMALIZED"
            }

        image_files = sorted([
            path
            for path in upload_path.iterdir()
            if path.suffix.lower()
            in {
                ".png",
                ".jpg",
                ".jpeg",
                ".webp"
            }
        ])

        if not image_files:
            raise FileNotFoundError(
                "No supported image files found."
            )

        output_directory = (
            NORMALIZED_DIRECTORY /
            f"source_{upload_id}"
        )

        output_directory.mkdir(
            parents=True,
            exist_ok=True
        )

        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM source_pages
            WHERE upload_id=?
        """, (upload_id,))

        for page_number, image_path in enumerate(
            image_files,
            start=1
        ):

            output_path = (
                output_directory /
                f"page_{page_number:04d}.png"
            )

            width, height = normalize_image(
                image_path,
                output_path
            )

            cursor.execute("""
                INSERT INTO source_pages (
                    upload_id,
                    page_number,
                    page_path,
                    original_type,
                    width,
                    height,
                    status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                upload_id,
                page_number,
                str(output_path),
                "IMAGE",
                width,
                height,
                "NORMALIZED"
            ))

        conn.commit()
        conn.close()

        set_upload_status(
            upload_id,
            "NORMALIZED"
        )

        return {
            "upload_id": upload_id,
            "source_type": "IMAGES",
            "page_count": len(image_files),
            "status": "NORMALIZED"
        }

    except Exception:

        set_upload_status(
            upload_id,
            "PROCESSING_FAILED"
        )

        raise


if __name__ == "__main__":
    create_normalization_tables()
    print("Examora Source Normalizer is ready.")
