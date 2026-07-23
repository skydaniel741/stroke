"""AfterCall — after-hours AI receptionist for NZ trades. Prototype."""
import datetime
import os
import sqlite3
import uuid

from flask import Flask, g, jsonify, render_template, request

import ai

DB = os.path.join(os.path.dirname(__file__), "aftercall.db")
app = Flask(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    session_id TEXT PRIMARY KEY,
    ts TEXT,
    name TEXT,
    phone TEXT,
    address TEXT,
    job_type TEXT,
    urgency TEXT,
    summary TEXT,
    est_value_nzd INTEGER,
    escalated INTEGER DEFAULT 0,
    turns INTEGER DEFAULT 0
);
"""


def db():
    conn = getattr(g, "_db", None)
    if conn is None:
        conn = g._db = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        conn.executescript(SCHEMA)
    return conn


@app.teardown_appcontext
def close_db(_exc):
    conn = getattr(g, "_db", None)
    if conn is not None:
        conn.close()


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/demo")
def demo():
    return render_template("demo.html", session_id=uuid.uuid4().hex[:12])


@app.route("/dashboard")
def dashboard():
    rows = [dict(r) for r in db().execute(
        "SELECT * FROM leads WHERE summary IS NOT NULL ORDER BY ts DESC LIMIT 50"
    ).fetchall()]
    total = sum(r["est_value_nzd"] or 0 for r in rows)
    return render_template("dashboard.html", leads=rows, total=total)


@app.route("/api/chat", methods=["POST"])
def chat():
    d = request.get_json()
    messages = d.get("messages", [])
    session_id = d.get("session_id", "anon")
    if not messages or len(messages) > 40:
        return jsonify({"error": "Bad conversation state."}), 400
    try:
        result = ai.respond(messages)
    except Exception as e:
        return jsonify({"error": f"Agent error: {e}"}), 502

    lead = result.get("lead") or {}
    db().execute(
        "INSERT INTO leads (session_id, ts, name, phone, address, job_type, urgency, "
        "summary, est_value_nzd, escalated, turns) VALUES (?,?,?,?,?,?,?,?,?,?,1) "
        "ON CONFLICT(session_id) DO UPDATE SET name=excluded.name, "
        "phone=excluded.phone, address=excluded.address, job_type=excluded.job_type, "
        "urgency=excluded.urgency, summary=excluded.summary, "
        "est_value_nzd=excluded.est_value_nzd, "
        "escalated=MAX(escalated, excluded.escalated), turns=turns+1",
        (session_id, datetime.datetime.now().strftime("%d %b %H:%M"),
         lead.get("name"), lead.get("phone"), lead.get("address"),
         lead.get("job_type"), lead.get("urgency"), lead.get("summary"),
         lead.get("est_value_nzd"), 1 if result.get("escalate") else 0),
    )
    db().commit()
    return jsonify(result)


if __name__ == "__main__":
    app.run(port=5098, debug=False)
