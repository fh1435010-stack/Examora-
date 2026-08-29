import sqlite3
import re


DB_PATH = "examora.db"


# =========================================================
# STOP WORDS
# =========================================================

STOP_WORDS = {
    "what", "is", "are", "the", "a", "an",
    "how", "does", "do", "why", "when",
    "and", "or", "of", "to", "in", "on",
    "for", "with", "from", "by", "about",
    "explain", "describe", "tell", "me",
    "please"
}


# =========================================================
# EXTRACT KEYWORDS
# =========================================================

def extract_keywords(question):

    words = re.findall(
        r"\b[a-zA-Z0-9]+\b",
        question.lower()
    )

    keywords = []

    for word in words:

        if word not in STOP_WORDS and len(word) > 2:
            keywords.append(word)

    return list(dict.fromkeys(keywords))


# =========================================================
# SEARCH KNOWLEDGE
# =========================================================

def search_knowledge(
    question,
    board="FBISE",
    class_name="9th",
    subject="Biology",
    limit=5
):

    keywords = extract_keywords(question)

    if not keywords:
        return []

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    SELECT
        id,
        topic,
        content
    FROM knowledge_chunks
    WHERE board = ?
    AND class_name = ?
    AND subject = ?
    AND status = 'APPROVED'
    """, (
        board,
        class_name,
        subject
    ))

    rows = cursor.fetchall()

    conn.close()

    scored_results = []

    for chunk_id, topic, content in rows:

        text = (
            topic + " " + content
        ).lower()

        score = 0

        for keyword in keywords:

            score += text.count(keyword)

        if score > 0:

            scored_results.append({
                "id": chunk_id,
                "topic": topic,
                "content": content,
                "score": score
            })

    scored_results.sort(
        key=lambda item: item["score"],
        reverse=True
    )

    return scored_results[:limit]


# =========================================================
# BUILD AI CONTEXT
# =========================================================

def get_knowledge_context(
    question,
    board="FBISE",
    class_name="9th",
    subject="Biology",
    limit=5
):

    results = search_knowledge(
        question=question,
        board=board,
        class_name=class_name,
        subject=subject,
        limit=limit
    )

    if not results:
        return ""

    context_parts = []

    for index, item in enumerate(results, start=1):

        context_parts.append(
            f"""
--- TEXTBOOK KNOWLEDGE {index} ---
TOPIC: {item['topic']}

{item['content']}
"""
        )

    return "\n".join(context_parts)


# =========================================================
# TEST MODE
# =========================================================

if __name__ == "__main__":

    question = input(
        "Ask a Biology question: "
    ).strip()

    results = search_knowledge(question)

    print()
    print("=" * 70)
    print("RETRIEVED KNOWLEDGE")
    print("=" * 70)

    print()

    for item in results:

        print(
            "ID:",
            item["id"]
        )

        print(
            "TOPIC:",
            item["topic"]
        )

        print(
            "SCORE:",
            item["score"]
        )

        print(
            "CONTENT:"
        )

        print(
            item["content"][:700]
        )

        print("-" * 70)
