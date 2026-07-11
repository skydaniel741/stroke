import base64
import io
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

_DASH_RE = _re.compile(r'\s*[—–]\s*|\s+--\s+')


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
                        "reps": {"type": "integer", "description": "Number of repeats, e.g. the 8 in 8x100."},
                        "dist": {"type": "integer", "description": "Distance per rep in metres, e.g. the 100 in 8x100."},
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
                                "drills -> note='+ backstroke, kick drill'. Empty string if none."
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
    "breakdown in 'note'."
)


def _clamp_block(raw):
    try:
        reps = int(raw.get('reps') or 0)
        dist = int(raw.get('dist') or 0)
    except (TypeError, ValueError):
        return None
    if reps <= 0 or dist <= 0:
        return None

    stroke = raw.get('stroke') if raw.get('stroke') in STROKE_CODES else 'FR'
    modifier = raw.get('modifier') if raw.get('modifier') in MODIFIERS else ''
    section = raw.get('section') if raw.get('section') in SECTIONS else 'Main set'
    rest = str(raw.get('rest') or '').strip()
    note = str(raw.get('note') or '').strip()
    # 'interval' = send-off/cycle time ("on 2:10" -- leave again every 2:10);
    # 'rest' = an explicit recovery gap. Most repeat sets (reps > 1) are written
    # as an interval/send-off, so that's the sensible default when unspecified.
    rest_type = raw.get('rest_type') if raw.get('rest_type') in ('interval', 'rest') else ('interval' if reps > 1 else 'rest')

    return {
        'section': section, 'reps': reps, 'dist': dist, 'stroke': stroke,
        'modifier': modifier, 'rest': rest, 'rest_type': rest_type, 'note': note,
    }


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
        return {'ok': False, 'error': "That doesn't look like a photo — try again."}

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
        return {'ok': False, 'error': "Couldn't read that photo — try again or enter it manually."}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use:
        return {'ok': False, 'error': "Couldn't read that photo — try again or enter it manually."}

    data = tool_use.input or {}
    blocks = [b for b in (_clamp_block(r) for r in data.get('blocks', [])) if b is not None]

    if not blocks:
        return {'ok': False, 'error': "Couldn't find a set in that photo — try a clearer shot."}

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
    "default to 'Main set'."
)


def extract_set_from_transcript(transcript, api_key, model):
    """Call Claude with forced tool-use to turn a dictated workout transcript into
    structured swim set blocks. Returns {'ok': True, 'blocks', 'pool', 'session_type'}
    on success or {'ok': False, 'error'} on any failure -- never raises."""
    text = (transcript or '').strip()
    if not text:
        return {'ok': False, 'error': "Didn't catch anything — try dictating again."}

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
        return {'ok': False, 'error': "Couldn't parse that — try again or enter it manually."}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use:
        return {'ok': False, 'error': "Couldn't parse that — try again or enter it manually."}

    data = tool_use.input or {}
    blocks = [b for b in (_clamp_block(r) for r in data.get('blocks', [])) if b is not None]

    if not blocks:
        return {'ok': False, 'error': "Couldn't find a set in that — try describing it differently."}

    pool = data.get('pool') if data.get('pool') in POOLS else '25m'
    session_type = (data.get('session_type') or 'Training').strip() or 'Training'

    return {'ok': True, 'blocks': blocks, 'pool': pool, 'session_type': session_type}


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


def generate_training_program(profile, meal_catalog, dryland_catalog, supplement_catalog, api_key, model):
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
        return {'ok': False, 'error': "Couldn't generate a program right now — try again in a moment."}

    if response.stop_reason == 'max_tokens':
        logger.error('generate_training_program: response truncated at max_tokens')
        return {'ok': False, 'error': "Couldn't generate a program right now — try again in a moment."}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use or not tool_use.input:
        logger.error('generate_training_program: no usable tool_use in response')
        return {'ok': False, 'error': "Couldn't generate a program right now — try again in a moment."}

    program = tool_use.input
    for day in program.get('days', []):
        day['blocks'] = [b for b in (_clamp_block(r) for r in day.get('blocks', [])) if b is not None]
        day['total'] = sum(b['reps'] * b['dist'] for b in day['blocks'])
    if not program.get('days'):
        logger.error('generate_training_program: program came back with no days')
        return {'ok': False, 'error': "Couldn't generate a program right now — try again in a moment."}

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
        return f"- {c['date']}: felt {c['feeling_rating']}/5{extra_str} — \"{c['notes']}\""

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
        f"Today's check-in: felt {feeling_rating}/5{today_extra_str} — \"{notes}\"\n\n"
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
        return {'ok': False, 'error': "Couldn't generate an analysis right now — try again in a moment."}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use or not tool_use.input:
        return {'ok': False, 'error': "Couldn't generate an analysis right now — try again in a moment."}

    return {'ok': True, 'insight': _humanize(tool_use.input)}


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
                            "description": "ONE sentence (max ~20 words): the data point + the action. e.g. 'No swim in 12 days — check in.'",
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
        return {'ok': False, 'error': "Couldn't generate insights right now — try again in a moment."}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use or not tool_use.input:
        return {'ok': False, 'error': "Couldn't generate insights right now — try again in a moment."}

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


def generate_coach_set(params, api_key, model):
    """Call Claude to write a coach's set from structured parameters, grounded
    in the elite-methodology notes above. `params` keys: focus, style,
    season_phase, level, pool, duration_minutes. Returns {'ok': True,
    'set': {...}} or {'ok': False, 'error': '...'} -- never raises."""
    focus = params.get('focus') or "coach's choice"
    prompt = (
        "You are an elite swim coach's assistant writing tomorrow's set.\n"
        f"{ELITE_METHODOLOGY_NOTES}\n"
        "The coach wants:\n"
        f"- Training focus: {focus}\n"
        f"- Methodology style: {params.get('style') or 'best fit for the focus'}\n"
        f"- Season phase: {params.get('season_phase') or 'mid season'}\n"
        f"- Squad level: {params.get('level') or 'senior club'}\n"
        f"- Pool: {params.get('pool') or '25m'}\n"
        f"- Session length: about {params.get('duration_minutes') or 60} minutes\n\n"
        "Call the create_coach_set tool with one complete session: warm up, main work, cool down. "
        "Total volume must be realistic for the session length and level (roughly 45-60m/min for "
        "seniors including rest, less for age-groupers). Intervals must be swimmable for the level. "
        "Use the note field for cues like 'descend 1-4' or 'hold 200 race pace'. Stay true to the "
        "requested methodology -- a USRPT set should look nothing like a Bowman aerobic set."
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
        return {'ok': False, 'error': "Couldn't generate a set right now — try again in a moment."}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use or not tool_use.input:
        return {'ok': False, 'error': "Couldn't generate a set right now — try again in a moment."}

    data = tool_use.input
    blocks = [b for b in (_clamp_block(r) for r in data.get('blocks', [])) if b is not None]
    if not blocks:
        return {'ok': False, 'error': "The generated set came back empty — try again."}

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
        return {'ok': False, 'error': "That doesn't look like a photo — try again."}

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
        return {'ok': False, 'error': "Couldn't read that photo — try again or enter times manually."}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use or not tool_use.input:
        return {'ok': False, 'error': "Couldn't read that photo — try again or enter times manually."}

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
