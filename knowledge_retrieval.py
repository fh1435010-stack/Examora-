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
    "please", "at", "that", "this"
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

def score_chunk(topic, content, keywords):

    topic_lower = topic.lower()

    content_lower = content.lower()

    score = 0


    # -----------------------------------------------------
    # KEYWORD MATCHING
    # -----------------------------------------------------

    for keyword in keywords:

        topic_count = topic_lower.count(keyword)

        content_count = content_lower.count(keyword)


        # Topic matches are more important
        score += topic_count * 20


        # Content matches
        score += content_count * 5


        # Specific words get extra importance
        if len(keyword) >= 6:

            score += topic_count * 10

            score += content_count * 3


    # -----------------------------------------------------
    # PHRASE BONUS
    # -----------------------------------------------------

    important_phrases = [
        "high temperature",
        "optimum temperature",
        "optimum ph",
        "competitive inhibition",
        "non-competitive inhibition",
        "enzyme activity",
        "active site",
        "lock and key",
        "induced fit",
        "enzyme concentration",
        "substrate concentration"
    ]


    question_text = " ".join(keywords)


    for phrase in important_phrases:

        phrase_words = phrase.split()


        if all(
            word in question_text
            for word in phrase_words
        ):

            if phrase in topic_lower:
                score += 100

            if phrase in content_lower:
                score += 50


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
            topic,
            content,
            keywords
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


    for index, item in enumerate(
        results,
        start=1
    ):

        context_parts.append(
            f"""
--- TEXTBOOK KNOWLEDGE {index} ---
TOPIC: {item['topic']}
RETRIEVAL SCORE: {item['score']}

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


    keywords = extract_keywords(question)


    print()

    print(
        "KEYWORDS:",
        keywords
    )


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
