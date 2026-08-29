from pypdf import PdfReader
import sqlite3
import re
import os


# =========================================================
# EXAMORA PDF → KNOWLEDGE DATABASE IMPORTER
# =========================================================


PDF_PATH = "Chapter_6_Complete_Enzymes.pdf"

BOOK_NAME = "Biology Textbook"

BOARD = "FBISE"

CLASS_NAME = "9th"

GROUP_NAME = "Science Biology"

SUBJECT = "Biology"

CHAPTER_NUMBER = "6"

CHAPTER_NAME = "Enzymes"

SOURCE_NAME = "Chapter_6_Complete_Enzymes.pdf"


# =========================================================
# CHECK PDF
# =========================================================

if not os.path.exists(PDF_PATH):
    raise FileNotFoundError(
        f"PDF not found: {PDF_PATH}"
    )


# =========================================================
# READ PDF
# =========================================================

reader = PdfReader(PDF_PATH)

print(
    "TOTAL PDF PAGES:",
    len(reader.pages)
)


# =========================================================
# DATABASE
# =========================================================

conn = sqlite3.connect("examora.db")

cursor = conn.cursor()


# =========================================================
# REMOVE OLD IMPORT OF THIS SAME CHAPTER
# =========================================================

cursor.execute("""
DELETE FROM book_knowledge
WHERE board = ?
AND class_name = ?
AND group_name = ?
AND subject = ?
AND chapter_number = ?
AND source = ?
""", (
    BOARD,
    CLASS_NAME,
    GROUP_NAME,
    SUBJECT,
    CHAPTER_NUMBER,
    SOURCE_NAME
))

deleted = cursor.rowcount

print(
    "OLD RECORDS REMOVED:",
    deleted
)


# =========================================================
# SECTION HEADING DETECTION
# Example:
# 6.1 UNDERSTANDING METABOLISM
# 6.2 INTRODUCTION TO ENZYMES
# =========================================================

section_pattern = re.compile(
    r"(?m)^("
    + re.escape(CHAPTER_NUMBER)
    + r"\.\d+)\s+([A-Z][A-Z &\-]+)$"
)


records_inserted = 0

current_section_number = None

current_section_title = None

current_section_text = ""

current_start_page = None


def save_section(
    section_number,
    section_title,
    section_text,
    start_page,
    end_page
):
    global records_inserted

    if not section_text.strip():
        return

    clean_text = section_text.strip()

    if len(clean_text) < 80:
        return

    title = (
        f"{section_number} {section_title}"
        if section_number and section_title
        else CHAPTER_NAME
    )

    cursor.execute("""
    INSERT INTO book_knowledge
    (
        book_name,
        board,
        class_name,
        group_name,
        subject,
        chapter_number,
        chapter_name,
        section_number,
        section_title,
        title,
        content,
        page_start,
        page_end,
        source
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        BOOK_NAME,
        BOARD,
        CLASS_NAME,
        GROUP_NAME,
        SUBJECT,
        CHAPTER_NUMBER,
        CHAPTER_NAME,
        section_number,
        section_title,
        title,
        clean_text,
        start_page,
        end_page,
        SOURCE_NAME
    ))

    records_inserted += 1

    print()
    print(
        "IMPORTED SECTION:",
        title
    )

    print(
        "PAGES:",
        start_page,
        "-",
        end_page
    )

    print(
        "CHARACTERS:",
        len(clean_text)
    )


# =========================================================
# PROCESS EACH PAGE
# =========================================================

for page_index, page in enumerate(reader.pages):

    page_number = page_index + 1

    text = page.extract_text() or ""

    text = text.replace(
        "\r",
        "\n"
    )

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    matches = list(
        section_pattern.finditer(text)
    )


    # -----------------------------------------------------
    # NO NEW SECTION ON THIS PAGE
    # -----------------------------------------------------

    if not matches:

        if current_section_number is None:

            current_section_number = (
                CHAPTER_NUMBER + ".0"
            )

            current_section_title = (
                CHAPTER_NAME
            )

            current_start_page = (
                page_number
            )

        current_section_text += (
            "\n\n" + text
        )

        continue


    # -----------------------------------------------------
    # PROCESS EACH SECTION FOUND
    # -----------------------------------------------------

    for match_index, match in enumerate(matches):

        new_section_number = (
            match.group(1)
        )

        new_section_title = (
            match.group(2)
            .strip()
            .title()
        )

        text_before_heading = (
            text[
                0:match.start()
            ]
            if match_index == 0
            else
            text[
                matches[
                    match_index - 1
                ].end():
                match.start()
            ]
        )


        # -------------------------------------------------
        # SAVE PREVIOUS SECTION
        # -------------------------------------------------

        if current_section_number:

            current_section_text += (
                "\n\n" + text_before_heading
            )

            save_section(
                current_section_number,
                current_section_title,
                current_section_text,
                current_start_page,
                page_number
            )


        # -------------------------------------------------
        # START NEW SECTION
        # -------------------------------------------------

        current_section_number = (
            new_section_number
        )

        current_section_title = (
            new_section_title
        )

        current_start_page = (
            page_number
        )

        next_position = (
            matches[
                match_index + 1
            ].start()
            if match_index + 1 < len(matches)
            else len(text)
        )

        current_section_text = (
            text[
                match.end():
                next_position
            ]
        )


# =========================================================
# SAVE FINAL SECTION
# =========================================================

if current_section_number:

    save_section(
        current_section_number,
        current_section_title,
        current_section_text,
        current_start_page,
        len(reader.pages)
    )


# =========================================================
# COMMIT
# =========================================================

conn.commit()

conn.close()


print()
print("=" * 60)

print(
    "SUCCESS: PDF IMPORT COMPLETED"
)

print(
    "TOTAL SECTIONS IMPORTED:",
    records_inserted
)

print(
    "CHAPTER:",
    f"{CHAPTER_NUMBER} {CHAPTER_NAME}"
)

print("=" * 60)
