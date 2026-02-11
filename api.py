from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime
import re

app = Flask(__name__)
CORS(app)

DB = "search_data.db"
RELATED_LIMIT = 5
GENERAL_PROMOTION_THRESHOLD = 5  # auto-create topic after this many similar "general" searches


# =====================================================
# Keyword Topics (negative / "You Aren’t Alone" focus)
# =====================================================

TOPIC_KEYWORDS = {

    # Loss
    "grief / loss": [
        "passed away", "lost someone", "someone died",
        "death in the family", "funeral", "grieving", "mourning"
    ],

    # Loneliness
    "loneliness / isolation": [
        "lonely", "alone", "no friends", "isolated",
        "nobody cares", "no one cares",
        "ignored", "left out"
    ],

    # Relationships
    "relationship conflict": [
        "breakup", "broke up", "divorce",
        "toxic relationship", "cheated",
        "relationship problems", "argument", "fight"
    ],

    "family problems": [
        "family issues", "toxic family",
        "parents fighting", "family conflict"
    ],

    # Mental health
    "depression / sadness": [
        "depressed", "hopeless", "empty",
        "numb", "nothing matters"
    ],

    "anxiety / panic": [
        "anxiety", "panic attack", "overthinking",
        "constantly worried"
    ],

    "stress / overwhelmed": [
        "overwhelmed", "too much", "cant handle",
        "under pressure"
    ],

    "burnout / exhaustion": [
        "burnt out", "burned out", "exhausted",
        "no energy", "drained"
    ],

    "low self-worth": [
        "worthless", "hate myself", "not good enough",
        "useless", "im a failure"
    ],

    # Addiction
    "substance addiction": [
        "alcohol problem", "drinking too much",
        "drug problem", "relapsed", "cant stay sober"
    ],

    "gaming addiction": [
        "video game addiction", "gaming too much",
        "cant stop gaming"
    ],

    "social media / phone addiction": [
        "doomscrolling", "phone addiction",
        "social media addiction", "scrolling all day"
    ],

    "ai overuse": [
        "ai addiction", "chatgpt all day",
        "cant stop using ai"
    ],

    # Sleep
    "sleep problems": [
        "cant sleep", "insomnia",
        "awake all night", "sleep schedule ruined"
    ],

    # Work / school
    "job stress": [
        "hate my job", "job stress",
        "boss is terrible", "burnout at work"
    ],

    "unemployment": [
        "lost my job", "unemployed",
        "cant find a job"
    ],

    "school stress": [
        "failing class", "exam anxiety",
        "school stress", "college stress"
    ],

    # Money
    "financial problems": [
        "money problems", "broke",
        "debt", "cant pay bills"
    ],

    # Life direction
    "life direction / feeling lost": [
        "no purpose", "feel lost",
        "directionless", "life is going nowhere"
    ]
}


# =====================================================
# Text normalization
# =====================================================

def normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def phrase_match(text, phrase):
    pattern = r"\b" + re.escape(phrase) + r"\b"
    return re.search(pattern, text) is not None


# =====================================================
# Topic classification
# =====================================================

def classify_topic(term: str) -> str:
    text = normalize(term)

    best_topic = None
    best_score = 0

    for topic, keywords in TOPIC_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if phrase_match(text, kw):
                score += len(kw)

        if score > best_score:
            best_score = score
            best_topic = topic

    # Require minimum strength
    if best_score >= 6:
        return best_topic

    return "general distress"


# =====================================================
# Database
# =====================================================

def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term TEXT,
            topic TEXT,
            timestamp TEXT
        )
    """)

    conn.commit()
    conn.close()


init_db()


# =====================================================
# Auto-learning for unknown topics
# =====================================================

def maybe_promote_general(term):
    """
    If many similar 'general distress' searches occur,
    create a new topic automatically.
    """
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*)
        FROM searches
        WHERE topic = 'general distress'
        AND term LIKE ?
    """, (f"%{term[:10]}%",))

    count = cur.fetchone()[0]

    if count >= GENERAL_PROMOTION_THRESHOLD:
        topic_name = term[:40]
        cur.execute("""
            UPDATE searches
            SET topic = ?
            WHERE topic = 'general distress'
            AND term LIKE ?
        """, (topic_name, f"%{term[:10]}%"))
        conn.commit()
        conn.close()
        return topic_name

    conn.close()
    return "general distress"


# =====================================================
# Core logic
# =====================================================

def record_search(term):
    topic = classify_topic(term)

    if topic == "general distress":
        topic = maybe_promote_general(term)

    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO searches (term, topic, timestamp) VALUES (?, ?, ?)",
        (term, topic, datetime.utcnow().isoformat())
    )

    conn.commit()
    conn.close()

    return topic


def get_stats(topic):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM searches WHERE topic = ?", (topic,))
    count = cur.fetchone()[0]

    cur.execute(
        "SELECT timestamp FROM searches WHERE topic = ? ORDER BY id DESC LIMIT 1",
        (topic,)
    )
    row = cur.fetchone()
    last = row[0] if row else None

    cur.execute("SELECT COUNT(*) FROM searches")
    total_all = cur.fetchone()[0]

    cur.execute(
        """
        SELECT term, COUNT(*) as c
        FROM searches
        WHERE topic = ?
        GROUP BY term
        ORDER BY c DESC
        LIMIT ?
        """,
        (topic, RELATED_LIMIT)
    )
    related = [r[0] for r in cur.fetchall()]

    conn.close()

    return {
        "topic": topic,
        "count": count,
        "last_searched": last,
        "total_searches": total_all,
        "related_terms": related
    }


# =====================================================
# Routes
# =====================================================

@app.route("/")
def home():
    return "You Aren’t Alone API running"


@app.route("/search")
def search():
    term = request.args.get("q", "").strip()

    if not term:
        return jsonify({"error": "No term"}), 400

    topic = record_search(term)
    stats = get_stats(topic)

    if stats["count"] > 1:
        message = "You’re not the only one feeling this."
    else:
        message = "You’re the first to share this. Others may feel it too."

    return jsonify({
        "term": term,
        "topic": stats["topic"],
        "count": stats["count"],
        "last_searched": stats["last_searched"],
        "total_searches": stats["total_searches"],
        "related_terms": stats["related_terms"],
        "message": message
    })


# =====================================================
# Run
# =====================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
