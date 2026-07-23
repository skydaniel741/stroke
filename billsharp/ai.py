"""Claude classification layer for detected recurring charges."""
import json
import os

import anthropic
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

MODEL = "claude-sonnet-5"
_client = None


def client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


SYSTEM = (
    "You are the analysis engine of BillSharp, a New Zealand household money-leak "
    "audit tool. You receive recurring charges detected in a Kiwi household's bank "
    "transactions. You know NZ providers, typical NZ prices, and NZ alternatives. "
    "Be practical and specific to New Zealand. Never give regulated financial advice; "
    "for insurance items only suggest reviewing cover and getting quotes, never "
    "recommend specific products. Respond with ONLY valid JSON, no markdown fences."
)

PROMPT = """Recurring charges detected (merchant, per-charge amount NZD, cadence, annual cost):
{items}

For EACH charge return an object; also look ACROSS the list for overlaps (e.g. two \
music or two video streaming services) and likely-forgotten small charges.

Return JSON exactly:
{{
  "items": [{{
    "merchant": "input merchant string, unchanged",
    "display_name": "clean service name",
    "category": "streaming|music|fitness|utility|telco|insurance|software|news|gaming|other",
    "action": "cancel|switch|review|keep",
    "flag": "none|forgotten|overlap|price_check",
    "cancel_how": "one NZ-specific sentence: exactly how to cancel or switch this",
    "save_estimate_nzd": integer conservative annual saving if actioned (0 if keep),
    "note": "max 12 words, why it's flagged or worth reviewing"
  }}],
  "summary": "two sentences, plain NZ English, most important findings first, no exclamation marks",
  "total_recoverable_nzd": integer sum of save estimates
}}"""


def classify(found):
    items_txt = "\n".join(
        f"- {f['merchant']} | ${f['mean_amount']} | {f['cadence']} | ${f['annual_cost']}/yr"
        for f in found
    )
    msg = client().messages.create(
        model=MODEL,
        max_tokens=2500,
        system=SYSTEM,
        messages=[{"role": "user", "content": PROMPT.format(items=items_txt)}],
    )
    text = next(b.text for b in msg.content if b.type == "text").strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)
