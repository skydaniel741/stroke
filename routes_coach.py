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
    from app import db
    from models import Squad, Club

    squads = db.session.query(Squad).filter_by(coach_id=current_user.id).order_by(Squad.created_at.desc()).all()
    clubs = db.session.query(Club).filter_by(owner_id=current_user.id).order_by(Club.created_at.desc()).all()
    return render_template('coach_dashboard.html', squads=squads, clubs=clubs)


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


@coach.route('/squad/<int:squad_id>/billing', methods=['GET', 'POST'])
@login_required
@coach_required
def squad_billing(squad_id):
    from app import db

    squad = _squad_or_404(squad_id)

    if request.method == 'POST':
        try:
            squad.base_fee = float(request.form.get('base_fee', 0) or 0)
            squad.per_swimmer_fee = float(request.form.get('per_swimmer_fee', 0) or 0)
            db.session.commit()
            flash('Billing estimate updated.', 'success')
        except ValueError:
            flash('Fees must be numbers.', 'error')
        return redirect(url_for('coach.squad_billing', squad_id=squad.id))

    return render_template('squad_billing.html', squad=squad)


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
