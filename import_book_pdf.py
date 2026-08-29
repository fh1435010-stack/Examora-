from pypdf import PdfReader
import sqlite3
import re
import os


# =========================================================
# EXAMORA PDF -> REAL KNOWLEDGE DATABASE IMPORTER
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

print("TOTAL PDF PAGES:", len(reader.pages))


# =========================================================
# DATABASE
# =========================================================

conn = sqlite3.connect("examora.db")
cursor = conn.cursor()


# =========================================================
# REMOVE OLD IMPORT OF THIS SAME BOOK
# =========================================================

cursor.execute("""
SELECT id
FROM books
WHERE board = ?
AND class_name = ?
AND group_name = ?
AND subject = ?
AND title = ?
AND source_file = ?
""", (
    BOARD,
    CLASS_NAME,
    GROUP_NAME,
    SUBJECT,
    BOOK_NAME,
    SOURCE_NAME
))

old_book = cursor.fetchone()

if old_book:

    old_book_id = old_book[0]

    cursor.execute("""
    SELECT id FROM chapters
    WHERE book_id = ?
    """, (old_book_id,))

    old_chapter_ids = [
        row[0] for row in cursor.fetchall()
    ]

    for chapter_id in old_chapter_ids:

        cursor.execute("""
        DELETE FROM concepts
        WHERE chapter_id = ?
        """, (chapter_id,))

        cursor.execute("""
        DELETE FROM figures
        WHERE chapter_id = ?
        """, (chapter_id,))

    cursor.execute("""
    DELETE FROM chapters
    WHERE book_id = ?
    """, (old_book_id,))

    cursor.execute("""
    DELETE FROM books
    WHERE id = ?
    """, (old_book_id,))

    print("OLD BOOK IMPORT REMOVED:", old_book_id)


# =========================================================
# INSERT BOOK
# =========================================================

cursor.execute("""
INSERT INTO books
(
    board,
    class_name,
    group_name,
    subject,
    title,
    source_file
)
VALUES (?, ?, ?, ?, ?, ?)
""", (
    BOARD,
    CLASS_NAME,
    GROUP_NAME,
    SUBJECT,
    BOOK_NAME,
    SOURCE_NAME
))

book_id = cursor.lastrowid

print("BOOK CREATED:", book_id)


# =========================================================
# INSERT CHAPTER
# =========================================================

cursor.execute("""
INSERT INTO chapters
(
    book_id,
    chapter_number,
    title,
    source_page_start,
    source_page_end
)
VALUES (?, ?, ?, ?, ?)
""", (
    book_id,
    CHAPTER_NUMBER,
    CHAPTER_NAME,
    1,
    len(reader.pages)
))

chapter_id = cursor.lastrowid

print("CHAPTER CREATED:", chapter_id)


# =========================================================
# SECTION DETECTION
# Example:
# 6.1 UNDERSTANDING METABOLISM
# 6.2 INTRODUCTION TO ENZYMES
# =========================================================

section_pattern = re.compile(
    r"(?m)^("
    + re.escape(CHAPTER_NUMBER)
    + r"\.\d+)\s+([A-Z][A-Z &\-]+)$"
)


current_section_number = None
current_section_title = None
current_section_text = ""
current_start_page = None

concepts_inserted = 0


# =========================================================
# SAVE CONCEPT
# =========================================================

def save_concept(
    section_number,
    section_title,
    section_text
):
    global concepts_inserted

    clean_text = section_text.strip()

    if len(clean_text) < 80:
        return

    concept_name = (
        f"{section_number} {section_title}"
        if section_number and section_title
        else CHAPTER_NAME
    )

    words = re.findall(
        r"[A-Za-z0-9']+",
        clean_text.lower()
    )

    keywords = []

    for word in words:
        if len(word) > 4 and word not in keywords:
            keywords.append(word)

        if len(keywords) >= 30:
            break

    cursor.execute("""
    INSERT INTO concepts
    (
        chapter_id,
        name,
        description,
        keywords
    )
    VALUES (?, ?, ?, ?)
    """, (
        chapter_id,
        concept_name,
        clean_text,
        ", ".join(keywords)
    ))

    concepts_inserted += 1

    print(
        "CONCEPT IMPORTED:",
        concept_name
    )


# =========================================================
# PROCESS EACH PDF PAGE
# =========================================================

for page_index, page in enumerate(reader.pages):

    page_number = page_index + 1

    text = page.extract_text() or ""

    text = text.replace("\r", "\n")

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    matches = list(
        section_pattern.finditer(text)
    )


    # -----------------------------------------------------
    # NO NEW SECTION
    # -----------------------------------------------------

    if not matches:

        if current_section_number is None:

            current_section_number = (
                CHAPTER_NUMBER + ".0"
            )

            current_section_title = CHAPTER_NAME

            current_start_page = page_number

        current_section_text += (
            "\n\n" + text
        )

        continue


    # -----------------------------------------------------
    # PROCESS NEW SECTIONS
    # -----------------------------------------------------

    for match_index, match in enumerate(matches):

        text_before_heading = (
            text[0:match.start()]
            if match_index == 0
            else text[
                matches[match_index - 1].end():
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

            save_concept(
                current_section_number,
                current_section_title,
                current_section_text
            )


        # -------------------------------------------------
        # START NEW SECTION
        # -------------------------------------------------

        current_section_number = match.group(1)

        current_section_title = (
            match.group(2)
            .strip()
            .title()
        )

        current_start_page = page_number

        next_position = (
            matches[match_index + 1].start()
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

    save_concept(
        current_section_number,
        current_section_title,
        current_section_text
    )


# =========================================================
# COMMIT
# =========================================================

conn.commit()
conn.close()


print()
print("=" * 60)
print("SUCCESS: REAL PDF IMPORT COMPLETED")
print("BOOK ID:", book_id)
print("CHAPTER ID:", chapter_id)
print("TOTAL CONCEPTS IMPORTED:", concepts_inserted)
print("CHAPTER:", f"{CHAPTER_NUMBER} {CHAPTER_NAME}")
print("=" * 60)
