from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

DB = "search_data.db"

def init_db():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS searches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term TEXT,
            timestamp TEXT
        )
    """)

    conn.commit()
    conn.close()


init_db()


def record_search(term):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    cur.execute(
        "INSERT INTO searches (term, timestamp) VALUES (?, ?)",
        (term, datetime.utcnow().isoformat())
    )

    conn.commit()
    conn.close()


def get_stats(term):
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # total count for this term
    cur.execute("SELECT COUNT(*) FROM searches WHERE term = ?", (term,))
    count = cur.fetchone()[0]

    # last searched
    cur.execute(
        "SELECT timestamp FROM searches WHERE term = ? ORDER BY id DESC LIMIT 1",
        (term,)
    )
    row = cur.fetchone()
    last = row[0] if row else None

    # total searches overall
    cur.execute("SELECT COUNT(*) FROM searches")
    total_all = cur.fetchone()[0]

    conn.close()

    return {
        "term": term,
        "count": count,
        "last_searched": last,
        "total_searches": total_all
    }

@app.route("/")
def home():
    return "Search analytics API running"


@app.route("/search")
def search():
    term = request.args.get("q", "").strip().lower()

    if not term:
        return jsonify({"error": "No term"}), 400

    record_search(term)
    stats = get_stats(term)

    return jsonify(stats)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
