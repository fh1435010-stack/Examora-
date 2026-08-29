import sqlite3
import re

DB_PATH = "examora.db"
MAX_CHUNK_SIZE = 900
MIN_CHUNK_SIZE = 120

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# ---------------------------------------------------------
# CREATE ONE TRUSTED SOURCE FOR THIS IMPORT
# ---------------------------------------------------------

cursor.execute("""
SELECT id
FROM knowledge_sources
WHERE title = ?
  AND source_type = ?
LIMIT 1
""", (
    "Examora Imported Textbook Knowledge",
    "BOOK"
))

row = cursor.fetchone()

if row:
    source_id = row[0]
    print("USING EXISTING SOURCE ID:", source_id)
else:
    cursor.execute("""
    INSERT INTO knowledge_sources
    (
        title,
        source_type,
        trust_level,
        status,
        added_by
    )
    VALUES (?, ?, ?, ?, ?)
    """, (
        "Examora Imported Textbook Knowledge",
        "BOOK",
        "TRUSTED",
        "APPROVED",
        "Examora System"
    ))

    source_id = cursor.lastrowid
    print("CREATED SOURCE ID:", source_id)


# ---------------------------------------------------------
# REMOVE OLD CHUNKS FROM THIS IMPORT SOURCE
# ---------------------------------------------------------

cursor.execute("""
DELETE FROM knowledge_chunks
WHERE source_id = ?
""", (source_id,))

print("OLD CHUNKS REMOVED:", cursor.rowcount)


# ---------------------------------------------------------
# GET CONCEPTS WITH STUDENT CONTEXT
# ---------------------------------------------------------

cursor.execute("""
SELECT
    concepts.id,
    concepts.name,
    concepts.description,
    books.board,
    books.class_name,
    books.subject
FROM concepts
JOIN chapters
    ON concepts.chapter_id = chapters.id
JOIN books
    ON chapters.book_id = books.id
WHERE concepts.description IS NOT NULL
  AND TRIM(concepts.description) != ''
ORDER BY concepts.id
""")

concepts = cursor.fetchall()

print("CONCEPTS FOUND:", len(concepts))


def clean_text(text):
    text = text.replace("\r", "\n")
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{2,}', '\n', text)
    return text.strip()


def split_into_chunks(text):
    text = clean_text(text)

    # Split into sentences while keeping the text meaningful
    sentences = re.split(
        r'(?<=[.!?])\s+',
        text
    )

    chunks = []
    current = ""

    for sentence in sentences:
        sentence = sentence.strip()

        if not sentence:
            continue

        # If one sentence is unusually long, keep it as-is
        if (
            current
            and len(current) + len(sentence) + 1 > MAX_CHUNK_SIZE
        ):
            if len(current) >= MIN_CHUNK_SIZE:
                chunks.append(current.strip())

            current = sentence
        else:
            if current:
                current += " "

            current += sentence

    if current.strip() and len(current.strip()) >= MIN_CHUNK_SIZE:
        chunks.append(current.strip())

    return chunks


# ---------------------------------------------------------
# BUILD CHUNKS
# ---------------------------------------------------------

total_chunks = 0

for (
    concept_id,
    concept_name,
    concept_description,
    board,
    class_name,
    subject
) in concepts:

    chunks = split_into_chunks(concept_description)

    print()
    print("=" * 60)
    print("CONCEPT:", concept_name)
    print("CHUNKS:", len(chunks))
    print("=" * 60)

    for index, chunk in enumerate(chunks, start=1):

        topic = f"{concept_name} | Part {index}"

        cursor.execute("""
        INSERT INTO knowledge_chunks
        (
            source_id,
            board,
            class_name,
            subject,
            topic,
            content,
            status,
            approved_by
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            source_id,
            board,
            class_name,
            subject,
            topic,
            chunk,
            "APPROVED",
            "Examora System"
        ))

        total_chunks += 1

        print(
            f"CHUNK {index}: "
            f"{len(chunk)} characters"
        )


conn.commit()


# ---------------------------------------------------------
# FINAL CHECK
# ---------------------------------------------------------

cursor.execute("""
SELECT COUNT(*)
FROM knowledge_chunks
WHERE source_id = ?
""", (source_id,))

final_count = cursor.fetchone()[0]

conn.close()

print()
print("=" * 60)
print("SUCCESS: KNOWLEDGE CHUNKS CREATED")
print("SOURCE ID:", source_id)
print("TOTAL CHUNKS CREATED:", total_chunks)
print("DATABASE CHUNKS FOR SOURCE:", final_count)
print("=" * 60)
