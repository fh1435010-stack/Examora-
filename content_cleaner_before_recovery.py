import re
import sqlite3


DATABASE = "examora.db"


def get_connection():

    conn = sqlite3.connect(DATABASE)

    conn.row_factory = sqlite3.Row

    return conn


def create_cleaned_content_table():

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cleaned_page_content (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            upload_id INTEGER NOT NULL,

            source_page_id INTEGER NOT NULL,

            page_number INTEGER NOT NULL,

            original_text TEXT,

            cleaned_text TEXT,

            original_characters INTEGER NOT NULL DEFAULT 0,

            cleaned_characters INTEGER NOT NULL DEFAULT 0,

            cleaning_status TEXT NOT NULL,

            quality_status TEXT NOT NULL,

            suspicious_patterns TEXT,

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
        idx_cleaned_page_content_unique

        ON cleaned_page_content(
            upload_id,
            source_page_id
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_cleaned_page_content_upload_page

        ON cleaned_page_content(
            upload_id,
            page_number
        )
    """)

    conn.commit()
    conn.close()


def get_verified_pages(upload_id):

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            upload_id,
            source_page_id,
            page_number,
            verified_text,
            verification_status
        FROM verified_page_content
        WHERE upload_id=?
        ORDER BY page_number
    """, (upload_id,))

    pages = cursor.fetchall()

    conn.close()

    return pages


def normalize_newlines(text):

    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    return text


def remove_control_characters(text):

    cleaned = []

    for character in text:

        if character == "\n":

            cleaned.append(character)

            continue

        if character == "\t":

            cleaned.append(" ")

            continue

        if ord(character) >= 32:

            cleaned.append(character)

    return "".join(cleaned)


def clean_spaces(text):

    text = re.sub(
        r"[ \t]{2,}",
        " ",
        text
    )

    text = re.sub(
        r" *\n *",
        "\n",
        text
    )

    return text


def clean_ocr_noise(text):

    text = text.replace("\u00a0", " ")

    text = re.sub(
        r"[|]{4,}",
        "",
        text
    )

    text = re.sub(
        r"[-_]{6,}",
        "",
        text
    )

    return text


def repair_line_breaks(text):

    lines = text.split("\n")

    repaired_lines = []

    for line in lines:

        line = line.strip()

        if not line:

            repaired_lines.append("")

            continue

        repaired_lines.append(line)

    return "\n".join(repaired_lines)


def find_suspicious_patterns(text):

    suspicious = []

    strange_symbol_matches = re.findall(
        r"[^\w\s.,;:!?()\[\]{}+\-*/=<>%°²³×÷'\"\\]",
        text
    )

    if len(strange_symbol_matches) > 10:

        suspicious.append(
            "MANY_UNUSUAL_SYMBOLS"
        )

    single_letter_lines = re.findall(
        r"(?m)^[A-Za-z]$",
        text
    )

    if len(single_letter_lines) > 10:

        suspicious.append(
            "MANY_SINGLE_LETTER_LINES"
        )

    broken_word_patterns = re.findall(
        r"\b[A-Za-z]{1,2}[^\w\s][A-Za-z]{1,2}\b",
        text
    )

    if len(broken_word_patterns) > 10:

        suspicious.append(
            "POSSIBLE_BROKEN_WORDS"
        )

    return suspicious


def determine_quality_status(
    cleaned_text,
    suspicious_patterns
):

    characters = len(
        cleaned_text.strip()
    )

    if characters == 0:

        return "NO_CONTENT"

    if characters < 50:

        return "VERY_LOW_TEXT"

    if len(suspicious_patterns) >= 2:

        return "NEEDS_REVIEW"

    if suspicious_patterns:

        return "MINOR_REVIEW"

    return "CLEAN"


def clean_text(text):

    original_text = text or ""

    cleaned_text = original_text

    cleaned_text = remove_control_characters(
        cleaned_text
    )

    cleaned_text = normalize_newlines(
        cleaned_text
    )

    cleaned_text = clean_ocr_noise(
        cleaned_text
    )

    cleaned_text = clean_spaces(
        cleaned_text
    )

    cleaned_text = repair_line_breaks(
        cleaned_text
    )

    cleaned_text = cleaned_text.strip()

    suspicious_patterns = find_suspicious_patterns(
        cleaned_text
    )

    quality_status = determine_quality_status(
        cleaned_text,
        suspicious_patterns
    )

    return {
        "original_text": original_text,
        "cleaned_text": cleaned_text,
        "suspicious_patterns": suspicious_patterns,
        "quality_status": quality_status
    }


def save_cleaned_content(
    upload_id,
    source_page_id,
    page_number,
    original_text,
    cleaned_text,
    quality_status,
    suspicious_patterns
):

    conn = get_connection()
    cursor = conn.cursor()

    suspicious_text = ",".join(
        suspicious_patterns
    )

    cursor.execute("""
        INSERT INTO cleaned_page_content (

            upload_id,
            source_page_id,
            page_number,

            original_text,
            cleaned_text,

            original_characters,
            cleaned_characters,

            cleaning_status,
            quality_status,

            suspicious_patterns,

            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)

        ON CONFLICT(upload_id, source_page_id)

        DO UPDATE SET

            original_text=excluded.original_text,
            cleaned_text=excluded.cleaned_text,

            original_characters=
                excluded.original_characters,

            cleaned_characters=
                excluded.cleaned_characters,

            cleaning_status=
                excluded.cleaning_status,

            quality_status=
                excluded.quality_status,

            suspicious_patterns=
                excluded.suspicious_patterns,

            updated_at=CURRENT_TIMESTAMP
    """, (

        upload_id,
        source_page_id,
        page_number,

        original_text,
        cleaned_text,

        len(original_text),
        len(cleaned_text),

        "CLEANED",
        quality_status,

        suspicious_text
    ))

    conn.commit()
    conn.close()


def build_cleaned_content(upload_id):

    create_cleaned_content_table()

    pages = get_verified_pages(
        upload_id
    )

    if not pages:

        raise ValueError(
            f"No verified pages found "
            f"for Upload ID {upload_id}."
        )

    print()
    print(
        "Examora Content Cleaning Engine "
        f"started for Upload ID {upload_id}"
    )

    print(
        f"Pages to clean: {len(pages)}"
    )

    quality_summary = {}

    for page in pages:

        source_page_id = page[
            "source_page_id"
        ]

        page_number = page[
            "page_number"
        ]

        verified_text = page[
            "verified_text"
        ] or ""

        result = clean_text(
            verified_text
        )

        save_cleaned_content(

            upload_id=upload_id,

            source_page_id=
                source_page_id,

            page_number=
                page_number,

            original_text=
                result["original_text"],

            cleaned_text=
                result["cleaned_text"],

            quality_status=
                result["quality_status"],

            suspicious_patterns=
                result["suspicious_patterns"]
        )

        quality_status = result[
            "quality_status"
        ]

        quality_summary[
            quality_status
        ] = (

            quality_summary.get(
                quality_status,
                0
            )
            + 1
        )

        print(
            f"Page {page_number} cleaned "
            f"| quality: {quality_status} "
            f"| characters: "
            f"{len(result['cleaned_text'])}"
        )

    print()
    print(
        "Examora Content Cleaning Engine "
        "completed."
    )

    return {

        "upload_id":
            upload_id,

        "pages_processed":
            len(pages),

        "quality_summary":
            quality_summary,

        "status":
            "CLEANED_CONTENT_READY"
    }


if __name__ == "__main__":

    create_cleaned_content_table()

    print(
        "Examora Content Cleaning Engine "
        "is ready."
    )
