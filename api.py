from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

DB = "search_data.db"
RELATED_LIMIT = 5

TOPIC_KEYWORDS = {

    # ---------- Positive ----------
    "achievement / success": [
        "got a job", "promotion", "passed", "graduated", "won",
        "achievement", "accomplished", "succeeded", "made it",
        "finished", "completed", "proud of myself"
    ],

    "happiness / good mood": [
        "happy", "excited", "great day", "feeling good",
        "amazing", "joy", "content", "life is good",
        "good mood", "feeling better"
    ],

    "relief / improvement": [
        "relieved", "finally better", "things improved",
        "getting better", "recovered", "healing", "improving"
    ],

    "relationships (positive)": [
        "made a friend", "new friend", "date went well",
        "engaged", "married", "reconnected", "family time"
    ],

    # ---------- Energy / Health ----------
    "fatigue / burnout": [
        "tired", "exhausted", "burnt", "burned out",
        "no energy", "drained", "fatigue", "sleepy"
    ],

    "physical health": [
        "sick", "ill", "pain", "headache", "doctor",
        "hospital", "injury", "health problem"
    ],

    # ---------- Social ----------
    "loneliness": [
        "lonely", "alone", "no friends", "isolated",
        "nobody", "no one", "left out", "ignored"
    ],

    "relationships (conflict)": [
        "argument", "fight", "breakup", "broke up",
        "divorce", "toxic", "relationship problems",
        "family issues"
    ],

    # ---------- Emotional distress ----------
    "anxiety / worry": [
        "anxious", "anxiety", "worried", "panic",
        "overthinking", "fear", "scared", "nervous"
    ],

    "stress / overwhelmed": [
        "stressed", "overwhelmed", "pressure",
        "too much", "cant handle"
    ],

    "sadness / depression": [
        "sad", "depressed", "hopeless", "empty",
        "down", "unhappy", "miserable"
    ],

    "self-esteem / worth": [
        "worthless", "hate myself", "not good enough",
        "failure", "useless"
    ],

    "anger / frustration": [
        "angry", "mad", "frustrated", "annoyed",
        "pissed", "irritated"
    ],

    # ---------- Life situations ----------
    "work / school": [
        "exam", "test", "homework", "school",
        "college", "work", "job", "boss", "deadline"
    ],

    "life changes": [
        "moving", "new city", "new job", "lost my job",
        "big change", "transition", "starting over"
    ]
}


def classify_topic(term: str) -> str:
    text = term.lower()

    best_topic = None
    best_score = 0

    for topic, keywords in TOPIC_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in text:
                score += len(kw)  # longer phrase = stronger match

        if score > best_score:
            best_score = score
            best_topic = topic

    if best_topic:
        return best_topic

    return "general"


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

def record_search(term):
    topic = classify_topic(term)

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


@app.route("/")
def home():
    return "Search analytics API running (lightweight)"


@app.route("/search")
def search():
    term = request.args.get("q", "").strip().lower()

    if not term:
        return jsonify({"error": "No term"}), 400

    topic = record_search(term)
    stats = get_stats(topic)

    if stats["count"] > 1:
        message = "You’re not the only one searching this."
    else:
        message = "You’re the first to search this. Others may feel the same soon."

    return jsonify({
        "term": term,
        "topic": stats["topic"],
        "count": stats["count"],
        "last_searched": stats["last_searched"],
        "total_searches": stats["total_searches"],
        "related_terms": stats["related_terms"],
        "message": message
    })



if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
