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
    "please", "at", "as", "be", "this",
    "that", "it", "its", "their", "can",
    "will", "would", "could"
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

        if (
            word not in STOP_WORDS
            and len(word) > 2
        ):
            keywords.append(word)

    return list(dict.fromkeys(keywords))


# =========================================================
# SCORE ONE CHUNK
# =========================================================

def score_chunk(
    question,
    keywords,
    topic,
    content
):

    question_lower = question.lower()
    topic_lower = topic.lower()
    content_lower = content.lower()

    score = 0


    # -----------------------------------------------------
    # TOPIC MATCHES
    # Topic matches are highly valuable.
    # -----------------------------------------------------

    for keyword in keywords:

        if keyword in topic_lower:
            score += 12


    # -----------------------------------------------------
    # EXACT QUESTION PHRASES
    # -----------------------------------------------------

    important_phrases = [
        "high temperature",
        "low temperature",
        "optimum temperature",
        "optimal temperature",
        "enzyme activity",
        "substrate concentration",
        "enzyme concentration",
        "competitive inhibition",
        "non-competitive inhibition",
        "active site",
        "activation energy",
        "lock and key",
        "induced fit",
        "enzyme substrate complex",
        "optimum ph",
        "optimal ph"
    ]

    for phrase in important_phrases:

        if phrase in question_lower:

            if phrase in topic_lower:
                score += 30

            if phrase in content_lower:
                score += 20


    # -----------------------------------------------------
    # KEYWORD MATCHES
    # -----------------------------------------------------

    for keyword in keywords:

        occurrences = content_lower.count(keyword)

        # Limit the effect of extremely common words
        occurrences = min(
            occurrences,
            5
        )

        score += occurrences * 3


    # -----------------------------------------------------
    # FIRST PART OF CHUNK
    # Important definitions are often near the start.
    # -----------------------------------------------------

    first_part = content_lower[:350]

    for keyword in keywords:

        if keyword in first_part:
            score += 4


    return score


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

        score = score_chunk(
            question,
            keywords,
            topic,
            content
        )

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
    limit=4
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

    for index, item in enumerate(
        results,
        start=1
    ):

        context_parts.append(
            f"""
--- TEXTBOOK KNOWLEDGE {index} ---
TOPIC: {item['topic']}

{item['content'].strip()}
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

    keywords = extract_keywords(question)

    print()
    print("KEYWORDS:", keywords)

    results = search_knowledge(question)

    print()
    print("=" * 70)
    print("RETRIEVED KNOWLEDGE")
    print("=" * 70)

    for item in results:

        print()

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
