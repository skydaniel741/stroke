"""SCOUT pass: cheap, high-volume relevance scoring for research items.

This is the cost-control layer. A small, fast model (claude-haiku-4-5) reads
each fetched item and scores it 0-10 for relevance to competitive swim
coaching, plus a couple of topic tags. Only survivors go on to the expensive
SYNTHESIZE pass, so most of the token spend never touches the big model.

Novelty is NOT decided here -- items are already de-duped on external_id
before they reach the scout (see scripts/run_research.py). Do not ask the model
whether something is "new"; its training cutoff makes it call old methodology
current. The scout only judges relevance.

Uses forced tool-use for structured output (the pattern every other AI feature
in this app uses -- see ai_utils.py), so there are no markdown fences to strip.
Scoring is batched to keep the number of API calls small. Every call is wrapped
so a failure degrades to "unscored" (score 0, discarded) rather than crashing.
"""
import logging

import anthropic

logger = logging.getLogger(__name__)

# The scout runs on the cheapest capable model -- this pass is pure triage and
# high volume, so cost matters more than nuance. Kept as a module constant so
# it's easy to change independently of the app's main ANTHROPIC_MODEL (which the
# synthesis pass uses).
SCOUT_MODEL = 'claude-haiku-4-5'

# Items scoring at or above this are kept for synthesis. A single knob to tune
# how selective the brief is.
RELEVANCE_THRESHOLD = 6.0

# How many items to score per API call. Batching keeps the request count low
# without making any single response huge.
BATCH_SIZE = 10

# Abstracts can be long; the scout only needs the gist to judge relevance, so
# truncate to keep each request small and cheap.
_ABSTRACT_CHARS = 900

SCOUT_PROMPT = (
    "You are triaging newly published sport-science and coaching literature for a "
    "COMPETITIVE SWIMMING coaching platform. For each item below, rate how useful it "
    "would be to a competitive swim coach who wants practical, applicable insight: new "
    "drills, biomechanics findings, training methodology and periodization, physiology "
    "relevant to performance, or elite/Olympic coaching practice.\n\n"
    "Scoring guide (0-10):\n"
    "- 9-10: directly about competitive human swimming technique, training, or physiology "
    "with clear coaching relevance.\n"
    "- 6-8: swimming-related and useful, or strongly transferable methodology.\n"
    "- 3-5: tangential -- general exercise science, or swimming but with little coaching "
    "value.\n"
    "- 0-2: not relevant (animal locomotion, swimming pool chemistry, unrelated medicine, "
    "open-water safety, etc.).\n\n"
    "Judge ONLY relevance and usefulness to a coach. Do NOT judge whether the finding is "
    "novel or recent -- that has already been handled. For each item also give 1-3 short "
    "lowercase topic tags (e.g. 'biomechanics', 'periodization', 'sprint', 'stroke "
    "technique', 'physiology', 'strength').\n\n"
    "Call score_research_items exactly once with a score for every item, keyed by its index."
)

SCOUT_TOOL_SCHEMA = {
    "name": "score_research_items",
    "description": "Report a relevance score and topic tags for each research item.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scores": {
                "type": "array",
                "description": "One entry per item, referenced by its index.",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer", "description": "The item's index as given in the prompt."},
                        "score": {"type": "integer", "description": "Relevance to competitive swim coaching, 0-10."},
                        "topics": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "1-3 short lowercase topic tags.",
                        },
                    },
                    "required": ["index", "score"],
                },
            },
        },
        "required": ["scores"],
    },
}


def _score_batch(batch, api_key, model):
    """Score one batch of items. Returns a dict {index: {'score', 'topics'}}.
    Never raises -- an API/parse failure yields an empty dict so the caller
    treats those items as unscored (and therefore discarded)."""
    lines = []
    for i, item in enumerate(batch):
        title = (item.get('title') or '').strip() or '(no title)'
        abstract = (item.get('abstract') or '').strip()[:_ABSTRACT_CHARS]
        lines.append(f"[{i}] TITLE: {title}\nABSTRACT: {abstract or '(no abstract)'}")
    prompt = f"{SCOUT_PROMPT}\n\nItems:\n\n" + "\n\n".join(lines)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            tools=[SCOUT_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "score_research_items"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        logger.exception('scout: API call failed for a batch of %s items', len(batch))
        return {}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use or not tool_use.input:
        logger.warning('scout: no usable tool_use in response for a batch')
        return {}

    out = {}
    for row in (tool_use.input.get('scores') or []):
        try:
            idx = int(row.get('index'))
        except (TypeError, ValueError):
            continue
        if idx < 0 or idx >= len(batch):
            continue
        try:
            score = float(row.get('score'))
        except (TypeError, ValueError):
            continue
        score = max(0.0, min(10.0, score))
        topics = [str(t).strip().lower() for t in (row.get('topics') or []) if str(t).strip()][:3]
        out[idx] = {'score': score, 'topics': topics}
    return out


def score_items(items, api_key, model=SCOUT_MODEL, batch_size=BATCH_SIZE):
    """Score every item for relevance. Returns the same list with two keys
    added to each item: 'relevance_score' (float 0-10) and 'topics' (list of
    str). Items the model didn't score (or a failed batch) default to score 0
    with no topics, so they fall below threshold and are dropped. Never raises."""
    if not items:
        return []
    if not api_key:
        logger.warning('scout: no ANTHROPIC_API_KEY; leaving all items unscored')
        for item in items:
            item.setdefault('relevance_score', 0.0)
            item.setdefault('topics', [])
        return items

    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        scored = _score_batch(batch, api_key, model)
        for i, item in enumerate(batch):
            result = scored.get(i)
            if result is None:
                item['relevance_score'] = 0.0
                item['topics'] = []
            else:
                item['relevance_score'] = result['score']
                item['topics'] = result['topics']

    kept = sum(1 for it in items if it['relevance_score'] >= RELEVANCE_THRESHOLD)
    logger.info('scout: scored %s items, %s at/above threshold %s',
                len(items), kept, RELEVANCE_THRESHOLD)
    return items


def survivors(items, threshold=RELEVANCE_THRESHOLD):
    """Filter to items that met the relevance bar, best first."""
    kept = [it for it in items if (it.get('relevance_score') or 0) >= threshold]
    kept.sort(key=lambda it: it.get('relevance_score') or 0, reverse=True)
    return kept
