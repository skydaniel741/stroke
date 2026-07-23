"""Kept — protein-first companion for GLP-1 users. Prototype."""
import base64
import datetime
import json
import os
import sqlite3

from flask import Flask, g, jsonify, render_template, request

import ai

DB = os.path.join(os.path.dirname(__file__), "kept.db")
app = Flask(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS user (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT,
    weight_kg REAL,
    med TEXT,
    target_g INTEGER,
    shot_date TEXT
);
CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT,
    ts TEXT,
    items_json TEXT,
    protein_g REAL,
    calories REAL,
    gentle INTEGER,
    coach_line TEXT
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


def today():
    return datetime.date.today().isoformat()


def get_user():
    return db().execute("SELECT * FROM user WHERE id = 1").fetchone()


def day_totals():
    row = db().execute(
        "SELECT COALESCE(SUM(protein_g),0) p, COALESCE(SUM(calories),0) c "
        "FROM meals WHERE day = ?", (today(),)
    ).fetchone()
    return round(row["p"]), round(row["c"])


def days_since_shot(user):
    if not user or not user["shot_date"]:
        return None
    return (datetime.date.today() - datetime.date.fromisoformat(user["shot_date"])).days


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def state():
    user = get_user()
    if not user:
        return jsonify({"onboarded": False})
    protein, cals = day_totals()
    meals = [dict(m) for m in db().execute(
        "SELECT * FROM meals WHERE day = ? ORDER BY id DESC", (today(),)
    ).fetchall()]
    for m in meals:
        m["items"] = json.loads(m["items_json"])
        del m["items_json"]
    return jsonify({
        "onboarded": True,
        "name": user["name"],
        "med": user["med"],
        "target_g": user["target_g"],
        "protein_today": protein,
        "calories_today": cals,
        "days_since_shot": days_since_shot(user),
        "meals": meals,
    })


@app.route("/api/onboard", methods=["POST"])
def onboard():
    d = request.get_json()
    weight = float(d["weight"])
    if d.get("unit") == "lb":
        weight *= 0.4536
    # Mid-range of the 1.2–1.6 g/kg guidance for GLP-1 users.
    target = round(weight * 1.4)
    db().execute(
        "INSERT OR REPLACE INTO user (id, name, weight_kg, med, target_g, shot_date) "
        "VALUES (1, ?, ?, ?, ?, (SELECT shot_date FROM user WHERE id = 1))",
        (d["name"].strip()[:40], round(weight, 1), d["med"], target),
    )
    db().commit()
    return state()


@app.route("/api/log", methods=["POST"])
def log_meal():
    text = request.form.get("text", "").strip()
    image_b64 = None
    media_type = None
    f = request.files.get("photo")
    if f and f.filename:
        raw = f.read()
        if len(raw) > 8 * 1024 * 1024:
            return jsonify({"error": "Photo too large (max 8MB)."}), 400
        media_type = f.mimetype if f.mimetype in (
            "image/jpeg", "image/png", "image/webp", "image/gif") else "image/jpeg"
        image_b64 = base64.b64encode(raw).decode()
    if not text and not image_b64:
        return jsonify({"error": "Add a photo or describe the meal."}), 400

    try:
        result = ai.analyze_meal(text=text or None, image_b64=image_b64,
                                 media_type=media_type)
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {e}"}), 502

    db().execute(
        "INSERT INTO meals (day, ts, items_json, protein_g, calories, gentle, coach_line) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (today(), datetime.datetime.now().strftime("%H:%M"),
         json.dumps(result["items"]), result["total_protein_g"],
         result["total_calories"], 1 if result.get("gentle") else 0,
         result.get("coach_line", "")),
    )
    db().commit()
    protein, cals = day_totals()
    return jsonify({"meal": result, "protein_today": protein, "calories_today": cals})


@app.route("/api/stomach", methods=["POST"])
def stomach():
    d = request.get_json()
    user = get_user()
    protein, _ = day_totals()
    remaining = (user["target_g"] if user else 90) - protein
    try:
        result = ai.stomach_ideas(int(d.get("nausea", 3)), d.get("note", ""),
                                  remaining, days_since_shot(user))
    except Exception as e:
        return jsonify({"error": f"Suggestion failed: {e}"}), 502
    return jsonify(result)


@app.route("/api/shot", methods=["POST"])
def shot():
    db().execute("UPDATE user SET shot_date = ? WHERE id = 1", (today(),))
    db().commit()
    return state()


@app.route("/api/reset", methods=["POST"])
def reset():
    db().execute("DELETE FROM user")
    db().execute("DELETE FROM meals")
    db().commit()
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(port=5099, debug=False)
