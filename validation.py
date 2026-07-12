"""Central input validation. Every numeric or structured field a user can
submit passes through here on the backend, regardless of what the frontend
already checked -- never trust frontend validation alone.

Design rules:
- Nothing here ever raises on bad input; you get None (or a cleaned value).
- Scientific notation ('1e100'), 'Infinity', 'NaN', negatives, blanks,
  emoji, and 40-digit numbers are all rejected the same way: None.
- Every limit lives in LIMITS so the bounds are visible in one place.
"""

import json
import math
import re

from swim_logic import parse_time, fmt_time

# One place for every numeric bound in the app: (min, max).
LIMITS = {
    'age': (5, 99),
    'training_days': (1, 14),
    'reps': (1, 200),
    'dist': (25, 3000),           # metres per rep
    'rest_seconds': (1, 3600),
    'swim_seconds': (8, 2 * 60 * 60),    # a timed swim: 8s (fast 25) to 2 hours
    'split_seconds': (8, 20 * 60),
    'goal_seconds': (8, 3 * 60 * 60),
    'duration_minutes': (15, 240),
    'rating': (1, 5),
    'heart_rate': (30, 250),
    'weight_kg': (20, 300),
    'height_cm': (80, 250),
    'fee': (0, 100000),
    'page': (1, 100000),
}

# Reject anything that isn't a plain decimal integer before int() ever runs --
# this is what kills '1e100', 'Infinity', 'NaN', '0x10', '  ', '½' etc.
_INT_RE = re.compile(r'^-?\d{1,10}$')
_FLOAT_RE = re.compile(r'^-?\d{1,10}(\.\d{1,4})?$')


def clean_int(raw, key=None, lo=None, hi=None):
    """Parse an integer field safely. Returns int within bounds, else None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not _INT_RE.match(s):
        return None
    n = int(s)
    lo, hi = _bounds(key, lo, hi)
    if lo is not None and n < lo:
        return None
    if hi is not None and n > hi:
        return None
    return n


def clean_float(raw, key=None, lo=None, hi=None):
    """Parse a decimal field safely. Returns float within bounds, else None."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not _FLOAT_RE.match(s):
        return None
    x = float(s)
    if not math.isfinite(x):
        return None
    lo, hi = _bounds(key, lo, hi)
    if lo is not None and x < lo:
        return None
    if hi is not None and x > hi:
        return None
    return x


def clean_time(raw, key='swim_seconds'):
    """Parse a swim-time string ('58.9', '1:02.5', '17:45.30'). Returns
    (normalized_string, seconds) or (None, None). Bounds come from LIMITS."""
    secs = parse_time(raw)
    if secs is None:
        return None, None
    lo, hi = LIMITS.get(key, (1, 7200))
    if secs < lo or secs > hi:
        return None, None
    # Normalize the stored string so downstream parsers always succeed.
    if secs >= 60:
        norm = f'{int(secs // 60)}:{secs % 60:05.2f}'
    else:
        norm = f'{secs:.2f}'
    return norm, secs


def clean_text(raw, max_len=2000):
    """Trim and cap free text. Never None -- empty string when blank."""
    return str(raw or '').strip()[:max_len]


def clean_splits(raw_list, max_splits=60):
    """Validate a list of 50m split strings. Returns the cleaned list (possibly
    empty); silently drops anything unparseable or out of range."""
    out = []
    if not isinstance(raw_list, list):
        return out
    for item in raw_list[:max_splits]:
        norm, _secs = clean_time(item, key='split_seconds')
        if norm is not None:
            out.append(norm)
    return out


# The canonical set-block shape used by log.html, SavedSet and the AI
# generators: section/reps/dist/stroke/modifier/rest/rest_type/note.
_STROKES = {'FR', 'BK', 'BR', 'FL', 'IM'}
_MODIFIERS = {'', 'Kick', 'Pull', 'Drill', 'Snorkel'}
_SECTIONS = {'Warm up', 'Pre set', 'Main set', 'Sub set', 'Cool down'}
MAX_BLOCKS = 60
MAX_SETS_JSON = 100_000  # bytes; a real session is a few KB


def clean_block(raw):
    """Validate one set block. Returns the cleaned block dict or None."""
    if not isinstance(raw, dict):
        return None
    reps = clean_int(raw.get('reps'), key='reps')
    dist = clean_int(raw.get('dist'), key='dist')
    if reps is None or dist is None:
        return None

    rest_raw = raw.get('rest')
    rest = ''
    if rest_raw not in (None, ''):
        secs = parse_time(rest_raw)
        lo, hi = LIMITS['rest_seconds']
        if secs is not None and lo <= secs <= hi:
            rest = fmt_time(secs)  # normalized 'M:SS'
        # Unparseable/absurd rest just gets dropped rather than sinking the block.

    reps_default_type = 'interval' if reps > 1 else 'rest'
    return {
        'section': raw.get('section') if raw.get('section') in _SECTIONS else 'Main set',
        'reps': reps,
        'dist': dist,
        'stroke': raw.get('stroke') if raw.get('stroke') in _STROKES else 'FR',
        'modifier': raw.get('modifier') if raw.get('modifier') in _MODIFIERS else '',
        'rest': rest,
        'rest_type': raw.get('rest_type') if raw.get('rest_type') in ('interval', 'rest') else reps_default_type,
        'note': clean_text(raw.get('note'), 200),
    }


def clean_sets_json(raw_json):
    """Parse and validate a sets_data JSON string from a form. Returns
    (json_string, blocks) with only valid blocks kept -- ('[]', []) for
    anything hopeless. Total volume is capped so a crafted payload can't
    create a 10-million-metre session."""
    if not raw_json or len(raw_json) > MAX_SETS_JSON:
        return '[]', []
    try:
        parsed = json.loads(raw_json)
    except (ValueError, TypeError):
        return '[]', []
    if not isinstance(parsed, list):
        return '[]', []
    blocks = [b for b in (clean_block(r) for r in parsed[:MAX_BLOCKS]) if b is not None]
    # Belt and braces on total volume: 100km in one logged session is garbage.
    total = sum(b['reps'] * b['dist'] for b in blocks)
    while blocks and total > 100_000:
        dropped = blocks.pop()
        total -= dropped['reps'] * dropped['dist']
    return json.dumps(blocks), blocks


def _bounds(key, lo, hi):
    if key and key in LIMITS:
        klo, khi = LIMITS[key]
        return (lo if lo is not None else klo), (hi if hi is not None else khi)
    return lo, hi
