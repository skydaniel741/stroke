"""Weekly swimming-research agent -- Render Cron Job entry point.

Standalone: builds its own Flask app context so it can be run directly as a
scheduled command (`python scripts/run_research.py`) with no web server.

Pipeline (see the module docstrings for detail):
    1. FETCH      pull recent items from every source (sources.py)
    2. DEDUPE     drop anything whose external_id we've already stored -- this
                  is BOTH the novelty check and the main cost control, and it
                  happens BEFORE any LLM call
    3. STORE new  persist the genuinely-new items (unscored) so they're on
                  record and can't be re-fetched-and-re-scored next week
    4. SCOUT      claude-haiku-4-5 scores the new items 0-10 (scout.py)
    5. SYNTHESIZE the app's ANTHROPIC_MODEL writes one brief from the survivors
                  (synthesize.py)
    6. STORE brief persist the brief and link its source items

Idempotent: a ResearchBrief already existing for the current week short-circuits
the whole run, so a second cron firing in the same week produces no second
brief and no duplicate items. Every external call is wrapped so one failure
can't kill the run.
"""
import json
import logging
import os
import sys
from datetime import date, datetime, timedelta

# Allow `python scripts/run_research.py` from anywhere: put the project root
# (this file's parent's parent) on the path before importing app modules.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
logger = logging.getLogger('run_research')

# How far back to look each week. A little wider than 7 days so a run that's a
# day late (or a source that indexes slowly) doesn't miss anything.
LOOKBACK_DAYS = 10


def _current_monday():
    """Monday (date) of the current week -- the week a brief is filed under.
    Same week convention used elsewhere in the app (routes_internal)."""
    today = date.today()
    return today - timedelta(days=today.weekday())


def run_weekly_research(db, api_key, model, lookback_days=LOOKBACK_DAYS):
    """Run the full pipeline once. Returns a summary dict. Assumes an active
    app context. Safe to run repeatedly in the same week (idempotent)."""
    from sqlalchemy.exc import IntegrityError

    from models import ResearchBrief, ResearchItem
    from sources import ALL_SOURCES
    import scout
    import synthesize

    week_of = _current_monday()

    # ── Idempotency gate: one brief per week ──
    existing = db.session.query(ResearchBrief).filter_by(week_of=week_of).first()
    if existing:
        logger.info('Brief for week_of=%s already exists (id=%s); nothing to do.',
                    week_of, existing.id)
        return {'ok': True, 'skipped': True, 'week_of': week_of.isoformat(), 'brief_id': existing.id}

    # ── 1. FETCH (per-source failures logged, not fatal) ──
    fetched = []
    for source in ALL_SOURCES:
        try:
            fetched.extend(source.fetch(since_days=lookback_days))
        except Exception:
            logger.exception('source %s failed; continuing with the others',
                             getattr(source, 'name', source))
    logger.info('Fetched %s items across %s source(s)', len(fetched), len(ALL_SOURCES))

    if not fetched:
        return {'ok': True, 'week_of': week_of.isoformat(), 'fetched': 0,
                'new': 0, 'kept': 0, 'brief_id': None}

    # ── 2. DEDUPE on external_id, BEFORE any LLM call ──
    incoming_ids = [it['external_id'] for it in fetched]
    known = {
        row.external_id for row in
        db.session.query(ResearchItem.external_id)
        .filter(ResearchItem.external_id.in_(incoming_ids)).all()
    }
    # De-dupe within this batch too (a paper can match several queries/sources).
    new_items, seen = [], set()
    for item in fetched:
        eid = item['external_id']
        if eid in known or eid in seen:
            continue
        seen.add(eid)
        new_items.append(item)
    logger.info('%s new items after dedupe (%s already known)', len(new_items), len(known))

    if not new_items:
        return {'ok': True, 'week_of': week_of.isoformat(), 'fetched': len(fetched),
                'new': 0, 'kept': 0, 'brief_id': None}

    # ── 3. STORE new items (unscored) so they're recorded and won't be
    #      re-fetched-and-re-scored next week. Keep the ORM rows keyed by
    #      external_id so we can update scores and link the brief afterwards. ──
    rows = {}
    for item in new_items:
        row = ResearchItem(
            source=item['source'],
            external_id=item['external_id'],
            title=item.get('title'),
            authors=item.get('authors'),
            abstract=item.get('abstract'),
            url=item.get('url'),
            published_date=item.get('published_date'),
            fetched_at=datetime.utcnow(),
        )
        db.session.add(row)
        rows[item['external_id']] = row
    db.session.commit()

    # ── 4. SCOUT: score only the new items ──
    scored = scout.score_items(new_items, api_key=api_key)
    for item in scored:
        row = rows.get(item['external_id'])
        if row is None:
            continue
        row.relevance_score = item.get('relevance_score')
        row.topics = json.dumps(item.get('topics') or [])
    db.session.commit()

    keepers = scout.survivors(scored)
    logger.info('%s items cleared the relevance bar', len(keepers))

    if not keepers:
        logger.info('No items cleared the scout; not writing a brief this week.')
        return {'ok': True, 'week_of': week_of.isoformat(), 'fetched': len(fetched),
                'new': len(new_items), 'kept': 0, 'brief_id': None}

    # ── 5. SYNTHESIZE the brief from survivors ──
    result = synthesize.synthesize_brief(keepers, api_key=api_key, model=model)
    if not result.get('ok'):
        logger.error('Synthesis failed: %s', result.get('error'))
        return {'ok': False, 'week_of': week_of.isoformat(), 'fetched': len(fetched),
                'new': len(new_items), 'kept': len(keepers), 'error': result.get('error')}

    # ── 6. STORE the brief and link its source items ──
    brief = ResearchBrief(
        week_of=week_of,
        title=result['title'],
        summary=result['summary'],
        coaching_takeaways=json.dumps(result['coaching_takeaways']),
        item_count=len(keepers),
        generated_at=datetime.utcnow(),
    )
    db.session.add(brief)
    db.session.flush()  # assign brief.id before linking
    for item in keepers:
        row = rows.get(item['external_id'])
        if row is not None:
            row.brief_id = brief.id
    try:
        db.session.commit()
    except IntegrityError:
        # The uq_research_brief_week constraint fired -- a concurrent run beat us
        # to this week. Back out cleanly rather than crashing; the winning run's
        # brief stands. (The scored items we already committed are kept and will
        # simply be deduped next week.)
        db.session.rollback()
        winner = db.session.query(ResearchBrief).filter_by(week_of=week_of).first()
        logger.warning('Brief for week_of=%s created concurrently (id=%s); skipping ours.',
                       week_of, getattr(winner, 'id', None))
        return {'ok': True, 'skipped': True, 'week_of': week_of.isoformat(),
                'fetched': len(fetched), 'new': len(new_items), 'kept': len(keepers),
                'brief_id': getattr(winner, 'id', None)}

    logger.info('Wrote brief id=%s for week_of=%s with %s items',
                brief.id, week_of, len(keepers))
    return {'ok': True, 'week_of': week_of.isoformat(), 'fetched': len(fetched),
            'new': len(new_items), 'kept': len(keepers), 'brief_id': brief.id}


def main():
    from app import create_app, db

    app = create_app()
    with app.app_context():
        api_key = app.config.get('ANTHROPIC_API_KEY')
        model = app.config.get('ANTHROPIC_MODEL')
        if not api_key:
            logger.error('ANTHROPIC_API_KEY is not set; cannot run the research agent.')
            return 1
        try:
            summary = run_weekly_research(db, api_key=api_key, model=model)
        except Exception:
            logger.exception('run_weekly_research crashed')
            try:
                db.session.rollback()
            except Exception:
                pass
            return 1
    logger.info('Done: %s', summary)
    return 0 if summary.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())
