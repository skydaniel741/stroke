"""Service-to-service routes with no user login concept -- hit by a Render
Cron Job on a schedule, not a browser. Protected by a shared-secret header
instead of a session cookie (see app.py's INTERNAL_CRON_SECRET config)."""
import json
import logging
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, current_app

internal_bp = Blueprint('internal', __name__, url_prefix='/internal')

logger = logging.getLogger(__name__)


def _current_week_start(now=None):
    """Monday 00:00 of the current week -- same convention as
    routes_coach.coach_pro_state's this_week_start."""
    now = now or datetime.utcnow()
    return (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


@internal_bp.route('/digest/generate', methods=['POST'])
def digest_generate():
    """Render Cron Job entry point (weekly): draft a ParentDigest for every
    active ParentLink that doesn't already have one for the current week.
    Per-link failures (API error, malformed tool output) are logged and
    skipped rather than aborting the whole batch. Every row lands as
    status='draft' -- this route never approves anything; that's a coach's
    call in the Coach Pro review queue (routes_coach)."""
    configured_secret = current_app.config.get('INTERNAL_CRON_SECRET')
    provided = request.headers.get('X-Cron-Secret') or ''
    # secrets.compare_digest instead of == to avoid a timing side-channel on
    # the comparison; also refuse outright if no secret is configured at all
    # (an unset secret must never mean "any header value validates").
    if not configured_secret or not secrets.compare_digest(provided, configured_secret):
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 401

    from app import db
    from models import ParentLink, ParentDigest, AttendanceRecord, SquadMembership
    import athlete_model
    from ai_utils import generate_parent_digest

    # The digest is about "the week just finished" (see generate_parent_digest's
    # docstring), not the week in progress -- _current_week_start() gives the
    # Monday of NOW's week, so a cron firing any time after that Monday (the
    # normal case for a weekly job) would otherwise report on a nearly-empty,
    # still-in-progress week. Subtract a week to land on the week that ended.
    week_start = (_current_week_start() - timedelta(weeks=1)).date()
    week_end = week_start + timedelta(days=7)

    links = db.session.query(ParentLink).filter_by(status='active').all()
    created, skipped, failed = 0, 0, 0

    for link in links:
        try:
            existing = (
                db.session.query(ParentDigest)
                .filter_by(parent_link_id=link.id, week_start=week_start)
                .first()
            )
            if existing:
                skipped += 1
                continue

            swimmer = link.swimmer
            if not swimmer:
                skipped += 1
                continue

            squad_ids = [
                m.squad_id for m in
                db.session.query(SquadMembership).filter_by(user_id=swimmer.id, status='active').all()
            ]
            week_records = (
                db.session.query(AttendanceRecord)
                .filter(
                    AttendanceRecord.swimmer_id == swimmer.id,
                    AttendanceRecord.squad_id.in_(squad_ids),
                    AttendanceRecord.session_date >= week_start,
                    AttendanceRecord.session_date < week_end,
                )
                .all()
                if squad_ids else []
            )
            scheduled = len(week_records)
            attended = sum(1 for r in week_records if r.status in ('present', 'late'))
            week_attendance = {
                'attended': attended,
                'scheduled': scheduled,
                'no_session_scheduled': scheduled == 0,
            }

            athlete_state = athlete_model.get_state(swimmer.id) if swimmer.id else {}

            result = generate_parent_digest(
                swimmer_name=swimmer.username,
                athlete_state=athlete_state,
                week_attendance=week_attendance,
                tone='balanced',
                api_key=current_app.config.get('ANTHROPIC_API_KEY'),
                model=current_app.config.get('ANTHROPIC_MODEL'),
            )
            if not result.get('ok'):
                failed += 1
                logger.warning(
                    'digest_generate: generation failed for parent_link_id=%s: %s',
                    link.id, result.get('error'),
                )
                continue

            content = json.dumps({
                'headline': result.get('headline'),
                'body': result.get('body'),
                'next_up': result.get('next_up'),
            })
            db.session.add(ParentDigest(
                parent_link_id=link.id,
                week_start=week_start,
                content=content,
                status='draft',
            ))
            db.session.commit()
            created += 1
        except Exception:
            db.session.rollback()
            failed += 1
            logger.exception('digest_generate: unexpected failure for parent_link_id=%s', link.id)

    return jsonify({
        'ok': True,
        'week_start': week_start.isoformat(),
        'created': created,
        'skipped': skipped,
        'failed': failed,
    })
