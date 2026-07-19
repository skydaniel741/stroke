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

        best_by_event = {}
        for s in swims:
            secs = s.time_in_seconds()
            if secs is None:
                continue
            cur = best_by_event.get(s.event)
            if cur is None or secs < cur['secs']:
                best_by_event[s.event] = {
                    'event': s.event, 'time': s.time, 'pool': s.pool, 'secs': secs,
                    'date': s.logged_at.strftime('%Y-%m-%d'),
                }

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
            'personalBests': sorted(best_by_event.values(), key=lambda x: x['event']),
            'recentActivity': recent_activity,
            'sessionsCount': len(swims) + len(sessions),
            'totalDistance': total_distance,
            'lastActive': last_active,
            'attendanceRate': attendance_rate(m),
            'weeklyVolume': weekly_volume,
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
        return {
            'id': sq.id,
            'name': sq.name,
            'color': sq.color or 'blue',
            'inviteCode': sq.invite_code,
            'memberCount': sum(1 for m in memberships if m.squad_id == sq.id),
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

        best_by_event = {}
        for s in swims:
            secs = s.time_in_seconds()
            if secs is None:
                continue
            cur = best_by_event.get(s.event)
            if cur is None or secs < cur[0]:
                best_by_event[s.event] = (secs, s.time)

        attended = sum(1 for r in attendance if r.swimmer_id == uid and r.status in ('present', 'late'))
        activity_dates = [s.logged_at for s in swims] + [se.logged_at for se in sessions]
        flag = flags.get(uid)

        swimmers_digest.append({
            'name': u.username,
            'sessions_60d': len(swims) + len(sessions),
            'distance_60d': sum(s.distance() for s in swims) + sum(se.total_distance() for se in sessions),
            'last_active': max(activity_dates).strftime('%Y-%m-%d') if activity_dates else None,
            'attendance': f'{attended}/{marked_days} marked practices (30d)' if marked_days else 'no roll calls yet',
            'best_times': [f'{ev}: {t}' for ev, (_, t) in sorted(best_by_event.items())][:6],
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


@coach.route('/squad/create', methods=['POST'])
@login_required
@coach_required
def squad_create():
    from app import db
    from models import Squad, Club

    name = request.form.get('name', '').strip()
    if not name:
        flash('Squad needs a name.', 'error')
        return redirect(url_for('coach.coach_dashboard'))

    club_id = request.form.get('club_id') or None
    if club_id:
        club = db.session.query(Club).filter_by(id=club_id, owner_id=current_user.id, status='active').first()
        club_id = club.id if club else None

    squad = Squad(
        name=name,
        coach_id=current_user.id,
        club_id=club_id,
        invite_code=secrets.token_urlsafe(6),
    )
    db.session.add(squad)
    db.session.commit()
    flash(f'Squad "{name}" created. Invite code: {squad.invite_code}', 'success')
    return redirect(url_for('coach.squad_roster', squad_id=squad.id))


@coach.route('/club/create', methods=['POST'])
@login_required
@coach_required
def club_create():
    from app import db
    from models import Club

    name = request.form.get('name', '').strip()
    if not name:
        flash('Club needs a name.', 'error')
        return redirect(url_for('coach.coach_dashboard'))

    # A coach's very first club is instantly usable. Any club after that needs
    # a site admin to approve it before it can hold squads.
    already_has_club = db.session.query(Club).filter_by(owner_id=current_user.id).count() > 0
    status = 'pending' if already_has_club else 'active'

    club = Club(
        name=name,
        owner_id=current_user.id,
        age_range=request.form.get('age_range', '').strip(),
        contact_email=request.form.get('contact_email', '').strip(),
        newsletter_url=request.form.get('newsletter_url', '').strip(),
        status=status,
        approved_at=None if status == 'pending' else datetime.utcnow(),
    )
    db.session.add(club)
    db.session.commit()

    if status == 'pending':
        flash(f'Club "{name}" submitted — an admin needs to approve it before you can add squads to it.', 'success')
        return redirect(url_for('coach.coach_dashboard'))

    flash(f'Club "{name}" created.', 'success')
    return redirect(url_for('coach.club_overview', club_id=club.id))


@coach.route('/squad/<int:squad_id>')
@login_required
@coach_required
def squad_roster(squad_id):
    from app import db
    from models import SquadMembership, CoachNote, StatusFlag, Swim, Standard

    squad = _squad_or_404(squad_id)
    memberships = (
        db.session.query(SquadMembership)
        .filter_by(squad_id=squad.id)
        .order_by(SquadMembership.created_at.desc())
        .all()
    )

    statuses = {
        s.swimmer_id: s for s in
        db.session.query(StatusFlag).filter_by(squad_id=squad.id).all()
    }
    note_counts = {}
    for n in db.session.query(CoachNote).filter_by(squad_id=squad.id).all():
        note_counts[n.swimmer_id] = note_counts.get(n.swimmer_id, 0) + 1

    standards = db.session.query(Standard).all()

    def _pool_key(p):
        return '50' if str(p or '25').startswith('50') else '25'

    rows = []
    for m in memberships:
        best_by_event = {}
        met_standards = []
        if m.user_id:
            swims = db.session.query(Swim).filter_by(user_id=m.user_id).all()
            for sw in swims:
                secs = sw.time_in_seconds()
                if secs is None:
                    continue
                cur = best_by_event.get(sw.event)
                if cur is None or secs < cur:
                    best_by_event[sw.event] = secs
            for st in standards:
                cutoff = st.cutoff_seconds()
                best = best_by_event.get(st.event)
                if cutoff is not None and best is not None and _pool_key(st.pool) == '25' and best <= cutoff:
                    met_standards.append(st.name)

        rows.append({
            'membership': m,
            'status': statuses.get(m.user_id),
            'note_count': note_counts.get(m.user_id, 0),
            'met_standards': met_standards,
        })

    return render_template('squad_roster.html', squad=squad, rows=rows)


@coach.route('/squad/<int:squad_id>/invite', methods=['POST'])
@login_required
@coach_required
def squad_invite(squad_id):
    from app import db
    from models import SquadMembership, User

    squad = _squad_or_404(squad_id)
    email = (request.form.get('email') or '').strip().lower()
    lane_group = request.form.get('lane_group', '').strip()
    requires_consent = bool(request.form.get('requires_consent'))

    if not email:
        flash('Enter an email to invite.', 'error')
        return redirect(url_for('coach.squad_roster', squad_id=squad.id))

    existing_user = db.session.query(User).filter_by(email=email).first()
    membership = SquadMembership(
        squad_id=squad.id,
        user_id=existing_user.id if existing_user else None,
        invited_email=email,
        status='invited',
        lane_group=lane_group,
        requires_consent=requires_consent,
    )
    db.session.add(membership)
    db.session.commit()
    flash(f'Invited {email}.', 'success')
    return redirect(url_for('coach.squad_roster', squad_id=squad.id))


@coach.route('/squad/<int:squad_id>/import', methods=['POST'])
@login_required
@coach_required
def squad_import(squad_id):
    from app import db
    from models import SquadMembership, User

    squad = _squad_or_404(squad_id)
    file = request.files.get('csv_file')
    if not file or not file.filename:
        flash('Choose a CSV file first.', 'error')
        return redirect(url_for('coach.squad_roster', squad_id=squad.id))

    try:
        text = file.stream.read().decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text))
        count = 0
        for row in reader:
            email = (row.get('email') or '').strip().lower()
            if not email:
                continue
            existing_user = db.session.query(User).filter_by(email=email).first()
            db.session.add(SquadMembership(
                squad_id=squad.id,
                user_id=existing_user.id if existing_user else None,
                invited_email=email,
                status='invited',
                lane_group=(row.get('lane_group') or '').strip(),
            ))
            count += 1
        db.session.commit()
        flash(f'Imported {count} swimmer(s).', 'success')
    except Exception:
        flash('Could not read that CSV — expected columns: name, email, lane_group.', 'error')

    return redirect(url_for('coach.squad_roster', squad_id=squad.id))


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
    return redirect(url_for('coach.squad_roster', squad_id=squad.id))


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
    note = request.form.get('note', '').strip()
    if note:
        db.session.add(CoachNote(squad_id=squad.id, swimmer_id=swimmer_id, coach_id=current_user.id, note=note))
        db.session.commit()
        flash('Note added.', 'success')
    return redirect(url_for('coach.squad_roster', squad_id=squad.id))


@coach.route('/squad/<int:squad_id>/swimmer/<int:swimmer_id>')
@login_required
@coach_required
def squad_swimmer_profile(squad_id, swimmer_id):
    from app import db
    from models import SquadMembership, Swim, Session, User, CoachNote, StatusFlag, Standard

    squad = _squad_or_404(squad_id)
    membership = (
        db.session.query(SquadMembership)
        .filter_by(squad_id=squad.id, user_id=swimmer_id)
        .first()
    )
    swimmer = db.session.query(User).get(swimmer_id)
    if not membership or not swimmer:
        abort(404)

    swims = db.session.query(Swim).filter_by(user_id=swimmer_id).order_by(Swim.logged_at.desc()).all()
    sessions = db.session.query(Session).filter_by(user_id=swimmer_id).order_by(Session.logged_at.desc()).all()

    best_by_event = {}
    for s in swims:
        secs = s.time_in_seconds()
        if secs is None:
            continue
        current = best_by_event.get(s.event)
        if current is None or secs < current['secs']:
            best_by_event[s.event] = {'event': s.event, 'time': s.time, 'pool': s.pool, 'secs': secs}
    personal_bests = sorted(best_by_event.values(), key=lambda x: x['event'])

    recent_activity = sorted(
        [
            {'kind': 'PB', 'label': s.event, 'pool': s.pool or '—', 'logged_at': s.logged_at}
            for s in swims
        ] + [
            {
                'kind': s.session_type or 'Session',
                'label': f"{len(s.get_sets())} set" + ('s' if len(s.get_sets()) != 1 else '') if s.get_sets() else (s.session_type or 'Session'),
                'pool': s.pool or '—',
                'logged_at': s.logged_at,
            }
            for s in sessions
        ],
        key=lambda x: x['logged_at'],
        reverse=True,
    )[:10]

    standards = db.session.query(Standard).all()

    def _pool_key(p):
        return '50' if str(p or '25').startswith('50') else '25'

    met_standards = []
    for st in standards:
        cutoff = st.cutoff_seconds()
        best = best_by_event.get(st.event, {}).get('secs')
        if cutoff is not None and best is not None and _pool_key(st.pool) == '25' and best <= cutoff:
            met_standards.append(st.name)

    status = db.session.query(StatusFlag).filter_by(squad_id=squad.id, swimmer_id=swimmer_id).first()
    note_count = db.session.query(CoachNote).filter_by(squad_id=squad.id, swimmer_id=swimmer_id).count()
    total_distance = sum(s.total_distance() for s in sessions) + sum(s.distance() for s in swims)

    return render_template(
        'coach_swimmer_profile.html',
        squad=squad,
        swimmer=swimmer,
        membership=membership,
        personal_bests=personal_bests,
        recent_activity=recent_activity,
        met_standards=met_standards,
        status=status,
        note_count=note_count,
        total_distance=total_distance,
        sessions_count=len(sessions) + len(swims),
    )


@coach.route('/squad/<int:squad_id>/swimmer/<int:swimmer_id>/notes')
@login_required
@coach_required
def squad_swimmer_notes(squad_id, swimmer_id):
    from app import db
    from models import CoachNote, User

    squad = _squad_or_404(squad_id)
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
    return redirect(url_for('coach.squad_roster', squad_id=squad.id))


@coach.route('/squad/<int:squad_id>/announcements', methods=['GET', 'POST'])
@login_required
@coach_required
def squad_announcements(squad_id):
    from app import db
    from models import Announcement

    squad = _squad_or_404(squad_id)

    if request.method == 'POST':
        message = request.form.get('message', '').strip()
        if message:
            db.session.add(Announcement(squad_id=squad.id, author_id=current_user.id, message=message))
            db.session.commit()
            flash('Announcement posted.', 'success')
        return redirect(url_for('coach.squad_announcements', squad_id=squad.id))

    announcements = (
        db.session.query(Announcement)
        .filter_by(squad_id=squad.id)
        .order_by(Announcement.created_at.desc())
        .all()
    )
    return render_template('coach_announcements.html', squad=squad, announcements=announcements)


@coach.route('/squad/<int:squad_id>/report')
@login_required
@coach_required
def squad_report(squad_id):
    from app import db
    from models import SquadMembership, Swim, Session, User

    squad = _squad_or_404(squad_id)
    memberships = (
        db.session.query(SquadMembership)
        .filter_by(squad_id=squad.id, status='active')
        .all()
    )

    since = datetime.utcnow() - timedelta(days=90)
    rows = []
    for m in memberships:
        if not m.user_id:
            continue
        user = db.session.query(User).get(m.user_id)
        swims = (
            db.session.query(Swim)
            .filter(Swim.user_id == m.user_id, Swim.logged_at >= since)
            .all()
        )
        sessions_count = (
            db.session.query(Session)
            .filter(Session.user_id == m.user_id, Session.logged_at >= since)
            .count()
        )
        best_by_event = {}
        for sw in swims:
            secs = sw.time_in_seconds()
            if secs is None:
                continue
            cur = best_by_event.get(sw.event)
            if cur is None or secs < cur['secs']:
                best_by_event[sw.event] = {'event': sw.event, 'time': sw.time}

        rows.append({
            'user': user,
            'pbs': sorted(best_by_event.values(), key=lambda x: x['event']),
            'attendance': sessions_count + len(swims),
        })

    return render_template('squad_report.html', squad=squad, rows=rows, since=since)


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


@coach.route('/club/<int:club_id>')
@login_required
@coach_required
def club_overview(club_id):
    from app import db
    from models import Club, Squad

    club = db.session.query(Club).get(club_id)
    if not club or (club.owner_id != current_user.id and not current_user.is_admin):
        abort(404)

    squads = db.session.query(Squad).filter_by(club_id=club.id).all()
    rows = [{
        'squad': s,
        'active_count': s.active_member_count(),
        'estimate': s.billing_estimate(),
    } for s in squads]

    return render_template('club_overview.html', club=club, rows=rows)
