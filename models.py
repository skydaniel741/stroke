import json
import re

from flask_login import UserMixin
from datetime import datetime
import random
from app import db, bcrypt

class User(db.Model, UserMixin):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    plan = db.Column(db.String(20), default='free')
    is_verified = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    verify_code = db.Column(db.String(6), nullable=True)
    verify_code_sent_at = db.Column(db.DateTime, nullable=True)
    verify_attempts = db.Column(db.Integer, default=0)
    failed_login_attempts = db.Column(db.Integer, default=0)
    login_locked_until = db.Column(db.DateTime, nullable=True)
    role = db.Column(db.String(20), default='swimmer')  # 'swimmer', 'coach', or 'parent'
    # Marked by a coach from the squad roster -- purely a display flag today
    # (shows a "Minor" badge, surfaces the "Invite parent" action). Doesn't
    # itself restrict anything; the existing requires_consent/ConsentRecord
    # flow on SquadMembership is the actual guardian-consent gate.
    is_minor = db.Column(db.Boolean, default=False)
    share_leaderboard = db.Column(db.Boolean, default=False)
    # Solo is a paid $12/mo tier (see index.html pricing) -- there's no card
    # checkout wired up yet, so payment is verified manually and an admin
    # flips this from the admin Solo panel once it's actually been paid.
    # plan alone ('solo'/'solo_pro') is NOT enough to unlock solo routes.
    solo_paid = db.Column(db.Boolean, default=False)
    solo_paid_at = db.Column(db.DateTime, nullable=True)

    def set_password(self, password):
        self.password = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password, password)

    def generate_verify_code(self):
        self.verify_code = str(random.randint(100000, 999999))
        self.verify_code_sent_at = datetime.utcnow()
        self.verify_attempts = 0
        return self.verify_code

    @property
    def is_solo(self):
        # Plan tier only -- does NOT mean access is unlocked, see has_solo_access.
        return self.plan in ('solo', 'solo_pro')

    @property
    def is_solo_pro(self):
        return self.plan == 'solo_pro'

    @property
    def has_solo_access(self):
        # The actual gate used by solo_required/dashboard nav: on the solo
        # tier AND marked paid, or an admin (who always has full access).
        return self.is_admin or (self.is_solo and self.solo_paid)

    swims = db.relationship('Swim', backref='user', lazy=True)
    sessions = db.relationship('Session', backref='user', lazy=True)


class Swim(db.Model):
    __tablename__ = 'swim'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event = db.Column(db.String(50), nullable=False)
    pool = db.Column(db.String(10))
    stroke = db.Column(db.String(10))
    time = db.Column(db.String(20))
    notes = db.Column(db.Text)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow)
    tag = db.Column(db.String(10), default='practice')  # 'practice' or 'meet'
    splits = db.Column(db.Text)  # JSON list of 50m split strings, optional

    def get_splits(self):
        try:
            return json.loads(self.splits or '[]')
        except (ValueError, TypeError):
            return []

    def time_in_seconds(self):
        t = self.time
        if not t:
            return None
        try:
            if ':' in t:
                mins, rest = t.split(':')
                return int(mins) * 60 + float(rest)
            return float(t)
        except:
            return None

    def distance(self):
        if not self.event:
            return 0
        match = re.match(r'\s*(\d+)', self.event)
        return int(match.group(1)) if match else 0


class Session(db.Model):
    __tablename__ = 'session'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    session_type = db.Column(db.String(50))
    pool = db.Column(db.String(10))
    sets_data = db.Column(db.Text)
    notes = db.Column(db.Text)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow)
    source = db.Column(db.String(20), default='self')  # 'self' or 'squad' (auto-logged by coach roll call)
    squad_event_id = db.Column(db.Integer, db.ForeignKey('squad_event.id'), nullable=True)
    # Set when this logged session fulfilled a TrainingPlan session (see plan_logic.link_completed).
    planned_session_id = db.Column(db.Integer, db.ForeignKey('planned_session.id'), nullable=True)

    def get_sets(self):
        try:
            return json.loads(self.sets_data or '[]')
        except:
            return []

    def total_distance(self):
        total = 0
        for s in self.get_sets():
            try:
                total += int(s.get('reps', 0)) * int(s.get('dist', 0))
            except:
                pass
        return total


class Goal(db.Model):
    __tablename__ = 'goal'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    event = db.Column(db.String(50), nullable=False)
    pool = db.Column(db.String(10))
    target_time = db.Column(db.String(20), nullable=False)
    target_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def target_seconds(self):
        t = self.target_time
        if not t:
            return None
        try:
            if ':' in t:
                mins, rest = t.split(':')
                return int(mins) * 60 + float(rest)
            return float(t)
        except (ValueError, TypeError):
            return None


class AthleteProfile(db.Model):
    """The Solo-tier onboarding questionnaire answers plus the AI-generated
    training program built from them. One row per user -- redoing the
    questionnaire overwrites it (see routes_solo.solo_onboarding)."""
    __tablename__ = 'athlete_profile'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    level = db.Column(db.String(30))  # Beginner/Intermediate/Advanced/Competitive
    age = db.Column(db.Integer)
    training_days_per_week = db.Column(db.Integer)
    fitness_ability = db.Column(db.String(30))  # self-rated: Low/Moderate/Good/High
    primary_stroke = db.Column(db.String(20))
    main_goal = db.Column(db.Text)
    # Deeper onboarding: how the AI personalizes training/nutrition/dryland together.
    swimmer_type = db.Column(db.String(30))       # Sprinter/Distance/IM & all-rounder/Technique-focused/Fitness & health
    coaching_situation = db.Column(db.String(40))  # none/club_want_extra/club_want_structure/self_coached
    coaching_focus = db.Column(db.Text)             # optional: what they work on with their coach
    eating_habits = db.Column(db.String(30))        # undereating/balanced/skip_meals/structured
    limitations = db.Column(db.Text)                 # optional: injuries/physical limitations
    program_json = db.Column(db.Text)  # AI-generated program, see ai_utils.generate_training_program
    nutrition_json = db.Column(db.Text)  # AI-selected nutrition guidance, see ai_utils.generate_training_program
    dryland_json = db.Column(db.Text)    # AI-selected dryland guidance, see ai_utils.generate_training_program
    # Solo Pro AI tuning knobs (free solo tier stays on the defaults).
    coaching_tone = db.Column(db.String(20), default='balanced')   # encouraging/balanced/direct
    intensity = db.Column(db.String(20), default='normal')          # easier/normal/harder
    # Rolling weekly cap on AI program rebuilds (see routes_solo.onboarding).
    regen_week_start = db.Column(db.Date, nullable=True)  # Monday of the counted week
    regen_count = db.Column(db.Integer, default=0)
    # Cached single-swimmer progression insight (see ai_utils.generate_progress_insight).
    progress_insight = db.Column(db.Text)
    progress_insight_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def regens_left(self, limit=3):
        from datetime import date, timedelta
        monday = date.today() - timedelta(days=date.today().weekday())
        used = self.regen_count or 0 if self.regen_week_start == monday else 0
        return max(0, limit - used)

    def get_program(self):
        try:
            return json.loads(self.program_json or '{}')
        except (ValueError, TypeError):
            return {}

    def get_nutrition(self):
        try:
            return json.loads(self.nutrition_json or '{}')
        except (ValueError, TypeError):
            return {}

    def get_dryland(self):
        try:
            return json.loads(self.dryland_json or '{}')
        except (ValueError, TypeError):
            return {}

    def get_progress_insight(self):
        try:
            return json.loads(self.progress_insight or '{}')
        except (ValueError, TypeError):
            return {}


class InjuryStatus(db.Model):
    """Current joint/pain status snapshot for one swimmer -- edited in place,
    NOT a log. STROKE has no other record of this (AthleteProfile.limitations
    is a one-off onboarding note, not a living status), so the AI dryland
    coach reads and updates this before every session prescription. See
    swim-coach/reference/injury-modifications.md -- re-ask if it's more than
    ~14 days old."""
    __tablename__ = 'injury_status'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    shoulder = db.Column(db.Text)   # side, sharp/dull, when it shows up -- or "none"
    knee = db.Column(db.Text)
    back = db.Column(db.Text)
    other = db.Column(db.Text)
    red_flag = db.Column(db.Boolean, default=False)  # sharp/numbness/locking/night pain -- stop dryland, see a clinician
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def is_stale(self, days=14):
        if not self.updated_at:
            return True
        return (datetime.utcnow() - self.updated_at).days >= days

    def has_anything_flagged(self):
        return any(
            v and v.strip().lower() not in ('', 'none', 'no', 'nothing')
            for v in (self.shoulder, self.knee, self.back, self.other)
        )


class DrylandLogEntry(db.Model):
    """Append-only log of completed dryland sessions -- STROKE's DB has no
    other record of land training. Feeds the dryland acute:chronic load
    signal in swim-coach/reference/load-management.md (session_load = RPE x
    duration), reconciled against the pool-only ACWR already computed by
    athlete_model.recompute_state()."""
    __tablename__ = 'dryland_log_entry'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    logged_at = db.Column(db.DateTime, default=datetime.utcnow)
    focus = db.Column(db.String(120))       # e.g. "Shoulder + core, light plyo"
    rpe = db.Column(db.Integer)              # 1-10
    duration_minutes = db.Column(db.Integer)
    pain_notes = db.Column(db.Text)

    def session_load(self):
        return (self.rpe or 0) * (self.duration_minutes or 0)


class CoachMessage(db.Model):
    """One turn of the swim-coach AI chat (nutrition or dryland). Kept
    per-user, per-topic so the coach has real conversational memory instead
    of answering each question cold."""
    __tablename__ = 'coach_message'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    topic = db.Column(db.String(20), nullable=False)  # 'nutrition' or 'dryland'
    role = db.Column(db.String(10), nullable=False)   # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AthleteState(db.Model):
    """The persisted 'digital athlete model': one evolving row per swimmer,
    recomputed from their full log every time they add a workout or check-in
    (see athlete_model.update_athlete_state). This is what lets the AI coach
    compare current week vs previous weeks instead of treating every workout
    independently."""
    __tablename__ = 'athlete_state'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False, unique=True)
    state_json = db.Column(db.Text)  # see athlete_model.recompute_state for the shape
    # Counts completed training weeks so the progression engine can schedule a
    # recovery week every 4th week (swim_logic.next_week_target).
    week_index = db.Column(db.Integer, default=0)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_state(self):
        try:
            return json.loads(self.state_json or '{}')
        except (ValueError, TypeError):
            return {}


class WeeklyReport(db.Model):
    """The AI coach's automatic 7-day review of one swimmer: progress score,
    PB improvements, strengths/weaknesses, consistency, recovery status and a
    suggested focus for next week. Generated lazily when a week has passed
    since the last one (athlete_model.ensure_weekly_report)."""
    __tablename__ = 'weekly_report'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    week_start = db.Column(db.Date, nullable=False)  # Monday of the reviewed week
    report_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_report(self):
        try:
            return json.loads(self.report_json or '{}')
        except (ValueError, TypeError):
            return {}


class CheckIn(db.Model):
    """A swimmer's periodic (typically daily) reflection: how training felt
    and what could improve, plus an AI-generated insight in response."""
    __tablename__ = 'check_in'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    checkin_date = db.Column(db.Date, nullable=False)
    feeling_rating = db.Column(db.Integer)  # 1-5
    fatigue_rating = db.Column(db.Integer)  # 1-5, soreness/fatigue
    sleep_quality = db.Column(db.Integer)   # 1-5, self-rated proxy for hours
    notes = db.Column(db.Text)
    ai_insight = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Standard(db.Model):
    """A public qualifying-standard reference time, e.g. a NAG cut or a
    club/regional qualifying time. Admin-managed. Used both for free-tier
    'compare against a standard' and coach-tier squad-promotion flags."""
    __tablename__ = 'standard'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)   # e.g. "NAG 12 & Under"
    event = db.Column(db.String(50), nullable=False)
    pool = db.Column(db.String(10), default='25m')
    gender = db.Column(db.String(10), default='open')  # 'men', 'women', 'open'
    age_group = db.Column(db.String(30))
    cutoff_time = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def cutoff_seconds(self):
        t = self.cutoff_time
        if not t:
            return None
        try:
            if ':' in t:
                mins, rest = t.split(':')
                return int(mins) * 60 + float(rest)
            return float(t)
        except (ValueError, TypeError):
            return None


class ParentLink(db.Model):
    """Links a parent/guardian account to a swimmer's, read-only. The
    swimmer generates the invite (see routes_parent.invite); the parent
    claims it at /parent/join/<token> to create or attach their own
    role='parent' account. One swimmer can have several parents linked,
    and one parent can be linked to several swimmers (e.g. siblings)."""
    __tablename__ = 'parent_link'

    id = db.Column(db.Integer, primary_key=True)
    swimmer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    invite_token = db.Column(db.String(64), unique=True, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending/active/revoked
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    claimed_at = db.Column(db.DateTime, nullable=True)

    swimmer = db.relationship('User', foreign_keys=[swimmer_id])
    parent = db.relationship('User', foreign_keys=[parent_id])


class AdminAuditLog(db.Model):
    __tablename__ = 'admin_audit_log'

    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(50), nullable=False)
    target_type = db.Column(db.String(30))
    target_id = db.Column(db.Integer)
    detail = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Announcement(db.Model):
    """squad_id NULL = platform-wide banner (posted by an admin).
    squad_id set = a coach's one-way announcement board for that squad."""
    __tablename__ = 'announcement'

    id = db.Column(db.Integer, primary_key=True)
    squad_id = db.Column(db.Integer, db.ForeignKey('squad.id'), nullable=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class TrainingProgram(db.Model):
    """Solo-tier content library: dryland/strength/mobility/core programs
    and nutrition/fueling suggestions. Same flexible shape serves both."""
    __tablename__ = 'training_program'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(30), default='Strength')  # Strength/Mobility/Core/Nutrition
    description = db.Column(db.Text)
    content_blocks = db.Column(db.Text)  # JSON: [{heading, body, reps?, sets?, rest?}]
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_blocks(self):
        try:
            return json.loads(self.content_blocks or '[]')
        except (ValueError, TypeError):
            return []


class Club(db.Model):
    """Groups multiple squads under one club-level owner (multi-squad admin view).
    A coach's first club is auto-active; any club after that needs admin approval
    (status='pending') before the coach can use it -- see routes_coach.club_create."""
    __tablename__ = 'club'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    age_range = db.Column(db.String(50))
    contact_email = db.Column(db.String(150))
    newsletter_url = db.Column(db.String(255))
    status = db.Column(db.String(20), default='active')  # 'active' or 'pending'
    approved_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    squads = db.relationship('Squad', backref='club', lazy=True)


class Squad(db.Model):
    __tablename__ = 'squad'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    coach_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    club_id = db.Column(db.Integer, db.ForeignKey('club.id'), nullable=True)
    invite_code = db.Column(db.String(20), unique=True, nullable=False)
    base_fee = db.Column(db.Numeric(10, 2), default=0)
    per_swimmer_fee = db.Column(db.Numeric(10, 2), default=0)
    color = db.Column(db.String(20), default='blue')  # badge/theme color for the coach dashboard
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    memberships = db.relationship('SquadMembership', backref='squad', lazy=True)

    def active_member_count(self):
        return sum(1 for m in self.memberships if m.status == 'active')

    def billing_estimate(self):
        base = float(self.base_fee or 0)
        per = float(self.per_swimmer_fee or 0)
        return base + per * self.active_member_count()


class SquadMembership(db.Model):
    __tablename__ = 'squad_membership'

    id = db.Column(db.Integer, primary_key=True)
    squad_id = db.Column(db.Integer, db.ForeignKey('squad.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    invited_email = db.Column(db.String(150))
    status = db.Column(db.String(20), default='invited')  # invited/pending_consent/active/declined
    lane_group = db.Column(db.String(30))
    requires_consent = db.Column(db.Boolean, default=False)
    joined_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    swimmer = db.relationship('User', foreign_keys=[user_id])


class ConsentRecord(db.Model):
    """Parental consent for a minor swimmer joining a squad. Placeholder
    copy only -- needs legal review before this is relied on in production."""
    __tablename__ = 'consent_record'

    id = db.Column(db.Integer, primary_key=True)
    membership_id = db.Column(db.Integer, db.ForeignKey('squad_membership.id'), nullable=False)
    guardian_name = db.Column(db.String(120))
    guardian_email = db.Column(db.String(150))
    consent_given = db.Column(db.Boolean, default=False)
    consent_requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    consent_given_at = db.Column(db.DateTime, nullable=True)


class CoachNote(db.Model):
    """Coach-private note about a swimmer. Never shown to the swimmer."""
    __tablename__ = 'coach_note'

    id = db.Column(db.Integer, primary_key=True)
    squad_id = db.Column(db.Integer, db.ForeignKey('squad.id'), nullable=False)
    swimmer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    coach_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    note = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class StatusFlag(db.Model):
    """Injury / availability status for a swimmer within a squad."""
    __tablename__ = 'status_flag'

    id = db.Column(db.Integer, primary_key=True)
    squad_id = db.Column(db.Integer, db.ForeignKey('squad.id'), nullable=False)
    swimmer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='available')  # available/injured/limited
    note = db.Column(db.Text)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_by = db.Column(db.Integer, db.ForeignKey('user.id'))


class SquadEvent(db.Model):
    """A scheduled practice/meet/event on a squad's coach-facing calendar.
    A practice can carry an AM/PM slot and an attached SavedSet -- when the
    coach marks attendance for that day, present swimmers get the attached
    set auto-logged as a Session (see routes_coach.coach_pro_attendance_save)."""
    __tablename__ = 'squad_event'

    id = db.Column(db.Integer, primary_key=True)
    squad_id = db.Column(db.Integer, db.ForeignKey('squad.id'), nullable=False)
    title = db.Column(db.String(150), nullable=False)
    event_date = db.Column(db.Date, nullable=False)
    event_time = db.Column(db.String(20))  # free text, e.g. '6:00 AM'
    slot = db.Column(db.String(10), default='')  # 'AM' / 'PM' / ''
    event_type = db.Column(db.String(20), default='practice')  # practice/meet/other
    saved_set_id = db.Column(db.Integer, db.ForeignKey('saved_set.id'), nullable=True)
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    saved_set = db.relationship('SavedSet')


class AttendanceRecord(db.Model):
    """One swimmer's roll-call mark for one squad practice date. Written by
    the coach dashboard's Attendance tab; a (squad, swimmer, date) triple is
    unique -- re-marking the same day overwrites the previous status."""
    __tablename__ = 'attendance_record'
    __table_args__ = (
        db.UniqueConstraint('squad_id', 'swimmer_id', 'session_date', name='uq_attendance_day'),
    )

    id = db.Column(db.Integer, primary_key=True)
    squad_id = db.Column(db.Integer, db.ForeignKey('squad.id'), nullable=False)
    swimmer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), default='present')  # present/late/excused/absent
    note = db.Column(db.Text)
    recorded_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class SavedSet(db.Model):
    __tablename__ = 'saved_set'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    pool = db.Column(db.String(10), default='25m')
    session_type = db.Column(db.String(50), default='Training')
    sets_data = db.Column(db.Text)  # JSON string, same shape as sessionSets in log.html
    category = db.Column(db.String(30), default='Fitness')
    difficulty = db.Column(db.String(20), default='Medium')  # Easy / Medium / Hard / Technical
    distance_focus = db.Column(db.String(20), default='All')  # Short / Middle / Long / All
    description = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_sets(self):
        try:
            return json.loads(self.sets_data or '[]')
        except:
            return []

    def total_distance(self):
        total = 0
        for s in self.get_sets():
            try:
                round_reps = int(s.get('round_reps') or 1)
                total += int(s.get('reps', 0)) * int(s.get('dist', 0)) * round_reps
            except:
                pass
        return total

    def estimated_duration_seconds(self):
        """Roughly how long this set takes to swim, using the same pace model
        the AI coach uses to validate sets (swim_logic.analyze_block) at a
        generic Intermediate pace, since a library set isn't tied to one
        swimmer's level."""
        from swim_logic import analyze_block
        total = 0.0
        for b in self.get_sets():
            try:
                reps = int(b.get('reps') or 0)
            except (TypeError, ValueError):
                reps = 0
            if reps <= 0:
                continue
            try:
                round_reps = int(b.get('round_reps') or 1)
            except (TypeError, ValueError):
                round_reps = 1
            analysis = analyze_block(b)
            est_swim = analysis.get('est_swim') or 0
            if analysis.get('interval') is not None:
                total += reps * round_reps * analysis['interval']
            elif analysis.get('rest') is not None:
                total += reps * round_reps * (est_swim + analysis['rest'])
            else:
                total += reps * round_reps * est_swim
        return round(total)

    def estimated_duration_label(self):
        secs = self.estimated_duration_seconds()
        if secs <= 0:
            return None
        mins = round(secs / 60)
        if mins < 1:
            return '<1 min'
        if mins < 60:
            return f'~{mins} min'
        hours, rem = divmod(mins, 60)
        return f'~{hours}h {rem}m' if rem else f'~{hours}h'


class CoachAssignment(db.Model):
    """Links a SavedSet to a squad or an individual swimmer -- the coach
    dashboard's active assignment queue. Exactly one of squad_id /
    swimmer_id is set."""
    __tablename__ = 'coach_assignment'

    id = db.Column(db.Integer, primary_key=True)
    saved_set_id = db.Column(db.Integer, db.ForeignKey('saved_set.id'), nullable=False)
    squad_id = db.Column(db.Integer, db.ForeignKey('squad.id'), nullable=True)
    swimmer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    assigned_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default='Assigned')  # Assigned/Completed
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    saved_set = db.relationship('SavedSet')
    squad = db.relationship('Squad')
    swimmer = db.relationship('User', foreign_keys=[swimmer_id])


class CssRecord(db.Model):
    """One Critical Swim Speed measurement for a swimmer. CSS is the pace
    (seconds per 100m) a swimmer can sustain for ~20-30 minutes -- the anchor
    every training-plan target time and send-off is derived from. Computed
    from a 400m + 200m freestyle time trial pair, estimated from the level
    pace model when no trials exist, or entered manually."""
    __tablename__ = 'css_record'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    t400_seconds = db.Column(db.Float, nullable=True)  # None when estimated
    t200_seconds = db.Column(db.Float, nullable=True)
    css_per_100 = db.Column(db.Float, nullable=False)  # seconds per 100m
    source = db.Column(db.String(20), default='time_trial')  # time_trial/estimated/manual
    swim_400_id = db.Column(db.Integer, db.ForeignKey('swim.id'), nullable=True)
    swim_200_id = db.Column(db.Integer, db.ForeignKey('swim.id'), nullable=True)
    pool = db.Column(db.String(10), default='25m')
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)


class TrainingPlan(db.Model):
    """A multi-week, event-targeted training plan (deterministic, built by
    plan_logic.build_plan -- separate from the AI weekly program on
    AthleteProfile). One active plan per user; generating a new one marks the
    previous plan 'abandoned'."""
    __tablename__ = 'training_plan'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='active')  # active/completed/abandoned
    goal_event = db.Column(db.String(50), nullable=True)  # e.g. '100m Freestyle'; NULL = just improve
    pool = db.Column(db.String(10), default='25m')
    race_date = db.Column(db.Date, nullable=True)
    target_time = db.Column(db.String(20), nullable=True)
    start_date = db.Column(db.Date, nullable=False)  # Monday of week 1
    weeks = db.Column(db.Integer, nullable=False)
    sessions_per_week = db.Column(db.Integer, nullable=False)
    preferred_days = db.Column(db.Text)  # JSON list of weekday ints, 0=Monday
    css_record_id = db.Column(db.Integer, db.ForeignKey('css_record.id'), nullable=True)
    phase_map_json = db.Column(db.Text)  # JSON list per week: {phase, deload}
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    planned_sessions = db.relationship('PlannedSession', backref='plan', lazy=True)
    css_record = db.relationship('CssRecord')

    def get_preferred_days(self):
        try:
            return json.loads(self.preferred_days or '[]')
        except (ValueError, TypeError):
            return []

    def get_phase_map(self):
        try:
            return json.loads(self.phase_map_json or '[]')
        except (ValueError, TypeError):
            return []


class PlannedSession(db.Model):
    """One dated workout inside a TrainingPlan. blocks_json holds the RESOLVED
    set blocks (same shape as SavedSet.sets_data / Session.sets_data) with
    real target times and send-offs already baked in from the swimmer's CSS."""
    __tablename__ = 'planned_session'

    id = db.Column(db.Integer, primary_key=True)
    plan_id = db.Column(db.Integer, db.ForeignKey('training_plan.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    week_index = db.Column(db.Integer, nullable=False)  # 0-based
    phase = db.Column(db.String(12))  # base/build/taper
    is_deload = db.Column(db.Boolean, default=False)
    slot = db.Column(db.String(20))  # technique/threshold/sprint/endurance/css_test
    scheduled_date = db.Column(db.Date, nullable=False)
    template_key = db.Column(db.String(60))
    title = db.Column(db.String(120))
    blocks_json = db.Column(db.Text)  # resolved blocks, SavedSet shape
    target_meters = db.Column(db.Integer)
    status = db.Column(db.String(12), default='planned')  # planned/completed/missed/skipped
    completed_session_id = db.Column(db.Integer, db.ForeignKey('session.id'), nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    def get_blocks(self):
        try:
            return json.loads(self.blocks_json or '[]')
        except (ValueError, TypeError):
            return []

    def total_distance(self):
        total = 0
        for b in self.get_blocks():
            try:
                total += int(b.get('reps', 0)) * int(b.get('dist', 0)) * int(b.get('round_reps') or 1)
            except (TypeError, ValueError):
                pass
        return total

