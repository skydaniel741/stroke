"""Recurring-charge detection from bank CSV transactions."""
import csv
import io
import re
import statistics
from datetime import datetime

DATE_FORMATS = ["%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y", "%d %b %Y"]

CADENCES = [
    (6, 8, "weekly", 52),
    (12, 16, "fortnightly", 26),
    (26, 34, "monthly", 12),
    (55, 68, "two-monthly", 6),
    (80, 100, "quarterly", 4),
    (330, 400, "annual", 1),
]


def _parse_date(s):
    s = s.strip()
    for f in DATE_FORMATS:
        try:
            return datetime.strptime(s, f)
        except ValueError:
            continue
    return None


def normalize(desc):
    d = desc.upper()
    d = re.sub(r"(POS W/D|EFTPOS|DIRECT DEBIT|AUTOMATIC PAYMENT|AP#?|DD|VISA PURCHASE|CARD \d+)", " ", d)
    d = re.sub(r"[^A-Z ]", " ", d)
    d = re.sub(r"\s+", " ", d).strip()
    return " ".join(d.split()[:3])


def parse_csv(text):
    """Accepts NZ-bank-style CSV. Finds date/amount/description columns by header."""
    reader = csv.reader(io.StringIO(text))
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]

    def col(*names):
        for i, h in enumerate(header):
            if any(n in h for n in names):
                return i
        return None

    di = col("date")
    ai = col("amount", "value", "debit")
    ci = col("description", "details", "particulars", "payee", "merchant", "narrative")
    if di is None or ai is None or ci is None:
        return []
    txns = []
    for r in rows[1:]:
        if len(r) <= max(di, ai, ci):
            continue
        date = _parse_date(r[di])
        try:
            amount = float(r[ai].replace("$", "").replace(",", ""))
        except ValueError:
            continue
        if date is None or amount >= 0:  # spends are negative
            continue
        txns.append({"date": date, "amount": -amount, "desc": r[ci].strip()})
    return txns


def find_recurring(txns):
    groups = {}
    for t in txns:
        groups.setdefault(normalize(t["desc"]), []).append(t)

    found = []
    for key, items in groups.items():
        if len(items) < 2 or not key:
            continue
        items.sort(key=lambda t: t["date"])
        gaps = [(b["date"] - a["date"]).days for a, b in zip(items, items[1:])]
        med_gap = statistics.median(gaps)
        cadence = next(((label, peryr) for lo, hi, label, peryr in CADENCES
                        if lo <= med_gap <= hi), None)
        if not cadence:
            continue
        amounts = [t["amount"] for t in items]
        mean_amt = statistics.mean(amounts)
        spread = (statistics.pstdev(amounts) / mean_amt) if mean_amt else 1
        if spread > 0.45:  # too erratic even for a utility
            continue
        found.append({
            "merchant": key.title(),
            "raw": items[0]["desc"],
            "count": len(items),
            "mean_amount": round(mean_amt, 2),
            "variable": spread > 0.12,
            "cadence": cadence[0],
            "annual_cost": round(mean_amt * cadence[1], 2),
            "last_seen": items[-1]["date"].strftime("%d %b %Y"),
        })
    found.sort(key=lambda x: -x["annual_cost"])
    return found
