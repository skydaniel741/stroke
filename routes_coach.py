import csv
import io
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from auth_utils import coach_required

coach = Blueprint('coach', __name__, url_prefix='/coach')


@coach.context_processor
def inject_coach_nav():
    if not current_user.is_authenticated:
        return {}
    from app import db
    from models import Squad

    nav_squads = db.session.query(Squad).filter_by(coach_id=current_user.id).order_by(Squad.name).all()
    return {'nav_squads': nav_squads}


def _squad_or_404(squad_id):
    from app import db
    from models import Squad

    squad = db.session.query(Squad).get(squad_id)
    if not squad:
        abort(404)
    is_owner = squad.coach_id == current_user.id
    is_club_owner = squad.club and squad.club.owner_id == current_user.id
    if not (is_owner or is_club_owner or current_user.is_admin):
        abort(403)
    return squad


def _member_or_404(squad, swimmer_id):
    """Confirm swimmer_id is actually a member of squad (not just any user id) --
    the coach-ownership check in _squad_or_404 only proves the coach owns the
    squad, not that the swimmer belongs to it."""
    from app import db
    from models import SquadMembership

    membership = (
        db.session.query(SquadMembership)
        .filter_by(squad_id=squad.id, user_id=swimmer_id)
        .first()
    )
    if not membership:
        abort(404)
    return membership


def _pool_key(p):
    return '50' if str(p or '25').startswith('50') else '25'


def _best_by_event_pool(swims):
    """Best (lowest) time per (event, pool) bucket. Keying by pool as well as
    event matters -- a 25m and 50m time for the same event aren't comparable,
    so keying by event alone lets a 50m time silently overwrite (or lose to) an
    unrelated 25m PB. Returns {(event, pool_key): {'event','time','pool','secs','date'}}."""
    best = {}
    for sw in swims:
        secs = sw.time_in_seconds()
        if secs is None:
            continue
        key = (sw.event, _pool_key(sw.pool))
        cur = best.get(key)
        if cur is None or secs < cur['secs']:
            best[key] = {
                'event': sw.event, 'time': sw.time, 'pool': sw.pool, 'secs': secs,
                'date': sw.logged_at.strftime('%Y-%m-%d'),
            }
    return best


def _css_trend(user_id):
    """Aerobic-capacity reading for a swimmer: CSS (Critical Swim Speed,
    sec/100m) plus the five training-pace zones derived from it, compared
    against the same computation for the prior 90-day window. Lower CSS =
    faster. Uses plan_logic.css_estimate, which prefers a real 400+200 pair
    but falls back to Riegel-predicting whichever is missing from any other
    freestyle PB on file -- so a swimmer with e.g. only an 800 free still
    gets a reading, just marked as estimated. Returns None only when there's
    no usable freestyle PB at all in the current window."""
    import plan_logic
    import pacing

    now = datetime.utcnow()
    current = plan_logic.css_estimate(user_id, days=90, end=now)
    if current is None:
        return None
    current_css = current['css']

    previous = plan_logic.css_estimate(user_id, days=90, end=now - timedelta(days=90))
    prev_css = previous['css'] if previous else None

    direction = None
    change_pct = None
    if prev_css:
        change_pct = round((prev_css - current_css) / prev_css * 100, 1)  # positive = faster (CSS dropped)
        if change_pct >= 0.5:
            direction = 'improving'
        elif change_pct <= -0.5:
            direction = 'slipping'
        else:
            direction = 'steady'

    zone_paces = plan_logic.zones(current_css)
    zone_rows = [
        {
            'key': key,
            'label': plan_logic.ZONE_META[key]['label'],
            'note': plan_logic.ZONE_META[key]['note'],
            'pace': pacing.fmt_secs(zone_paces[key]),
        }
        for key in plan_logic.ZONE_ORDER
    ]

    basis_note = None
    if current['source'] == 'estimated_riegel':
        parts = sorted({current['basis400'], current['basis200']})
        basis_note = f"Estimated from {' & '.join(parts)}. No direct 400+200 pair logged yet."

    return {
        'cssPace': pacing.fmt_secs(current_css),
        'source': current['source'],
        'basisNote': basis_note,
        'previousCssPace': pacing.fmt_secs(prev_css) if prev_css else None,
        'direction': direction,
        'changePct': change_pct,
        'zones': zone_rows,
    }


def _swimmer_type(user_id):
    """Sprint vs. distance aptitude reading for the Athlete Hub, or None when
    the swimmer doesn't have enough freestyle spread logged yet (see
    plan_logic.classify_swimmer_type for the minimum-data rule)."""
    import plan_logic

    result = plan_logic.classify_swimmer_type(user_id)
    if result is None:
        return None
    return {
        'profile': result['profile'],
        'label': plan_logic.SWIMMER_TYPE_LABELS[result['profile']],
        'note': plan_logic.SWIMMER_TYPE_NOTES[result['profile']],
        'exponent': result['exponent'],
        'basedOn': result['basedOn'],
    }


@coach.route('/')
@login_required
@coach_required
def coach_dashboard():
    return render_template('coach_pro.html')


@coach.route('/pro')
@login_required
@coach_required
def coach_pro():
    return redirect(url_for('coach.coach_dashboard'))


@coach.route('/pro/api/state')
@login_required
@coach_required
def coach_pro_state():
    from app import db
    from models import Squad, SquadMembership, User, Swim, Session, SavedSet, CoachAssignment, AttendanceRecord, SquadEvent, Announcement, ParentLink
    from sqlalchemy import or_
    import json as json_module
    import athlete_model
    import pacing

    squads = db.session.query(Squad).filter_by(coach_id=current_user.id).order_by(Squad.created_at.asc()).all()
    squad_ids = [s.id for s in squads]

    memberships = (
        db.session.query(SquadMembership)
        .filter(SquadMembership.squad_id.in_(squad_ids))
        .order_by(SquadMembership.created_at.asc())
        .all()
        if squad_ids else []
    )

    swimmer_ids = [m.user_id for m in memberships if m.user_id]
    users_by_id = {
        u.id: u for u in db.session.query(User).filter(User.id.in_(swimmer_ids)).all()
    } if swimmer_ids else {}

    swims_by_user = {}
    for sw in (db.session.query(Swim).filter(Swim.user_id.in_(swimmer_ids)).all() if swimmer_ids else []):
        swims_by_user.setdefault(sw.user_id, []).append(sw)

    sessions_by_user = {}
    for se in (db.session.query(Session).filter(Session.user_id.in_(swimmer_ids)).all() if swimmer_ids else []):
        sessions_by_user.setdefault(se.user_id, []).append(se)

    # Batched, not per-swimmer: get_states_batch is one query for every
    # already-fresh cached row, instead of swimmer_payload calling get_state()
    # once per SquadMembership (an N+1, and a double read for anyone in more
    # than one of this coach's squads).
    athlete_states_by_user = athlete_model.get_states_batch(swimmer_ids)

    # Attendance rate over the last 30 days: attended (present/late) marks
    # divided by the days their squad actually held a marked roll call.
    since_30 = (datetime.utcnow() - timedelta(days=30)).date()
    recent_attendance = (
        db.session.query(AttendanceRecord)
        .filter(AttendanceRecord.squad_id.in_(squad_ids), AttendanceRecord.session_date >= since_30)
        .all()
        if squad_ids else []
    )
    squad_marked_days = {}
    attendance_by_swimmer = {}
    for rec in recent_attendance:
        squad_marked_days.setdefault(rec.squad_id, set()).add(rec.session_date)
        attendance_by_swimmer.setdefault(rec.swimmer_id, []).append(rec)

    def attendance_rate(m):
        marked = len(squad_marked_days.get(m.squad_id, set()))
        if not m.user_id or marked == 0:
            return None
        attended = sum(
            1 for r in attendance_by_swimmer.get(m.user_id, [])
            if r.squad_id == m.squad_id and r.status in ('present', 'late')
        )
        return round(100 * attended / marked)

    # Monday 00:00 of the current week, for per-swimmer weekly volume bars
    now = datetime.utcnow()
    this_week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)

    parent_links_by_swimmer = {}
    if swimmer_ids:
        for l in db.session.query(ParentLink).filter(ParentLink.swimmer_id.in_(swimmer_ids), ParentLink.status != 'revoked').order_by(ParentLink.created_at.desc()).all():
            parent_links_by_swimmer.setdefault(l.swimmer_id, l)  # most recent non-revoked link wins

    def swimmer_payload(m):
        u = users_by_id.get(m.user_id)
        swims = swims_by_user.get(m.user_id, [])
        sessions = sessions_by_user.get(m.user_id, [])
        parent_link = parent_links_by_swimmer.get(m.user_id)

        weekly_volume = []
        for i in range(7, -1, -1):
            wk_start = this_week_start - timedelta(weeks=i)
            wk_end = wk_start + timedelta(days=7)
            weekly_volume.append(
                sum(s.distance() for s in swims if wk_start <= s.logged_at < wk_end) +
                sum(se.total_distance() for se in sessions if wk_start <= se.logged_at < wk_end)
            )

        best_by_event_pool = _best_by_event_pool(swims)

        # Cached per-swimmer progression model (load, per-event trends, overall
        # classification) -- already kept fresh by athlete_model.update_athlete_state,
        # called from the attendance-save and test-set-log routes. Read from the
        # batch fetched once above (athlete_states_by_user), not a per-swimmer
        # get_state() call here -- see that comment for why.
        athlete_state = athlete_states_by_user.get(m.user_id, {}) if m.user_id else {}

        activity_dates = [s.logged_at for s in swims] + [se.logged_at for se in sessions]
        last_active = max(activity_dates).strftime('%Y-%m-%d') if activity_dates else None
        total_distance = sum(s.distance() for s in swims) + sum(se.total_distance() for se in sessions)

        recent_activity = sorted(
            [
                {'kind': 'PB attempt', 'label': s.event, 'pool': s.pool or '—', 'loggedAt': s.logged_at.strftime('%Y-%m-%d')}
                for s in swims
            ] + [
                {
                    'kind': se.session_type or 'Session',
                    'label': (f"{len(se.get_sets())} set" + ('s' if len(se.get_sets()) != 1 else '')) if se.get_sets() else (se.session_type or 'Session'),
                    'pool': se.pool or '—',
                    'loggedAt': se.logged_at.strftime('%Y-%m-%d'),
                }
                for se in sessions
            ],
            key=lambda x: x['loggedAt'],
            reverse=True,
        )[:10]

        return {
            'membershipId': m.id,
            'userId': m.user_id,
            'name': u.username if u else (m.invited_email or 'Invited swimmer'),
            'email': u.email if u else m.invited_email,
            'squadId': m.squad_id,
            'status': m.status,
            'laneGroup': m.lane_group,
            'personalBests': sorted(best_by_event_pool.values(), key=lambda x: (x['event'], x['pool'] or '')),
            # Pacing (split) analysis for this swimmer's recent races that carry
            # 50m splits -- same engine the solo analytics page uses (pacing.py),
            # rendered coach-facing in the Athlete Hub.
            'pacingAnalyses': pacing.analyze_swims(swims, limit=5, voice='coach'),
            # Aerobic-capacity trend (Critical Swim Speed) -- reuses the same CSS
            # engine the solo training-plan feature already computes from,
            # None when the swimmer has no recent 400+200 freestyle pair.
            'cssTrend': _css_trend(m.user_id) if m.user_id else None,
            # Sprint vs. distance aptitude, fit from the swimmer's own
            # freestyle PBs across distances (see plan_logic.classify_swimmer_type).
            'swimmerType': _swimmer_type(m.user_id) if m.user_id else None,
            'recentActivity': recent_activity,
            'sessionsCount': len(swims) + len(sessions),
            'totalDistance': total_distance,
            'lastActive': last_active,
            'attendanceRate': attendance_rate(m),
            'weeklyVolume': weekly_volume,
            # Raw athlete_model state (same shape /solo/analytics renders from):
            # {trend, trend_reason, acwr, events: {event: {direction, change_pct,
            # recent_avg, n}}, chronic_weekly_load, acute_load, total_logs, ...}.
            # Passed through as-is (snake_case, matching the engine) rather than
            # remapped to camelCase, so this stays in lockstep with athlete_model.py.
            'athleteState': athlete_state or None,
            'isMinor': bool(u and u.is_minor),
            'parentStatus': parent_link.status if parent_link else 'none',
            'parentName': parent_link.parent.username if (parent_link and parent_link.status == 'active') else None,
            'parentInviteUrl': f'/parent/join/{parent_link.invite_token}' if (parent_link and parent_link.status == 'pending') else None,
        }

    swimmers_payload = [swimmer_payload(m) for m in memberships]

    saved_sets = (
        db.session.query(SavedSet)
        .filter_by(created_by=current_user.id)
        .order_by(SavedSet.created_at.desc())
        .all()
    )

    conditions = []
    if squad_ids:
        conditions.append(CoachAssignment.squad_id.in_(squad_ids))
    if swimmer_ids:
        conditions.append(CoachAssignment.swimmer_id.in_(swimmer_ids))
    assignments = (
        db.session.query(CoachAssignment).filter(or_(*conditions)).order_by(CoachAssignment.created_at.desc()).all()
        if conditions else []
    )

    def squad_payload(sq):
        season_plan = None
        if sq.season_plan_json:
            try:
                season_plan = json_module.loads(sq.season_plan_json)
            except ValueError:
                season_plan = None
        return {
            'id': sq.id,
            'name': sq.name,
            'color': sq.color or 'blue',
            'inviteCode': sq.invite_code,
            'memberCount': sum(1 for m in memberships if m.squad_id == sq.id),
            'seasonPlan': season_plan,
        }

    def set_payload(s):
        return {
            'id': s.id,
            'title': s.name,
            'description': s.description,
            'category': s.category or 'Fitness',
            'pool': s.pool,
            'sessionType': s.session_type,
            'totalDistance': s.total_distance(),
            'blocks': s.get_sets(),
        }

    def assignment_payload(a):
        target_type = 'squad' if a.squad_id else 'swimmer'
        target_id = a.squad_id if a.squad_id else a.swimmer_id
        return {
            'id': a.id,
            'setId': a.saved_set_id,
            'setTitle': a.saved_set.name if a.saved_set else 'Deleted set',
            'targetType': target_type,
            'targetId': target_id,
            'dueDate': a.due_date.isoformat() if a.due_date else None,
            'status': a.status,
            'notes': a.notes,
        }

    today = datetime.utcnow().date()
    upcoming_events = (
        db.session.query(SquadEvent)
        .filter(
            SquadEvent.squad_id.in_(squad_ids),
            SquadEvent.event_date >= today,
            SquadEvent.event_date <= today + timedelta(days=13),
        )
        .order_by(SquadEvent.event_date, SquadEvent.slot, SquadEvent.event_time)
        .all()
        if squad_ids else []
    )

    def event_payload(e):
        return {
            'id': e.id,
            'squadId': e.squad_id,
            'title': e.title,
            'date': e.event_date.isoformat(),
            'time': e.event_time or '',
            'slot': e.slot or '',
            'type': e.event_type or 'practice',
            'notes': e.notes or '',
            'setId': e.saved_set_id,
            'setTitle': e.saved_set.name if e.saved_set else None,
            'setDistance': e.saved_set.total_distance() if e.saved_set else None,
        }

    announcements = (
        db.session.query(Announcement)
        .filter(Announcement.squad_id.in_(squad_ids))
        .order_by(Announcement.created_at.desc())
        .limit(30)
        .all()
        if squad_ids else []
    )

    def announcement_payload(a):
        return {
            'id': a.id,
            'squadId': a.squad_id,
            'message': a.message,
            'createdAt': a.created_at.strftime('%Y-%m-%d %H:%M'),
        }

    from flask import current_app
    return {
        'squads': [squad_payload(s) for s in squads],
        'swimmers': swimmers_payload,
        'savedSets': [set_payload(s) for s in saved_sets],
        'assignments': [assignment_payload(a) for a in assignments],
        'upcomingEvents': [event_payload(e) for e in upcoming_events],
        'announcements': [announcement_payload(a) for a in announcements],
        'today': today.isoformat(),
        'aiEnabled': bool(current_app.config.get('AI_SCAN_ENABLED')),
    }


@coach.route('/pro/api/announcements', methods=['POST'])
@login_required
@coach_required
def coach_pro_announcement_create():
    from app import db
    from models import Announcement

    squad = _squad_or_404(request.form.get('squad_id', type=int) or 0)
    message = (request.form.get('message') or '').strip()
    if not message:
        return {'ok': False, 'error': 'Write a message first.'}, 400

    db.session.add(Announcement(squad_id=squad.id, author_id=current_user.id, message=message))
    db.session.commit()
    return {'ok': True}


@coach.route('/pro/api/announcements/<int:announcement_id>/delete', methods=['POST'])
@login_required
@coach_required
def coach_pro_announcement_delete(announcement_id):
    from app import db
    from models import Announcement

    a = db.session.query(Announcement).get(announcement_id)
    if not a or not a.squad_id:
        abort(404)
    _squad_or_404(a.squad_id)
    db.session.delete(a)
    db.session.commit()
    return {'ok': True}


@coach.route('/pro/api/schedule', methods=['POST'])
@login_required
@coach_required
def coach_pro_schedule_create():
    from app import db
    from models import SquadEvent, SavedSet

    squad = _squad_or_404(request.form.get('squad_id', type=int) or 0)
    title = (request.form.get('title') or '').strip()
    try:
        day = datetime.strptime(request.form.get('date', ''), '%Y-%m-%d').date()
    except ValueError:
        return {'ok': False, 'error': 'Pick a valid date.'}, 400
    if not title:
        return {'ok': False, 'error': 'The session needs a title.'}, 400

    slot = request.form.get('slot', '')
    if slot not in ('AM', 'PM', ''):
        slot = ''

    saved_set_id = request.form.get('set_id', type=int)
    if saved_set_id:
        s = db.session.query(SavedSet).filter_by(id=saved_set_id, created_by=current_user.id).first()
        saved_set_id = s.id if s else None

    db.session.add(SquadEvent(
        squad_id=squad.id,
        title=title,
        event_date=day,
        event_time=(request.form.get('time') or '').strip(),
        slot=slot,
        event_type=request.form.get('event_type', 'practice'),
        saved_set_id=saved_set_id,
        notes=(request.form.get('notes') or '').strip(),
        created_by=current_user.id,
    ))
    db.session.commit()
    return {'ok': True}


@coach.route('/pro/api/schedule/<int:event_id>/delete', methods=['POST'])
@login_required
@coach_required
def coach_pro_schedule_delete(event_id):
    from app import db
    from models import SquadEvent

    e = db.session.query(SquadEvent).get(event_id)
    if not e:
        abort(404)
    _squad_or_404(e.squad_id)
    db.session.delete(e)
    db.session.commit()
    return {'ok': True}


@coach.route('/pro/api/squads', methods=['POST'])
@login_required
@coach_required
def coach_pro_create_squad():
    from app import db
    from models import Squad

    name = (request.form.get('name') or '').strip()
    color = request.form.get('color', 'blue')
    if not name:
        return {'ok': False, 'error': 'Squad needs a name.'}, 400

    squad = Squad(name=name, coach_id=current_user.id, invite_code=secrets.token_urlsafe(6), color=color)
    db.session.add(squad)
    db.session.commit()
    return {'ok': True, 'id': squad.id}


@coach.route('/pro/api/squads/<int:squad_id>/delete', methods=['POST'])
@login_required
@coach_required
def coach_pro_delete_squad(squad_id):
    from app import db
    from models import SquadMembership, CoachAssignment

    squad = _squad_or_404(squad_id)
    db.session.query(SquadMembership).filter_by(squad_id=squad.id).delete()
    db.session.query(CoachAssignment).filter_by(squad_id=squad.id).delete()
    db.session.delete(squad)
    db.session.commit()
    return {'ok': True}


@coach.route('/pro/api/squads/<int:squad_id>/season-plan', methods=['POST'])
@login_required
@coach_required
def coach_pro_save_season_plan(squad_id):
    import json as json_module
    from datetime import date as date_cls
    from app import db

    squad = _squad_or_404(squad_id)
    try:
        payload = json_module.loads(request.form.get('season_plan') or '{}')
    except ValueError:
        return {'ok': False, 'error': 'Malformed season plan.'}, 400

    target_meet = payload.get('targetMeet') or {}
    meet_name = (target_meet.get('name') or '').strip()[:120]
    meet_date = (target_meet.get('date') or '').strip()
    if not meet_name or not meet_date:
        return {'ok': False, 'error': 'A target meet name and date are required.'}, 400

    phases = []
    for p in payload.get('phases') or []:
        phase = (p.get('phase') or '').strip()[:120]
        start = (p.get('start') or '').strip()
        end = (p.get('end') or '').strip()
        if not phase or not start or not end:
            continue
        try:
            date_cls.fromisoformat(start)
            date_cls.fromisoformat(end)
        except ValueError:
            return {'ok': False, 'error': 'Phase dates must be valid dates.'}, 400
        phases.append({'phase': phase, 'start': start, 'end': end})

    try:
        date_cls.fromisoformat(meet_date)
    except ValueError:
        return {'ok': False, 'error': 'Target meet date must be a valid date.'}, 400

    squad.season_plan_json = json_module.dumps({
        'targetMeet': {'name': meet_name, 'date': meet_date},
        'phases': phases,
    })
    db.session.commit()
    return {'ok': True}


@coach.route('/pro/api/squads/<int:squad_id>/invite', methods=['POST'])
@login_required
@coach_required
def coach_pro_invite(squad_id):
    from app import db
    from models import SquadMembership, User

    squad = _squad_or_404(squad_id)
    email = (request.form.get('email') or '').strip().lower()
    if not email:
        return {'ok': False, 'error': 'Enter an email to invite.'}, 400

    existing_user = db.session.query(User).filter_by(email=email).first()
    membership = SquadMembership(
        squad_id=squad.id,
        user_id=existing_user.id if existing_user else None,
        invited_email=email,
        status='invited',
    )
    db.session.add(membership)
    db.session.commit()
    return {'ok': True, 'membershipId': membership.id}


def _read_roster_csv(file):
    """Decode an uploaded roster CSV into (headers, rows). Rows are dicts
    keyed by the original headers. Returns (None, None) if it can't be read."""
    try:
        raw = file.stream.read()
        text = raw.decode('utf-8-sig')
    except Exception:
        try:
            text = raw.decode('latin-1')  # last-ditch for odd exports
        except Exception:
            return None, None
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return None, None
    headers = [h for h in reader.fieldnames if h and h.strip()]
    rows = [row for row in reader]
    return headers, rows


@coach.route('/pro/api/squads/<int:squad_id>/import/preview', methods=['POST'])
@login_required
@coach_required
def coach_pro_import_preview(squad_id):
    """Step 1 of AI roster import: parse the uploaded CSV, ask the AI which
    column is which, and return a preview the coach confirms. Writes NOTHING
    to the DB -- the human-in-the-loop check happens before any insert."""
    from flask import current_app
    from app import db
    from models import SquadMembership, User
    from ai_utils import map_roster_columns

    squad = _squad_or_404(squad_id)

    file = request.files.get('csv_file')
    if not file or not file.filename:
        return {'ok': False, 'error': 'Choose a CSV file to import.'}, 400

    headers, rows = _read_roster_csv(file)
    if not headers:
        return {'ok': False, 'error': "Couldn't read that file. Export your roster as a CSV and try again."}, 400
    if not rows:
        return {'ok': False, 'error': 'That CSV has headers but no swimmer rows.'}, 400

    mapping = map_roster_columns(
        headers, rows[:6],
        current_app.config.get('ANTHROPIC_API_KEY'),
        current_app.config.get('ANTHROPIC_MODEL'),
    )

    def _cell(row, header):
        return (row.get(header) or '').strip() if header else ''

    # Emails already on this squad (linked users + still-pending invites), so we
    # can flag duplicates instead of creating a second membership for them.
    existing = set()
    for m in db.session.query(SquadMembership).filter_by(squad_id=squad.id).all():
        if m.invited_email:
            existing.add(m.invited_email.strip().lower())
        if m.user_id and m.swimmer and m.swimmer.email:
            existing.add(m.swimmer.email.strip().lower())

    known_users = {}
    if mapping.get('email'):
        emails_in_file = {_cell(r, mapping['email']).lower() for r in rows if _cell(r, mapping['email'])}
        if emails_in_file:
            for u in db.session.query(User).filter(User.email.in_(emails_in_file)).all():
                known_users[u.email.strip().lower()] = u

    preview = []
    seen_in_file = set()
    for row in rows:
        if mapping.get('full_name'):
            name = _cell(row, mapping['full_name'])
        else:
            name = ' '.join(p for p in (_cell(row, mapping.get('first_name')), _cell(row, mapping.get('last_name'))) if p)
        email = _cell(row, mapping.get('email')).lower()
        group = _cell(row, mapping.get('group'))
        dob = _cell(row, mapping.get('dob'))

        if not email:
            status = 'no_email'
        elif email in existing or email in seen_in_file:
            status = 'duplicate'
        else:
            status = 'new'
        if email:
            seen_in_file.add(email)

        preview.append({
            'name': name or '(no name)',
            'email': email,
            'group': group,
            'dob': dob,
            'status': status,
            'hasAccount': email in known_users,
        })

    counts = {
        'new': sum(1 for p in preview if p['status'] == 'new'),
        'duplicate': sum(1 for p in preview if p['status'] == 'duplicate'),
        'no_email': sum(1 for p in preview if p['status'] == 'no_email'),
    }
    return {'ok': True, 'mapping': mapping, 'headers': headers, 'rows': preview, 'counts': counts}


@coach.route('/pro/api/squads/<int:squad_id>/import/commit', methods=['POST'])
@login_required
@coach_required
def coach_pro_import_commit(squad_id):
    """Step 2 of AI roster import: insert the rows the coach confirmed. Takes a
    JSON body of {rows: [{name, email, group}]} -- typically the 'new' rows the
    preview surfaced. Re-checks for duplicates server-side so a stale preview
    can't create doubles."""
    from app import db
    from models import SquadMembership, User

    squad = _squad_or_404(squad_id)

    payload = request.get_json(silent=True) or {}
    incoming = payload.get('rows') or []
    if not incoming:
        return {'ok': False, 'error': 'No swimmers selected to import.'}, 400

    existing = set()
    for m in db.session.query(SquadMembership).filter_by(squad_id=squad.id).all():
        if m.invited_email:
            existing.add(m.invited_email.strip().lower())
        if m.user_id and m.swimmer and m.swimmer.email:
            existing.add(m.swimmer.email.strip().lower())

    imported = 0
    skipped = 0
    for row in incoming:
        email = (row.get('email') or '').strip().lower()
        if not email or email in existing:
            skipped += 1
            continue
        existing_user = db.session.query(User).filter_by(email=email).first()
        db.session.add(SquadMembership(
            squad_id=squad.id,
            user_id=existing_user.id if existing_user else None,
            invited_email=email,
            status='invited',
            lane_group=(row.get('group') or '').strip(),
        ))
        existing.add(email)
        imported += 1

    db.session.commit()
    return {'ok': True, 'imported': imported, 'skipped': skipped}


@coach.route('/pro/api/memberships/<int:membership_id>/toggle-minor', methods=['POST'])
@login_required
@coach_required
def coach_pro_toggle_minor(membership_id):
    from app import db
    from models import SquadMembership

    m = db.session.query(SquadMembership).get(membership_id)
    if not m or not m.user_id:
        abort(404)
    _squad_or_404(m.squad_id)
    m.swimmer.is_minor = not m.swimmer.is_minor
    db.session.commit()
    return {'ok': True, 'isMinor': m.swimmer.is_minor}


@coach.route('/pro/api/memberships/<int:membership_id>/invite-parent', methods=['POST'])
@login_required
@coach_required
def coach_pro_invite_parent(membership_id):
    """Coach-initiated parent link (see routes_parent.py) -- the coach already
    knows exactly which swimmer this is for, so the parent lands connected
    the moment they sign up at /parent/join/<token>, no separate claim step."""
    from app import db
    from models import SquadMembership, ParentLink

    m = db.session.query(SquadMembership).get(membership_id)
    if not m:
        abort(404)
    _squad_or_404(m.squad_id)
    if not m.user_id:
        return {'ok': False, 'error': "This swimmer doesn't have a STROKE account yet — invite them first."}, 400

    existing_pending = (
        db.session.query(ParentLink)
        .filter_by(swimmer_id=m.user_id, status='pending')
        .first()
    )
    if existing_pending:
        return {'ok': True, 'inviteUrl': f'/parent/join/{existing_pending.invite_token}'}

    token = secrets.token_urlsafe(24)
    db.session.add(ParentLink(swimmer_id=m.user_id, invite_token=token, status='pending'))
    db.session.commit()
    return {'ok': True, 'inviteUrl': f'/parent/join/{token}'}


@coach.route('/pro/api/memberships/<int:membership_id>/reassign', methods=['POST'])
@login_required
@coach_required
def coach_pro_reassign(membership_id):
    from app import db
    from models import SquadMembership, Squad

    m = db.session.query(SquadMembership).get(membership_id)
    if not m:
        abort(404)
    _squad_or_404(m.squad_id)
    new_squad_id = request.form.get('squad_id', type=int)
    new_squad = db.session.query(Squad).filter_by(id=new_squad_id, coach_id=current_user.id).first()
    if not new_squad:
        return {'ok': False, 'error': 'Invalid squad.'}, 400
    m.squad_id = new_squad.id
    db.session.commit()
    return {'ok': True}


@coach.route('/pro/api/memberships/<int:membership_id>/remove', methods=['POST'])
@login_required
@coach_required
def coach_pro_remove_membership(membership_id):
    from app import db
    from models import SquadMembership, CoachAssignment

    m = db.session.query(SquadMembership).get(membership_id)
    if not m:
        abort(404)
    _squad_or_404(m.squad_id)
    if m.user_id:
        db.session.query(CoachAssignment).filter_by(swimmer_id=m.user_id).delete()
    db.session.delete(m)
    db.session.commit()
    return {'ok': True}


@coach.route('/pro/api/sets/<int:set_id>/delete', methods=['POST'])
@login_required
@coach_required
def coach_pro_delete_set(set_id):
    from app import db
    from models import SavedSet, CoachAssignment

    s = db.session.query(SavedSet).filter_by(id=set_id, created_by=current_user.id).first()
    if not s:
        abort(404)
    db.session.query(CoachAssignment).filter_by(saved_set_id=s.id).delete()
    db.session.delete(s)
    db.session.commit()
    return {'ok': True}


@coach.route('/pro/api/sets/<int:set_id>/update', methods=['POST'])
@login_required
@coach_required
def coach_pro_update_set(set_id):
    import json as json_module
    from app import db
    from models import SavedSet

    s = db.session.query(SavedSet).filter_by(id=set_id, created_by=current_user.id).first()
    if not s:
        abort(404)

    name = (request.form.get('name') or '').strip()
    if not name:
        return {'ok': False, 'error': 'The set needs a title.'}, 400

    # Blocks come through as the same JSON shape the create form / AI generator
    # use. Full validation so a bad edit can't corrupt the stored set.
    from validation import clean_sets_json
    _sets_json, blocks = clean_sets_json(request.form.get('sets_data') or '[]')
    if not blocks:
        return {'ok': False, 'error': 'That set has no valid blocks — check the reps and distances.'}, 400

    s.name = name[:100]
    s.category = request.form.get('category') or s.category
    s.pool = request.form.get('pool') if request.form.get('pool') in ('25m', '50m') else s.pool
    s.description = (request.form.get('description') or '').strip()
    if request.form.get('session_type'):
        s.session_type = request.form.get('session_type').strip()[:50]
    s.sets_data = json_module.dumps(blocks)
    db.session.commit()
    return {'ok': True, 'id': s.id}


@coach.route('/pro/api/assignments', methods=['POST'])
@login_required
@coach_required
def coach_pro_create_assignment():
    from app import db
    from models import CoachAssignment, SavedSet, Squad, SquadMembership

    set_id = request.form.get('set_id', type=int)
    target_type = request.form.get('target_type')
    target_id = request.form.get('target_id', type=int)
    due_date = request.form.get('due_date')
    notes = request.form.get('notes', '')

    saved_set = db.session.query(SavedSet).filter_by(id=set_id, created_by=current_user.id).first()
    if not saved_set or target_type not in ('squad', 'swimmer') or not target_id:
        return {'ok': False, 'error': 'Invalid assignment.'}, 400

    squad_id = None
    swimmer_id = None
    if target_type == 'squad':
        squad = db.session.query(Squad).filter_by(id=target_id, coach_id=current_user.id).first()
        if not squad:
            return {'ok': False, 'error': 'Invalid squad.'}, 400
        squad_id = squad.id
    else:
        membership = (
            db.session.query(SquadMembership)
            .join(Squad, Squad.id == SquadMembership.squad_id)
            .filter(SquadMembership.user_id == target_id, Squad.coach_id == current_user.id)
            .first()
        )
        if not membership:
            return {'ok': False, 'error': 'Invalid swimmer.'}, 400
        swimmer_id = target_id

    try:
        due = datetime.strptime(due_date, '%Y-%m-%d').date() if due_date else None
    except ValueError:
        due = None

    assignment = CoachAssignment(
        saved_set_id=saved_set.id, squad_id=squad_id, swimmer_id=swimmer_id,
        assigned_by=current_user.id, due_date=due, notes=notes, status='Assigned',
    )
    db.session.add(assignment)
    db.session.commit()
    return {'ok': True, 'id': assignment.id}


@coach.route('/pro/api/assignments/<int:assignment_id>/toggle', methods=['POST'])
@login_required
@coach_required
def coach_pro_toggle_assignment(assignment_id):
    from app import db
    from models import CoachAssignment

    a = db.session.query(CoachAssignment).get(assignment_id)
    if not a or a.assigned_by != current_user.id:
        abort(404)
    a.status = 'Completed' if a.status != 'Completed' else 'Assigned'
    db.session.commit()
    return {'ok': True, 'status': a.status}


@coach.route('/pro/api/assignments/<int:assignment_id>/delete', methods=['POST'])
@login_required
@coach_required
def coach_pro_delete_assignment(assignment_id):
    from app import db
    from models import CoachAssignment

    a = db.session.query(CoachAssignment).get(assignment_id)
    if not a or a.assigned_by != current_user.id:
        abort(404)
    db.session.delete(a)
    db.session.commit()
    return {'ok': True}


@coach.route('/pro/api/attendance')
@login_required
@coach_required
def coach_pro_attendance_get():
    from app import db
    from models import AttendanceRecord

    squad = _squad_or_404(request.args.get('squad_id', type=int) or 0)
    try:
        day = datetime.strptime(request.args.get('date', ''), '%Y-%m-%d').date()
    except ValueError:
        return {'ok': False, 'error': 'Invalid date.'}, 400

    records = (
        db.session.query(AttendanceRecord)
        .filter_by(squad_id=squad.id, session_date=day)
        .all()
    )
    return {'ok': True, 'marks': {str(r.swimmer_id): r.status for r in records}}


@coach.route('/pro/api/attendance', methods=['POST'])
@login_required
@coach_required
def coach_pro_attendance_save():
    import json as json_module
    from app import db
    from models import AttendanceRecord, SquadMembership, SquadEvent, Session

    squad = _squad_or_404(request.form.get('squad_id', type=int) or 0)
    try:
        day = datetime.strptime(request.form.get('date', ''), '%Y-%m-%d').date()
    except ValueError:
        return {'ok': False, 'error': 'Invalid date.'}, 400

    try:
        marks = json_module.loads(request.form.get('marks') or '{}')
    except ValueError:
        return {'ok': False, 'error': 'Invalid marks payload.'}, 400

    valid_ids = {
        m.user_id for m in
        db.session.query(SquadMembership).filter_by(squad_id=squad.id).all()
        if m.user_id
    }
    allowed = {'present', 'late', 'excused', 'absent'}
    saved = 0
    attended_ids = []
    for swimmer_id_str, status in marks.items():
        try:
            swimmer_id = int(swimmer_id_str)
        except (TypeError, ValueError):
            continue
        if swimmer_id not in valid_ids or status not in allowed:
            continue
        record = (
            db.session.query(AttendanceRecord)
            .filter_by(squad_id=squad.id, swimmer_id=swimmer_id, session_date=day)
            .first()
        )
        if not record:
            record = AttendanceRecord(squad_id=squad.id, swimmer_id=swimmer_id, session_date=day)
            db.session.add(record)
        record.status = status
        record.recorded_by = current_user.id
        saved += 1
        if status in ('present', 'late'):
            attended_ids.append(swimmer_id)

    # Any scheduled session that day with a set attached gets auto-logged for
    # swimmers who were there -- this is what saves squads from spreadsheets:
    # the swimmer's logbook fills itself in from the coach's roll call.
    auto_logged = 0
    auto_logged_ids = set()
    events_with_sets = (
        db.session.query(SquadEvent)
        .filter(
            SquadEvent.squad_id == squad.id,
            SquadEvent.event_date == day,
            SquadEvent.saved_set_id.isnot(None),
        )
        .all()
    )
    for event in events_with_sets:
        s = event.saved_set
        if not s:
            continue
        for swimmer_id in attended_ids:
            exists = (
                db.session.query(Session)
                .filter_by(user_id=swimmer_id, squad_event_id=event.id)
                .first()
            )
            if exists:
                continue
            db.session.add(Session(
                user_id=swimmer_id,
                session_type=s.session_type or 'Training',
                pool=s.pool,
                sets_data=s.sets_data,
                notes=f'Squad session: {event.title}' + (f' ({event.slot})' if event.slot else ''),
                logged_at=datetime.combine(day, datetime.min.time().replace(hour=9 if event.slot != 'PM' else 18)),
                source='squad',
                squad_event_id=event.id,
            ))
            auto_logged += 1
            auto_logged_ids.add(swimmer_id)

    db.session.commit()

    # Auto-logged squad sessions feed each swimmer's athlete model, same as
    # if they'd logged the session themselves.
    import athlete_model
    for sid in auto_logged_ids:
        athlete_model.update_athlete_state(sid)

    return {'ok': True, 'saved': saved, 'autoLogged': auto_logged}


@coach.route('/pro/api/ai/insights', methods=['POST'])
@login_required
@coach_required
def coach_pro_ai_insights():
    from flask import current_app
    from app import db
    from models import SquadMembership, User, Swim, Session, AttendanceRecord, StatusFlag
    from ai_utils import generate_squad_insights

    if not current_app.config.get('AI_SCAN_ENABLED'):
        return {'ok': False, 'error': 'AI features are not configured on this server.'}, 400

    squad = _squad_or_404(request.form.get('squad_id', type=int) or 0)

    memberships = (
        db.session.query(SquadMembership)
        .filter_by(squad_id=squad.id, status='active')
        .all()
    )
    swimmer_ids = [m.user_id for m in memberships if m.user_id]
    if not swimmer_ids:
        return {'ok': False, 'error': 'No active swimmers in this squad yet.'}, 400

    since = datetime.utcnow() - timedelta(days=60)
    since_30 = (datetime.utcnow() - timedelta(days=30)).date()

    users = {u.id: u for u in db.session.query(User).filter(User.id.in_(swimmer_ids)).all()}
    flags = {
        f.swimmer_id: f for f in
        db.session.query(StatusFlag).filter_by(squad_id=squad.id).all()
    }
    attendance = (
        db.session.query(AttendanceRecord)
        .filter(AttendanceRecord.squad_id == squad.id, AttendanceRecord.session_date >= since_30)
        .all()
    )
    marked_days = len({r.session_date for r in attendance})

    swimmers_digest = []
    for uid in swimmer_ids:
        u = users.get(uid)
        if not u:
            continue
        swims = db.session.query(Swim).filter(Swim.user_id == uid, Swim.logged_at >= since).all()
        sessions = db.session.query(Session).filter(Session.user_id == uid, Session.logged_at >= since).all()

        best_by_event_pool = _best_by_event_pool(swims)

        attended = sum(1 for r in attendance if r.swimmer_id == uid and r.status in ('present', 'late'))
        activity_dates = [s.logged_at for s in swims] + [se.logged_at for se in sessions]
        flag = flags.get(uid)

        swimmers_digest.append({
            'name': u.username,
            'sessions_60d': len(swims) + len(sessions),
            'distance_60d': sum(s.distance() for s in swims) + sum(se.total_distance() for se in sessions),
            'last_active': max(activity_dates).strftime('%Y-%m-%d') if activity_dates else None,
            'attendance': f'{attended}/{marked_days} marked practices (30d)' if marked_days else 'no roll calls yet',
            'best_times': [
                f"{pb['event']} ({pb['pool']}): {pb['time']}"
                for pb in sorted(best_by_event_pool.values(), key=lambda x: (x['event'], x['pool'] or ''))
            ][:6],
            'status_flag': f'{flag.status}: {flag.note}' if flag and flag.status != 'available' else None,
        })

    tone = request.form.get('tone', 'balanced')
    if tone not in ('encouraging', 'balanced', 'direct'):
        tone = 'balanced'

    result = generate_squad_insights(
        squad.name,
        swimmers_digest,
        current_app.config['ANTHROPIC_API_KEY'],
        current_app.config['ANTHROPIC_MODEL'],
        tone=tone,
    )
    if not result.get('ok'):
        return result, 502
    return result


@coach.route('/pro/api/ai/generate-set', methods=['POST'])
@login_required
@coach_required
def coach_pro_ai_generate_set():
    import json as json_module
    from flask import current_app
    from app import db
    from models import SavedSet
    from ai_utils import generate_coach_set

    if not current_app.config.get('AI_SCAN_ENABLED'):
        return {'ok': False, 'error': 'AI features are not configured on this server.'}, 400

    from validation import clean_int

    params = {
        'focus': (request.form.get('focus') or '').strip()[:200],
        'style': (request.form.get('style') or '').strip()[:100],
        'season_phase': (request.form.get('season_phase') or '').strip()[:100],
        'level': (request.form.get('level') or '').strip()[:100],
        'pool': request.form.get('pool') if request.form.get('pool') in ('25m', '50m') else '25m',
        'duration_minutes': clean_int(request.form.get('duration_minutes'), key='duration_minutes') or 60,
    }

    result = generate_coach_set(
        params,
        current_app.config['ANTHROPIC_API_KEY'],
        current_app.config['ANTHROPIC_MODEL'],
    )
    if not result.get('ok'):
        return result, 502

    generated = result['set']
    saved = SavedSet(
        name=generated['name'],
        pool=params['pool'],
        session_type=generated['session_type'],
        category=generated['category'],
        description=generated['description'],
        sets_data=json_module.dumps(generated['blocks']),
        created_by=current_user.id,
    )
    db.session.add(saved)
    db.session.commit()
    return {'ok': True, 'setId': saved.id, 'name': saved.name}


@coach.route('/pro/api/dryland/search', methods=['POST'])
@login_required
@coach_required
def coach_pro_dryland_search():
    from flask import current_app
    from ai_utils import fetch_dryland_content

    if not current_app.config.get('AI_SCAN_ENABLED'):
        return {'ok': False, 'error': 'AI features are not configured on this server.'}, 400

    params = {
        'focus': (request.form.get('focus') or '').strip()[:200],
        'age_range': (request.form.get('age_range') or '').strip()[:50],
        'level': (request.form.get('level') or '').strip()[:100],
    }

    result = fetch_dryland_content(
        params,
        current_app.config['ANTHROPIC_API_KEY'],
        current_app.config['ANTHROPIC_MODEL'],
    )
    if not result.get('ok'):
        return result, 502
    return result


DRYLAND_SAVE_CATEGORIES = ('Strength', 'Mobility', 'Core')


@coach.route('/pro/api/dryland/save', methods=['POST'])
@login_required
@coach_required
def coach_pro_dryland_save():
    """Save one coach-reviewed dryland candidate (nothing was persisted after
    /dryland/search -- results are ephemeral until this point) as a
    TrainingProgram row, distinguishable from the admin-curated solo library
    via created_by. squad_id/swimmer_id are accepted here for a later
    assignment-wiring phase (see docs/plans/2026-07-19-coach-dryland-content
    -agent-design.md) -- not stored anywhere yet, TrainingProgram has no such
    columns; squad_id is only used to confirm the coach actually owns that
    squad before proceeding, out of caution."""
    import json as json_module
    from flask import current_app
    from app import db
    from models import TrainingProgram

    if not current_app.config.get('AI_SCAN_ENABLED'):
        return {'ok': False, 'error': 'AI features are not configured on this server.'}, 400

    squad_id = request.form.get('squad_id', type=int)
    if squad_id:
        _squad_or_404(squad_id)

    title = (request.form.get('title') or '').strip()[:150]
    description = (request.form.get('description') or '').strip()[:300]
    category = request.form.get('category') if request.form.get('category') in DRYLAND_SAVE_CATEGORIES else 'Strength'
    source_name = (request.form.get('source_name') or '').strip()[:100]
    source_url = (request.form.get('source_url') or '').strip()[:500]

    try:
        exercises = json_module.loads(request.form.get('exercises') or '[]')
        if not isinstance(exercises, list):
            exercises = []
    except (ValueError, TypeError):
        exercises = []

    blocks = []
    for ex in exercises:
        if not isinstance(ex, dict):
            continue
        name = str(ex.get('name') or '').strip()
        if not name:
            continue
        blocks.append({
            'heading': name[:100],
            'body': str(ex.get('notes') or '').strip()[:200],
            'sets': str(ex.get('sets') or '').strip()[:20],
            'reps': str(ex.get('reps') or '').strip()[:30],
            'rest': str(ex.get('rest') or '').strip()[:30],
        })

    if not title or not blocks:
        return {'ok': False, 'error': "Missing that session's title or exercises — try searching again."}, 400

    full_description = description
    if source_name or source_url:
        source_line = f"Source: {source_name or 'web'}" + (f" ({source_url})" if source_url else "")
        full_description = f"{description}\n\n{source_line}" if description else source_line

    program = TrainingProgram(
        title=title,
        category=category,
        description=full_description,
        content_blocks=json_module.dumps(blocks),
        created_by=current_user.id,
    )
    db.session.add(program)
    db.session.commit()
    return {'ok': True, 'programId': program.id, 'title': program.title}


MAX_SCAN_BYTES = 20 * 1024 * 1024


@coach.route('/pro/api/test-sets/scan', methods=['POST'])
@login_required
@coach_required
def coach_pro_test_set_scan():
    from flask import current_app
    from app import db
    from models import SquadMembership, User
    from ai_utils import extract_test_results_from_image

    if not current_app.config.get('AI_SCAN_ENABLED'):
        return {'ok': False, 'error': 'AI features are not configured on this server.'}, 400

    squad = _squad_or_404(request.form.get('squad_id', type=int) or 0)
    file = request.files.get('photo')
    if not file or not file.filename:
        return {'ok': False, 'error': 'Choose a photo first.'}, 400
    image_bytes = file.read()
    if len(image_bytes) > MAX_SCAN_BYTES:
        return {'ok': False, 'error': 'That photo is too large — try a smaller image.'}, 400

    memberships = (
        db.session.query(SquadMembership)
        .filter_by(squad_id=squad.id, status='active')
        .all()
    )
    swimmer_ids = [m.user_id for m in memberships if m.user_id]
    users = db.session.query(User).filter(User.id.in_(swimmer_ids)).all() if swimmer_ids else []
    name_to_id = {u.username: u.id for u in users}

    result = extract_test_results_from_image(
        image_bytes,
        list(name_to_id.keys()),
        current_app.config['ANTHROPIC_API_KEY'],
        current_app.config['ANTHROPIC_MODEL'],
    )
    if not result.get('ok'):
        return result, 422

    for r in result['results']:
        r['userId'] = name_to_id.get(r['name'])
    return result


@coach.route('/pro/api/sets/scan', methods=['POST'])
@login_required
@coach_required
def coach_pro_set_scan():
    from flask import current_app
    from ai_utils import extract_set_from_image

    if not current_app.config.get('AI_SCAN_ENABLED'):
        return {'ok': False, 'error': 'AI features are not configured on this server.'}, 400

    file = request.files.get('photo')
    if not file or not file.filename:
        return {'ok': False, 'error': 'Choose a photo first.'}, 400
    image_bytes = file.read()
    if len(image_bytes) > MAX_SCAN_BYTES:
        return {'ok': False, 'error': 'That photo is too large — try a smaller image.'}, 400

    result = extract_set_from_image(
        image_bytes,
        current_app.config['ANTHROPIC_API_KEY'],
        current_app.config['ANTHROPIC_MODEL'],
    )
    return result, (200 if result.get('ok') else 422)


@coach.route('/pro/api/test-sets/log', methods=['POST'])
@login_required
@coach_required
def coach_pro_test_set_log():
    import json as json_module
    from app import db
    from models import SquadMembership, Swim

    squad = _squad_or_404(request.form.get('squad_id', type=int) or 0)
    event = (request.form.get('event') or '').strip()[:50]
    test_label = (request.form.get('test_label') or 'Test set').strip()[:100]
    pool = request.form.get('pool') if request.form.get('pool') in ('25m', '50m') else '25m'
    if not event:
        return {'ok': False, 'error': 'The results need an event, e.g. 100m Freestyle.'}, 400

    try:
        entries = json_module.loads(request.form.get('entries') or '[]')
    except ValueError:
        return {'ok': False, 'error': 'Invalid entries payload.'}, 400

    valid_ids = {
        m.user_id for m in
        db.session.query(SquadMembership).filter_by(squad_id=squad.id).all()
        if m.user_id
    }

    # Strict time parsing: rejects '1e100', 'Infinity', negatives and other
    # junk a hand-edited payload could carry, not just unparseable strings.
    from validation import clean_time

    def _secs(t):
        _norm, secs = clean_time(t, key='swim_seconds')
        return secs

    logged = 0
    logged_ids = set()
    for entry in entries:
        try:
            user_id = int(entry.get('userId'))
        except (TypeError, ValueError):
            continue
        times = [str(t).strip() for t in (entry.get('times') or []) if _secs(str(t).strip()) is not None][:30]
        if user_id not in valid_ids or not times:
            continue
        best = min(times, key=_secs)
        all_times_note = f'{test_label} — reps: {", ".join(times)}' if len(times) > 1 else test_label
        db.session.add(Swim(
            user_id=user_id,
            event=event,
            pool=pool,
            time=best,
            tag='test',
            notes=all_times_note,
        ))
        logged += 1
        logged_ids.add(user_id)

    db.session.commit()

    # Test swims are prime progression data: refresh each swimmer's model.
    import athlete_model
    for sid in logged_ids:
        athlete_model.update_athlete_state(sid)

    return {'ok': True, 'logged': logged}


def _coach_swimmer_ids():
    """user_ids of every active-membership swimmer across squads this coach
    owns -- the scoping set for the digest review queue below, same IDOR
    guard shape as _squad_or_404/_member_or_404 (a coach only ever sees
    data for their own squads, never another coach's). Mirrors
    _squad_or_404's ownership predicate (direct coach OR club owner OR
    admin) rather than direct coach_id alone, so a club owner reviewing
    squads run by someone else on their staff isn't silently excluded."""
    from app import db
    from models import Squad, SquadMembership

    if current_user.is_admin:
        squad_ids = [s.id for s in db.session.query(Squad).all()]
    else:
        squad_ids = [
            s.id for s in db.session.query(Squad).all()
            if s.coach_id == current_user.id or (s.club and s.club.owner_id == current_user.id)
        ]
    if not squad_ids:
        return []
    return [
        m.user_id for m in
        db.session.query(SquadMembership).filter(SquadMembership.squad_id.in_(squad_ids)).all()
        if m.user_id
    ]


@coach.route('/pro/api/digests/pending')
@login_required
@coach_required
def coach_pro_digests_pending():
    """Draft ParentDigest rows awaiting this coach's review -- scoped to
    ParentLink.swimmer_id values that are actually in one of this coach's
    own squads (via SquadMembership), never another coach's swimmers."""
    from app import db
    from models import ParentDigest, ParentLink, User
    import json as json_module

    swimmer_ids = _coach_swimmer_ids()
    if not swimmer_ids:
        return {'ok': True, 'digests': []}

    links = (
        db.session.query(ParentLink)
        .filter(ParentLink.swimmer_id.in_(swimmer_ids), ParentLink.status == 'active')
        .all()
    )
    link_ids = [l.id for l in links]
    links_by_id = {l.id: l for l in links}
    if not link_ids:
        return {'ok': True, 'digests': []}

    drafts = (
        db.session.query(ParentDigest)
        .filter(ParentDigest.parent_link_id.in_(link_ids), ParentDigest.status == 'draft')
        .order_by(ParentDigest.generated_at.desc())
        .all()
    )
    swimmer_ids_needed = {links_by_id[d.parent_link_id].swimmer_id for d in drafts}
    users_by_id = {
        u.id: u for u in db.session.query(User).filter(User.id.in_(swimmer_ids_needed)).all()
    } if swimmer_ids_needed else {}

    out = []
    for d in drafts:
        try:
            parsed = json_module.loads(d.content or '{}')
        except ValueError:
            parsed = {}
        link = links_by_id[d.parent_link_id]
        swimmer = users_by_id.get(link.swimmer_id)
        out.append({
            'id': d.id,
            'swimmerName': swimmer.username if swimmer else 'Unknown swimmer',
            'weekStart': d.week_start.isoformat(),
            'headline': parsed.get('headline'),
            'body': parsed.get('body'),
            'nextUp': parsed.get('next_up'),
        })
    return {'ok': True, 'digests': out}


@coach.route('/pro/api/digests/<int:digest_id>/approve', methods=['POST'])
@login_required
@coach_required
def coach_pro_digest_approve(digest_id):
    """Flip one draft digest to approved so it appears on the parent
    dashboard. Re-derives the coach's own swimmer_ids and checks the
    digest's ParentLink.swimmer_id against it before touching the row --
    the same IDOR guard as the pending-list query above, so a coach can't
    approve (or probe the existence of) another coach's swimmer's digest
    just by guessing an id in the URL."""
    from app import db
    from models import ParentDigest, ParentLink

    digest = db.session.get(ParentDigest, digest_id)
    if not digest:
        abort(404)
    link = db.session.get(ParentLink, digest.parent_link_id)
    if not link or link.swimmer_id not in _coach_swimmer_ids():
        abort(404)

    if digest.status == 'draft':
        digest.status = 'approved'
        digest.approved_at = datetime.utcnow()
        db.session.commit()
    return {'ok': True}


@coach.route('/squad/<int:squad_id>/membership/<int:membership_id>/lane', methods=['POST'])
@login_required
@coach_required
def squad_membership_lane(squad_id, membership_id):
    from app import db
    from models import SquadMembership

    squad = _squad_or_404(squad_id)
    m = db.session.query(SquadMembership).get(membership_id)
    if m and m.squad_id == squad.id:
        m.lane_group = request.form.get('lane_group', '').strip()
        db.session.commit()
        flash('Lane group updated.', 'success')
    return redirect(url_for('coach.coach_dashboard'))


@coach.route('/join/<invite_code>')
@login_required
def squad_join(invite_code):
    from app import db
    from models import Squad, SquadMembership

    squad = db.session.query(Squad).filter_by(invite_code=invite_code).first()
    if not squad:
        abort(404)

    # A membership may already exist for this user — either because they
    # were invited by email while already having an account (user_id was
    # linked at invite time), or because they joined previously. Either way,
    # only an 'active' membership means there's nothing left to do here;
    # 'invited' or 'pending_consent' must still pass through the checks below.
    membership = (
        db.session.query(SquadMembership)
        .filter_by(squad_id=squad.id, user_id=current_user.id)
        .first()
    )
    if membership and membership.status == 'active':
        flash('You are already part of this squad.', 'success')
        return redirect(url_for('main.dashboard'))

    if not membership:
        # Claim an invited-by-email row if one matches, otherwise self-serve join.
        membership = (
            db.session.query(SquadMembership)
            .filter_by(squad_id=squad.id, invited_email=current_user.email, user_id=None)
            .first()
        )
        if membership:
            membership.user_id = current_user.id
        else:
            membership = SquadMembership(squad_id=squad.id, user_id=current_user.id, status='invited')
            db.session.add(membership)

    if membership.requires_consent:
        membership.status = 'pending_consent'
        db.session.commit()
        return redirect(url_for('coach.consent_form', membership_id=membership.id))

    membership.status = 'active'
    membership.joined_at = datetime.utcnow()
    db.session.commit()
    flash(f'Joined {squad.name}.', 'success')
    return redirect(url_for('main.dashboard'))


@coach.route('/consent/<int:membership_id>', methods=['GET', 'POST'])
@login_required
def consent_form(membership_id):
    from app import db
    from models import SquadMembership, ConsentRecord, Squad

    membership = db.session.query(SquadMembership).get(membership_id)
    if not membership or membership.user_id != current_user.id:
        abort(404)
    squad = db.session.query(Squad).get(membership.squad_id)

    if request.method == 'POST':
        guardian_name = request.form.get('guardian_name', '').strip()
        guardian_email = request.form.get('guardian_email', '').strip()
        confirmed = bool(request.form.get('confirm'))

        if not guardian_name or not guardian_email or not confirmed:
            flash('Guardian name, email and confirmation are all required.', 'error')
            return redirect(url_for('coach.consent_form', membership_id=membership.id))

        record = ConsentRecord(
            membership_id=membership.id,
            guardian_name=guardian_name,
            guardian_email=guardian_email,
            consent_given=True,
            consent_given_at=datetime.utcnow(),
        )
        db.session.add(record)
        membership.status = 'active'
        membership.joined_at = datetime.utcnow()
        db.session.commit()
        flash(f'Consent recorded — welcome to {squad.name}.', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('consent_form.html', membership=membership, squad=squad)


@coach.route('/squad/<int:squad_id>/swimmer/<int:swimmer_id>/note', methods=['POST'])
@login_required
@coach_required
def squad_swimmer_note(squad_id, swimmer_id):
    from app import db
    from models import CoachNote

    squad = _squad_or_404(squad_id)
    _member_or_404(squad, swimmer_id)
    note = request.form.get('note', '').strip()
    if note:
        db.session.add(CoachNote(squad_id=squad.id, swimmer_id=swimmer_id, coach_id=current_user.id, note=note))
        db.session.commit()
        flash('Note added.', 'success')
    return redirect(url_for('coach.squad_swimmer_notes', squad_id=squad.id, swimmer_id=swimmer_id))


@coach.route('/squad/<int:squad_id>/swimmer/<int:swimmer_id>/notes')
@login_required
@coach_required
def squad_swimmer_notes(squad_id, swimmer_id):
    from app import db
    from models import CoachNote, User

    squad = _squad_or_404(squad_id)
    _member_or_404(squad, swimmer_id)
    notes = (
        db.session.query(CoachNote)
        .filter_by(squad_id=squad.id, swimmer_id=swimmer_id)
        .order_by(CoachNote.created_at.desc())
        .all()
    )
    swimmer = db.session.query(User).get(swimmer_id)
    return render_template('swimmer_notes.html', squad=squad, swimmer=swimmer, notes=notes)


@coach.route('/squad/<int:squad_id>/swimmer/<int:swimmer_id>/status', methods=['POST'])
@login_required
@coach_required
def squad_swimmer_status(squad_id, swimmer_id):
    from app import db
    from models import StatusFlag

    squad = _squad_or_404(squad_id)
    _member_or_404(squad, swimmer_id)
    status = request.form.get('status', 'available')
    note = request.form.get('note', '').strip()

    flag = (
        db.session.query(StatusFlag)
        .filter_by(squad_id=squad.id, swimmer_id=swimmer_id)
        .first()
    )
    if not flag:
        flag = StatusFlag(squad_id=squad.id, swimmer_id=swimmer_id)
        db.session.add(flag)

    flag.status = status
    flag.note = note
    flag.updated_at = datetime.utcnow()
    flag.updated_by = current_user.id
    db.session.commit()
    flash('Status updated.', 'success')
    return redirect(url_for('coach.squad_swimmer_notes', squad_id=squad.id, swimmer_id=swimmer_id))


@coach.route('/squad/<int:squad_id>/calendar')
@login_required
@coach_required
def squad_calendar(squad_id):
    import calendar as cal_module
    from app import db
    from models import SquadEvent

    squad = _squad_or_404(squad_id)

    today = datetime.utcnow().date()
    month_param = request.args.get('month', '')
    try:
        year, month = (int(x) for x in month_param.split('-'))
    except (ValueError, TypeError):
        year, month = today.year, today.month

    cal = cal_module.Calendar(firstweekday=6)  # Sunday-first
    weeks = cal.monthdatescalendar(year, month)

    month_start = weeks[0][0]
    month_end = weeks[-1][-1]
    events = (
        db.session.query(SquadEvent)
        .filter(
            SquadEvent.squad_id == squad.id,
            SquadEvent.event_date >= month_start,
            SquadEvent.event_date <= month_end,
        )
        .order_by(SquadEvent.event_time)
        .all()
    )
    events_by_date = {}
    for e in events:
        events_by_date.setdefault(e.event_date, []).append(e)

    calendar_weeks = [
        [{
            'date': d,
            'in_month': d.month == month,
            'is_today': d == today,
            'events': events_by_date.get(d, []),
        } for d in week]
        for week in weeks
    ]

    prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_month = (year + 1, 1) if month == 12 else (year, month + 1)

    upcoming = (
        db.session.query(SquadEvent)
        .filter(SquadEvent.squad_id == squad.id, SquadEvent.event_date >= today)
        .order_by(SquadEvent.event_date, SquadEvent.event_time)
        .limit(8)
        .all()
    )

    return render_template(
        'squad_calendar.html',
        squad=squad,
        calendar_weeks=calendar_weeks,
        month_label=f'{cal_module.month_name[month]} {year}',
        prev_month=f'{prev_month[0]}-{prev_month[1]:02d}',
        next_month=f'{next_month[0]}-{next_month[1]:02d}',
        current_month=f'{year}-{month:02d}',
        upcoming=upcoming,
        today=today,
    )


@coach.route('/squad/<int:squad_id>/calendar/create', methods=['POST'])
@login_required
@coach_required
def squad_calendar_create(squad_id):
    from app import db
    from models import SquadEvent

    squad = _squad_or_404(squad_id)

    title = request.form.get('title', '').strip()
    date_str = request.form.get('event_date', '').strip()
    if not title or not date_str:
        flash('An event needs a title and a date.', 'error')
        return redirect(url_for('coach.squad_calendar', squad_id=squad.id))

    try:
        event_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('That date didn\'t make sense.', 'error')
        return redirect(url_for('coach.squad_calendar', squad_id=squad.id))

    db.session.add(SquadEvent(
        squad_id=squad.id,
        title=title,
        event_date=event_date,
        event_time=request.form.get('event_time', '').strip(),
        event_type=request.form.get('event_type', 'practice'),
        notes=request.form.get('notes', '').strip(),
        created_by=current_user.id,
    ))
    db.session.commit()
    flash(f'"{title}" added to the calendar.', 'success')
    return redirect(url_for('coach.squad_calendar', squad_id=squad.id, month=f'{event_date.year}-{event_date.month:02d}'))


@coach.route('/squad/<int:squad_id>/calendar/<int:event_id>/delete', methods=['POST'])
@login_required
@coach_required
def squad_calendar_delete(squad_id, event_id):
    from app import db
    from models import SquadEvent

    squad = _squad_or_404(squad_id)
    event = db.session.query(SquadEvent).get(event_id)
    month = request.form.get('month', '')
    if event and event.squad_id == squad.id:
        db.session.delete(event)
        db.session.commit()
        flash('Event removed.', 'success')
    return redirect(url_for('coach.squad_calendar', squad_id=squad.id, month=month))


def _import_notes(ev):
    """Build the SquadEvent.notes line for an imported event: the date range
    (for multi-day meets, since SquadEvent stores only the start date), venue,
    and provenance so the coach knows it was auto-imported."""
    bits = []
    start, end = ev.get('start_date'), ev.get('end_date')
    if end and end != start:
        if start.month == end.month and start.year == end.year:
            bits.append(f"{start.day}–{end.strftime('%d %b %Y')}")
        else:
            bits.append(f"{start.strftime('%d %b')} – {end.strftime('%d %b %Y')}")
    if ev.get('location'):
        bits.append(ev['location'])
    bits.append('Imported from SCWC calendar')
    return ' · '.join(bits)


@coach.route('/squad/<int:squad_id>/calendar/import-scwc', methods=['POST'])
@login_required
@coach_required
def squad_calendar_import_scwc(squad_id):
    """Auto-import upcoming meets/championships from the SCWC club calendar onto
    this squad's schedule, so the coach doesn't have to enter them by hand.
    Fully automatic (no preview): fetch -> AI-classify to competitions only ->
    write new SquadEvents. Idempotent: dedupes on (event_date, title) against
    what's already on the squad, so re-running never double-books."""
    from app import db
    from flask import current_app
    from models import SquadEvent
    from events_sources import SquarespaceEventsSource
    from ai_utils import classify_swim_events

    squad = _squad_or_404(squad_id)
    month = request.form.get('month', '')
    back = redirect(url_for('coach.squad_calendar', squad_id=squad.id, month=month))

    # 1. Fetch upcoming events from the club calendar (never let a scrape error
    #    crash the page).
    try:
        events = SquarespaceEventsSource().fetch()
    except Exception:
        import logging
        logging.getLogger(__name__).exception('SCWC import: fetch failed')
        events = None
    if not events:
        flash("Couldn't reach the SCWC calendar just now. Try again in a moment.", 'error')
        return back

    # 2. Keep only real competitions (meets/championships), dropping AGMs/socials.
    verdicts = classify_swim_events(
        events,
        api_key=current_app.config.get('ANTHROPIC_API_KEY'),
        model=current_app.config.get('ANTHROPIC_MODEL'),
    )
    competitions = [ev for ev, keep in zip(events, verdicts) if keep]
    if not competitions:
        flash('No new meets found to import.', 'success')
        return back

    # 3. Dedupe against what's already on this squad (idempotent re-runs).
    existing = {
        (e.event_date, (e.title or '').strip().lower())
        for e in db.session.query(SquadEvent).filter_by(squad_id=squad.id).all()
    }

    imported, skipped = 0, 0
    seen = set()
    for ev in competitions:
        key = (ev['start_date'], ev['title'].strip().lower())
        if key in existing or key in seen:
            skipped += 1
            continue
        seen.add(key)
        db.session.add(SquadEvent(
            squad_id=squad.id,
            title=ev['title'][:150],
            event_date=ev['start_date'],
            event_time='',
            slot='',
            event_type='meet',
            notes=_import_notes(ev)[:500],
            created_by=current_user.id,
        ))
        imported += 1

    db.session.commit()

    if imported:
        msg = f"Imported {imported} meet{'s' if imported != 1 else ''} from the SCWC calendar."
        if skipped:
            msg += f" {skipped} were already on your calendar."
        flash(msg, 'success')
    else:
        flash('Your calendar is already up to date with the SCWC meets.', 'success')
    return back


