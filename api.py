from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import datetime
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

DB = "analytics.db"
SIMILARITY_THRESHOLD = 0.75

app = Flask(name)
CORS(app)

print("Loading embedding model...")
model = SentenceTransformer("all-MiniLM-L6-v2")
print("Model loaded")

def init_db():
conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    label TEXT,
    embedding BLOB,
    count INTEGER,
    last_seen TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS searches (
    id INTEGER PRIMARY KEY,
    query TEXT,
    topic_id INTEGER,
    timestamp TEXT
)
""")

conn.commit()
conn.close()


init_db()

def embed(text):
vec = model.encode([text])[0]
return vec.astype(np.float32)

def serialize(vec):
return vec.tobytes()

def deserialize(blob):
return np.frombuffer(blob, dtype=np.float32)

def find_matching_topic(query_vec, conn):
cur = conn.cursor()
cur.execute("SELECT id, embedding FROM topics")

best_id = None
best_score = 0

for topic_id, blob in cur.fetchall():
    topic_vec = deserialize(blob)
    score = cosine_similarity([query_vec], [topic_vec])[0][0]

    if score > best_score:
        best_score = score
        best_id = topic_id

if best_score >= SIMILARITY_THRESHOLD:
    return best_id

return None

@app.route("/log")
def log_search():
query = request.args.get("q", "").strip().lower()
if not query:
return jsonify({"error": "no query"}), 400

now = datetime.datetime.utcnow().isoformat()

conn = sqlite3.connect(DB)
cur = conn.cursor()

vec = embed(query)

topic_id = find_matching_topic(vec, conn)

if topic_id:
    # update existing topic
    cur.execute("""
        UPDATE topics
        SET count = count + 1,
            last_seen = ?
        WHERE id = ?
    """, (now, topic_id))
else:
    # create new topic
    cur.execute("""
        INSERT INTO topics (label, embedding, count, last_seen)
        VALUES (?, ?, ?, ?)
    """, (query, serialize(vec), 1, now))
    topic_id = cur.lastrowid

# store raw search
cur.execute("""
    INSERT INTO searches (query, topic_id, timestamp)
    VALUES (?, ?, ?)
""", (query, topic_id, now))

conn.commit()
conn.close()

return jsonify({
    "query": query,
    "topic_id": topic_id
})

@app.route("/stats")
def stats():
conn = sqlite3.connect(DB)
cur = conn.cursor()

cur.execute("""
    SELECT label, count, last_seen
    FROM topics
    ORDER BY count DESC
    LIMIT 20
""")

topics = []
for label, count, last_seen in cur.fetchall():
    topics.append({
        "topic": label,
        "count": count,
        "last_seen": last_seen
    })

conn.close()

return jsonify({
    "top_topics": topics
})

@app.route("/")
def home():
return "Search analytics API running"

if name == "main":
app.run(host="0.0.0.0", port=10000)
