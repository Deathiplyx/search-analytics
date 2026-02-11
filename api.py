from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime
import numpy as np
import pickle

from sentence_transformers import SentenceTransformer

app = Flask(__name__)
CORS(app)

DB = "search_data.db"
SIM_THRESHOLD = 0.75
RELATED_LIMIT = 5

model = SentenceTransformer("all-MiniLM-L6-v2")


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

    cur.execute("""
        CREATE TABLE IF NOT EXISTS topics (
            topic TEXT PRIMARY KEY,
            embedding BLOB
        )
    """)

    conn.commit()
    conn.close()


init_db()


def get_embedding(text):
    emb = model.encode(text)
    return emb


def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def find_or_create_topic(term):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    emb = get_embedding(term)

    cur.execute("SELECT topic, embedding FROM topics")
    rows = cur.fetchall()

    best_topic = None
    best_score = 0

    for topic, blob in rows:
        topic_emb = pickle.loads(blob)
        score = cosine_similarity(emb, topic_emb)

        if score > best_score:
            best_score = score
            best_topic = topic

    if best_topic and best_score >= SIM_THRESHOLD:
        conn.close()
        return best_topic

    cur.execute(
        "INSERT INTO topics (topic, embedding) VALUES (?, ?)",
        (term, pickle.dumps(emb))
    )
    conn.commit()
    conn.close()

    return term

def record_search(term):
    topic = find_or_create_topic(term)

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
    return "Search analytics API running"


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
        "topic": topic,
        "count": stats["count"],
        "last_searched": stats["last_searched"],
        "total_searches": stats["total_searches"],
        "related_terms": stats["related_terms"],
        "message": message
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
