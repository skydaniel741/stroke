import base64
import io

import anthropic
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
MODIFIERS = {'', 'Kick', 'Pull', 'Drill'}
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
                                "Rest or send-off interval, normalized to 'M:SS' or '0:SS' regardless of how it was "
                                "written on the board. Coaches write this many different ways -- convert them all: "
                                "'with 10' or '10 sec rest' -> '0:10'; 'on 45' or '@45' (send-off interval) -> '0:45'; "
                                "'on 1.00' or 'on 1:00' -> '1:00'. Empty string only if truly no rest/interval is given."
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
    "- Rest/send-off shorthand: 'with 10', 'on 45', '@45', 'on 1.00' are all rest/interval "
    "values, not part of the distance or stroke -- always fill in the 'rest' field for them.\n"
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

    return {
        'section': section, 'reps': reps, 'dist': dist, 'stroke': stroke,
        'modifier': modifier, 'rest': rest, 'note': note,
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
