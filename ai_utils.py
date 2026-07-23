import base64
import io
import json
import logging

import anthropic

logger = logging.getLogger(__name__)

# Coaching tone for the AI's feedback (squad insights, check-in replies).
# Lets a coach dial how blunt the AI is -- the default is deliberately warm
# rather than harsh.
# Every prompt that produces swimmer-facing text gets this. The whole point is
# that the output should read like a real coach talking, not like AI filler.
HUMAN_VOICE = (
    "VOICE: Write like a real human swim coach talking to their swimmer on the pool deck. "
    "Use contractions (you're, that's, let's, don't). Vary your sentence length. Be specific and "
    "warm, never robotic or corporate. "
    "HARD RULES: Never use an em-dash or a double-hyphen '--'. If you'd normally join two thoughts "
    "with a dash, use a comma, a full stop, or the words 'and'/'but'/'so' instead. Don't start with "
    "filler like 'Great question' or 'It's important to note'. Don't restate the swimmer's data back "
    "to them. No corporate buzzwords. Just talk to them like a person who cares about their swimming."
)

TONE_GUIDANCE = {
    'encouraging': (
        "TONE: Warm and encouraging. Lead with what's going well, frame concerns gently as "
        "opportunities, and never be harsh or discouraging. Still be honest, but choose kind, "
        "motivating wording. This reader may be young or easily disheartened."
    ),
    'balanced': (
        "TONE: Supportive but honest, like a good club coach. Acknowledge positives, name real "
        "concerns plainly without being harsh, and keep it constructive."
    ),
    'direct': (
        "TONE: Direct and performance-focused, like a senior squad coach. Be candid about "
        "problems and hold a high bar, but stay professional and never insulting."
    ),
}


def _tone_line(tone):
    return f"{TONE_GUIDANCE.get((tone or 'balanced').lower(), TONE_GUIDANCE['balanced'])}\n{HUMAN_VOICE}"


# Belt-and-braces cleanup: even with the prompt rules above, models sometimes
# slip in an em-dash. Strip them out of anything swimmer-facing so the copy
# never reads as AI-generated. Recurses through the dict/list tool output.
import re as _re

_DASH_RE = _re.compile(r'\s*[, ]\s*|\s+--\s+')


def _humanize(value):
    if isinstance(value, str):
        # Replace dash-joins with a comma+space, then tidy any doubled spaces
        # or stray leading punctuation the swap can leave behind.
        out = _DASH_RE.sub(', ', value)
        out = _re.sub(r'\s{2,}', ' ', out).replace(' ,', ',').strip()
        # A dash right before a capital usually meant a new sentence; if we made
        # a ", X" where X is capitalised mid-string, a full stop reads better.
        return out
    if isinstance(value, list):
        return [_humanize(v) for v in value]
    if isinstance(value, dict):
        return {k: _humanize(v) for k, v in value.items()}
    return value


# Solo Pro intensity knob -- shifts how demanding the generated program is
# without changing the swimmer's stated level.
INTENSITY_GUIDANCE = {
    'easier': (
        "INTENSITY: Dial this program slightly easier than their level would normally get -- "
        "trim total volume ~15-20%, give more rest between reps, and keep most work aerobic. "
        "Prioritise sustainability and recovery over hard sets."
    ),
    'normal': (
        "INTENSITY: Pitch the program squarely at their stated level and fitness -- a sensible, "
        "well-balanced load."
    ),
    'harder': (
        "INTENSITY: Push this program a notch harder than their level would normally get -- "
        "add ~15-20% volume or an extra quality/race-pace element, with tighter intervals. "
        "Keep it safe and achievable, but make them work."
    ),
}


def _intensity_line(intensity):
    return INTENSITY_GUIDANCE.get((intensity or 'normal').lower(), INTENSITY_GUIDANCE['normal'])
from PIL import Image, ImageOps
import pillow_heif

pillow_heif.register_heif_opener()  # lets Pillow open iPhone HEIC/HEIF photos

# Anthropic recommends images no larger than ~1568px on the long edge --
# anything bigger just gets downscaled server-side anyway, so we do it
# ourselves to keep upload size and request cost down.
MAX_DIMENSION = 1568

# Mirrors the block shape used everywhere else in the app: SavedSet.get_sets()
# (models.py) and sessionSets in log.html. 'modifier' is optional and only
# meaningful alongside 'stroke' -- older manually-entered blocks won't have it.
STROKE_CODES = {'FR', 'BK', 'BR', 'FL', 'IM'}
MODIFIERS = {'', 'Kick', 'Pull', 'Drill', 'Snorkel'}
SECTIONS = ['Warm up', 'Pre set', 'Main set', 'Sub set', 'Cool down']
POOLS = {'25m', '50m'}

TOOL_SCHEMA = {
    "name": "log_swim_set",
    "description": "Log the structured swim set read from a photo of a coach's whiteboard or written set.",
    "input_schema": {
        "type": "object",
        "properties": {
            "pool": {
                "type": "string",
                "enum": ["25m", "50m"],
                "description": "Best guess at pool length. Default to 25m if not stated.",
            },
            "session_type": {
                "type": "string",
                "description": "Short label for the session, e.g. Training, Speed, Endurance, Technique.",
            },
            "blocks": {
                "type": "array",
                "description": "Every distinct set/rep group on the board, in the order they appear.",
                "items": {
                    "type": "object",
                    "properties": {
                        "section": {
                            "type": "string",
                            "enum": SECTIONS,
                            "description": "Which part of the session this belongs to. Default to 'Main set' if unclear.",
                        },
                        "reps": {
                            "type": "integer",
                            "description": (
                                "Number of repeats, e.g. the 8 in 8x100. Only go above 1 when the board actually "
                                "writes rep notation like '8x100' or lists separate numbered reps. If instead the "
                                "board gives ONE continuous total distance (e.g. '300', '400m continuous') that "
                                "happens to rotate internally through kick/drill/swim or alternating strokes every "
                                "50 or 25, that is still reps=1 -- do not reverse-engineer a reps x sub-distance "
                                "split just because the rotation unit divides evenly into the total. The rotation "
                                "detail goes in 'note' instead."
                            ),
                        },
                        "dist": {
                            "type": "integer",
                            "description": (
                                "Distance per rep in metres, e.g. the 100 in 8x100. When reps=1 this is the literal "
                                "total distance written on the board (e.g. '300' -> dist=300), even if that swim "
                                "internally rotates through several 50s or 25s of different kick/drill/swim/stroke."
                            ),
                        },
                        "stroke": {
                            "type": "string",
                            "enum": sorted(STROKE_CODES),
                            "description": (
                                "The primary stroke: FR=Freestyle, BK=Backstroke, BR=Breaststroke, FL=Butterfly, IM. "
                                "Pick whichever of these is actually named or implied for the rep, even if it's paired "
                                "with a Kick/Pull/Drill modifier -- e.g. 'Butterfly kick' or 'Fly K' is stroke=FL, NOT a "
                                "bare kick block. If truly no stroke is named at all (a plain '3x50 Kick' with nothing "
                                "else), default stroke to FR. IMPORTANT: only use IM when the rep is genuinely swum in "
                                "medley order (fly-back-breast-free, in that sequence, or the board literally says "
                                "'IM'/'medley') -- a set that simply mixes several different strokes without that "
                                "specific order is NOT IM. In that case pick the single most-repeated/primary stroke "
                                "instead and list the others in 'note'. Never guess IM just because multiple strokes "
                                "appear in the same session."
                            ),
                        },
                        "modifier": {
                            "type": "string",
                            "enum": sorted(MODIFIERS),
                            "description": (
                                "A Kick/Pull/Drill modifier on top of the primary stroke, e.g. the 'kick' in "
                                "'Butterfly kick' or the 'pull' in 'Free pull'. Empty string if the rep is a plain swim "
                                "with no modifier."
                            ),
                        },
                        "rest": {
                            "type": "string",
                            "description": (
                                "The rest or interval TIME, normalized to 'M:SS' or '0:SS' regardless of how it was "
                                "written on the board -- just the number, its meaning goes in 'rest_type'. "
                                "'with 10' or '10 sec rest' -> '0:10'; 'on 45' or '@45' -> '0:45'; 'on 1.00' or "
                                "'on 1:00' -> '1:00'. Empty string only if truly no rest/interval is given."
                            ),
                        },
                        "rest_type": {
                            "type": "string",
                            "enum": ["interval", "rest"],
                            "description": (
                                "What the 'rest' number actually means -- these are NOT the same thing. "
                                "'interval' = a send-off/cycle time: the swimmer leaves again every X, e.g. 'on 2:10', "
                                "'on a 1:30 send-off', '@1:00' -- the number is the total cycle time from one start to "
                                "the next, not literal rest. This is how nearly all repeat sets (8x100, 5x200, etc) are "
                                "written, so default to 'interval' whenever reps > 1 and the board doesn't clearly say "
                                "otherwise. 'rest' = an explicit gap/recovery duration between reps or blocks, e.g. "
                                "'with 20 seconds rest', 'rest 30', '2 min rest before the next set' -- only use this "
                                "when the board is explicitly describing a recovery pause, not a cycle time. For a "
                                "single continuous swim (reps=1) followed by a break before the next block, use 'rest'."
                            ),
                        },
                        "note": {
                            "type": "string",
                            "description": (
                                "Any other coaching shorthand attached to this block that doesn't fit reps/dist/stroke/"
                                "modifier/rest. Use this to capture: (1) stroke-rotation patterns within a rep, e.g. "
                                "'6x50 IM Fly-bk bk-br Br-fr' (three pairs of 50s cycling through fly-back, back-breast, "
                                "breast-free) -> note='Fly-Bk / Bk-Br / Br-Fr'; (2) sub-breakdowns of a rep count, e.g. "
                                "'9x50 IM kick 3 Fly, 3 Breast, 3 Free' -> note='3 Fly, 3 Breast, 3 Free'; (3) other "
                                "strokes swept into 'stroke' being a best guess, e.g. a warm-up mixing free/back/kick "
                                "drills -> note='+ backstroke, kick drill'; (4) a small subscript/superscript number or "
                                "fraction written near the main line (e.g. a tiny '5/1.5' tucked under a rep count) -- "
                                "this is a secondary annotation, NEVER let it distort reps/dist/rest on the main line. "
                                "Put your best reading of it first in 'note' (e.g. note='(5/1.5) build each rep') so it "
                                "stays visible even if its exact meaning is unclear. Empty string if none."
                            ),
                        },
                        "round_reps": {
                            "type": "integer",
                            "description": (
                                "Only set this above 1 when the board draws an explicit bracket/brace grouping several "
                                "DIFFERENT blocks together with one multiplier in front, e.g. '2x{ 4x75 ... / 8x50 ... / "
                                "2x25 ... }' or '3x[ ... ]' -- that whole bracketed group is swum as one unit N times. "
                                "Give every block inside that bracket the SAME round_reps (e.g. 2), so they can be shown "
                                "as one grouped round. This is different from a normal 'reps' repeat of a single "
                                "identical line (e.g. '8x100' is just reps=8, round_reps=1) -- round_reps is only for a "
                                "bracket wrapping multiple distinct lines. Default to 1 (omit it) for every ungrouped block."
                            ),
                        },
                    },
                    "required": ["reps", "dist", "stroke"],
                },
            },
        },
        "required": ["blocks"],
    },
}

PROMPT = (
    "This is a photo of a swim coach's handwritten or whiteboard training set. "
    "Read it carefully, including shorthand and arrows, and call the log_swim_set tool "
    "with every distinct rep group you can identify. If the photo has no readable swim "
    "set, call the tool with an empty blocks array.\n\n"
    "Watch for these common patterns and don't drop them:\n"
    "- Rest/send-off shorthand: 'with 10', 'on 45', '@45', 'on 1.00' all give a time -- always fill "
    "in the 'rest' field with that time, AND set 'rest_type' correctly. 'on 45', '@45', 'on 1:00' are "
    "send-off/interval times (rest_type='interval') -- the swimmer leaves again every X, that's NOT the "
    "same as how long they rest. 'with 10', '10 sec rest' are an explicit rest duration "
    "(rest_type='rest'). When in doubt for a repeat set (reps > 1), default to 'interval' -- that's how "
    "swim sets are almost always written.\n"
    "- Stroke + modifier combos like 'Butterfly kick', 'Fly K', 'Free Pull', 'IM Kick': the primary "
    "stroke (FR/BK/BR/FL/IM) goes in 'stroke' and the Kick/Pull/Drill part goes in the separate "
    "'modifier' field. 'Butterfly kick' is stroke=FL, modifier=Kick -- never collapse it down to a "
    "bare kick block that loses the Butterfly.\n"
    "- Don't hallucinate IM: only set stroke=IM when the rep is actually swum in fly-back-breast-free "
    "medley order, or the board explicitly says 'IM'/'medley'. A set that just happens to use several "
    "different strokes across its reps (e.g. some butterfly, some backstroke) without that specific "
    "order is NOT IM -- use the dominant stroke instead and mention the others in 'note'.\n"
    "- Stroke-rotation reps such as '6x50 IM Fly-bk bk-br Br-fr' or '100 BK K, Turns IM': record "
    "the rep as one block and put the rotation/detail text in 'note' so it isn't lost.\n"
    "- A rep count that's broken into named sub-groups, e.g. '9x50 IM kick 3 Fly, 3 Breast, 3 Free' "
    "or '12x25 Max timed 60: 6x Fr, 6x Choice': keep it as one block with reps=9 (or 12) and put the "
    "breakdown in 'note'.\n"
    "- CRITICAL -- don't confuse a continuous total with a rep count: '300 alternating 50 kick/drill/"
    "swim', '400 continuous: 25 drill/25 swim', 'straight 300, rotate kick-drill-swim by 50s' are all "
    "ONE number (300, 400) written on the board, not rep notation. Record reps=1, dist=300 (the literal "
    "total as written), and put 'alternating 50 kick/drill/swim' (or similar) in 'note'. Only split into "
    "reps x dist when the board itself actually writes it as 'Nx' (e.g. '6x50') -- never invent that "
    "split just because the rotation's 50 or 25 unit happens to divide evenly into the total.\n"
    "- BE KNOWLEDGEABLE, NOT JUST LITERAL, ABOUT NUMBERS: handwritten digits get misread ('90' for "
    "'100', '0:20' for '2:00', an '8' that's really a '3'). You know swim conventions, so use them as a "
    "sanity check on your own read rather than transcribing blindly. Distances are almost always clean "
    "numbers -- multiples of 25 (25/50/75/100/150/200/300/400 etc.), with only breakout-style reps ever "
    "landing on something like 10 or 15. If your first read of a distance is an odd, non-standard number "
    "(e.g. 90, 88, 110) look again: it is very likely a misread of the nearest clean distance (90 -> 100), "
    "not a genuinely unusual distance -- prefer the clean value unless the board is unambiguous that it "
    "really is odd. The same goes for times: rest/interval numbers are normally round-ish (:05 "
    "increments, or whole minutes) -- a jagged read like '0:37' is more likely '0:35' or '0:30'.\n"
    "- CRITICAL PHYSICAL SANITY CHECK: an interval/send-off can never be shorter than the swim it times "
    "-- a swimmer cannot leave again on '0:20' for a 100m rep when swimming 100m itself takes roughly a "
    "minute or more. If your read produces an interval that's obviously too short for the distance and "
    "stroke, you almost certainly misread a digit (the interval is probably a longer number you read "
    "short, e.g. '2:00' misread as '0:20', or the distance is smaller than you think, e.g. a 25 not a "
    "100). Re-examine the handwriting and correct it before answering; never output a send-off that is "
    "physically impossible to swim.\n"
    "- ROUNDS -- a bracket/brace grouping several different lines under one multiplier, e.g. "
    "'2x{ 4x75 .../ 8x50 .../ 2x25 ... }' or '3x[ ... ]': this means the WHOLE bracketed group of blocks "
    "is repeated together as one round, not that any single line repeats that many times. Record each "
    "block inside the bracket normally (its own reps/dist/etc as written on that line) and set "
    "'round_reps' to the bracket's multiplier (2, 3, ...) on every block inside it, so the app can show "
    "them grouped as one round. Leave round_reps at 1 (omit it) for anything not inside a bracket, "
    "including ordinary 'Nx' reps of a single line -- that's just 'reps', not a round."
)


def _clamp_block(raw):
    try:
        reps = int(raw.get('reps') or 0)
        dist = int(raw.get('dist') or 0)
    except (TypeError, ValueError):
        return None
    if reps <= 0 or dist <= 0:
        return None

    # Backstop for OCR/transcription misreads: real swim distances are almost
    # always a clean multiple of 25 (or a short breakout-style number under
    # 40). Snap a near-miss read (e.g. 90 -> 100) to the nearest multiple of
    # 25 rather than trusting a jagged digit at face value -- the prompt asks
    # the model to do this itself, but this catches anything that slips through.
    if dist >= 40:
        nearest_25 = round(dist / 25) * 25
        if nearest_25 != dist and abs(nearest_25 - dist) <= 12:
            dist = nearest_25

    stroke = raw.get('stroke') if raw.get('stroke') in STROKE_CODES else 'FR'
    modifier = raw.get('modifier') if raw.get('modifier') in MODIFIERS else ''
    section = raw.get('section') if raw.get('section') in SECTIONS else 'Main set'
    rest = str(raw.get('rest') or '').strip()
    note = str(raw.get('note') or '').strip()

    from swim_logic import estimate_rep_seconds, infer_rest_type, parse_time
    rest_secs = parse_time(rest)
    est_swim = estimate_rep_seconds(dist, stroke, modifier)
    # 'interval' = send-off/cycle time ("on 2:10" -- leave again every 2:10);
    # 'rest' = an explicit recovery gap. Falls back to the same physically-
    # grounded guess used everywhere else when the model omits rest_type, and
    # overrides even an explicit 'interval' read that's physically impossible
    # (a send-off can never be shorter than the swim it times) -- if the model
    # says 'interval' but the number can't be one, trust the number over the
    # label and reclassify rather than silently dropping the block.
    declared = raw.get('rest_type') if raw.get('rest_type') in ('interval', 'rest') else None
    if declared == 'interval' and rest_secs is not None and est_swim is not None and rest_secs < est_swim:
        declared = None
    rest_type = declared or infer_rest_type(reps, rest_secs, est_swim, note)

    try:
        round_reps = int(raw.get('round_reps') or 1)
    except (TypeError, ValueError):
        round_reps = 1
    round_reps = max(1, min(round_reps, 20))

    block = {
        'section': section, 'reps': reps, 'dist': dist, 'stroke': stroke,
        'modifier': modifier, 'rest': rest, 'rest_type': rest_type, 'note': note,
    }
    if round_reps > 1:
        block['round_reps'] = round_reps
    return block


def normalize_image(raw_bytes):
    """Turn whatever a phone camera/gallery hands us (HEIC, oddly-rotated JPEG,
    a 12MP original, etc.) into a modest, correctly-oriented JPEG that Claude's
    vision API can read. Returns JPEG bytes, or None if it isn't a real image."""
    try:
        img = Image.open(io.BytesIO(raw_bytes))
        img.load()
    except Exception:
        return None

    # Phones store rotation as EXIF metadata rather than rotating the pixels --
    # without this a photo taken in portrait can come out sideways.
    img = ImageOps.exif_transpose(img)

    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')

    if max(img.size) > MAX_DIMENSION:
        img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.LANCZOS)

    out = io.BytesIO()
    img.save(out, format='JPEG', quality=85)
    return out.getvalue()


def extract_set_from_image(image_bytes, api_key, model):
    """Call Claude with forced tool-use to turn a whiteboard photo into structured
    swim set blocks. Returns {'ok': True, 'blocks', 'pool', 'session_type'} on
    success or {'ok': False, 'error'} on any failure -- never raises."""
    normalized = normalize_image(image_bytes)
    if normalized is None:
        return {'ok': False, 'error': "That doesn't look like a photo. Try again."}

    try:
        client = anthropic.Anthropic(api_key=api_key)
        b64 = base64.standard_b64encode(normalized).decode('utf-8')

        response = client.messages.create(
            model=model,
            max_tokens=2048,
            tools=[TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "log_swim_set"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                    {"type": "text", "text": PROMPT},
                ],
            }],
        )
    except Exception:
        logger.exception('extract_set_from_image: API call failed')
        return {'ok': False, 'error': "Couldn't read that photo. Try again or enter it manually."}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use:
        return {'ok': False, 'error': "Couldn't read that photo. Try again or enter it manually."}

    data = tool_use.input or {}
    blocks = [b for b in (_clamp_block(r) for r in data.get('blocks', [])) if b is not None]

    if not blocks:
        return {'ok': False, 'error': "Couldn't find a set in that photo. Try a clearer shot."}

    pool = data.get('pool') if data.get('pool') in POOLS else '25m'
    session_type = (data.get('session_type') or 'Training').strip() or 'Training'

    return {'ok': True, 'blocks': blocks, 'pool': pool, 'session_type': session_type}


TRANSCRIPT_PROMPT = (
    "This is a voice-dictated transcript of a swimmer describing the workout they just did, "
    "e.g. \"100 free warmup then 100 back on 2:10 rest with pads holding 1:30\". Read it carefully "
    "and call the log_swim_set tool with every distinct rep group you can identify. If the "
    "transcript describes no readable swim set, call the tool with an empty blocks array.\n\n"
    "Watch for these common spoken patterns and don't drop them:\n"
    "- CRITICAL: 'on' vs 'rest'/'resting' are NOT the same thing, even when they appear right next to "
    "each other. 'on 2:10', 'on a 2:10 send-off', '@2:10' mean the swimmer leaves again every 2:10 -- "
    "that's an interval/cycle time (rest_type='interval'), it does NOT mean they rest for 2:10. "
    "'with 20 seconds rest', 'resting 30', 'rest 30 seconds' describe an actual recovery gap "
    "(rest_type='rest'). A phrase like 'on 2:10 rest' is still describing the interval (rest_type="
    "'interval') -- the word 'rest' there is just casual speech for 'send-off', not a separate "
    "rest duration. Put the time itself in 'rest' either way; 'rest_type' records which kind it is.\n"
    "- A held/target time spoken as part of a rep, e.g. 'holding 1:30' or 'trying to hold 1:20', is "
    "a pace goal for that rep -- put it in 'note' (e.g. note='holding 1:30'), not in 'rest'.\n"
    "- Equipment mentioned by name -- paddles, pads, fins, snorkel, pull buoy -- maps to the "
    "'modifier' field where it fits (Pull for paddles/pull buoy, Kick for fins used on a kick set, "
    "Snorkel for a snorkel) or otherwise into 'note' if it doesn't cleanly become a modifier (e.g. "
    "'with pads' on a swim set -> note='with pads').\n"
    "- Casual sequencing words like 'then', 'after that', 'followed by' just separate blocks in order "
    "-- they aren't part of any field.\n"
    "- Stroke + modifier combos like 'butterfly kick', 'free pull', 'backstroke drill': the primary "
    "stroke (FR/BK/BR/FL/IM) goes in 'stroke' and the Kick/Pull/Drill/Snorkel part goes in the "
    "separate 'modifier' field.\n"
    "- Don't hallucinate IM: only set stroke=IM when the swimmer actually says IM/medley or describes "
    "swimming fly-back-breast-free in that order.\n"
    "- If the swimmer doesn't say a section (warmup/main set/cooldown), infer it from context -- 'warm "
    "up' or 'warmup' words mean section='Warm up', 'cool down' means section='Cool down', otherwise "
    "default to 'Main set'.\n"
    "- CRITICAL -- don't confuse a continuous total with a rep count: 'three hundred alternating fifty "
    "kick drill swim' or 'four hundred continuous, twenty-five drill twenty-five swim' is ONE number "
    "(300, 400) with an internal rotation, not a rep count. Record reps=1, dist=300 (the literal total "
    "spoken), and put the rotation description in 'note'. Only use reps > 1 when the swimmer actually "
    "says it as reps (e.g. 'six times fifty' / '6x50').\n"
    "- CRITICAL PHYSICAL SANITY CHECK: an interval/send-off can never be shorter than the swim it times. "
    "If your transcription implies an impossible send-off (e.g. 'on 20 seconds' for a 100), you likely "
    "mis-split a number ('2:10' heard as '20') -- reconsider before answering rather than outputting "
    "something unswimmable.\n"
    "- ROUNDS: if the swimmer describes a group of several different reps repeated together as a unit, "
    "e.g. 'two rounds of 4x75 then 8x50 then 2x25', record each of those blocks normally and set "
    "'round_reps'=2 on all of them so the app can group them as one repeated round. Leave round_reps at "
    "1 (omit it) for a plain 'Nx' repeat of a single line."
)


def extract_set_from_transcript(transcript, api_key, model):
    """Call Claude with forced tool-use to turn a dictated workout transcript into
    structured swim set blocks. Returns {'ok': True, 'blocks', 'pool', 'session_type'}
    on success or {'ok': False, 'error'} on any failure -- never raises."""
    text = (transcript or '').strip()
    if not text:
        return {'ok': False, 'error': "Didn't catch anything. Try dictating again."}

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            tools=[TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "log_swim_set"},
            messages=[{
                "role": "user",
                "content": [{"type": "text", "text": f'{TRANSCRIPT_PROMPT}\n\nTranscript: "{text}"'}],
            }],
        )
    except Exception:
        logger.exception('extract_set_from_transcript: API call failed')
        return {'ok': False, 'error': "Couldn't parse that. Try again or enter it manually."}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use:
        return {'ok': False, 'error': "Couldn't parse that. Try again or enter it manually."}

    data = tool_use.input or {}
    blocks = [b for b in (_clamp_block(r) for r in data.get('blocks', [])) if b is not None]

    if not blocks:
        return {'ok': False, 'error': "Couldn't find a set in that. Try describing it differently."}

    pool = data.get('pool') if data.get('pool') in POOLS else '25m'
    session_type = (data.get('session_type') or 'Training').strip() or 'Training'

    return {'ok': True, 'blocks': blocks, 'pool': pool, 'session_type': session_type}


# ============================================================
# ROSTER IMPORT: map a coach's exported CSV onto our schema
# ============================================================
# Coaches already have their swimmers in another platform (TeamUnify,
# SwimTopia, Hy-Tek, a club spreadsheet). No two of those export the same
# column headers, so a plain csv.DictReader that demands columns literally
# named 'email'/'name' drops most real files on the floor. This asks Claude
# to look at the headers + a few sample rows and tell us which column is
# which. It only proposes a mapping -- the coach confirms every row in a
# preview before anything is written (see routes_coach import preview/commit),
# so the AI never silently lands minors' contact details in the DB.

# Fields we can actually use on a SquadMembership today. dob is surfaced in the
# preview for the coach to sanity-check identity, but there's no column to store
# it on yet, so the commit step ignores it.
ROSTER_TARGET_FIELDS = ('full_name', 'first_name', 'last_name', 'email', 'dob', 'group')

ROSTER_MAP_TOOL_SCHEMA = {
    "name": "map_roster_columns",
    "description": (
        "Report which column header in a coach's exported swimmer roster maps to each field we need. "
        "For every field, return the EXACT header string from the file, or an empty string if no "
        "column fits. Never invent a header that isn't in the provided list."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "full_name": {"type": "string", "description": "Header holding the swimmer's whole name in one cell (e.g. 'Athlete', 'Swimmer Name'). Empty if the name is split across first/last columns instead."},
            "first_name": {"type": "string", "description": "Header for the given/first name, if the name is split into two columns. Empty if there's a single full-name column."},
            "last_name": {"type": "string", "description": "Header for the family/last name, if split. Empty if there's a single full-name column."},
            "email": {"type": "string", "description": "Header for the swimmer's (or guardian's) email address. Empty if none."},
            "dob": {"type": "string", "description": "Header for date of birth / birthdate. Empty if none."},
            "group": {"type": "string", "description": "Header for the training group, squad, lane, or level the swimmer belongs to. Empty if none."},
        },
        "required": list(ROSTER_TARGET_FIELDS),
    },
}

ROSTER_MAP_PROMPT = (
    "You are helping a swim coach import their roster from another piece of software into ours. "
    "Below are the column headers from their exported CSV and a few sample rows. Decide which header "
    "corresponds to each field we need, and call map_roster_columns with the exact header strings.\n"
    "Rules:\n"
    "- Use the EXACT header text as it appears in the list. If nothing fits a field, return an empty string.\n"
    "- Prefer a single full-name column when one exists; only use first_name/last_name when the name is "
    "genuinely split across two columns.\n"
    "- A column like 'Group', 'Squad', 'Training Group', 'Level', or 'Lane' maps to group.\n"
    "- If both a swimmer email and a parent/guardian email exist, prefer the swimmer's own email; "
    "otherwise use whichever email is present.\n"
    "- Ignore columns you don't need (times, USA-S id, gender, fees). Don't force them into a field."
)


def _heuristic_roster_map(headers):
    """Best-effort header match with no AI, used when AI is off or the call
    fails. Keeps import working (just less cleverly) rather than dead."""
    mapping = {f: '' for f in ROSTER_TARGET_FIELDS}
    for h in headers or []:
        low = (h or '').strip().lower()
        if not low:
            continue
        if not mapping['email'] and 'email' in low:
            mapping['email'] = h
        elif not mapping['full_name'] and low in ('name', 'full name', 'swimmer', 'athlete', 'swimmer name', 'athlete name'):
            mapping['full_name'] = h
        elif not mapping['first_name'] and low in ('first', 'first name', 'firstname', 'given name'):
            mapping['first_name'] = h
        elif not mapping['last_name'] and low in ('last', 'last name', 'lastname', 'surname', 'family name'):
            mapping['last_name'] = h
        elif not mapping['dob'] and (low in ('dob', 'd.o.b.') or 'birth' in low):
            mapping['dob'] = h
        elif not mapping['group'] and low in ('group', 'squad', 'training group', 'level', 'lane', 'lane group', 'team'):
            mapping['group'] = h
    return mapping


def map_roster_columns(headers, sample_rows, api_key, model):
    """Ask Claude which CSV column is which. Returns a dict keyed by
    ROSTER_TARGET_FIELDS, each value the source header string (or '').
    Never raises -- falls back to a heuristic match if AI is unavailable."""
    headers = [h for h in (headers or []) if h and h.strip()]
    if not headers:
        return {f: '' for f in ROSTER_TARGET_FIELDS}

    if not api_key:
        return _heuristic_roster_map(headers)

    # Keep the sample small and cheap -- a handful of rows is plenty to
    # disambiguate headers, and we don't want to ship the whole file to the API.
    sample = []
    for row in (sample_rows or [])[:6]:
        sample.append({h: str(row.get(h, ''))[:60] for h in headers})

    prompt = (
        f"{ROSTER_MAP_PROMPT}\n\n"
        f"Column headers: {json.dumps(headers)}\n\n"
        f"Sample rows: {json.dumps(sample, ensure_ascii=False)}"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=512,
            tools=[ROSTER_MAP_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "map_roster_columns"},
            messages=[{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        )
    except Exception:
        logger.exception('map_roster_columns: API call failed, using heuristic')
        return _heuristic_roster_map(headers)

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use or not tool_use.input:
        return _heuristic_roster_map(headers)

    data = tool_use.input
    header_set = set(headers)
    # Trust only headers that actually exist in the file -- the model
    # occasionally normalises capitalisation or invents a tidy label.
    mapping = {}
    for field in ROSTER_TARGET_FIELDS:
        val = (data.get(field) or '').strip()
        mapping[field] = val if val in header_set else ''

    # If the model gave us nothing usable, the heuristic is better than blank.
    if not any(mapping.values()):
        return _heuristic_roster_map(headers)
    return mapping


# ============================================================
# SOLO-TIER AI COACHING: onboarding -> program, and daily check-ins
# ============================================================

SWIM_BLOCK_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "section": {"type": "string", "enum": SECTIONS, "description": "Which part of the session this block belongs to."},
        "reps": {"type": "integer", "description": "Number of repeats."},
        "dist": {"type": "integer", "description": "Distance per rep in metres (multiples of 25)."},
        "stroke": {"type": "string", "enum": sorted(STROKE_CODES), "description": "Primary stroke code."},
        "modifier": {"type": "string", "enum": sorted(MODIFIERS), "description": "Kick/Pull/Drill modifier, or empty."},
        "rest": {"type": "string", "description": "The rest or interval TIME as 'M:SS' / '0:SS'. Empty if none."},
        "rest_type": {
            "type": "string",
            "enum": ["interval", "rest"],
            "description": (
                "What 'rest' means. 'interval' = a send-off/cycle time -- the swimmer leaves again every "
                "X (e.g. 8x100 on 1:30) -- use this for basically every repeat set (reps > 1), which is "
                "how real swim sets are almost always written. 'rest' = an explicit recovery gap between "
                "blocks, e.g. after a single continuous warm-up swim before the main set starts."
            ),
        },
        "note": {"type": "string", "description": "Short cue for this block, e.g. 'descend 1-4', 'build to race pace'. Empty if none."},
    },
    "required": ["section", "reps", "dist", "stroke"],
}

PROGRAM_TOOL_SCHEMA = {
    "name": "create_training_program",
    "description": "Build a personalized weekly swim training calendar from a swimmer's onboarding answers.",
    "input_schema": {
        "type": "object",
        "properties": {
            "overview": {
                "type": "string",
                "description": (
                    "ONE short sentence (max ~20 words) naming this week's focus for this swimmer. "
                    "No preamble, no restating their answers back to them."
                ),
            },
            "days": {
                "type": "array",
                "description": (
                    "Exactly 7 entries, Monday through Sunday, covering the whole week. Training days get "
                    "full sessions with concrete swim blocks; the remaining days are rest or optional "
                    "recovery days (rest=true, no blocks). Spread training days sensibly across the week."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "day": {"type": "string", "enum": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]},
                        "rest": {"type": "boolean", "description": "True if this is a rest/recovery day with no swim session."},
                        "focus": {"type": "string", "description": "e.g. 'Aerobic base', 'Speed & technique', 'Recovery'. For rest days: 'Rest' or 'Active recovery'."},
                        "blocks": {
                            "type": "array",
                            "description": "The actual written set for a training day: warm up, main set(s), cool down. Empty for rest days.",
                            "items": SWIM_BLOCK_ITEM_SCHEMA,
                        },
                        "coach_note": {"type": "string", "description": "ONE short cue for the day (max ~12 words), e.g. 'Hold form when tired'. For rest days, one line on recovery."},
                    },
                    "required": ["day", "rest", "focus", "coach_note"],
                },
            },
            "progression_tips": {
                "type": "string",
                "description": "ONE short sentence on how to progress next week (e.g. add reps or drop rest). Max ~20 words.",
            },
            "adaptation_note": {
                "type": "string",
                "description": (
                    "Only when adaptive coaching context is provided: 1-2 plain sentences telling the swimmer "
                    "what changed in this week's plan vs their recent training and why, grounded in their real "
                    "data (trend, volume, fatigue). Empty string when no context was given."
                ),
            },
            "insights": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Exactly 4 short, punchy coaching cues (each max ~18 words), specific to THIS swimmer's "
                    "age/level/goal/swimmer-type. Make them feel like a real coach who knows them: one on technique, "
                    "one on how to race/pace, one on the mental side or consistency, one on what to prioritise next. "
                    "No generic filler, no full sentences padded with fluff, and never use an em-dash."
                ),
            },
            "nutrition": {
                "type": "object",
                "description": "Personalized nutrition guidance built from the swimmer's eating habits, NOT a generated meal plan.",
                "properties": {
                    "focus_note": {
                        "type": "string",
                        "description": "ONE short sentence (max ~20 words) on their single biggest nutrition lever given their eating habits and training load.",
                    },
                    "tip": {
                        "type": "string",
                        "description": "ONE short, concrete, actionable tip (max ~20 words) specific to their eating habits answer.",
                    },
                    "recommended_meal_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "3-5 meal IDs picked ONLY from the provided meal catalog below (copy the id exactly, "
                            "never invent one). Favor pre/post-training meals on their training days; if they said "
                            "they struggle to eat enough, favor higher-calorie options; if they skip meals often, "
                            "favor faster/simpler ones."
                        ),
                    },
                    "recommended_supplement_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "0-3 supplement IDs picked ONLY from the provided supplement catalog below (copy the id "
                            "exactly, never invent one). Only suggest ones that genuinely fit this swimmer. Prefer the "
                            "strongest-evidence options (creatine has the best research for swimmers). Fine to return "
                            "an empty list if food already covers their needs, don't push supplements for the sake of it."
                        ),
                    },
                },
                "required": ["focus_note", "tip", "recommended_meal_ids"],
            },
            "dryland": {
                "type": "object",
                "description": "Which existing dryland library programs fit this swimmer, NOT newly written exercises.",
                "properties": {
                    "focus_note": {
                        "type": "string",
                        "description": "ONE short sentence (max ~20 words) on what their dryland work should prioritise this block (e.g. shoulder stability for a sprinter, hip mobility for breaststroke).",
                    },
                    "recommended_program_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": (
                            "1-3 program IDs picked ONLY from the provided dryland catalog below (copy the id "
                            "exactly, never invent one). Respect any stated limitations/injuries -- do not "
                            "recommend a program that would aggravate them."
                        ),
                    },
                    "note": {
                        "type": "string",
                        "description": "ONE short line (max ~15 words) on how these fit around their swim training this week.",
                    },
                },
                "required": ["focus_note", "recommended_program_ids", "note"],
            },
        },
        "required": ["overview", "days", "insights", "nutrition", "dryland"],
    },
}


EATING_HABITS_LABELS = {
    'undereating': "Struggles to eat enough, especially around training",
    'balanced': "Eats a pretty balanced diet already",
    'skip_meals': "Often skips meals / eats on the run",
    'structured': "Follows a fairly structured diet already",
}

COACHING_SITUATION_LABELS = {
    'none': "Not currently coached by anyone else",
    'club_want_extra': "Club-coached, wants extra edge on top of that",
    'club_want_structure': "Coached but wants structure for rest/extra days",
    'self_coached': "Fully self-coached, no other coach involved",
}


def generate_training_program(profile, meal_catalog, dryland_catalog, supplement_catalog, api_key, model,
                              adaptation=None):
    """Call Claude to turn a swimmer's onboarding answers into a structured
    week-calendar program (7 day boxes with real swim blocks) PLUS matched
    nutrition, supplement and dryland recommendations. `profile` is an
    AthleteProfile instance. `meal_catalog`/`dryland_catalog`/`supplement_catalog`
    are lists of {'id', 'name'/'title', 'category'} the model must pick real IDs
    from -- it never invents new meals, supplements or dryland programs, it only
    curates from what already exists (see routes_solo.onboarding for how the
    catalogs are built and how the returned IDs get validated). Returns
    {'ok': True, 'program': {...}} or {'ok': False, 'error': '...'}."""
    meal_lines = "\n".join(
        f"- id={m['id']} | {m['name']} | {m['category']}" for m in meal_catalog
    ) or "No meals available."
    dryland_lines = "\n".join(
        f"- id={p['id']} | {p['title']} | {p['category']}" for p in dryland_catalog
    ) or "No dryland programs available."
    supplement_lines = "\n".join(
        f"- id={s['id']} | {s['name']} | {s['category']} | evidence: {s.get('evidence', 'n/a')}"
        for s in supplement_catalog
    ) or "No supplements available."

    prompt = (
        "You are an experienced swim coach building a personalized weekly training calendar, plus "
        "matching nutrition and dryland guidance. Here is what the swimmer told you about themselves:\n\n"
        f"- Level: {profile.level or 'not specified'}\n"
        f"- Age: {profile.age or 'not specified'}\n"
        f"- Can train {profile.training_days_per_week or 'an unspecified number of'} days per week\n"
        f"- Self-rated fitness ability: {profile.fitness_ability or 'not specified'}\n"
        f"- Primary/favourite stroke: {profile.primary_stroke or 'not specified'}\n"
        f"- Swimmer type: {profile.swimmer_type or 'not specified'}\n"
        f"- Main goal: {profile.main_goal or 'not specified'}\n"
        f"- Current coaching situation: {COACHING_SITUATION_LABELS.get(profile.coaching_situation, 'not specified')}"
        + (f" -- what they work on with that coach: \"{profile.coaching_focus}\"" if profile.coaching_focus else "") + "\n"
        f"- Eating habits: {EATING_HABITS_LABELS.get(profile.eating_habits, 'not specified')}\n"
        + (f"- Injuries/limitations to respect: \"{profile.limitations}\"\n" if profile.limitations else "")
        + "\n"
        f"{_intensity_line(getattr(profile, 'intensity', 'normal'))}\n"
        f"{_tone_line(getattr(profile, 'coaching_tone', 'balanced'))} Apply this tone to the "
        "overview, coach notes, insights and nutrition/dryland notes.\n\n"
        + (f"{adaptation}\n\n" if adaptation else "")
        + "CRITICAL INTERVAL RULE: when a block's rest_type is 'interval', the time is a SEND-OFF -- "
        "the swimmer starts a new rep every X, and their actual rest is the send-off minus their swim "
        "time. It is NOT a rest duration. So every interval must comfortably exceed what THIS swimmer "
        "needs to swim the rep: a beginner swims 100m in roughly 2:10-2:30, so '4x100 on 1:30' would be "
        "physically impossible for them, while '4x100 on 2:45' works. Scale every send-off to the "
        "swimmer's realistic pace for their level, age and stroke, leaving sensible rest (beginners "
        "~15-30s per rep, advanced can be as low as 5-10s for threshold work). Use rest_type='rest' "
        "only for genuine recovery gaps between blocks.\n\n"
        "Call the create_training_program tool with a full 7-day week (Monday-Sunday). "
        "The number of non-rest days MUST exactly equal the days per week they said they can train. "
        "Give each training day a complete written session -- warm up, main set, cool down -- as "
        "concrete blocks (reps x distance, stroke, rest interval, short cue), with total volume and "
        "intensity pitched honestly at their level and fitness. Beginners get short sessions "
        "(under ~1500m) with generous rest; competitive swimmers get real volume and race-pace work. "
        "Non-training days are rest days. Let swimmer type shape the emphasis (e.g. a sprinter gets more "
        "speed/power work, a distance swimmer more aerobic volume, technique-focused gets more drill work).\n\n"
        f"Available meals to choose from for the nutrition section (pick real IDs only):\n{meal_lines}\n\n"
        f"Available supplements to choose from (pick real IDs only, or none):\n{supplement_lines}\n\n"
        f"Available dryland programs to choose from for the dryland section (pick real IDs only):\n{dryland_lines}\n\n"
        "STYLE: The swim blocks carry the detail -- keep all the text (overview, focus, coach notes, "
        "insights, nutrition/dryland notes) short and punchy. Quality over quantity: no filler, no "
        "repeating their answers back."
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        # 7 full days of structured blocks plus insights/nutrition/dryland is a long
        # response -- a small budget here truncates the tool JSON and the whole call fails.
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            tools=[PROGRAM_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "create_training_program"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        logger.exception('generate_training_program: API call failed')
        return {'ok': False, 'error': "Couldn't generate a program right now. Try again in a moment."}

    if response.stop_reason == 'max_tokens':
        logger.error('generate_training_program: response truncated at max_tokens')
        return {'ok': False, 'error': "Couldn't generate a program right now. Try again in a moment."}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use or not tool_use.input:
        logger.error('generate_training_program: no usable tool_use in response')
        return {'ok': False, 'error': "Couldn't generate a program right now. Try again in a moment."}

    program = tool_use.input
    for day in program.get('days', []):
        day['blocks'] = [b for b in (_clamp_block(r) for r in day.get('blocks', [])) if b is not None]
        day['total'] = sum(b['reps'] * b['dist'] for b in day['blocks'])
    if not program.get('days'):
        logger.error('generate_training_program: program came back with no days')
        return {'ok': False, 'error': "Couldn't generate a program right now. Try again in a moment."}

    # The model is instructed to only pick real IDs from the catalogs we gave it,
    # but never trust that blindly -- drop anything hallucinated before it can
    # turn into a dead link on the program page.
    valid_meal_ids = {m['id'] for m in meal_catalog}
    valid_dryland_ids = {p['id'] for p in dryland_catalog}
    valid_supplement_ids = {s['id'] for s in supplement_catalog}

    nutrition = program.pop('nutrition', None) or {}
    nutrition['recommended_meal_ids'] = [
        mid for mid in nutrition.get('recommended_meal_ids', []) if mid in valid_meal_ids
    ]
    nutrition['recommended_supplement_ids'] = [
        sid for sid in nutrition.get('recommended_supplement_ids', []) if sid in valid_supplement_ids
    ]

    dryland = program.pop('dryland', None) or {}
    dryland['recommended_program_ids'] = [
        pid for pid in dryland.get('recommended_program_ids', []) if pid in valid_dryland_ids
    ]

    return {
        'ok': True,
        'program': _humanize(program),
        'nutrition': _humanize(nutrition),
        'dryland': _humanize(dryland),
    }


INSIGHT_TOOL_SCHEMA = {
    "name": "give_checkin_insight",
    "description": "Respond to a swimmer's daily training check-in with a short, specific insight.",
    "input_schema": {
        "type": "object",
        "properties": {
            "insight": {
                "type": "string",
                "description": (
                    "1-2 short sentences (max ~30 words total) reacting to their words and any visible trend. "
                    "One concrete takeaway. No platitudes, no restating what they said."
                ),
            },
        },
        "required": ["insight"],
    },
}


def generate_checkin_insight(profile, feeling_rating, notes, recent_checkins, api_key, model, tone='encouraging',
                              fatigue_rating=None, sleep_quality=None):
    """Call Claude to respond to a single check-in with a short personalized insight.
    `recent_checkins` is a list of {'date', 'feeling_rating', 'fatigue_rating', 'sleep_quality',
    'notes'} dicts, most recent last, excluding the one just submitted. `fatigue_rating`/
    `sleep_quality` are today's optional 1-5 taps (None if skipped) -- early signals of a
    plateau that often show up before the stopwatch does. `tone` defaults to encouraging
    since this talks straight to the swimmer. Returns a plain string insight, or a friendly
    fallback string on any failure -- never raises."""
    def _fmt(c):
        extra = []
        if c.get('fatigue_rating'):
            extra.append(f"fatigue {c['fatigue_rating']}/5")
        if c.get('sleep_quality'):
            extra.append(f"sleep {c['sleep_quality']}/5")
        extra_str = f" ({', '.join(extra)})" if extra else ""
        return f"- {c['date']}: felt {c['feeling_rating']}/5{extra_str}, \"{c['notes']}\""

    history_lines = "\n".join(_fmt(c) for c in recent_checkins) or "No previous check-ins."

    today_extra = []
    if fatigue_rating:
        today_extra.append(f"fatigue {fatigue_rating}/5")
    if sleep_quality:
        today_extra.append(f"sleep {sleep_quality}/5")
    today_extra_str = f" ({', '.join(today_extra)})" if today_extra else ""

    prompt = (
        "You are a swim coach reviewing a swimmer's daily training check-in.\n\n"
        f"{_tone_line(tone)}\n\n"
        f"Swimmer level: {profile.level or 'not specified'}, goal: {profile.main_goal or 'not specified'}.\n\n"
        f"Recent check-in history:\n{history_lines}\n\n"
        f"Today's check-in: felt {feeling_rating}/5{today_extra_str}, \"{notes}\"\n\n"
        "Call the give_checkin_insight tool with your response."
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=512,
            tools=[INSIGHT_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "give_checkin_insight"},
            messages=[{"role": "user", "content": prompt}],
        )
        tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
        if tool_use and tool_use.input and tool_use.input.get('insight'):
            return _humanize(tool_use.input['insight'])
    except Exception:
        pass

    return "Logged, keep it up. Come back tomorrow and check in again so I can start building a trend to learn from."


PROGRESS_INSIGHT_TOOL_SCHEMA = {
    "name": "give_progress_insight",
    "description": "Explain a swimmer's progression trend from their computed training digest.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": (
                    "1-2 tight sentences (max ~30 words) on the single most important trend in the data -- "
                    "improving, plateaued, or slipping -- and by roughly how much. Talk directly to the swimmer as 'you'."
                ),
            },
            "likely_cause": {
                "type": "string",
                "description": (
                    "ONE sentence (max ~25 words) on the most likely driver visible in the data (e.g. training "
                    "load dropped, fatigue/sleep trending down, or simply early in a new block). Don't invent a "
                    "cause the data doesn't support -- say the data doesn't show a clear cause if it doesn't."
                ),
            },
            "suggested_focus": {
                "type": "string",
                "description": "ONE concrete, actionable suggestion (max ~20 words) for what to focus on next.",
            },
        },
        "required": ["summary", "likely_cause", "suggested_focus"],
    },
}


def generate_progress_insight(digest, api_key, model, tone='encouraging'):
    """Call Claude to explain a single swimmer's progression digest (see
    routes.personal_bests for how it's built -- rolling-window time trends,
    training load, consistency, PB recency, check-in correlation). Talks
    directly to the swimmer, so tone defaults to encouraging same as
    generate_checkin_insight. Returns {'ok': True, 'insight': {...}} or
    {'ok': False, 'error': '...'} -- never raises."""
    prompt = (
        "You are a swim coach explaining a swimmer's own progression data back to them.\n\n"
        f"{_tone_line(tone)}\n\n"
        f"Their training digest:\n{digest}\n\n"
        "Call the give_progress_insight tool. Be specific and honest -- cite the actual numbers/trends "
        "above, don't invent anything the data doesn't support. If the data is too thin for a real "
        "trend, say so plainly rather than manufacturing one."
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            tools=[PROGRESS_INSIGHT_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "give_progress_insight"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        logger.exception('generate_progress_insight: API call failed')
        return {'ok': False, 'error': "Couldn't generate an analysis right now. Try again in a moment."}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use or not tool_use.input:
        return {'ok': False, 'error': "Couldn't generate an analysis right now. Try again in a moment."}

    return {'ok': True, 'insight': _humanize(tool_use.input)}


WEEKLY_REVIEW_TOOL_SCHEMA = {
    "name": "give_weekly_review",
    "description": "Narrate a swimmer's automatic weekly progress review from the computed report.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {
                "type": "string",
                "description": (
                    "ONE sentence (max ~18 words) summing up the week, talking straight to the swimmer as 'you'. "
                    "Lead with the single biggest signal."
                ),
            },
            "detail": {
                "type": "string",
                "description": (
                    "2-3 short sentences (max ~50 words) on what drove the week: cite the real numbers from "
                    "the report (volume change, PBs, fatigue). No filler, nothing the data doesn't support."
                ),
            },
            "next_week": {
                "type": "string",
                "description": "ONE sentence (max ~20 words) on what next week looks like and why, matching the report's plan.",
            },
        },
        "required": ["headline", "detail", "next_week"],
    },
}


def generate_weekly_review(digest, api_key, model, tone='encouraging'):
    """Narrate the deterministic weekly report (athlete_model.build_weekly_report)
    in a human coach voice. Returns {'ok': True, 'review': {...}} or
    {'ok': False, 'error': ...} -- never raises."""
    prompt = (
        "You are a swim coach writing a swimmer's automatic weekly review from their computed report.\n\n"
        f"{_tone_line(tone)}\n\n"
        f"This week's computed report:\n{digest}\n\n"
        "Call the give_weekly_review tool. Be specific, cite the actual numbers, and never invent a trend "
        "the report doesn't show. If confidence is low, say the picture is still building."
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            tools=[WEEKLY_REVIEW_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "give_weekly_review"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        logger.exception('generate_weekly_review: API call failed')
        return {'ok': False, 'error': "Couldn't write the review right now."}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use or not tool_use.input:
        return {'ok': False, 'error': "Couldn't write the review right now."}

    return {'ok': True, 'review': _humanize(tool_use.input)}


# ============================================================
# PARENT-FACING: AI-drafted weekly digest (coach-reviewed before it's ever
# shown on the parent dashboard -- see routes_internal.digest_generate, the
# Render Cron entry point, and routes_coach's digest review queue).
# ============================================================

DIGEST_TOOL_SCHEMA = {
    "name": "write_parent_digest",
    "description": "Draft a short weekly update for a swimmer's parent covering attendance, PBs and training this week.",
    "input_schema": {
        "type": "object",
        "properties": {
            "headline": {
                "type": "string",
                "description": "ONE sentence (max ~18 words): the single most relevant thing about this swimmer's week.",
            },
            "body": {
                "type": "string",
                "description": (
                    "2-4 sentences (max ~70 words) covering attendance, any new PBs, and how training's "
                    "going this week. Plain and factual, talking about the swimmer in the third person to "
                    "their parent."
                ),
            },
            "next_up": {
                "type": "string",
                "description": (
                    "Optional: ONE short sentence naming the next upcoming squad event, only if one was "
                    "given in the input. Leave empty if none was given."
                ),
            },
        },
        "required": ["headline", "body"],
    },
}


def generate_parent_digest(swimmer_name, athlete_state, week_attendance, tone, api_key, model):
    """Draft a coach-reviewed weekly update for one swimmer's parent.
    `athlete_state` is the cached athlete_model.get_state(swimmer_id) dict
    (trend, pbs, events -- reused as-is, not recomputed here). `week_attendance`
    is {'attended', 'scheduled', 'no_session_scheduled'} for the week just
    finished (a bye week reads as "no session scheduled", not a bad week).
    This is a new, standalone call path, not a variant of generate_weekly_review
    or generate_progress_insight, so it repeats the low-week and
    back-half-slower guardrails explicitly rather than assuming they carry
    over from elsewhere. Never raises -- returns {'ok': False, 'error': ...}
    on any failure, otherwise {'ok': True, 'headline', 'body', 'next_up'}."""
    athlete_state = athlete_state or {}
    pbs = athlete_state.get('pbs') or {}
    new_pbs = []
    for key, p in pbs.items():
        if not isinstance(p, dict):
            continue
        days_ago = p.get('days_ago') if p.get('days_ago') is not None else 999
        if days_ago > 7:
            continue
        # Tolerate a not-yet-recomputed cached row from before PBs were keyed
        # by (event, pool) -- key was the bare event name and the value had no
        # event/pool fields. Derive from the key so this never renders
        # "None (Nonem)" while waiting for the swimmer's next log to refresh
        # the cache; self-heals within update_athlete_state's normal cadence.
        event = p.get('event') or (str(key).split('|')[0] if '|' in str(key) else key)
        pool = p.get('pool') or (str(key).split('|')[1] if '|' in str(key) else None)
        pool_label = f' ({pool}m)' if pool else ''
        new_pbs.append(f"{event}{pool_label}: {p.get('time')}")
    events = athlete_state.get('events') or {}
    trend_lines = [
        f"{event}: {data.get('direction')} ({data.get('change_pct')}%)"
        for event, data in events.items()
    ]

    if week_attendance.get('no_session_scheduled'):
        attendance_line = "No squad session was scheduled this week (a bye/off week), so there's nothing to report on attendance."
    else:
        attendance_line = (
            f"Attended {week_attendance.get('attended', 0)} of "
            f"{week_attendance.get('scheduled', 0)} scheduled squad sessions this week."
        )

    prompt = (
        "You are a swim coach's assistant drafting a short weekly update for a swimmer's parent. "
        "A human coach will review this before the parent ever sees it, so be accurate and plain, never "
        "speculative or dramatic.\n\n"
        f"{_tone_line(tone)}\n\n"
        f"Swimmer: {swimmer_name}\n"
        f"{attendance_line}\n"
        f"New personal bests this week: {'; '.join(new_pbs) if new_pbs else 'None'}\n"
        f"Longer-term event trends: {'; '.join(trend_lines) if trend_lines else 'Not enough data yet'}\n"
        f"Overall training trend (this swimmer's own model, not a comparison to anyone else): "
        f"{athlete_state.get('trend') or 'not enough data yet'} "
        f"({athlete_state.get('trend_reason') or 'still building a picture'})\n\n"
        "RULES SPECIFIC TO THIS UPDATE:\n"
        "- If attendance was low or there's nothing notable this week, do not manufacture positivity or "
        "imply concern. State what happened plainly and let the coach's own judgment carry any real "
        "concern in person -- this draft is not the place to raise an alarm.\n"
        "- A slower back half or a single off day is completely normal, not a red flag. Never frame it "
        "as one, even if the data mentions a slip.\n"
        "- Don't invent PBs, events, or attendance numbers that weren't given above.\n"
        "- Write about the swimmer in the third person to their parent (e.g. 'Jamie had a solid week'), "
        "never talk directly to the swimmer as 'you'.\n\n"
        "Call the write_parent_digest tool with your draft."
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=512,
            tools=[DIGEST_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "write_parent_digest"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        logger.exception('generate_parent_digest: API call failed')
        return {'ok': False, 'error': "Couldn't draft the digest right now."}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use or not tool_use.input or not tool_use.input.get('headline') or not tool_use.input.get('body'):
        return {'ok': False, 'error': "Couldn't draft the digest right now."}

    result = _humanize(tool_use.input)
    return {
        'ok': True,
        'headline': result.get('headline'),
        'body': result.get('body'),
        'next_up': result.get('next_up') or None,
    }


# ============================================================
# COACH-TIER AI: squad performance insights for the coach dashboard
# ============================================================

SQUAD_INSIGHTS_TOOL_SCHEMA = {
    "name": "give_squad_insights",
    "description": "Analyze a swim squad's recent training data and give the coach actionable insights.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": (
                    "1-2 tight sentences (max ~35 words) on how the squad is trending. Lead with the single "
                    "most important signal in the data. No filler, no listing every swimmer."
                ),
            },
            "swimmer_flags": {
                "type": "array",
                "description": (
                    "Swimmers who need the coach's attention this week, most urgent first. "
                    "Include at-risk swimmers (inactive, low attendance, injured) AND standouts "
                    "worth stretching. Skip swimmers who are simply fine."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Swimmer's name exactly as given in the data."},
                        "kind": {
                            "type": "string",
                            "enum": ["at_risk", "watch", "standout"],
                            "description": "at_risk = needs intervention, watch = keep an eye on, standout = performing above the group.",
                        },
                        "reason": {
                            "type": "string",
                            "description": "ONE sentence (max ~20 words): the data point + the action. e.g. 'No swim in 12 days. Check in.'",
                        },
                    },
                    "required": ["name", "kind", "reason"],
                },
            },
            "focus_suggestions": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "2-3 short, concrete next-focus suggestions (each max ~15 words), each tied to something "
                    "visible in the data (a stroke nobody logs, attendance dips, volume plateaus)."
                ),
            },
        },
        "required": ["summary", "swimmer_flags", "focus_suggestions"],
    },
}


def generate_squad_insights(squad_name, swimmers_digest, api_key, model, tone='balanced'):
    """Call Claude to analyze a squad's recent training/attendance digest and
    return coaching insights. `swimmers_digest` is a list of per-swimmer dicts
    built in routes_coach.coach_pro_ai_insights. `tone` is one of
    encouraging/balanced/direct. Returns {'ok': True, 'insights': {...}} or
    {'ok': False, 'error': '...'} -- never raises."""
    lines = []
    for s in swimmers_digest:
        lines.append(
            f"- {s['name']}: {s['sessions_60d']} sessions / {s['distance_60d']}m in last 60 days; "
            f"last active {s['last_active'] or 'never'}; attendance {s['attendance']}; "
            f"best times: {', '.join(s['best_times']) or 'none logged'}"
            + (f"; STATUS FLAG: {s['status_flag']}" if s.get('status_flag') else "")
        )

    prompt = (
        f"You are an experienced swim coach's assistant reviewing the squad \"{squad_name}\".\n\n"
        f"{_tone_line(tone)}\n\n"
        f"Recent data for each swimmer:\n" + "\n".join(lines) + "\n\n"
        "Call the give_squad_insights tool with your analysis. Be specific and honest -- "
        "cite the actual numbers and names above. If the data is thin, say so plainly in the "
        "summary rather than inventing trends. Keep everything terse: quality over quantity, no filler."
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            tools=[SQUAD_INSIGHTS_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "give_squad_insights"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        logger.exception('generate_squad_insights: API call failed')
        return {'ok': False, 'error': "Couldn't generate insights right now. Try again in a moment."}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use or not tool_use.input:
        return {'ok': False, 'error': "Couldn't generate insights right now. Try again in a moment."}

    return {'ok': True, 'insights': _humanize(tool_use.input)}


# ============================================================
# COACH-TIER AI: set generator grounded in elite training methodology
# ============================================================

# Compressed knowledge base of how elite programs actually structure training.
# Injected into the set-generator prompt so generated sets follow real
# methodology instead of generic filler.
ELITE_METHODOLOGY_NOTES = """
Methodology reference (draw on whichever matches the request):

- Bowman-style aerobic engine (Michael Phelps' program at NBAC): very high aerobic base,
  heavy IM and kick emphasis year-round, long freestyle/IM ladders at threshold, descend
  patterns, negative-split discipline. Typical main sets 2000-4000m for seniors, e.g.
  5x400 IM descend, 8x200 free on tight intervals holding pace, 1000+ of quality kick.
- USRPT / race-pace (Rushall): short rest, exact race-pace repeats, stop-when-you-fail.
  E.g. 20x50 free at 100-pace on 0:50, 30x25 fly at 50-pace. Low volume, maximal specificity.
- Sprint/power (e.g. Bob Gillett / Magnussen-era Australian sprint work): low volume, full
  recovery, maximal velocity 15-25m efforts, resisted/assisted work, dive 25s, broken 50s
  with 10-15s rest. Quality over volume, long rest (2:00+ between max efforts).
- Threshold / CSS (British Swimming style): sustained sub-threshold repeats with short rest,
  e.g. 3x(4x100) at CSS with 0:15 rest, step-test informed pacing, controlled heart rate.
- Season phasing: early season = aerobic base + technique volume; mid season = threshold and
  quality race-pace blocks; taper = drop volume ~40-60%, keep intensity sharp with broken
  race-pace and speed touches; post-long-course transition = lower volume, stroke variety,
  drill emphasis, rebuild aerobic base gently.
- Age-group swimmers: cap volume sensibly, more drill/kick variety, avoid heavy lactate work.
"""

COACH_SET_TOOL_SCHEMA = {
    "name": "create_coach_set",
    "description": "Write a structured swim set for a coach, grounded in elite training methodology.",
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Short punchy title for the set, e.g. 'Bowman IM Engine 3k'."},
            "description": {
                "type": "string",
                "description": "ONE short sentence: what this set trains + the methodology it draws on. Max ~20 words.",
            },
            "session_type": {"type": "string", "description": "Short label, e.g. Endurance, Speed, Race pace, Technique."},
            "category": {
                "type": "string",
                "enum": ["Fast", "Easy", "Heart Rate", "Drill", "Lactate", "Fitness", "Open Water", "Triathlon"],
                "description": "Library category that best fits.",
            },
            "blocks": {
                "type": "array",
                "description": "The full written session in order: warm up, pre set, main set(s), cool down.",
                "items": SWIM_BLOCK_ITEM_SCHEMA,
            },
        },
        "required": ["name", "description", "blocks"],
    },
}


# Realistic pool volume per minute of session time (INCLUDING rest, warm-up and
# cool-down), by squad level. Elite squads genuinely cover far more ground than
# an age-group group in the same hour -- a 2-hour national session is 6-9k,
# whereas nobody is writing a 750m senior main set. Scaling the rate by level is
# what lets a 90-120 min elite session reach the 7k a coach actually expects.
COACH_SET_VOLUME_RATES = {
    'age_group': (25, 40),   # 12 & under: lots of rest, drill, technique
    'junior': (38, 55),      # 13-16
    'senior': (48, 68),      # senior club (default)
    'elite': (60, 90),       # national / elite
}


def _coach_set_level_key(level_text):
    lt = (level_text or '').lower()
    if 'age group' in lt or '12' in lt or 'novice' in lt or 'learn' in lt:
        return 'age_group'
    if 'junior' in lt or '13' in lt or '16' in lt or 'youth' in lt:
        return 'junior'
    if 'elite' in lt or 'national' in lt or 'advanced' in lt:
        return 'elite'
    return 'senior'


def _coach_set_volume_target(level_text, minutes):
    """Total-session volume range (metres, rounded to 100) for a level+duration,
    used to anchor the generator so it stops under-producing thin sets."""
    lo_rate, hi_rate = COACH_SET_VOLUME_RATES[_coach_set_level_key(level_text)]
    lo = int(round(minutes * lo_rate / 100.0)) * 100
    hi = int(round(minutes * hi_rate / 100.0)) * 100
    return lo, hi


def generate_coach_set(params, api_key, model):
    """Call Claude to write a coach's set from structured parameters, grounded
    in the elite-methodology notes above. `params` keys: focus, style,
    season_phase, level, pool, duration_minutes. Returns {'ok': True,
    'set': {...}} or {'ok': False, 'error': '...'} -- never raises."""
    focus = params.get('focus') or "coach's choice"
    try:
        minutes = int(float(params.get('duration_minutes') or 60))
    except (ValueError, TypeError):
        minutes = 60
    minutes = max(20, min(minutes, 180))
    level = params.get('level') or 'senior club'
    vol_lo, vol_hi = _coach_set_volume_target(level, minutes)
    prompt = (
        "You are an elite swim coach's assistant writing tomorrow's set.\n"
        f"{ELITE_METHODOLOGY_NOTES}\n"
        "The coach wants:\n"
        f"- Training focus: {focus}\n"
        f"- Methodology style: {params.get('style') or 'best fit for the focus'}\n"
        f"- Season phase: {params.get('season_phase') or 'mid season'}\n"
        f"- Squad level: {level}\n"
        f"- Pool: {params.get('pool') or '25m'}\n"
        f"- Session length: about {minutes} minutes\n\n"
        "Call the create_coach_set tool with one complete session: warm up, main work, cool down. "
        f"TARGET TOTAL VOLUME: {vol_lo}-{vol_hi} m across all blocks combined. This is the amount this "
        "level genuinely covers in the session length (including rest, warm-up and cool-down). Land inside "
        "this range: do NOT come in far under it (a thin 750m senior session is wrong), and don't blow "
        "past it either. Build the main set(s) up to the volume the range demands rather than writing one "
        "small set. "
        "Intervals must be swimmable for the level. "
        "Remember rest_type='interval' means a SEND-OFF (the swimmer leaves every X; actual rest is "
        "whatever's left after the swim), so every send-off must exceed the level's realistic swim "
        "time for the rep with sensible rest to spare. "
        "Use the note field for cues like 'descend 1-4' or 'hold 200 race pace'. Stay true to the "
        "requested methodology -- a USRPT set should look nothing like a Bowman aerobic set. (USRPT/pure "
        "sprint work is deliberately lower volume; if that's the style, aim near the lower bound.)"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            tools=[COACH_SET_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "create_coach_set"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        logger.exception('generate_coach_set: API call failed')
        return {'ok': False, 'error': "Couldn't generate a set right now. Try again in a moment."}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use or not tool_use.input:
        return {'ok': False, 'error': "Couldn't generate a set right now. Try again in a moment."}

    data = tool_use.input
    blocks = [b for b in (_clamp_block(r) for r in data.get('blocks', [])) if b is not None]
    if not blocks:
        return {'ok': False, 'error': "The generated set came back empty. Try again."}

    # Realism pass: even with the prompt rules, models occasionally write a
    # send-off the squad can't make. Fix intervals deterministically against
    # the pace model rather than shipping an impossible set.
    import swim_logic
    level_text = (params.get('level') or '').lower()
    if any(w in level_text for w in ('beginner', 'learn', 'novice')):
        check_level = 'Beginner'
    elif any(w in level_text for w in ('age', 'junior', 'youth', 'intermediate', 'club')):
        check_level = 'Intermediate'
    elif 'advanced' in level_text:
        check_level = 'Advanced'
    else:
        check_level = 'Competitive'
    blocks, _fixes = swim_logic.validate_day_blocks(blocks, level=check_level)

    return {'ok': True, 'set': {
        'name': (data.get('name') or 'AI generated set').strip()[:100],
        'description': (data.get('description') or '').strip(),
        'session_type': (data.get('session_type') or 'Training').strip()[:50],
        'category': data.get('category') if data.get('category') in (
            'Fast', 'Easy', 'Heart Rate', 'Drill', 'Lactate', 'Fitness', 'Open Water', 'Triathlon'
        ) else 'Fitness',
        'blocks': blocks,
    }}


# ============================================================
# COACH-TIER AI: on-demand dryland content search (live web)
#
# Two-call pattern (see docs/plans/2026-07-19-coach-dryland-content-agent-design.md):
# Call 1 lets Claude search/fetch the open web freely -- tool_choice is left
# at its default ("auto") so it isn't forced into a tool from turn 1, which
# would skip the web_search/web_fetch step entirely (the whole point of this
# feature). Call 2 takes Call 1's plain-text findings and forces structured
# extraction via tool_choice, same pattern as every other generation path in
# this file. This is the one feature in the app where output isn't grounded
# in a pre-vetted catalog, so allowed_domains + mandatory coach review are
# load-bearing, not optional -- see the design doc's safety guardrails.
# ============================================================

# Curated allowlist for web_search -- reputable research, S&C and swimming
# sources only, never the open web. FLAG FOR REVIEW: this is a starting
# list, not exhaustive or final; revisit as coaches actually use the feature.
DRYLAND_ALLOWED_DOMAINS = [
    "ncbi.nlm.nih.gov",        # PubMed Central -- open-access research papers
    "pubmed.ncbi.nlm.nih.gov",
    "scholar.google.com",      # research aggregator
    "nsca.com",                # National Strength and Conditioning Association
    "usaswimming.org",
    "britishswimming.org",
    "youtube.com",             # metadata only -- see note in the prompt below
    "stanford.edu",            # university athletics program with published swim S&C material
]

DRYLAND_TOOL_SCHEMA = {
    "name": "extract_dryland_sets",
    "description": (
        "Extract 1-3 structured dryland/conditioning sessions from research findings already "
        "gathered, each grounded in a real source found during that research."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "description": (
                    "1-3 candidate sessions, best match first. Never invent a candidate that wasn't "
                    "actually found in the research findings above."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Short title for the session, e.g. 'Shoulder Prehab Circuit (NSCA)'."},
                        "description": {
                            "type": "string",
                            "description": "ONE short sentence: what this trains and why it fits the requested focus/age/level. Max ~25 words.",
                        },
                        "category": {
                            "type": "string",
                            "enum": ["Strength", "Mobility", "Core"],
                            "description": "Library category that best fits this session's primary emphasis.",
                        },
                        "source_url": {"type": "string", "description": "The exact URL this candidate was found at."},
                        "source_name": {
                            "type": "string",
                            "description": "Human-readable source, e.g. 'NSCA', 'PubMed', 'USA Swimming', or the YouTube channel name.",
                        },
                        "source_type": {
                            "type": "string",
                            "enum": ["research_paper", "youtube_video", "org_program", "other"],
                            "description": (
                                "research_paper/org_program sources are safe to extract exercise detail "
                                "from directly. youtube_video sources only ever had title/description "
                                "metadata available (web_fetch cannot read a video's transcript) -- treat "
                                "as 'a video to watch', not a page you read exercises off of."
                            ),
                        },
                        "exercises": {
                            "type": "array",
                            "description": (
                                "The actual exercises. For a youtube_video source with no readable "
                                "description detail, this may be a single entry pointing the coach to "
                                "watch the video rather than fabricated exercise specifics."
                            ),
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string", "description": "Exercise name, e.g. 'Band external rotation'."},
                                    "sets": {"type": "string", "description": "Number of sets, e.g. '3'. Empty if not specified in the source."},
                                    "reps": {"type": "string", "description": "Reps or duration, e.g. '10-12' or '30s hold'. Empty if not specified."},
                                    "rest": {"type": "string", "description": "Rest between sets, e.g. '30-45s'. Empty if not specified."},
                                    "notes": {"type": "string", "description": "Short cue or form note. Empty if none."},
                                },
                                "required": ["name"],
                            },
                        },
                    },
                    "required": ["title", "description", "category", "source_url", "source_name", "exercises"],
                },
            },
        },
        "required": ["candidates"],
    },
}


def fetch_dryland_content(params, api_key, model):
    """On-demand, coach-triggered live web search for dryland/conditioning
    content. `params` keys: focus, age_range (explicit, e.g. '13-14' or
    'senior' -- never inferred from context), level. Two-call pattern: Call 1
    lets Claude search/fetch freely (tool_choice left at default), Call 2
    forces structured extraction of Call 1's findings via tool_choice.
    Returns {'ok': True, 'candidates': [...]} or {'ok': False, 'error':
    '...'} -- never raises. Never saves or assigns anything itself -- purely
    returns candidates for a coach to review."""
    focus = (params.get('focus') or '').strip() or "general dryland conditioning"
    age_range = (params.get('age_range') or '').strip() or "not specified -- keep it general and age-appropriate"
    level = (params.get('level') or '').strip() or "club level"

    research_prompt = (
        "You are a swim coach's assistant researching dryland/conditioning content on the open web. "
        "Search for and review real, credible sources: university/research papers (many swim-specific "
        "strength & conditioning papers are open-access on PubMed/NCBI), known reputable S&C "
        "organizations (e.g. NSCA), swimming federations (USA Swimming, British Swimming), and YouTube "
        "videos.\n\n"
        f"Coach's request:\n- Focus: {focus}\n- Age range: {age_range}\n- Level: {level}\n\n"
        "Find 1-3 real candidate sessions or well-described exercise sets that fit this focus, age range "
        "and level. Note: web_fetch on a YouTube URL only ever returns page metadata (title/description), "
        "never the video's transcript -- so treat a YouTube hit as a video worth pointing the coach to "
        "watch, not as a source you can extract detailed exercise prescriptions from. Only pull specific "
        "sets/reps/rest detail from sources whose page text you actually fetched (research papers, org "
        "pages). Age-appropriateness matters on safety grounds: keep youth/age-group recommendations "
        "conservative on plyometric and loaded work.\n\n"
        "When you're done researching, write a plain-text summary of what you found: for each candidate, "
        "its exact source URL, the source name, and the exercise detail (sets/reps/rest) you were actually "
        "able to read from the page. Don't fabricate detail you didn't find."
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        research_response = client.messages.create(
            model=model,
            # Generous headroom: fetched page content (research papers can be
            # long) plus multiple search/fetch round trips can otherwise eat
            # the whole budget before the model writes its findings summary,
            # leaving findings_text empty and a misleading "nothing found" error
            # even when real content was actually retrieved.
            max_tokens=8192,
            tools=[
                # allowed_domains on BOTH tools, not just web_search -- without
                # it here, a search hit on an allowlisted page could link out
                # to an arbitrary site and web_fetch would happily follow it,
                # quietly defeating the "never the open web" guarantee this
                # feature depends on for safety.
                {"type": "web_search_20260209", "name": "web_search", "allowed_domains": DRYLAND_ALLOWED_DOMAINS},
                {"type": "web_fetch_20260209", "name": "web_fetch", "allowed_domains": DRYLAND_ALLOWED_DOMAINS},
            ],
            messages=[{"role": "user", "content": research_prompt}],
        )
    except Exception:
        logger.exception('fetch_dryland_content: research call failed')
        return {'ok': False, 'error': "Couldn't search the web right now. Try again in a moment."}

    findings_text = "\n".join(
        block.text for block in research_response.content
        if getattr(block, 'type', None) == 'text' and getattr(block, 'text', None)
    ).strip()
    if not findings_text:
        return {'ok': False, 'error': "No dryland content found for that focus. Try broadening it or picking a different focus."}

    extract_prompt = (
        "Here are a swim coach's research findings for a dryland content search:\n\n"
        f"{findings_text}\n\n"
        "Call the extract_dryland_sets tool with 1-3 candidate sessions drawn ONLY from the findings "
        "above. Never invent a source or exercise detail that isn't in the findings. If a candidate is a "
        "YouTube video with no readable exercise detail, mark it source_type='youtube_video' and give a "
        "single exercises entry pointing the coach to watch the video rather than fabricating sets/reps."
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        extract_response = client.messages.create(
            model=model,
            max_tokens=4096,
            tools=[DRYLAND_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "extract_dryland_sets"},
            messages=[{"role": "user", "content": extract_prompt}],
        )
    except Exception:
        logger.exception('fetch_dryland_content: extraction call failed')
        return {'ok': False, 'error': "Found some content but couldn't process it. Try again in a moment."}

    tool_use = next((c for c in extract_response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use or not tool_use.input:
        return {'ok': False, 'error': "Found some content but couldn't process it. Try again in a moment."}

    raw_candidates = tool_use.input.get('candidates') or []
    candidates = []
    for c in raw_candidates:
        title = str(c.get('title') or '').strip()
        source_url = str(c.get('source_url') or '').strip()
        exercises = []
        for ex in (c.get('exercises') or []):
            name = str(ex.get('name') or '').strip()
            if not name:
                continue
            exercises.append({
                'name': name[:100],
                'sets': str(ex.get('sets') or '').strip()[:20],
                'reps': str(ex.get('reps') or '').strip()[:30],
                'rest': str(ex.get('rest') or '').strip()[:30],
                'notes': str(ex.get('notes') or '').strip()[:200],
            })
        if not title or not source_url or not exercises:
            continue
        candidates.append({
            'title': title[:150],
            'description': str(c.get('description') or '').strip()[:300],
            'category': c.get('category') if c.get('category') in ('Strength', 'Mobility', 'Core') else 'Strength',
            'source_url': source_url[:500],
            'source_name': str(c.get('source_name') or '').strip()[:100] or 'Unknown source',
            'source_type': c.get('source_type') if c.get('source_type') in (
                'research_paper', 'youtube_video', 'org_program', 'other'
            ) else 'other',
            'exercises': exercises,
        })
        if len(candidates) >= 3:
            break

    if not candidates:
        return {'ok': False, 'error': "No dryland content found for that focus. Try broadening it or picking a different focus."}

    return {'ok': True, 'candidates': _humanize(candidates)}


# ============================================================
# COACH-TIER AI: read a test-set results board into per-swimmer times
# ============================================================

TEST_RESULTS_TOOL_SCHEMA = {
    "name": "log_test_results",
    "description": "Read swimmers' names and times off a photo of a test set results board or notebook.",
    "input_schema": {
        "type": "object",
        "properties": {
            "test_label": {
                "type": "string",
                "description": "What the test was, as written or implied, e.g. '5x100 FR max', '200 IM time trial'.",
            },
            "event": {
                "type": "string",
                "description": (
                    "The single event these results map to, normalized like '100m Freestyle', "
                    "'200m IM', '50m Butterfly'. Use the per-rep distance for multi-rep tests "
                    "(5x100 max -> '100m Freestyle')."
                ),
            },
            "results": {
                "type": "array",
                "description": "One entry per swimmer whose results are readable.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": (
                                "The swimmer's name. If it clearly matches a roster name you were "
                                "given, return the roster name EXACTLY as provided; otherwise "
                                "return the name as written on the board."
                            ),
                        },
                        "times": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "All of this swimmer's times in order, normalized to 'M:SS.ss' or "
                                "'SS.ss' -- e.g. '1:02.5', '58.9'. Coaches write 62.5 for 1:02.5; "
                                "convert anything over 60 seconds to minutes notation."
                            ),
                        },
                        "note": {"type": "string", "description": "Anything else written next to this swimmer. Empty if none."},
                    },
                    "required": ["name", "times"],
                },
            },
        },
        "required": ["results"],
    },
}


def extract_test_results_from_image(image_bytes, roster_names, api_key, model):
    """Read a photo of a test-set results board and return per-swimmer times,
    matching names against `roster_names` where possible. Returns {'ok': True,
    'test_label', 'event', 'results': [{name, times, note, matched}]} or
    {'ok': False, 'error': '...'} -- never raises."""
    normalized = normalize_image(image_bytes)
    if normalized is None:
        return {'ok': False, 'error': "That doesn't look like a photo. Try again."}

    roster_line = ", ".join(roster_names) if roster_names else "(no roster provided)"
    prompt = (
        "This is a photo of a swim coach's test set results -- swimmers' names with their times, "
        "written on a whiteboard, clipboard or notebook.\n\n"
        f"The squad roster is: {roster_line}\n\n"
        "Call the log_test_results tool with every swimmer's times you can read. Match written "
        "names (often first names, surnames or nicknames) to the roster: if a board name clearly "
        "corresponds to one roster name, return that roster name exactly as given above. Times may "
        "be shorthand: '62.5' means 1:02.5, '1.05.3' means 1:05.3. Keep each swimmer's times in the "
        "order written. If the photo has no readable results, return an empty results array."
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        b64 = base64.standard_b64encode(normalized).decode('utf-8')
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            tools=[TEST_RESULTS_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "log_test_results"},
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
    except Exception:
        logger.exception('extract_test_results_from_image: API call failed')
        return {'ok': False, 'error': "Couldn't read that photo. Try again or enter times manually."}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use or not tool_use.input:
        return {'ok': False, 'error': "Couldn't read that photo. Try again or enter times manually."}

    data = tool_use.input
    roster_set = set(roster_names or [])
    results = []
    for r in data.get('results', []):
        name = str(r.get('name') or '').strip()
        times = [str(t).strip() for t in (r.get('times') or []) if str(t).strip()]
        if not name or not times:
            continue
        results.append({
            'name': name,
            'times': times,
            'note': str(r.get('note') or '').strip(),
            'matched': name in roster_set,
        })

    if not results:
        return {'ok': False, 'error': "Couldn't find any readable names and times in that photo."}

    return {
        'ok': True,
        'test_label': str(data.get('test_label') or 'Test set').strip(),
        'event': str(data.get('event') or '').strip(),
        'results': results,
    }


# ============================================================
# SOLO-TIER AI COACHING: interactive nutrition + dryland coach chat
#
# Grounded in the swim-coach skill (swim-coach/SKILL.md and its reference/
# files) -- pool + dryland load reasoned together, injury status checked
# before every dryland answer, nutrition tied to training phase and today's
# actual session load rather than a static diet sheet. Knowledge below is a
# condensed version of those reference files; anything marked (unverified)
# there is a fresh design/general S&C-nutrition consensus, not a cited
# swim-specific standard -- the model is told to hold that same caveat.
# ============================================================

NUTRITION_KNOWLEDGE = """
NUTRITION KNOWLEDGE (swim-specific, not a static diet plan -- key to training phase and today's actual pool load):

Training phase framing:
- Base (moderate-high volume, aerobic): consistent carbs, this is where eating habits get built, not a time to under-fuel.
- Build (volume + intensity both up, peak load): highest carb needs of any phase -- under-fueling here shows up fastest as flat performance or illness/injury risk.
- Taper (volume drops, intensity holds): total intake comes down roughly with volume, but don't cut carbs on quality/race-pace days -- protein/fat can trend down more than carbs.

Carb timing around a pool session (unverified general endurance-nutrition ranges, be conservative for junior/age-group swimmers -- "eat enough" not precise g/kg):
- Pre-session (2-3h before high-volume/intensity): carb-forward, moderate protein, lower fat/fibre. E.g. oats + banana + honey, or rice + chicken.
- Close to session (30-60 min before, only if needed): small fast carb -- toast + jam, banana, sports drink. Skip if they train fine fasted.
- During (only genuinely long sessions, 90+ min continuous): carb drink -- most age-group sessions don't need this.
- Post-session recovery window (within ~30-60 min out of the pool): carbs + protein together -- the single highest-leverage timing point for a swimmer training multiple times a week. E.g. chocolate milk + banana, protein shake + fruit, or a full meal.

High-volume/double day vs light/rest day:
- High-volume or double-session day: bias carbs up across the WHOLE day, not just around the session.
- Light/rest day: carbs can trend down somewhat, protein holds steady (recovery still happening), don't crash-diet a rest day.
- Two-a-day: the gap between AM and PM sessions is a critical refuel window.

Meal structure: most swimmers training 5-6x/week do well with 3 meals + 1-2 snacks timed around training. Protein at every meal. Hydration: swimmers chronically under-recognize sweat loss because they're already wet and don't feel thirsty -- flag this explicitly, water at every meal plus deliberate hydration around sessions.

What NOT to do: never hand a strict calorie deficit/surplus target (especially to a minor) -- redirect body-composition goals to a sports dietitian and keep this to performance fueling/timing. Don't prescribe supplements beyond the basics (creatine, protein as a convenience tool, vitamin D if flagged low) unless asked, and never to a minor without flagging a parent/guardian + clinician should be involved. If eating_habits is flagged undereating/skip_meals, lead with "are you eating enough, especially around sessions" rather than macro precision.

Conflicting goals: "eat less" + "hit peak training load this block" is a real conflict -- under-fueling during build/peak directly costs performance and raises injury/illness risk, say so plainly and reframe toward fueling the training they're doing.

Disclaimer (state once, near the start of a new conversation, and always for a minor or any disordered-eating flag): this is general sports-nutrition guidance, not an individualized dietetic prescription. A minor, anyone with a disordered-eating flag, or a medical condition should keep to meal structure/timing (not calorie/macro numbers) and see a registered sports dietitian for anything more specific.
"""

DRYLAND_KNOWLEDGE = """
DRYLAND KNOWLEDGE (swim-specific dryland only -- three mandatory categories per full session, unless the load guardrail or an injury modification says to drop one):

1. Shoulder/rotator cuff health -- highest-yield category, touch it even on a light day. Prone Y-T-W raises 2-3x10-12 each; band external rotation 3x12-15 (elbow pinned to ribs); band internal rotation 2-3x12-15; Cuban press 2-3x8-10; scaption raises 2-3x10-12 (lower impingement risk than lateral raises); face pulls/band pull-aparts 2-3x15; wall slides/scap push-ups 2x10-12. (unverified exact rep ranges) Endurance/health work favors higher reps (12-15+) light load over heavy low-rep, since the cuff's job is stabilization through thousands of repetitive strokes.

2. Core/rotation -- anti-rotation and controlled-rotation over crunches. Plank front+side 2-3x30-45s; Pallof press 2-3x10-12 each side; dead bug 2-3x8-10 each side; med ball rotational throw 2-3x6-8 each side; Russian twist (controlled) 2-3x12-16; hollow body hold 2-3x20-30s.

3. Explosive/plyometric (starts/turns) -- most sensitive to overload, gated by the load guardrail below. Progression order, don't skip ahead: (1) landing mechanics/box step-offs first for anyone new to plyo, (2) bilateral low-amplitude (squat jumps 3x5-6 full recovery between reps, broad jumps 3x4-5), (3) bilateral higher-amplitude (box jumps 3x5, moderate height), (4) unilateral (single-leg bounds 2-3x4-5 each side), (5) depth drops/reactive -- most advanced, reserve for experienced athletes with clean landing mechanics only, skip for anyone under a certain training age or with lower-limb injury history. (unverified age/training-age cutoffs, volume caps) True plyo work 1-2x/week is a reasonable cap; don't chase max height/reps, chase landing quality.

Equipment -- never prescribe gear they don't have, ask first: bodyweight only still makes a complete session (planks, push-ups, Y-T-W no load, bodyweight squats, pool-deck broad jumps). Bands unlock external/internal rotation, face pulls, Pallof press -- cheapest and most useful cuff kit. Light dumbbells add Cuban press, scaption raises, loaded Y-T-W. Med ball adds rotational throws/slams. Box/platform adds box jumps/step-ups. Full gym adds cable face pulls, loaded squats as a power base.

Conflicting goals: heavy plyo progression on only 15-20 min twice a week isn't realistic -- that's enough for cuff+core maintenance, not a real plyo progression. Say so plainly and offer the honest tradeoff.
"""

LOAD_GUARDRAIL_KNOWLEDGE = """
COMBINED LOAD GUARDRAIL (fresh design, not a cited standard -- pool load in meters and dryland load in RPE x duration aren't the same currency, so use two parallel signals reconciled by whichever is more conservative, don't average them):

Pool ACWR is already computed (0.55-1.35 = normal; >=1.35 with high fatigue/low feeling check-ins, or >=1.7 regardless = overtraining flag; <=0.55 with meaningful chronic volume = undertraining).
Dryland load = RPE(1-10) x duration_minutes per session; acute = sum last 7 days, chronic weekly = sum last 28 days / 4, dryland ACWR = acute/chronic (only meaningful with ~2+ weeks of logged sessions -- with less data, fall back to "don't jump total session_load week-over-week by more than ~20-30%").

Reconciliation table:
- Pool normal + dryland normal/no data -> full session, all three categories, standard volume.
- Pool normal + dryland elevated -> back off dryland specifically (it's the thing driving risk): cuff/core only, skip plyo.
- Pool elevated/overtraining flag (regardless of dryland trend) -> back off regardless: light cuff/core activation only, skip plyo, keep it short.
- Pool undertraining + dryland normal -> fine to progress dryland if they want.
- Pool undertraining + dryland also low/no data -> flag the conflict, ask if it's a deliberate recovery block/taper rather than assuming.

Same-day check (separate from the weekly table): always ask/check whether they had a hard pool session today or yesterday before prescribing plyo specifically -- stacking plyo on a same-day hard water session is the most common way to accidentally overload a swimmer even when weekly ACWR looks fine.

Progression when things are going well: cuff/core progresses by adding reps before load; plyo progresses by moving down the bilateral->unilateral->reactive progression order, not by adding volume to the current tier. Never progress dryland load the same week pool ACWR is elevated. Recovery week (cuff/core maintenance only, skip plyo) every 3-4 weeks, or sooner if 2+ of: pool overtraining flag, dryland ACWR spiking, fatigue trending up 3+ days, reported joint pain.
"""

INJURY_KNOWLEDGE = """
INJURY-STATUS RULES for dryland:

Red flags -- if ANY of these are present, tell the swimmer to STOP dryland training, mention it to their swim coach, and see a physiotherapist/clinician. Do NOT offer a modification path or continue prescribing around it: sharp/sudden-onset pain, numbness or tingling radiating down an arm or leg, a joint that locks/catches/gives way, pain that wakes them at night, visible swelling/bruising/deformity, or pain that's worsening session over session despite rest.

Common modification paths (unverified specifics, general S&C/rehab-adjacent common sense, not a physio protocol -- nothing here clears an athlete to train through pain):
- Shoulder impingement/swimmer's shoulder: avoid overhead pressing through end-range, straight lateral raises above shoulder height, anything reproducing a pinch at the top. Modify toward scaption raises instead of lateral raises, external rotation in pain-free range only, reduce overhead volume. Core and lower-body plyo (no overhead loading) are usually still fine -- don't shut the whole session down. Only add range/load back once pain-free through full range for multiple sessions in a row.
- Breaststroker's knee (medial knee pain): avoid deep loaded squats/lunges with knee valgus, explicit whip-kick-pattern drills. Modify toward strict knee-tracking squat/lunge variants, lower-impact plyo (broad jumps over box jumps). Upper body/core usually unaffected. Flag that in-pool breaststroke kick volume may need to come down too, that's outside this coach's lane.
- Lower back tightness/pain: avoid loaded spinal flexion/extension under fatigue, aggressive plyo landing volume until resolved. Modify toward anti-extension/anti-rotation core (plank, dead bug, Pallof press) over flexion-based ab work. Reintroduce rotational core before reintroducing plyo landing volume as it resolves.

Always check injury status before prescribing a dryland session -- never assume "no injuries" just because none is on file.
"""


def generate_coach_chat_reply(topic, message, profile, pool_state, injury_summary, dryland_load, recent_history,
                               api_key, model):
    """Interactive nutrition/dryland coach chat, grounded in the swim-coach
    skill's reasoning (see the *_KNOWLEDGE constants above) plus this
    swimmer's real STROKE data. `topic` is 'nutrition' or 'dryland'.
    `pool_state` is athlete_model.recompute_state(user_id) (or {} if none
    yet). `injury_summary` is a plain-text description of current injury
    status, or None/"" if never recorded. `dryland_load` is {'acute',
    'chronic_weekly', 'acwr', 'entries_count'} from the swimmer's own
    DrylandLogEntry history, or None. `recent_history` is a list of
    {'role': 'user'|'assistant', 'content': str} for this topic, oldest
    first, excluding the message just sent. Returns a plain string reply, or
    a friendly fallback on any failure -- never raises."""
    knowledge = NUTRITION_KNOWLEDGE if topic == 'nutrition' else (DRYLAND_KNOWLEDGE + "\n" + LOAD_GUARDRAIL_KNOWLEDGE + "\n" + INJURY_KNOWLEDGE)

    age = profile.age if profile else None
    is_minor = age is not None and age < 18

    data_lines = [
        f"- Level: {profile.level or 'not specified'}" if profile else "- Level: not specified",
        f"- Age: {age or 'not specified'}{' (MINOR -- keep guidance general, recommend a dietitian/physio+guardian for anything specific)' if is_minor else ''}",
        f"- Swimmer type: {getattr(profile, 'swimmer_type', None) or 'not specified'}",
        f"- Eating habits flag: {EATING_HABITS_LABELS.get(getattr(profile, 'eating_habits', None), 'not specified')}" if profile else "",
        f"- Stated injuries/limitations at onboarding: {profile.limitations}" if profile and profile.limitations else "",
    ]
    if pool_state:
        data_lines.append(
            f"- Pool acute:chronic load ratio (ACWR): {pool_state.get('acwr', 'not enough data')} "
            f"-- trend: {pool_state.get('trend', 'unknown')} ({pool_state.get('trend_reason', '')})"
        )
        weekly = pool_state.get('weekly') or []
        if weekly:
            data_lines.append(f"- This week's pool volume so far: {weekly[-1]['vol']}m across {weekly[-1]['sessions']} session(s)")
        data_lines.append(f"- Last logged pool activity: {pool_state.get('last_active') or 'never'}")

    if topic == 'dryland':
        if dryland_load and dryland_load.get('entries_count'):
            data_lines.append(
                f"- Dryland load (last 7d acute / 28d-avg chronic): {dryland_load['acute']} / {dryland_load['chronic_weekly']}"
                f", ACWR {dryland_load.get('acwr') or 'not enough history yet'} (from {dryland_load['entries_count']} logged sessions)"
            )
        else:
            data_lines.append("- No dryland sessions logged yet -- not enough history for a dryland load trend, default to the simple ramp-rate rule, don't block on this.")
        data_lines.append(
            f"- Current injury status on file: {injury_summary}" if injury_summary else
            "- No injury status on file yet. There is a SEPARATE quick injury-status form already shown on this "
            "page above the chat -- do NOT ask the injury-status questions yourself or make the swimmer answer "
            "them in the chat. Just give safe, conservative general-population dryland guidance (moderate volume, "
            "pain-free range, nothing maximal-effort) and add one short line pointing them at that form if "
            "anything's bothering them, then move on."
        )

    data_block = "\n".join(l for l in data_lines if l)

    history_block = "\n".join(f"{h['role'].upper()}: {h['content']}" for h in recent_history) or "(this is the first message in this conversation)"

    # The system prompt (role, knowledge, formatting/behaviour rules) is
    # IDENTICAL across every message for a given topic+tone -- only the
    # swimmer-specific data/history/question below actually changes per call.
    # Splitting it out with cache_control lets Anthropic's prompt cache reuse
    # it (~90% cheaper on cache hits) instead of re-billing the full knowledge
    # block on every single message, which is where the real per-message cost
    # was coming from, not the (already-capped-at-12) message history.
    system_text = (
        f"You are the swimmer's {topic} coach inside STROKE (a swim training app). You are NOT their pool "
        "technique coach -- stay in your lane: nutrition/fueling or land-based conditioning depending on topic. "
        f"{_tone_line(getattr(profile, 'coaching_tone', 'balanced') if profile else 'balanced')}\n\n"
        f"{knowledge}\n\n"
        + (
            "RED FLAG CHECK: if the swimmer's message describes sharp/sudden pain, numbness or tingling down a "
            "limb, a joint locking/catching/giving way, pain waking them at night, visible swelling/deformity, or "
            "pain worsening session over session, STOP -- tell them plainly to stop dryland training, mention it "
            "to their swim coach, and see a physiotherapist/clinician. Do not prescribe anything around it.\n\n"
            if topic == 'dryland' else ""
        )
        + "GIVE A REAL, COMPLETE ANSWER RIGHT NOW -- this is the single most important rule. Never open with a "
        "list of questions before you'll help; that's exactly the kind of friction that makes people give up on "
        "an AI coach and close the tab. If something genuinely unstated would sharpen the answer (equipment for "
        "dryland, meal timing gap for nutrition), make the single most sensible default -- for dryland, assume "
        "bodyweight + resistance bands, the most common home setup; for nutrition, assume a normal moderate-effort "
        "day unless the data above says otherwise -- and say what you assumed in ONE short line, then give the "
        "full session/meal guidance anyway. Don't wait for confirmation. At most one optional follow-up question "
        "is allowed, and only at the very end, after they already have something real to use today.\n\n"
        "Answer their actual question directly and specifically -- real sets/reps/durations or real meal/timing "
        "examples, not vague filler like 'a few rounds of core work' or 'eat a balanced diet'. Ground it in the "
        "data above (today's/this week's pool load, injury status, training phase) rather than generic advice. "
        "If their goals conflict (e.g. wanting max plyo progression on 15 min twice a week, or cutting calories "
        "during a peak-load block), say so plainly and offer the honest tradeoff rather than quietly complying. "
        "Keep it conversational and tight, like a real coach texting back, not an essay -- a few sentences unless "
        "they're asking for a full session/meal plan.\n\n"
        "FORMATTING (a normal person is reading this on their phone, not a document): short plain sentences by "
        "default. Only reach for structure when giving an actual session or meal plan, and even then keep it "
        "light -- a `**Section Name**` header line followed by a few `- ` bullet points, nothing nested, no long "
        "paragraphs under a header. Never use numbered lists, tables, or multiple heading levels."
    )

    prompt = (
        f"What you know about this swimmer:\n{data_block}\n\n"
        f"Conversation so far:\n{history_block}\n\n"
        f"Swimmer's new message: \"{message}\""
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            system=[{"type": "text", "text": system_text, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in response.content if getattr(block, 'type', None) == 'text').strip()
        if text:
            return _humanize(text)
    except Exception:
        logger.exception('generate_coach_chat_reply: API call failed')

    return "Couldn't get a reply right now, give it another try in a moment."


import html as _html

_COACH_BOLD_RE = _re.compile(r'\*\*(.+?)\*\*')


def render_coach_markdown(text):
    """Turn the coach chat's lightweight markdown (see the FORMATTING rule in
    generate_coach_chat_reply -- '**Header**' lines and '- ' bullets only)
    into safe HTML for the chat bubble. Escapes first, so nothing in the raw
    text (AI output or, via the same filter, a user's own message) can inject
    markup -- only our own inserted <b>/<ul>/<li>/<p> tags are real HTML."""
    if not text:
        return ''
    escaped = _html.escape(text)
    escaped = _COACH_BOLD_RE.sub(r'<b>\1</b>', escaped)

    out = []
    in_list = False
    for raw_line in escaped.split('\n'):
        line = raw_line.strip()
        if line.startswith('- '):
            if not in_list:
                out.append('<ul>')
                in_list = True
            out.append(f'<li>{line[2:].strip()}</li>')
            continue
        if in_list:
            out.append('</ul>')
            in_list = False
        if line:
            out.append(f'<p>{line}</p>')
    if in_list:
        out.append('</ul>')

    return ''.join(out)


# ============================================================
# EVENT IMPORT: classify scraped calendar events for a squad
# ============================================================
# An external club calendar (see events_sources.py) lists everything: real
# swim meets and championships, but also AGMs, awards nights and social dates.
# When a coach auto-imports "key dates" they only want the competitions on
# their squad calendar, not the admin noise. This asks Claude to tag each event
# as a competition or not; a keyword heuristic covers the AI-off / failure case
# so the import still works (same fallback philosophy as map_roster_columns).

# Titles that clearly aren't a swim competition -- used by the heuristic and as
# a belt-and-braces exclusion even after the AI classifies.
_NON_COMPETITION_KEYWORDS = (
    # NB: keep these specific -- avoid words like 'course' that appear in real
    # meet names ('long course' / 'short course' championships).
    'meeting', 'agm', 'annual general', 'awards', 'prizegiving',
    'committee', 'social', 'quiz', 'fundraiser', 'working bee', 'clinic',
    'workshop', 'camp', 'entries close', 'entry deadline',
)

EVENT_CLASSIFY_TOOL_SCHEMA = {
    "name": "classify_swim_events",
    "description": "Tag each listed swim-club calendar event as a competition or not, so only meets/championships get imported.",
    "input_schema": {
        "type": "object",
        "properties": {
            "events": {
                "type": "array",
                "description": "One entry per event, referenced by its index.",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "description": "The event's index as given in the prompt."},
                        "is_competition": {
                            "type": "boolean",
                            "description": (
                                "True only if this is an actual swimming COMPETITION a squad would attend: a meet, "
                                "championship, gala, open-water race, junior league/festival, best-time or ribbon "
                                "meet. False for AGMs, awards nights, socials, committee meetings, camps, clinics, "
                                "entry deadlines, or anything that isn't a race."
                            ),
                        },
                        "category": {
                            "type": "string",
                            "description": "Short lowercase label, e.g. 'championship', 'meet', 'open water', 'junior', 'social', 'admin'.",
                        },
                    },
                    "required": ["index", "is_competition"],
                },
            },
        },
        "required": ["events"],
    },
}

EVENT_CLASSIFY_PROMPT = (
    "You are helping a swim coach auto-import a regional swimming calendar onto their squad's "
    "schedule. The coach only wants actual COMPETITIONS (meets, championships, galas, open-water "
    "races, junior leagues/festivals, best-time and ribbon meets). They do NOT want administrative "
    "or social entries (AGMs, awards nights, committee meetings, socials, training camps, clinics, "
    "entry deadlines).\n\n"
    "For each event below, decide whether it's a competition and give a short category label. Call "
    "classify_swim_events exactly once with a verdict for every event, keyed by its index."
)


def _heuristic_event_classify(events):
    """Keyword fallback used when AI is off or the call fails. Treats an event
    as a competition unless its title matches a clearly non-competition word.
    Returns {index: is_competition_bool}."""
    out = {}
    for i, ev in enumerate(events):
        title = (ev.get('title') or '').lower()
        out[i] = not any(kw in title for kw in _NON_COMPETITION_KEYWORDS)
    return out


def classify_swim_events(events, api_key, model):
    """Tag each event dict (needs a 'title') as a competition or not. Returns a
    list of bools aligned to `events`. Never raises -- falls back to the keyword
    heuristic if AI is unavailable, and always applies the non-competition
    keyword list as a final backstop so an obvious AGM can't slip through."""
    if not events:
        return []

    if not api_key:
        verdicts = _heuristic_event_classify(events)
    else:
        verdicts = None
        lines = []
        for i, ev in enumerate(events):
            loc = (ev.get('location') or '').strip()
            lines.append(f"[{i}] {ev.get('title') or '(untitled)'}" + (f"  @ {loc}" if loc else ""))
        prompt = f"{EVENT_CLASSIFY_PROMPT}\n\nEvents:\n" + "\n".join(lines)
        try:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=model,
                max_tokens=1024,
                tools=[EVENT_CLASSIFY_TOOL_SCHEMA],
                tool_choice={"type": "tool", "name": "classify_swim_events"},
                messages=[{"role": "user", "content": prompt}],
            )
            tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
            if tool_use and tool_use.input:
                verdicts = {}
                for row in (tool_use.input.get('events') or []):
                    try:
                        idx = int(row.get('index'))
                    except (TypeError, ValueError):
                        continue
                    if 0 <= idx < len(events):
                        verdicts[idx] = bool(row.get('is_competition'))
        except Exception:
            logger.exception('classify_swim_events: API call failed, using heuristic')
            verdicts = None
        if not verdicts:
            verdicts = _heuristic_event_classify(events)

    # Final backstop: whatever the model said, never import an obvious
    # non-competition title (defends against a stray true on an AGM).
    result = []
    for i, ev in enumerate(events):
        is_comp = verdicts.get(i, False)
        title = (ev.get('title') or '').lower()
        if is_comp and any(kw in title for kw in _NON_COMPETITION_KEYWORDS):
            is_comp = False
        result.append(is_comp)
    return result
