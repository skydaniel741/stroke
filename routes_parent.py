import re
import secrets
from datetime import datetime, timedelta

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user

from auth_utils import parent_required

parent_bp = Blueprint('parent', __name__, url_prefix='/parent')


def _pool_key(p):
    return '50' if str(p or '25').startswith('50') else '25'


def _fmt_secs(secs):
    if secs >= 60:
        return f'{int(secs // 60)}:{secs % 60:05.2f}'
    return f'{secs:.2f}'


def _swimmer_snapshot(swimmer_id, limit_recent=8, limit_checkins=5):
    """Everything the parent view shows for one linked swimmer: best time per
    event with an improving/steady/slipping read (same trend logic as
    routes.personal_bests, kept separate since this is scoped to a
    swimmer_id argument rather than current_user), recent squad attendance
    and upcoming squad events, and the swimmer's own AI check-in insights.
    Deliberately excludes CoachNote -- that stays coach-private, never shown
    outside the coach dashboard -- and the full training log/splits, which
    the parent scope explicitly leaves out."""
    from app import db
    from models import Swim, SquadMembership, AttendanceRecord, SquadEvent, CheckIn

    swims = (
        db.session.query(Swim)
        .filter_by(user_id=swimmer_id)
        .order_by(Swim.logged_at.desc())
        .all()
    )

    best_by_event = {}
    swims_by_event = {}
    for s in swims:
        secs = s.time_in_seconds()
        if secs is None:
            continue
        current = best_by_event.get(s.event)
        if current is None or secs < current['secs']:
            best_by_event[s.event] = {'swim': s, 'secs': secs}
        swims_by_event.setdefault(s.event, []).append(secs)

    pb_rows = []
    for event, data in best_by_event.items():
        times = swims_by_event.get(event, [])
        trend = None
        if len(times) >= 4:
            half = len(times) // 2
            recent_avg = sum(times[:half]) / half
            earlier_avg = sum(times[-half:]) / half
            change_pct = (recent_avg - earlier_avg) / earlier_avg * 100
            trend = 'improving' if change_pct < -0.4 else 'slipping' if change_pct > 0.4 else 'steady'
        pb_rows.append({
            'event': event,
            'time': _fmt_secs(data['secs']),
            'pool': data['swim'].pool,
            'logged_at': data['swim'].logged_at,
            'trend': trend,
        })
    pb_rows.sort(key=lambda r: r['event'])

    recent_swims = swims[:limit_recent]

    squad_ids = [
        m.squad_id for m in
        db.session.query(SquadMembership).filter_by(user_id=swimmer_id, status='active').all()
    ]

    recent_attendance = []
    upcoming_events = []
    if squad_ids:
        recent_attendance = (
            db.session.query(AttendanceRecord)
            .filter(AttendanceRecord.swimmer_id == swimmer_id, AttendanceRecord.squad_id.in_(squad_ids))
            .order_by(AttendanceRecord.session_date.desc())
            .limit(6)
            .all()
        )
        today = datetime.utcnow().date()
        upcoming_events = (
            db.session.query(SquadEvent)
            .filter(SquadEvent.squad_id.in_(squad_ids), SquadEvent.event_date >= today)
            .order_by(SquadEvent.event_date.asc())
            .limit(5)
            .all()
        )

    checkins = (
        db.session.query(CheckIn)
        .filter_by(user_id=swimmer_id)
        .order_by(CheckIn.checkin_date.desc())
        .limit(limit_checkins)
        .all()
    )

    return {
        'pb_rows': pb_rows,
        'recent_swims': recent_swims,
        'recent_attendance': recent_attendance,
        'upcoming_events': upcoming_events,
        'checkins': checkins,
    }


@parent_bp.route('/invite', methods=['GET', 'POST'])
@login_required
def invite():
    """Swimmer-side: generate a link a parent can use to get a read-only
    view of this account, and see/revoke who already has one."""
    from app import db
    from models import ParentLink

    if request.method == 'POST':
        existing_pending = (
            db.session.query(ParentLink)
            .filter_by(swimmer_id=current_user.id, status='pending')
            .first()
        )
        if not existing_pending:
            token = secrets.token_urlsafe(24)
            link = ParentLink(swimmer_id=current_user.id, invite_token=token, status='pending')
            db.session.add(link)
            db.session.commit()

    links = (
        db.session.query(ParentLink)
        .filter_by(swimmer_id=current_user.id)
        .order_by(ParentLink.created_at.desc())
        .all()
    )
    return render_template('parent_invite.html', links=links)


@parent_bp.route('/invite/<int:link_id>/revoke', methods=['POST'])
@login_required
def revoke(link_id):
    from app import db
    from models import ParentLink

    link = db.session.query(ParentLink).filter_by(id=link_id, swimmer_id=current_user.id).first()
    if link:
        link.status = 'revoked'
        db.session.commit()
        flash('That parent link has been revoked.', 'success')
    return redirect(url_for('parent.invite'))


@parent_bp.route('/join/<token>', methods=['GET', 'POST'])
def join(token):
    """Where a parent lands from the swimmer's invite link. Creating a
    fresh parent account here goes through the same email-verification
    code flow as the main /signup -- without it, anyone could register a
    login-capable account under an email they don't own, permanently
    squatting that address (the uniqueness check would then block its
    real owner from ever signing up)."""
    from app import db
    from models import ParentLink, User
    from email_utils import send_verification_email

    link = db.session.query(ParentLink).filter_by(invite_token=token).first()
    if not link or link.status == 'revoked':
        flash("That invite link isn't valid. Ask for a new one.", 'error')
        return redirect(url_for('main.home'))

    if link.status == 'active':
        flash('That invite has already been used.', 'error')
        return redirect(url_for('main.login'))

    if current_user.is_authenticated:
        # Any signed-in account can claim a link. A parent who also swims,
        # or who coaches, keeps ONE account: their own training stays where
        # it is and the parent view is added alongside it. Forcing a second
        # account here was the old behaviour and it meant a masters swimmer
        # with a kid in the club had to log out to check on their own child.
        if link.swimmer_id == current_user.id:
            flash("That's your own invite link. Send it to a parent or guardian instead.", 'error')
            return redirect(url_for('parent.invite'))

        already = (
            db.session.query(ParentLink)
            .filter_by(swimmer_id=link.swimmer_id, parent_id=current_user.id, status='active')
            .first()
        )
        if already:
            flash("You're already linked to that swimmer.", 'info')
            return redirect(url_for('parent.parent_dashboard'))

        # Confirm before claiming. Opening a link used to attach the account
        # on the GET, which is a state change on a page load: anyone who got
        # a signed-in user to follow their invite URL could attach themselves
        # to that user's view. Now the link has to be accepted deliberately.
        if request.method != 'POST':
            swimmer = db.session.get(User, link.swimmer_id)
            return render_template('parent_join.html', link=link, swimmer=swimmer,
                                   confirm_existing=True)

        link.parent_id = current_user.id
        link.status = 'active'
        link.claimed_at = datetime.utcnow()
        db.session.commit()
        flash("You're now linked to that swimmer. Your own account is unchanged.", 'success')
        return redirect(url_for('parent.parent_dashboard'))

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip().lower()
        password = request.form.get('password') or ''

        if not (3 <= len(username) <= 30):
            flash('Name must be between 3 and 30 characters.', 'error')
            return render_template('parent_join.html', link=link)
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', email) or len(email) > 150:
            flash('Please enter a valid email address.', 'error')
            return render_template('parent_join.html', link=link)
        if not (8 <= len(password) <= 200):
            flash('Password must be between 8 and 200 characters.', 'error')
            return render_template('parent_join.html', link=link)

        existing = db.session.query(User).filter_by(email=email).first()
        if existing:
            flash('An account with that email already exists. Log in, then open this link again.', 'error')
            return redirect(url_for('main.login'))
        if db.session.query(User).filter_by(username=username).first():
            flash('That name is taken, try another.', 'error')
            return render_template('parent_join.html', link=link)

        user = User(email=email, username=username, role='parent')
        user.set_password(password)
        code = user.generate_verify_code()
        db.session.add(user)
        db.session.flush()

        link.parent_id = user.id
        link.status = 'active'
        link.claimed_at = datetime.utcnow()
        db.session.commit()

        if not send_verification_email(email, username, code):
            flash(
                "Your account was created, but we couldn't send the verification email "
                "right now. Try 'Resend code' on the next screen in a moment, or contact us.",
                'error',
            )
        return redirect(url_for('main.verify', email=email))

    return render_template('parent_join.html', link=link)


@parent_bp.route('/enable-training', methods=['POST'])
@login_required
@parent_required
def enable_training():
    """Turn a parent-only account into one that also swims.

    The other direction (a swimmer being sent a parent link) needs no route:
    claiming the link is enough, because parent access is derived from the
    link rather than stored on the account. This is the same idea going the
    other way, and it only touches role -- every existing parent link stays
    exactly as it was.
    """
    from app import db

    if current_user.role == 'parent':
        current_user.role = 'swimmer'
        db.session.commit()
        flash("Your account can now log swims too. Your parent view is still here.", 'success')
    return redirect(url_for('main.dashboard'))


def _latest_digest(parent_link_id):
    """Most recent approved ParentDigest for this link, or None. Only
    'approved' rows are ever considered here -- a draft awaiting coach
    review must never be visible on this page (see ParentDigest/
    routes_internal.digest_generate/routes_coach's review queue)."""
    import json
    from app import db
    from models import ParentDigest

    digest = (
        db.session.query(ParentDigest)
        .filter_by(parent_link_id=parent_link_id, status='approved')
        .order_by(ParentDigest.week_start.desc())
        .first()
    )
    if not digest:
        return None
    try:
        parsed = json.loads(digest.content or '{}')
    except ValueError:
        parsed = {}
    return {
        'weekStart': digest.week_start,
        'headline': parsed.get('headline'),
        'body': parsed.get('body'),
        'nextUp': parsed.get('next_up'),
    }


@parent_bp.route('/dashboard')
@login_required
@parent_required
def parent_dashboard():
    from app import db
    from models import ParentLink

    links = (
        db.session.query(ParentLink)
        .filter_by(parent_id=current_user.id, status='active')
        .all()
    )
    swimmer_id = request.args.get('swimmer', type=int)
    active_link = None
    if links:
        active_link = next((l for l in links if l.swimmer_id == swimmer_id), links[0])

    snapshot = _swimmer_snapshot(active_link.swimmer_id) if active_link else None
    digest = _latest_digest(active_link.id) if active_link else None
    return render_template(
        'parent_dashboard.html',
        links=links,
        active_link=active_link,
        snapshot=snapshot,
        digest=digest,
    )
