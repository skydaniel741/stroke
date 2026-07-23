"""BillSharp — NZ household money-leak audit. Prototype."""
import os

from flask import Flask, jsonify, render_template, request

import ai
import detector

app = Flask(__name__)
DEMO = os.path.join(os.path.dirname(__file__), "demo.csv")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/audit", methods=["POST"])
def audit():
    if request.form.get("demo"):
        with open(DEMO, encoding="utf-8") as f:
            text = f.read()
    else:
        f = request.files.get("csv")
        if not f or not f.filename:
            return jsonify({"error": "Upload a bank CSV export or run the demo."}), 400
        raw = f.read()
        if len(raw) > 4 * 1024 * 1024:
            return jsonify({"error": "File too large (max 4MB)."}), 400
        text = raw.decode("utf-8", errors="replace")

    txns = detector.parse_csv(text)
    if not txns:
        return jsonify({"error": "Couldn't read that CSV. It needs date, description "
                        "and amount columns (spending as negative amounts)."}), 400
    found = detector.find_recurring(txns)
    if not found:
        return jsonify({"error": "No recurring charges detected in this file."}), 400

    try:
        cls = ai.classify(found)
    except Exception as e:
        return jsonify({"error": f"Analysis failed: {e}"}), 502

    by_merchant = {c["merchant"]: c for c in cls.get("items", [])}
    for f_ in found:
        f_.update(by_merchant.get(f_["merchant"], {}))

    return jsonify({
        "items": found,
        "annual_total": round(sum(f_["annual_cost"] for f_ in found), 2),
        "recoverable": cls.get("total_recoverable_nzd", 0),
        "summary": cls.get("summary", ""),
        "txn_count": len(txns),
    })


if __name__ == "__main__":
    app.run(port=5097, debug=False)
