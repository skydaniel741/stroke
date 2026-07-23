"""Claude-powered nutrition analysis for Kept."""
import json
import os

import anthropic
from dotenv import load_dotenv

# Prototype runs off the existing local .env one directory up (swim ai project).
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
    "You are the nutrition engine inside Kept, a protein-first food tracker for people "
    "on GLP-1 medication (semaglutide/tirzepatide). Users eat small portions, often have "
    "nausea and food aversions, and their #1 job is hitting a daily protein target to "
    "protect lean mass while losing weight. Be accurate, warm, and brief. Never give "
    "medical or dosage advice. Always respond with ONLY valid JSON, no markdown fences."
)

MEAL_PROMPT = """Analyze this meal for a GLP-1 user. Estimate portions conservatively \
(GLP-1 users eat 30-60% smaller portions than average).

Return JSON exactly in this shape:
{
  "items": [{"name": "...", "protein_g": 0, "calories": 0}],
  "total_protein_g": 0,
  "total_calories": 0,
  "gentle": true,
  "gentle_note": "one short phrase on how easy this sits on a GLP-1 stomach",
  "coach_line": "one warm sentence, max 14 words, protein-focused, no exclamation marks"
}

"gentle" = true if this food is typically well tolerated with GLP-1 nausea \
(bland, low-fat, low-grease, not overly sweet)."""

STOMACH_PROMPT = """A GLP-1 user needs food ideas RIGHT NOW.
Nausea level: {nausea}/5. Days since last shot: {shot}. \
Protein still needed today: {remaining}g.
What they said: "{note}"

Suggest exactly 3 specific, realistic foods/mini-meals they could actually stomach, \
ranked by tolerability. Prioritize protein density. Small portions. Common supermarket \
foods, nothing that needs real cooking if nausea >= 3.

Return JSON exactly:
{{
  "ideas": [{{"name": "...", "protein_g": 0, "why": "max 10 words on why it will sit ok"}}],
  "coach_line": "one warm sentence, max 14 words, no exclamation marks"
}}"""


def _text(msg):
    return next(b.text for b in msg.content if b.type == "text")


def _parse(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)


def analyze_meal(text=None, image_b64=None, media_type=None):
    content = []
    if image_b64:
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": image_b64},
        })
    desc = MEAL_PROMPT
    if text:
        desc += f'\n\nUser description: "{text}"'
    content.append({"type": "text", "text": desc})

    msg = client().messages.create(
        model=MODEL,
        max_tokens=700,
        system=SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    return _parse(_text(msg))


def stomach_ideas(nausea, note, remaining, days_since_shot):
    prompt = STOMACH_PROMPT.format(
        nausea=nausea,
        shot="unknown" if days_since_shot is None else days_since_shot,
        remaining=max(0, remaining),
        note=note or "nothing specific",
    )
    msg = client().messages.create(
        model=MODEL,
        max_tokens=500,
        system=SYSTEM,
        messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
    )
    return _parse(_text(msg))
