"""SYNTHESIZE pass: turn the scout's survivors into a coach-usable brief.

The expensive model (the app's configured ANTHROPIC_MODEL) reads ONLY the items
that cleared the scout's relevance bar and writes a single weekly brief: a
title, a short narrative summary, and a handful of concrete coaching takeaways.

Structured output via forced tool-use (same pattern as the rest of the app --
see ai_utils.py), so there are no markdown fences to strip and malformed output
degrades to {'ok': False} rather than crashing.
"""
import logging

import anthropic

logger = logging.getLogger(__name__)

# House copy rule shared with the swimmer-facing AI (see ai_utils.HUMAN_VOICE):
# never an em-dash or double-hyphen, so nothing reads as AI filler. This brief
# is coach-facing rather than swimmer-facing, so the tone is professional and
# practical rather than pool-deck warm.
SYNTHESIZE_PROMPT = (
    "You are a swim-science analyst writing this week's research brief for competitive "
    "swimming COACHES. You are given a set of recently published items (papers and "
    "preprints) that have already been filtered for relevance. Read them and write ONE "
    "brief that a busy coach can act on.\n\n"
    "Write the brief around what actually matters to coaching practice: new drills or "
    "technique cues, biomechanics findings, training methodology and periodization, "
    "performance physiology, and elite/Olympic coaching practice. Group related items, "
    "call out what is genuinely useful, and be honest when something is preliminary or "
    "thin. Ground every claim in the provided items -- do not invent findings, and do not "
    "describe anything as brand-new or a breakthrough unless the item itself supports it.\n\n"
    "VOICE: Write like a knowledgeable coach educator briefing peers. Be specific and "
    "practical, not academic. Use plain professional language.\n"
    "HARD RULE: Never use an em-dash or a double-hyphen '--'. Use a comma, a full stop, or "
    "the words 'and'/'but'/'so' instead.\n\n"
    "Call write_research_brief exactly once."
)

SYNTHESIZE_TOOL_SCHEMA = {
    "name": "write_research_brief",
    "description": "Write this week's coach-facing swimming research brief from the provided items.",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "A short, specific headline for the week's brief (max ~12 words). No date needed.",
            },
            "summary": {
                "type": "string",
                "description": (
                    "2-4 short paragraphs synthesizing the week's most useful findings for a coach. "
                    "Reference the actual items and what they mean for practice. No preamble, no "
                    "restating this instruction back."
                ),
            },
            "coaching_takeaways": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "3-6 concrete, actionable takeaways a coach could apply or test, each one short "
                    "sentence. Practical over theoretical."
                ),
            },
        },
        "required": ["title", "summary", "coaching_takeaways"],
    },
}

# Keep each item compact in the prompt; the abstract carries the substance but
# doesn't need to be complete for a synthesis-level read.
_ABSTRACT_CHARS = 1400

# Upper bound on how many survivors we feed the expensive model in one brief.
# The scout already ranks by relevance, so on a big week we brief the top items
# rather than letting the prompt (and cost) grow without limit.
MAX_SYNTHESIS_ITEMS = 25


def _format_items(items):
    lines = []
    for i, item in enumerate(items, start=1):
        title = (item.get('title') or '').strip() or '(no title)'
        authors = (item.get('authors') or '').strip()
        abstract = (item.get('abstract') or '').strip()[:_ABSTRACT_CHARS]
        topics = ', '.join(item.get('topics') or [])
        block = [f"ITEM {i}: {title}"]
        if authors:
            block.append(f"Authors: {authors}")
        if topics:
            block.append(f"Topics: {topics}")
        block.append(f"Abstract: {abstract or '(no abstract available)'}")
        lines.append("\n".join(block))
    return "\n\n".join(lines)


def synthesize_brief(items, api_key, model):
    """Write one brief from the scout survivors. `model` is the app's configured
    ANTHROPIC_MODEL. Returns {'ok': True, 'title', 'summary', 'coaching_takeaways'}
    on success or {'ok': False, 'error': '...'} on any failure. Never raises."""
    if not items:
        return {'ok': False, 'error': 'No items to synthesize.'}
    if not api_key:
        return {'ok': False, 'error': 'AI is not configured (no ANTHROPIC_API_KEY).'}

    # Bound the prompt (and cost) on a big week -- items arrive ranked by the
    # scout's relevance score, so the head is the most useful.
    items = items[:MAX_SYNTHESIS_ITEMS]

    prompt = (
        f"{SYNTHESIZE_PROMPT}\n\n"
        f"Here are this week's {len(items)} relevant items:\n\n"
        f"{_format_items(items)}"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            tools=[SYNTHESIZE_TOOL_SCHEMA],
            tool_choice={"type": "tool", "name": "write_research_brief"},
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        logger.exception('synthesize: API call failed')
        return {'ok': False, 'error': "Couldn't generate the brief right now."}

    if response.stop_reason == 'max_tokens':
        logger.error('synthesize: response truncated at max_tokens')
        return {'ok': False, 'error': "The brief came back truncated."}

    tool_use = next((c for c in response.content if getattr(c, 'type', None) == 'tool_use'), None)
    if not tool_use or not tool_use.input:
        logger.error('synthesize: no usable tool_use in response')
        return {'ok': False, 'error': "Couldn't generate the brief right now."}

    data = tool_use.input
    title = (data.get('title') or '').strip()
    summary = (data.get('summary') or '').strip()
    takeaways = [str(t).strip() for t in (data.get('coaching_takeaways') or []) if str(t).strip()]

    if not summary or not takeaways:
        logger.error('synthesize: brief missing summary or takeaways')
        return {'ok': False, 'error': "The brief came back empty."}

    return {
        'ok': True,
        'title': title or 'This week in swimming science',
        'summary': summary,
        'coaching_takeaways': takeaways,
    }
