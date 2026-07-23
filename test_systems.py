"""End-to-end checks for the adaptive coach systems: swim science, interval
logic, unrealistic-set detection, progression engine, athlete model, weekly
reports, input validation and the HTTP layer.

Run with:  python test_systems.py
Uses its own throwaway SQLite database -- never touches stroke.db.
"""

import os
import sys
import tempfile
import traceback
from datetime import datetime, timedelta

# Point the app at a throwaway DB BEFORE anything imports app.py.
_TMP_DB = os.path.join(tempfile.mkdtemp(prefix='stroke_test_'), 'test.db')
os.environ['DATABASE_URL'] = f'sqlite:///{_TMP_DB}'
os.environ.pop('ANTHROPIC_API_KEY', None)  # tests never call the AI

PASS, FAIL = 0, 0
FAILURES = []


def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        FAILURES.append(f'{name}  {detail}')
        print(f'  FAIL: {name}  {detail}')


# ===========================================================================
# 1. Time parsing: the one true parser rejects every kind of junk
# ===========================================================================

def test_parse_time():
    from swim_logic import parse_time
    check('parse 1:30', parse_time('1:30') == 90.0)
    check('parse 0:45', parse_time('0:45') == 45.0)
    check('parse 90', parse_time('90') == 90.0)
    check('parse 1:05.3', abs(parse_time('1:05.3') - 65.3) < 0.001)
    check('parse 58.9', abs(parse_time('58.9') - 58.9) < 0.001)
    for junk in ['abc', '-500', '1e100', 'Infinity', 'NaN', '', '   ', None,
                 '999999999999999999', '1:75', '1;30', '4x100', '½', '0', '-1:30']:
        check(f'reject {junk!r}', parse_time(junk) is None, f'got {parse_time(junk)}')


# ===========================================================================
# 2. Interval vs rest semantics (the critical fix)
# ===========================================================================

def test_interval_logic():
    from swim_logic import analyze_block, fix_block, estimate_rep_seconds

    # 4x100 on 1:30 for a competitive swimmer: send-off means LEAVE every
    # 1:30; rest is interval minus swim, never 1:30.
    block = {'reps': 4, 'dist': 100, 'stroke': 'FR', 'rest': '1:30', 'rest_type': 'interval'}
    a = analyze_block(block, level='Competitive')
    check('competitive 4x100 on 1:30 is realistic', a['realistic'], a['issue'])
    check('rest = interval - swim', a['rest'] is not None and 5 <= a['rest'] <= 30,
          f"implied rest {a['rest']}")
    check('rest is NOT the interval', a['rest'] != 90.0)

    # Same set is impossible for a beginner (they swim 100m in ~2:15).
    a_beg = analyze_block(block, level='Beginner')
    check('beginner 4x100 on 1:30 flagged impossible', not a_beg['realistic'])
    fixed, note = fix_block(block, level='Beginner')
    check('beginner fix produced a note', note is not None)
    from swim_logic import parse_time
    new_interval = parse_time(fixed['rest'])
    est = estimate_rep_seconds(100, level='Beginner')
    check('fixed send-off exceeds swim time + min rest', new_interval >= est + 15,
          f'interval {new_interval} vs est {est}')

    # 6x50 on 0:50: fine for competitive (swim ~36-38s, rest ~12-14s),
    # impossible for intermediate (swim ~50s).
    b50 = {'reps': 6, 'dist': 50, 'stroke': 'FR', 'rest': '0:50', 'rest_type': 'interval'}
    a_comp = analyze_block(b50, level='Competitive')
    check('competitive 6x50 on 0:50 realistic', a_comp['realistic'], a_comp['issue'])
    check('competitive 6x50 rest ~10-16s', a_comp['rest'] and 8 <= a_comp['rest'] <= 18,
          f"rest {a_comp['rest']}")
    a_int = analyze_block(b50, level='Intermediate')
    check('intermediate 6x50 on 0:50 flagged', not a_int['realistic'])

    # Explicit rest: 4x200 with 20s rest for a beginner is the classic
    # unrealistic AI output (PART 6's example).
    b200 = {'reps': 4, 'dist': 200, 'stroke': 'FR', 'rest': '0:20', 'rest_type': 'rest'}
    a200 = analyze_block(b200, level='Beginner')
    check('beginner 200s w/ 20s rest flagged unrealistic', not a200['realistic'])
    fixed200, note200 = fix_block(b200, level='Beginner')
    check('beginner 200s rest raised', parse_time(fixed200['rest']) > 20, fixed200['rest'])

    # Trained swimmers legitimately use short rest (USRPT) -- don't flag it.
    a_usrpt = analyze_block({'reps': 20, 'dist': 50, 'stroke': 'FR', 'rest': '0:50',
                             'rest_type': 'interval'}, level='Competitive')
    check('USRPT-style short rest allowed for competitive', a_usrpt['realistic'], a_usrpt['issue'])

    # Kick sets are much slower: 4x100 kick on 1:45 impossible even for advanced.
    a_kick = analyze_block({'reps': 4, 'dist': 100, 'stroke': 'FR', 'modifier': 'Kick',
                            'rest': '1:45', 'rest_type': 'interval'}, level='Advanced')
    check('kick pace respected in feasibility', not a_kick['realistic'])

    # Children swim slower: same send-off fine for adult, not for a 9-year-old.
    a_adult = analyze_block({'reps': 8, 'dist': 50, 'stroke': 'FR', 'rest': '1:00',
                             'rest_type': 'interval'}, level='Intermediate', age=25)
    a_child = analyze_block({'reps': 8, 'dist': 50, 'stroke': 'FR', 'rest': '1:00',
                             'rest_type': 'interval'}, level='Intermediate', age=9)
    check('adult 8x50 on 1:00 ok', a_adult['realistic'], a_adult['issue'])
    check('child 8x50 on 1:00 flagged', not a_child['realistic'])


# ===========================================================================
# 3. Session volume caps + program validation
# ===========================================================================

def test_volume_caps():
    from swim_logic import validate_day_blocks, validate_program

    huge_day = [
        {'section': 'Warm up', 'reps': 1, 'dist': 400, 'stroke': 'FR', 'rest': '', 'rest_type': 'rest'},
        {'section': 'Main set', 'reps': 40, 'dist': 100, 'stroke': 'FR', 'rest': '3:00', 'rest_type': 'interval'},
        {'section': 'Cool down', 'reps': 1, 'dist': 200, 'stroke': 'FR', 'rest': '', 'rest_type': 'rest'},
    ]
    fixed, notes = validate_day_blocks([dict(b) for b in huge_day], level='Beginner')
    total = sum(b['reps'] * b['dist'] for b in fixed)
    check('beginner 4600m day trimmed to cap', total <= 2200, f'total {total}')
    check('trim produced a note', any('trimmed' in n for n in notes))
    warm = next(b for b in fixed if b['section'] == 'Warm up')
    check('warm up untouched by trim', warm['reps'] == 1 and warm['dist'] == 400)

    program = {'days': [
        {'day': 'Monday', 'rest': False, 'blocks': [
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'FR', 'rest': '1:30', 'rest_type': 'interval'},
        ]},
        {'day': 'Tuesday', 'rest': True, 'blocks': []},
    ]}
    notes = validate_program(program, level='Beginner')
    check('program validation fixed impossible interval', len(notes) >= 1)
    check('program day total recomputed', program['days'][0]['total'] == 400)


# ===========================================================================
# 4. Progression engine
# ===========================================================================

def test_progression():
    from swim_logic import next_week_target

    t = next_week_target(0, 0, 'plateauing', level='Beginner', days_per_week=3)
    check('no history -> baseline week', t['kind'] == 'baseline' and t['volume'] > 0)

    t = next_week_target(10000, 0, 'improving', level='Intermediate', days_per_week=4)
    check('improving -> ~+6%', t['kind'] == 'build' and 10500 <= t['volume'] <= 10700, t)

    t = next_week_target(10000, 3, 'improving', level='Intermediate', days_per_week=4)
    check('every 4th week -> recovery', t['kind'] == 'recovery' and t['volume'] == 7500, t)

    t = next_week_target(10000, 1, 'plateauing', level='Intermediate')
    check('plateau -> stimulus change, volume held', t['kind'] == 'stimulus-change' and t['volume'] == 10000)

    t = next_week_target(10000, 1, 'overtraining', level='Intermediate')
    check('overtraining -> -15%', t['kind'] == 'reduce' and t['volume'] == 8500)

    t = next_week_target(10000, 1, 'undertraining', level='Intermediate')
    check('undertraining -> +10%', t['kind'] == 'rebuild' and t['volume'] == 11000)

    t = next_week_target(11000, 1, 'improving', level='Beginner')
    check('level weekly cap respected', t['volume'] <= 11000, t)

    check('why text always present', all(
        next_week_target(8000, i, tr, level='Advanced')['why']
        for i in range(5) for tr in ('improving', 'plateauing', 'regressing', 'overtraining', 'undertraining')
    ))


# ===========================================================================
# 5. Input validation
# ===========================================================================

def test_validation():
    from validation import clean_int, clean_float, clean_time, clean_splits, clean_sets_json, clean_block

    for junk in ['1000000000000000', '999999999999999999', '-500', 'abc', '1e100',
                 'Infinity', 'NaN', '', '   ', None, '12.5', '0x10', '½', '10 000']:
        check(f'clean_int rejects {junk!r}', clean_int(junk, key='age') is None)
    check('clean_int accepts 25', clean_int('25', key='age') == 25)
    check('clean_int respects min', clean_int('4', key='age') is None)
    check('clean_int respects max', clean_int('100', key='age') is None)
    check('clean_int strips spaces', clean_int(' 30 ', key='age') == 30)

    check('clean_float rejects inf', clean_float('Infinity', lo=0, hi=100) is None)
    check('clean_float rejects 1e100', clean_float('1e100', lo=0, hi=100) is None)
    check('clean_float accepts 12.5', clean_float('12.5', lo=0, hi=100) == 12.5)

    norm, secs = clean_time('1:02.5', key='swim_seconds')
    check('clean_time normalizes 1:02.5', norm == '1:02.50' and abs(secs - 62.5) < 0.001)
    norm, secs = clean_time('58.9', key='swim_seconds')
    check('clean_time normalizes 58.9', norm == '58.90')
    check('clean_time rejects 1e100', clean_time('1e100')[0] is None)
    check('clean_time rejects 2 (too fast)', clean_time('2', key='swim_seconds')[0] is None)

    splits = clean_splits(['30.1', '31.5', 'garbage', '1e100', '32.0'])
    check('clean_splits keeps good drops bad', splits == ['30.10', '31.50', '32.00'], splits)

    check('clean_block rejects 1e100 reps', clean_block({'reps': '1e100', 'dist': 50}) is None)
    check('clean_block rejects negative dist', clean_block({'reps': 4, 'dist': -100}) is None)
    b = clean_block({'reps': 4, 'dist': 100, 'stroke': 'XX', 'rest': '1:30', 'note': 'x' * 999})
    check('clean_block clamps stroke + note', b['stroke'] == 'FR' and len(b['note']) <= 200)

    js, blocks = clean_sets_json('not json at all')
    check('clean_sets_json handles junk', js == '[]' and blocks == [])
    js, blocks = clean_sets_json('{"a": 1}')
    check('clean_sets_json handles non-list', blocks == [])
    js, blocks = clean_sets_json('[{"reps": 4, "dist": 100, "stroke": "FR"}, {"reps": "abc", "dist": 50}]')
    check('clean_sets_json keeps only valid blocks', len(blocks) == 1)
    # 60 blocks of 200x100 = a crafted 1.2M metre payload gets cut down
    import json as _json
    huge = _json.dumps([{'reps': 200, 'dist': 100, 'stroke': 'FR'}] * 60)
    js, blocks = clean_sets_json(huge)
    total = sum(b['reps'] * b['dist'] for b in blocks)
    check('clean_sets_json caps total volume', total <= 100_000, f'total {total}')


# ===========================================================================
# 6. Athlete model + weekly reports (with a real app + throwaway DB)
# ===========================================================================

def _mk_user(db, User, email, plan='solo'):
    u = User(email=email, username=email.split('@')[0], is_verified=True, plan=plan)
    u.set_password('test1234')
    db.session.add(u)
    db.session.commit()
    return u


def _seed_swims(db, Swim, user_id, event, times_and_daysago):
    for t, days in times_and_daysago:
        db.session.add(Swim(user_id=user_id, event=event, pool='25m', stroke='FR',
                            time=t, logged_at=datetime.utcnow() - timedelta(days=days)))
    db.session.commit()


def _seed_sessions(db, Session, user_id, spec):
    """spec: list of (days_ago, metres)."""
    import json as _json
    for days, metres in spec:
        blocks = [{'section': 'Main set', 'reps': metres // 100, 'dist': 100,
                   'stroke': 'FR', 'rest': '2:00', 'rest_type': 'interval'}]
        db.session.add(Session(user_id=user_id, session_type='Training', pool='25m',
                               sets_data=_json.dumps(blocks),
                               logged_at=datetime.utcnow() - timedelta(days=days)))
    db.session.commit()


def _mk_squad(db, Squad, coach_id, name='Senior Squad'):
    import secrets as _secrets
    squad = Squad(name=name, coach_id=coach_id, invite_code=_secrets.token_hex(6))
    db.session.add(squad)
    db.session.commit()
    return squad


def _mk_membership(db, SquadMembership, squad_id, user_id, status='active'):
    m = SquadMembership(squad_id=squad_id, user_id=user_id, status=status)
    db.session.add(m)
    db.session.commit()
    return m


def test_athlete_model(app):
    from app import db
    from models import User, Swim, Session, CheckIn, AthleteProfile, WeeklyReport
    import athlete_model

    with app.app_context():
        # --- improving swimmer: times coming down, steady volume ---
        u1 = _mk_user(db, User, 'improver@test.com')
        _seed_swims(db, Swim, u1.id, '100m Freestyle',
                    [('1:20.00', 50), ('1:19.00', 40), ('1:18.00', 30),
                     ('1:16.50', 20), ('1:15.00', 10), ('1:14.20', 3)])
        _seed_sessions(db, Session, u1.id, [(3, 3000), (5, 3000), (10, 3200), (12, 2800),
                                            (17, 3000), (20, 3000), (24, 3000)])
        state = athlete_model.update_athlete_state(u1.id)
        check('state persisted + computed', state is not None and state['total_logs'] == 13)
        check('improver classified improving', state['trend'] == 'improving', state['trend_reason'])
        check('event trend captured', state['events']['100m Freestyle']['direction'] == 'improving')
        check('PB tracked', state['pbs']['100m Freestyle|25']['time'] == '1:14.20')

        # --- regressing swimmer: times going up ---
        u2 = _mk_user(db, User, 'slipper@test.com')
        _seed_swims(db, Swim, u2.id, '50m Butterfly',
                    [('31.00', 40), ('31.20', 30), ('32.50', 15), ('33.40', 5)])
        _seed_sessions(db, Session, u2.id, [(4, 2000), (11, 2000), (18, 2000), (25, 2000)])
        s2 = athlete_model.update_athlete_state(u2.id)
        check('slipper classified regressing', s2['trend'] == 'regressing', s2['trend_reason'])

        # --- overtraining: volume spike + wrecked check-ins ---
        u3 = _mk_user(db, User, 'overloaded@test.com')
        _seed_sessions(db, Session, u3.id, [(1, 6000), (2, 6000), (3, 5000), (5, 5500),
                                            (10, 2000), (17, 2000), (24, 2000)])
        for d in range(1, 6):
            db.session.add(CheckIn(user_id=u3.id, checkin_date=(datetime.utcnow() - timedelta(days=d)).date(),
                                   feeling_rating=2, fatigue_rating=5, sleep_quality=2))
        db.session.commit()
        s3 = athlete_model.update_athlete_state(u3.id)
        check('overload classified overtraining', s3['trend'] == 'overtraining', (s3['acwr'], s3['trend_reason']))

        # --- undertraining: established load then nothing this week ---
        u4 = _mk_user(db, User, 'ghost@test.com')
        _seed_sessions(db, Session, u4.id, [(10, 4000), (13, 4000), (17, 4000),
                                            (20, 4000), (24, 4000), (27, 4000)])
        s4 = athlete_model.update_athlete_state(u4.id)
        check('ghost classified undertraining', s4['trend'] == 'undertraining', (s4['acwr'], s4['trend_reason']))

        # --- weekly report for the improver ---
        db.session.add(AthleteProfile(user_id=u1.id, level='Intermediate', age=17,
                                      training_days_per_week=3))
        db.session.commit()
        report = athlete_model.ensure_weekly_report(u1.id)
        check('weekly report generated', report is not None)
        if report:
            check('report has progress %', 5 <= report['progress_pct'] <= 98, report['progress_pct'])
            check('report detects new PB', any(p['event'] == '100m Freestyle' for p in report['pb_improvements']),
                  report['pb_improvements'])
            check('report has strengths + weaknesses', report['strengths'] and report['weaknesses'])
            check('report has next-week target', report['next_week']['volume'] > 0)
            check('report has confidence', report['confidence'] in ('low', 'medium', 'high'))
            check('report has recovery status', report['recovery_status'] in ('fresh', 'normal', 'run down', 'unknown'))
        n_reports = db.session.query(WeeklyReport).filter_by(user_id=u1.id).count()
        athlete_model.ensure_weekly_report(u1.id)  # within 7 days: reuse, don't duplicate
        check('report not duplicated within 7 days',
              db.session.query(WeeklyReport).filter_by(user_id=u1.id).count() == n_reports)

        # --- empty swimmer: everything degrades gracefully ---
        u5 = _mk_user(db, User, 'empty@test.com')
        s5 = athlete_model.update_athlete_state(u5.id)
        check('empty swimmer state safe', s5 is not None and s5['trend'] == 'plateauing')
        check('empty swimmer report is None', athlete_model.ensure_weekly_report(u5.id) is None)

        # --- adaptation context ---
        profile = db.session.query(AthleteProfile).filter_by(user_id=u1.id).first()
        text, target = athlete_model.adaptation_context(u1.id, profile)
        check('adaptation context built', text is not None and 'NEXT WEEK TARGET' in text)
        check('adaptation target sane', target and 600 <= target['volume'] <= 24000, target)
        p5 = AthleteProfile(user_id=u5.id, level='Beginner')
        db.session.add(p5)
        db.session.commit()
        t5, tg5 = athlete_model.adaptation_context(u5.id, p5)
        check('no-history adaptation is None', t5 is None and tg5 is None)

        # --- check-in nudge cadence ---
        nudge = athlete_model.checkin_nudge(u5.id)
        check('nudge due with no check-ins', nudge['due'] and nudge['question'])
        db.session.add(CheckIn(user_id=u5.id, checkin_date=datetime.utcnow().date(), feeling_rating=4))
        db.session.commit()
        check('nudge not due right after check-in', not athlete_model.checkin_nudge(u5.id)['due'])
        # 5 large datasets exist now; recompute them all once more for stability
        for uid in (u1.id, u2.id, u3.id, u4.id, u5.id):
            check(f'recompute stable for user {uid}', athlete_model.update_athlete_state(uid) is not None)


# ===========================================================================
# 7. Coach routes: IDOR guard + PB pool-conflation regression checks
# ===========================================================================

def test_coach_routes(app):
    """Regression guard for two bugs found and fixed this session: (1) a coach
    could tag notes/status onto ANY user id under their own squad_id, without
    that user actually being a member of the squad (IDOR); (2) personal-best
    computation keyed by event only, so a 50m-pool time could silently
    overwrite (or lose to) an unrelated 25m-pool PB for the same event."""
    from app import db
    from models import User, Squad, SquadMembership, Swim, CoachNote, StatusFlag

    with app.app_context():
        coach = _mk_user(db, User, 'coach1@test.com')
        coach.role = 'coach'
        member = _mk_user(db, User, 'member1@test.com')
        outsider = _mk_user(db, User, 'outsider1@test.com')
        squad = _mk_squad(db, Squad, coach.id)
        _mk_membership(db, SquadMembership, squad.id, member.id)
        coach_id, squad_id, member_id, outsider_id = coach.id, squad.id, member.id, outsider.id

    client = app.test_client()
    client.post('/login', data={'email': 'coach1@test.com', 'password': 'test1234'},
                follow_redirects=True)

    # --- IDOR: swimmer_id not a member of squad_id must 404, not succeed ---
    r = client.post(f'/coach/squad/{squad_id}/swimmer/{outsider_id}/note',
                    data={'note': 'should never be stored'})
    check('IDOR: note on non-member 404s', r.status_code == 404, r.status_code)
    with app.app_context():
        check('IDOR: no note row created for non-member',
              db.session.query(CoachNote).filter_by(squad_id=squad_id, swimmer_id=outsider_id).count() == 0)

    r = client.post(f'/coach/squad/{squad_id}/swimmer/{outsider_id}/status',
                    data={'status': 'injured', 'note': 'should never be stored'})
    check('IDOR: status on non-member 404s', r.status_code == 404, r.status_code)
    with app.app_context():
        check('IDOR: no status row created for non-member',
              db.session.query(StatusFlag).filter_by(squad_id=squad_id, swimmer_id=outsider_id).count() == 0)

    # --- positive case: an actual member still works (fix isn't over-broad) ---
    r = client.post(f'/coach/squad/{squad_id}/swimmer/{member_id}/note',
                    data={'note': 'real note'}, follow_redirects=True)
    check('note on real member succeeds', r.status_code == 200)
    with app.app_context():
        check('note row created for real member',
              db.session.query(CoachNote).filter_by(squad_id=squad_id, swimmer_id=member_id).count() == 1)

    # --- dead route stays deleted ---
    r = client.get(f'/coach/squad/{squad_id}/swimmer/{member_id}')
    check('deleted squad_swimmer_profile route is gone', r.status_code == 404, r.status_code)

    # --- PB pool-conflation: same event at both 25m and 50m must NOT collide ---
    with app.app_context():
        db.session.add(Swim(user_id=member_id, event='100m Freestyle', pool='25m', stroke='FR',
                            time='58.00', logged_at=datetime.utcnow() - timedelta(days=5)))
        db.session.add(Swim(user_id=member_id, event='100m Freestyle', pool='50m', stroke='FR',
                            time='1:02.00', logged_at=datetime.utcnow() - timedelta(days=3)))
        db.session.commit()

        from routes_coach import _best_by_event_pool
        swims = db.session.query(Swim).filter_by(user_id=member_id).all()
        best = _best_by_event_pool(swims)
        check('25m PB kept separately from 50m',
              best.get(('100m Freestyle', '25'), {}).get('time') == '58.00',
              best.get(('100m Freestyle', '25')))
        check('50m PB kept separately from 25m',
              best.get(('100m Freestyle', '50'), {}).get('time') == '1:02.00',
              best.get(('100m Freestyle', '50')))

    # --- same fix in athlete_model.recompute_state's pbs dict ---
    with app.app_context():
        import athlete_model
        state = athlete_model.update_athlete_state(member_id)
        check('athlete_model pbs keeps 25m/50m separate',
              state['pbs'].get('100m Freestyle|25', {}).get('time') == '58.00'
              and state['pbs'].get('100m Freestyle|50', {}).get('time') == '1:02.00',
              state['pbs'])


def test_admin_routes(app):
    """Regression guard for the admin-facing CSS/swimmer-type panels added
    2026-07-24: /admin gets an adoption-stats + roadmap panel, /admin/solo/<id>
    gets a per-user CSS+zones card. Also checks access control isn't
    accidentally loosened by the new code path."""
    from app import db
    from models import User, Swim

    with app.app_context():
        admin = _mk_user(db, User, 'siteadmin@test.com')
        admin.is_admin = True
        solo = _mk_user(db, User, 'solo-admin-view@test.com', plan='solo')
        _seed_swims(db, Swim, solo.id, '400m Freestyle', [('5:52.00', 1)])
        db.session.commit()
        admin_id, solo_id = admin.id, solo.id

    client = app.test_client()

    # --- non-admin gets refused ---
    client.post('/login', data={'email': 'solo-admin-view@test.com', 'password': 'test1234'},
                follow_redirects=True)
    r = client.get('/admin')
    check('non-admin refused /admin', r.status_code in (302, 403), r.status_code)
    client.get('/logout')

    # --- admin sees the adoption stats + roadmap panel ---
    client.post('/login', data={'email': 'siteadmin@test.com', 'password': 'test1234'},
                follow_redirects=True)
    r = client.get('/admin')
    check('admin /admin renders', r.status_code == 200, r.status_code)
    body = r.get_data(as_text=True)
    check('adoption stats panel present', 'CSS / swimmer-type adoption' in body)
    check('roadmap panel present', 'Roadmap: not yet built' in body)
    check('roadmap lists meet-results importer gap', 'Meet-results importer' in body)

    # --- admin sees the per-user CSS card, sourced from routes_coach's engine ---
    r = client.get(f'/admin/solo/{solo_id}')
    check('admin solo detail renders', r.status_code == 200, r.status_code)
    body2 = r.get_data(as_text=True)
    check('CSS panel present on solo detail', 'CSS &amp; training zones' in body2, body2[:200])
    check('estimated badge shown for single-swim CSS', 'Estimated' in body2)


# ===========================================================================
# 8. HTTP layer: invalid input never crashes or corrupts data
# ===========================================================================

def test_http(app):
    from app import db
    from models import User, Swim, Session, Goal

    with app.app_context():
        u = _mk_user(db, User, 'webuser@test.com', plan='solo')
        uid = u.id

    client = app.test_client()
    r = client.post('/login', data={'email': 'webuser@test.com', 'password': 'test1234'},
                    follow_redirects=True)
    check('login works', r.status_code == 200)

    # PB with junk times: rejected, nothing stored, no crash.
    for bad_time in ['1e100', 'Infinity', 'NaN', '-500', 'abc', '', '999999999999999999']:
        r = client.post('/log', data={'log_type': 'pb', 'event': '100m Freestyle',
                                      'pool': '25m', 'time': bad_time}, follow_redirects=True)
        check(f'PB junk time {bad_time!r} handled', r.status_code == 200)
    with app.app_context():
        check('no junk swims stored', db.session.query(Swim).filter_by(user_id=uid).count() == 0)

    # Valid PB stores + normalizes.
    r = client.post('/log', data={'log_type': 'pb', 'event': '100m Freestyle', 'pool': '25m',
                                  'time': '62.5', 'splits': '["30.1", "garbage", "32.4"]'},
                    follow_redirects=True)
    with app.app_context():
        s = db.session.query(Swim).filter_by(user_id=uid).first()
        check('valid PB stored normalized', s is not None and s.time == '1:02.50', s.time if s else None)
        check('splits filtered', s and s.get_splits() == ['30.10', '32.40'], s.get_splits() if s else None)

    # Session with invalid blocks: rejected.
    r = client.post('/log', data={'log_type': 'session', 'event': 'Training', 'pool': '25m',
                                  'session_data': '[{"reps": "1e100", "dist": 50}]'},
                    follow_redirects=True)
    with app.app_context():
        check('junk session rejected', db.session.query(Session).filter_by(user_id=uid).count() == 0)

    # Valid session stored.
    r = client.post('/log', data={'log_type': 'session', 'event': 'Training', 'pool': '25m',
                                  'session_data': '[{"reps": 8, "dist": 50, "stroke": "FR", "rest": "1:00", "rest_type": "interval"}]'},
                    follow_redirects=True)
    with app.app_context():
        check('valid session stored', db.session.query(Session).filter_by(user_id=uid).count() == 1)

    # Goals with junk target times: rejected.
    for bad in ['1e100', 'Infinity', '-500', 'abc']:
        client.post('/goals', data={'event': '100m Freestyle', 'target_time': bad}, follow_redirects=True)
    with app.app_context():
        check('junk goals rejected', db.session.query(Goal).filter_by(user_id=uid).count() == 0)
    client.post('/goals', data={'event': '100m Freestyle', 'target_time': '1:00.00'}, follow_redirects=True)
    with app.app_context():
        check('valid goal stored', db.session.query(Goal).filter_by(user_id=uid).count() == 1)

    # Onboarding with insane age: rejected by validation before any AI call.
    app.config['ANTHROPIC_API_KEY'] = 'test-key-never-used'
    r = client.post('/solo/onboarding', data={'age': '-500', 'level': 'Beginner',
                                              'training_days_per_week': '3'}, follow_redirects=True)
    check('onboarding junk age handled', r.status_code == 200 and b'between 5 and 99' in r.data)
    r = client.post('/solo/onboarding', data={'age': '17', 'level': 'Beginner',
                                              'training_days_per_week': '1e100'}, follow_redirects=True)
    check('onboarding junk days handled', r.status_code == 200 and b'1 to 7' in r.data)
    app.config['ANTHROPIC_API_KEY'] = None

    # Analytics page renders (weekly report generates without AI).
    r = client.get('/solo/analytics')
    check('analytics page renders', r.status_code == 200)
    check('weekly review shows', b'Weekly review' in r.data)

    # Check-in flow with junk ratings.
    r = client.post('/solo/checkin', data={'feeling_rating': '1e100'}, follow_redirects=True)
    check('junk check-in rating handled', r.status_code == 200)

    # Dashboard renders with the check-in nudge machinery in play.
    r = client.get('/dashboard')
    check('dashboard renders', r.status_code == 200)

    # 404 is friendly, not a stack trace.
    r = client.get('/definitely-not-a-page')
    check('404 handled gracefully', r.status_code == 404 and b'Back to your dashboard' in r.data)


# ===========================================================================
# Training plans: CSS engine, template resolution, plan generation
# ===========================================================================

def test_training_plan(app):
    import json as _json
    from datetime import date
    import plan_logic as pl
    from workout_templates import TEMPLATES, templates_for
    from swim_logic import parse_time, MIN_REST, WEEK_CAP, SESSION_CAP, STROKE_FACTOR, MODIFIER_FACTOR

    # --- CSS math ---
    check('CSS from 400/200 pair', pl.compute_css(352.0, 168.0) == 92.0)
    check('CSS rejects implausible pair', pl.compute_css(300.0, 168.0) is None)
    check('CSS rejects missing input', pl.compute_css(None, 168.0) is None)
    check('CSS rejects absurd pace', pl.compute_css(1000.0, 100.0) is None)
    z = pl.zones(92.0)
    check('zone offsets exact', z['recovery'] == 104.0 and z['endurance'] == 98.0
          and z['tempo'] == 94.0 and z['threshold'] == 92.0 and z['vo2max'] == 88.0)

    # --- every template resolves consistently at every level ---
    bad = []
    for t in TEMPLATES:
        for lvl, css in (('Beginner', 130.0), ('Intermediate', 95.0),
                         ('Advanced', 80.0), ('Competitive', 70.0)):
            for tm in (1200, 2200, 3500):
                blocks = pl.resolve_template(t, css, level=lvl, target_meters=tm)
                zz = pl.zones(css)
                for b in blocks:
                    if b.get('rest_type') != 'interval' or b.get('zone') in (None, 'max'):
                        continue
                    pace = (zz[b['zone']] * STROKE_FACTOR.get(b.get('stroke') or 'FR', 1.0)
                            * MODIFIER_FACTOR.get(b.get('modifier') or '', 1.0))
                    so = parse_time(b['rest'])
                    if so is None or so - pace * b['dist'] / 100.0 < MIN_REST[lvl] - 0.01:
                        bad.append((t['key'], lvl, tm))
    check('all send-offs leave at least min rest at prescribed pace', not bad, bad[:5])

    # Every slot/phase pool a plan can ask for has at least one template.
    empty = [(s, p, l) for s in ('technique', 'threshold', 'sprint', 'endurance', 'css_test')
             for p in ('base', 'build') for l in ('Beginner', 'Intermediate', 'Advanced', 'Competitive')
             if not templates_for(s, p, l)]
    check('no empty template pools for base/build', not empty, empty)
    check('taper pools exist for technique+sprint', templates_for('technique', 'taper', 'Beginner')
          and templates_for('sprint', 'taper', 'Intermediate'))

    # --- phase map ---
    pm = pl.build_phase_map(16, 3)
    check('16wk: base then build then taper',
          pm[0]['phase'] == 'base' and pm[7]['phase'] == 'build' and pm[13]['phase'] == 'taper'
          and pm[15]['phase'] == 'taper')
    check('deloads on the 4-week wave, never in taper',
          pm[3]['deload'] and pm[7]['deload'] and pm[11]['deload'] and not pm[15]['deload'])

    # --- full plan generation against the DB ---
    from app import db
    from models import User, Swim, Session, AthleteProfile, TrainingPlan, PlannedSession, CssRecord

    with app.app_context():
        # Swimmer WITH recent time trials: CSS comes from real swims.
        u = _mk_user(db, User, 'planner@test.com')
        _seed_swims(db, Swim, u.id, '400m Freestyle', [('5:52.00', 20)])
        _seed_swims(db, Swim, u.id, '200m Freestyle', [('2:48.00', 20)])
        prof = AthleteProfile(user_id=u.id, level='Intermediate', age=17,
                              training_days_per_week=4, fitness_ability='Good')
        db.session.add(prof)
        db.session.commit()

        race = date.today() + timedelta(weeks=12)
        plan = pl.build_plan(u.id, prof, goal_event='100m Freestyle', pool='25m',
                             race_date=race, target_time='1:00.00',
                             sessions_per_week=4, preferred_days=[0, 2, 4, 6])
        check('plan created', plan is not None and plan.status == 'active')
        rec = db.session.get(CssRecord, plan.css_record_id)
        check('CSS measured from logged trials', rec.source == 'time_trial'
              and abs(rec.css_per_100 - 92.0) < 0.01, (rec.source, rec.css_per_100))

        sessions = PlannedSession.query.filter_by(plan_id=plan.id).all()
        check('one session per slot per week', len(sessions) == plan.weeks * 4, len(sessions))
        check('100m event gets a 2-week taper',
              sum(1 for w in plan.get_phase_map() if w['phase'] == 'taper') == 2)

        # Volume respects caps; no template repeats in the same slot two weeks running.
        by_week = {}
        for s in sessions:
            by_week.setdefault(s.week_index, []).append(s)
        for w, ss in by_week.items():
            wk_total = sum(s.target_meters or 0 for s in ss)
            check(f'week {w} volume under cap', wk_total <= WEEK_CAP['Intermediate'], wk_total)
            for s in ss:
                check(f'session under cap w{w}', (s.target_meters or 0) <= SESSION_CAP['Intermediate'],
                      s.target_meters)
        repeats = []
        for s in sessions:
            nxt = [x for x in by_week.get(s.week_index + 1, []) if x.slot == s.slot]
            if nxt and nxt[0].template_key == s.template_key and s.slot != 'css_test':
                repeats.append((s.week_index, s.slot, s.template_key))
        check('no same-slot template repeats in consecutive weeks', not repeats, repeats[:4])

        # Blocks are stored resolved and renderable.
        b0 = sessions[0].get_blocks()
        check('blocks resolved with rest + note', b0 and all('rest' in b and 'note' in b for b in b0))

        # completion linking: log a Session on a planned day.
        first = min((s for s in sessions), key=lambda s: s.scheduled_date)
        logged = Session(user_id=u.id, session_type='Training', pool='25m',
                         sets_data=_json.dumps(b0),
                         logged_at=datetime.combine(first.scheduled_date, datetime.min.time()))
        db.session.add(logged)
        db.session.commit()
        ps = pl.link_completed(u.id, logged)
        check('logged session completes the planned one', ps is not None and ps.status == 'completed'
              and logged.planned_session_id == ps.id)

        # Swimmer WITHOUT trials: estimated CSS + week-0 test scheduled.
        u2 = _mk_user(db, User, 'newbie-plan@test.com')
        prof2 = AthleteProfile(user_id=u2.id, level='Beginner', age=30,
                               training_days_per_week=3, fitness_ability='Moderate')
        db.session.add(prof2)
        db.session.commit()
        plan2 = pl.build_plan(u2.id, prof2, sessions_per_week=3)  # no race date
        check('no-race plan is 8 weeks, no taper', plan2.weeks == 8
              and all(w['phase'] != 'taper' for w in plan2.get_phase_map()))
        rec2 = db.session.get(CssRecord, plan2.css_record_id)
        check('CSS estimated for trial-less swimmer', rec2.source == 'estimated')
        wk0 = PlannedSession.query.filter_by(plan_id=plan2.id, week_index=0).all()
        check('week 0 includes the CSS test', any(s.slot == 'css_test' for s in wk0))
        last_wk = PlannedSession.query.filter_by(plan_id=plan2.id, week_index=plan2.weeks - 1).all()
        check('no-race plan ends in a retest', any(s.slot == 'css_test' for s in last_wk))

        # New plan abandons the old one.
        plan3 = pl.build_plan(u2.id, prof2, sessions_per_week=2)
        check('previous plan abandoned', db.session.get(TrainingPlan, plan2.id).status == 'abandoned'
              and plan3.status == 'active')

        # Race too soon: refused with a friendly error.
        try:
            pl.build_plan(u.id, prof, goal_event='100m Freestyle',
                          race_date=date.today() + timedelta(days=10), sessions_per_week=3)
            check('too-soon race refused', False, 'no ValueError raised')
        except ValueError as e:
            check('too-soon race refused', '4 weeks' in str(e))

        # rebuild_future_sessions after a manual CSS entry.
        newrec = CssRecord(user_id=u2.id, css_per_100=100.0, source='manual', pool='25m')
        db.session.add(newrec)
        db.session.commit()
        n = pl.rebuild_future_sessions(plan3, newrec)
        check('future sessions re-resolved on new CSS', n > 0
              and db.session.get(TrainingPlan, plan3.id).css_record_id == newrec.id, n)

        # sweep_missed marks stale sessions without touching future ones.
        stale = PlannedSession.query.filter_by(plan_id=plan3.id).order_by(PlannedSession.scheduled_date).first()
        stale.scheduled_date = date.today() - timedelta(days=10)
        db.session.commit()
        pl.sweep_missed(plan3)
        check('stale session marked missed',
              db.session.get(PlannedSession, stale.id).status == 'missed')
        future_ok = PlannedSession.query.filter(PlannedSession.plan_id == plan3.id,
                                                PlannedSession.scheduled_date >= date.today(),
                                                PlannedSession.status == 'planned').count()
        check('future sessions untouched by sweep', future_ok > 0)

        # --- shared Riegel predictor (swim_logic.riegel_predict) ---
        from swim_logic import riegel_predict
        check('riegel_predict basic', abs(riegel_predict(60.0, 100, 200) - 60.0 * 2 ** 1.06) < 1e-9)
        check('riegel_predict rejects >4x extrapolation', riegel_predict(30.0, 50, 1500) is None)
        check('riegel_predict rejects <0.25x extrapolation', riegel_predict(1200.0, 1500, 50) is None)
        check('riegel_predict rejects missing input', riegel_predict(None, 100, 200) is None)

        # --- css_estimate: generalizes beyond a literal 400+200 pair ---
        css_u1 = _mk_user(db, User, 'css-pair@test.com')
        _seed_swims(db, Swim, css_u1.id, '400m Freestyle', [('5:52.00', 1)])
        _seed_swims(db, Swim, css_u1.id, '200m Freestyle', [('2:48.00', 1)])
        est1 = pl.css_estimate(css_u1.id)
        check('css_estimate real pair -> time_trial',
              est1 is not None and est1['source'] == 'time_trial' and abs(est1['css'] - 92.0) < 0.01, est1)

        css_u2 = _mk_user(db, User, 'css-single@test.com')
        _seed_swims(db, Swim, css_u2.id, '800m Freestyle', [('9:30.00', 1)])
        est2 = pl.css_estimate(css_u2.id)
        check('css_estimate single distant swim -> estimated_riegel',
              est2 is not None and est2['source'] == 'estimated_riegel', est2)
        check('css_estimate basis reflects the logged swim',
              est2 is not None and est2['basis400'] == '800m Freestyle' and est2['basis200'] == '800m Freestyle')

        css_u3 = _mk_user(db, User, 'css-none@test.com')
        _seed_swims(db, Swim, css_u3.id, '50m Freestyle', [('28.00', 1)])
        check('css_estimate no trustworthy anchor -> None', pl.css_estimate(css_u3.id) is None)

        # --- classify_swimmer_type: sprint/distance lean from the swimmer's own curve ---
        type_u1 = _mk_user(db, User, 'type-sprint@test.com')
        _seed_swims(db, Swim, type_u1.id, '100m Freestyle', [('1:00.00', 1)])
        _seed_swims(db, Swim, type_u1.id, '400m Freestyle', [('5:20.00', 1)])
        sprint_type = pl.classify_swimmer_type(type_u1.id)
        check('classify_swimmer_type reads a sprint lean',
              sprint_type is not None and sprint_type['profile'] == 'sprint', sprint_type)

        type_u2 = _mk_user(db, User, 'type-distance@test.com')
        _seed_swims(db, Swim, type_u2.id, '100m Freestyle', [('1:05.00', 1)])
        _seed_swims(db, Swim, type_u2.id, '400m Freestyle', [('4:20.00', 1)])
        distance_type = pl.classify_swimmer_type(type_u2.id)
        check('classify_swimmer_type reads a distance lean',
              distance_type is not None and distance_type['profile'] == 'distance', distance_type)

        type_u3 = _mk_user(db, User, 'type-none@test.com')
        _seed_swims(db, Swim, type_u3.id, '100m Freestyle', [('1:00.00', 1)])
        _seed_swims(db, Swim, type_u3.id, '200m Freestyle', [('2:10.00', 1)])
        check('classify_swimmer_type needs >= 3x distance spread',
              pl.classify_swimmer_type(type_u3.id) is None)


# ===========================================================================
# 10. Research agent: source hardening, scout filtering, pipeline idempotency,
#     and route access control
# ===========================================================================

def _load_run_research():
    """Import scripts/run_research.py as a module (it isn't a package)."""
    import importlib.util
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scripts', 'run_research.py')
    spec = importlib.util.spec_from_file_location('run_research', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeSource:
    """Stand-in for a real source: returns canned items, no network."""
    name = 'faketest'

    def __init__(self, items):
        self._items = items

    def fetch(self, since_days=10):
        return [dict(it) for it in self._items]


def test_research_sources():
    from sources import EuropePMCSource

    # --- URL scheme hardening: only http(s) survives (stored-XSS guard) ---
    check('https url kept', EuropePMCSource._safe_url('https://europepmc.org/x') == 'https://europepmc.org/x')
    check('javascript: url dropped', EuropePMCSource._safe_url('javascript:alert(1)') == '')
    check('data: url dropped', EuropePMCSource._safe_url('data:text/html,<script>') == '')
    check('empty url stays empty', EuropePMCSource._safe_url('') == '')
    check('overlong url dropped', EuropePMCSource._safe_url('https://x/' + 'a' * 600) == '')

    # --- _to_item maps onto the contract and namespaces external_id ---
    src = EuropePMCSource()
    item = src._to_item({
        'source': 'MED', 'id': '123', 'doi': '10.1/x',
        'title': 'Stroke mechanics', 'authorString': 'A B',
        'abstractText': 'text', 'firstPublicationDate': '2026-01-02',
    })
    check('external_id namespaced', item['external_id'] == 'europepmc:MED:123', item['external_id'])
    check('item url is europepmc article', item['url'] == 'https://europepmc.org/article/MED/123', item['url'])
    check('item keys match contract',
          set(item.keys()) == {'source', 'external_id', 'title', 'authors', 'abstract', 'url', 'published_date'})
    # An item with no source/id is unusable and dropped.
    check('item without ids dropped', src._to_item({'title': 'x'}) is None)

    # --- _http_get_json refuses non-https outright (SSRF hardening), no network ---
    from sources import _http_get_json
    check('non-https GET refused', _http_get_json('http://169.254.169.254/latest/meta-data/') is None)
    check('ftp GET refused', _http_get_json('ftp://example.com/x') is None)


def test_research_scout_filter():
    import scout
    items = [
        {'external_id': 'a', 'relevance_score': 9.0},
        {'external_id': 'b', 'relevance_score': 2.0},
        {'external_id': 'c', 'relevance_score': 6.0},
        {'external_id': 'd'},  # unscored -> treated as 0
    ]
    kept = scout.survivors(items, threshold=6.0)
    check('survivors keeps >= threshold only', [i['external_id'] for i in kept] == ['a', 'c'],
          [i['external_id'] for i in kept])
    check('survivors sorted best-first', kept[0]['external_id'] == 'a')


def test_research_pipeline(app):
    """Full runner with sources/AI stubbed: it stores items, links a brief,
    is idempotent across a second run, and the DB blocks two briefs per week."""
    from app import db
    import sources, scout, synthesize
    from models import ResearchBrief, ResearchItem
    rr = _load_run_research()

    good = {'source': 'faketest', 'external_id': 'faketest:GOOD:1', 'title': 'GOOD swim study',
            'authors': 'X', 'abstract': 'relevant', 'url': 'https://europepmc.org/article/MED/1',
            'published_date': '2026-01-01'}
    bad = {'source': 'faketest', 'external_id': 'faketest:BAD:1', 'title': 'BAD dolphin study',
           'authors': 'Y', 'abstract': 'irrelevant', 'url': 'https://europepmc.org/article/MED/2',
           'published_date': '2026-01-01'}

    def fake_score(items, api_key, model=None, batch_size=None):
        for it in items:
            it['relevance_score'] = 8.0 if 'GOOD' in it['title'] else 1.0
            it['topics'] = ['technique']
        return items

    def fake_synth(items, api_key, model):
        return {'ok': True, 'title': 'Test brief', 'summary': 'A summary.',
                'coaching_takeaways': ['Do the thing.']}

    orig_sources, orig_score, orig_synth = sources.ALL_SOURCES, scout.score_items, synthesize.synthesize_brief
    sources.ALL_SOURCES = [_FakeSource([good, bad])]
    scout.score_items = fake_score
    synthesize.synthesize_brief = fake_synth
    try:
        with app.app_context():
            r1 = rr.run_weekly_research(db, api_key='k', model='m')
            check('first run wrote a brief', r1.get('ok') and r1.get('brief_id'), r1)
            check('first run kept only the survivor', r1.get('kept') == 1, r1)
            check('both fetched items stored (novelty record)',
                  db.session.query(ResearchItem).count() == 2)
            check('only the survivor is linked to the brief',
                  db.session.query(ResearchItem).filter(ResearchItem.brief_id.isnot(None)).count() == 1)
            check('bad item stored but unlinked (will not re-score next week)',
                  db.session.query(ResearchItem).filter_by(external_id='faketest:BAD:1').first().brief_id is None)

            # Second run, same week: idempotent short-circuit, no dupes.
            r2 = rr.run_weekly_research(db, api_key='k', model='m')
            check('second run skipped (idempotent)', r2.get('skipped') is True, r2)
            check('still exactly one brief', db.session.query(ResearchBrief).count() == 1)
            check('still exactly two items (no dupes)', db.session.query(ResearchItem).count() == 2)

            # DB-level backstop: two briefs for one week is rejected.
            from sqlalchemy.exc import IntegrityError
            wk = db.session.query(ResearchBrief).first().week_of
            db.session.add(ResearchBrief(week_of=wk, title='dupe', item_count=0))
            raised = False
            try:
                db.session.commit()
            except IntegrityError:
                raised = True
                db.session.rollback()
            check('uq_research_brief_week blocks a second brief for the week', raised)
    finally:
        sources.ALL_SOURCES, scout.score_items, synthesize.synthesize_brief = orig_sources, orig_score, orig_synth


def test_research_routes(app):
    """/research and /research/<id> are coach-gated and render for a coach."""
    from app import db
    from models import User, ResearchBrief
    import json as _json

    with app.app_context():
        coach = _mk_user(db, User, 'researchcoach@test.com')
        coach.role = 'coach'
        swimmer = _mk_user(db, User, 'researchswimmer@test.com')  # role stays 'swimmer'
        db.session.commit()
        from datetime import date as _date
        brief = ResearchBrief(week_of=_date(2026, 2, 2), title='Feb brief',
                              summary='Line one.\nLine two.',
                              coaching_takeaways=_json.dumps(['Cue one.']), item_count=0)
        db.session.add(brief)
        db.session.commit()
        brief_id = brief.id

    client = app.test_client()

    # Anonymous is not served the page (login redirect or 403), never 200.
    r = client.get('/research')
    check('anon cannot view research list', r.status_code != 200, r.status_code)

    # A logged-in non-coach swimmer is forbidden.
    client.post('/login', data={'email': 'researchswimmer@test.com', 'password': 'test1234'},
                follow_redirects=True)
    r = client.get('/research')
    check('non-coach forbidden from research list', r.status_code == 403, r.status_code)
    r = client.get(f'/research/{brief_id}')
    check('non-coach forbidden from a brief', r.status_code == 403, r.status_code)
    client.get('/logout')

    # A coach sees the list and the brief.
    client.post('/login', data={'email': 'researchcoach@test.com', 'password': 'test1234'},
                follow_redirects=True)
    r = client.get('/research')
    check('coach sees research list', r.status_code == 200, r.status_code)
    check('list shows the brief title', b'Feb brief' in r.data)
    r = client.get(f'/research/{brief_id}')
    check('coach sees the brief', r.status_code == 200, r.status_code)
    check('brief renders a takeaway', b'Cue one.' in r.data)
    # A missing brief 404s rather than 500s.
    r = client.get('/research/99999')
    check('missing brief 404s', r.status_code == 404, r.status_code)


# ===========================================================================
# 11. Club event import: Squarespace source parsing, competition classifier,
#     and the idempotent auto-import route
# ===========================================================================

def _fake_squarespace_payload():
    """A canned Squarespace ?format=json body with a multi-day championship, a
    single-day meet, and two non-competition entries (AGM, awards)."""
    from zoneinfo import ZoneInfo
    tz = ZoneInfo('Pacific/Auckland')

    def ms(y, m, d):
        return int(datetime(y, m, d, 10, 0, tzinfo=tz).timestamp() * 1000)

    return {'upcoming': [
        {'id': 'a1', 'title': 'South Island Long Course Championships',
         'startDate': ms(2026, 3, 13), 'endDate': ms(2026, 3, 15),
         'location': {'addressTitle': 'Parakiore Rec. Centre'}, 'fullUrl': '/events/si-lc-champs'},
        {'id': 'a2', 'title': 'Temuka Best Time Meet',
         'startDate': ms(2026, 1, 10), 'endDate': None,
         'location': {'addressTitle': 'Temuka Pool'}, 'fullUrl': '/events/temuka'},
        {'id': 'a3', 'title': 'Annual General Meeting',
         'startDate': ms(2026, 8, 23), 'endDate': None,
         'location': {'addressTitle': 'Wharenui Sports Centre'}, 'fullUrl': '/events/agm'},
        {'id': 'a4', 'title': 'Annual Awards',
         'startDate': ms(2026, 11, 21), 'endDate': None,
         'location': {'addressTitle': 'Addington Raceway'}, 'fullUrl': '/events/awards'},
    ], 'past': []}


def test_event_source_parsing():
    import events_sources
    from events_sources import SquarespaceEventsSource
    from datetime import date

    orig = events_sources._http_get_json
    events_sources._http_get_json = lambda url: _fake_squarespace_payload()
    try:
        events = SquarespaceEventsSource().fetch()
    finally:
        events_sources._http_get_json = orig

    check('all upcoming events parsed', len(events) == 4, len(events))
    champs = next((e for e in events if e['title'].startswith('South Island')), None)
    check('external_id namespaced', champs and champs['external_id'] == 'scwc:a1', champs and champs['external_id'])
    check('start date converted to NZ local', champs and champs['start_date'] == date(2026, 3, 13),
          champs and champs['start_date'])
    check('multi-day end date kept', champs and champs['end_date'] == date(2026, 3, 15),
          champs and champs['end_date'])
    check('location extracted', champs and champs['location'] == 'Parakiore Rec. Centre')
    check('event url is absolute https', champs and champs['url'] == 'https://wearescwc.org/events/si-lc-champs',
          champs and champs['url'])

    # A record with no id/title/date is dropped.
    events_sources._http_get_json = lambda url: {'upcoming': [{'title': 'no id or date'}]}
    try:
        check('unusable record dropped', SquarespaceEventsSource().fetch() == [])
    finally:
        events_sources._http_get_json = orig


def test_event_classifier_heuristic():
    from ai_utils import classify_swim_events
    events = [
        {'title': 'South Island Long Course Championships'},
        {'title': 'Temuka Best Time Meet'},
        {'title': 'Annual General Meeting'},
        {'title': 'Annual Awards'},
        {'title': 'Junior Development Camp'},
    ]
    # api_key=None -> heuristic path (no network).
    verdicts = classify_swim_events(events, api_key=None, model=None)
    check('championship kept', verdicts[0] is True)
    check('best time meet kept', verdicts[1] is True)
    check('AGM excluded', verdicts[2] is False)
    check('awards excluded', verdicts[3] is False)
    check('camp excluded', verdicts[4] is False)


def test_event_import_route(app):
    """The import route is coach-gated, imports only competitions, and is
    idempotent (a second import adds nothing)."""
    from app import db
    import events_sources
    from models import User, Squad, SquadEvent
    from datetime import date

    with app.app_context():
        coach = _mk_user(db, User, 'evcoach@test.com')
        coach.role = 'coach'
        swimmer = _mk_user(db, User, 'evswimmer@test.com')
        db.session.commit()
        squad = _mk_squad(db, Squad, coach.id, name='Import Squad')
        squad_id = squad.id

    # AI off in tests -> classifier uses the heuristic; stub the network fetch.
    orig = events_sources._http_get_json
    events_sources._http_get_json = lambda url: _fake_squarespace_payload()
    try:
        client = app.test_client()

        # Non-coach is forbidden.
        client.post('/login', data={'email': 'evswimmer@test.com', 'password': 'test1234'},
                    follow_redirects=True)
        r = client.post(f'/coach/squad/{squad_id}/calendar/import-scwc')
        check('non-coach cannot import events', r.status_code == 403, r.status_code)
        client.get('/logout')

        # Coach imports: only the 2 competitions land, AGM + awards are skipped.
        client.post('/login', data={'email': 'evcoach@test.com', 'password': 'test1234'},
                    follow_redirects=True)
        r = client.post(f'/coach/squad/{squad_id}/calendar/import-scwc', follow_redirects=True)
        check('import request ok', r.status_code == 200, r.status_code)
        with app.app_context():
            rows = db.session.query(SquadEvent).filter_by(squad_id=squad_id).all()
            titles = sorted(e.title for e in rows)
            check('exactly 2 competitions imported', len(rows) == 2, titles)
            check('AGM not imported', all('General Meeting' not in t for t in titles), titles)
            check('awards not imported', all('Awards' not in t for t in titles), titles)
            champs = next((e for e in rows if e.title.startswith('South Island')), None)
            check('imported as a meet', champs and champs.event_type == 'meet')
            check('start date correct', champs and champs.event_date == date(2026, 3, 13),
                  champs and champs.event_date)
            check('multi-day range in notes', champs and '13' in (champs.notes or '') and 'Mar' in (champs.notes or ''),
                  champs and champs.notes)
            check('provenance in notes', champs and 'SCWC' in (champs.notes or ''))

        # Second import is idempotent -- no duplicates.
        client.post(f'/coach/squad/{squad_id}/calendar/import-scwc', follow_redirects=True)
        with app.app_context():
            check('re-import creates no duplicates',
                  db.session.query(SquadEvent).filter_by(squad_id=squad_id).count() == 2)
    finally:
        events_sources._http_get_json = orig


# ===========================================================================
# 15. Role isolation: a parent sees one swimmer, a swimmer sees only itself
# ===========================================================================

def test_role_isolation(app):
    """The promises on /privacy, /data-safety and /for/parents, as tests.

    Every claim we make publicly about who can see whose data is asserted
    here against the real HTTP layer, so the marketing copy cannot drift away
    from the code. Specifically:
      - a parent reaches only the swimmer(s) they are linked to, and asking
        for another swimmer's id does not widen that;
      - a revoked link cuts access immediately;
      - a swimmer cannot open the parent or coach areas at all;
      - the parent view never renders coach-private notes or status flags;
      - one swimmer's log is not reachable from another swimmer's account.
    """
    from app import db
    from models import (User, Swim, Squad, SquadMembership, ParentLink,
                        CoachNote, StatusFlag)
    import secrets as _secrets

    with app.app_context():
        coach = _mk_user(db, User, 'isocoach@test.com')
        coach.role = 'coach'
        mine = _mk_user(db, User, 'isomine@test.com')       # the linked swimmer
        theirs = _mk_user(db, User, 'isotheirs@test.com')   # someone else's kid
        parent = _mk_user(db, User, 'isoparent@test.com')
        parent.role = 'parent'
        db.session.commit()

        squad = _mk_squad(db, Squad, coach.id, name='Isolation Squad')
        _mk_membership(db, SquadMembership, squad.id, mine.id)
        _mk_membership(db, SquadMembership, squad.id, theirs.id)

        # Distinctive times so we can grep the rendered HTML for a leak.
        db.session.add(Swim(user_id=mine.id, event='100m Freestyle', pool='25m',
                            stroke='FR', time='59.11', logged_at=datetime.utcnow()))
        db.session.add(Swim(user_id=theirs.id, event='200m Butterfly', pool='50m',
                            stroke='FL', time='2:34.77', logged_at=datetime.utcnow()))

        # Coach-private material that must never reach the parent view.
        db.session.add(CoachNote(squad_id=squad.id, swimmer_id=mine.id, coach_id=coach.id,
                                 note='PRIVATECOACHNOTE do not show parents'))
        db.session.add(StatusFlag(squad_id=squad.id, swimmer_id=mine.id, updated_by=coach.id,
                                  status='injured', note='SECRETSTATUSFLAG shoulder'))

        link = ParentLink(swimmer_id=mine.id, parent_id=parent.id,
                          invite_token=_secrets.token_urlsafe(24), status='active',
                          claimed_at=datetime.utcnow())
        db.session.add(link)
        db.session.commit()
        mine_id, theirs_id, link_id, squad_id = mine.id, theirs.id, link.id, squad.id

    client = app.test_client()

    # --- the parent ---
    client.post('/login', data={'email': 'isoparent@test.com', 'password': 'test1234'},
                follow_redirects=True)

    r = client.get('/parent/dashboard')
    body = r.get_data(as_text=True)
    check('parent dashboard loads', r.status_code == 200, r.status_code)
    check('parent sees their own swimmer\'s time', '59.11' in body)
    check('parent does NOT see another swimmer\'s time', '2:34.77' not in body)
    check('parent does NOT see the coach\'s private note', 'PRIVATECOACHNOTE' not in body)
    check('parent does NOT see the status flag', 'SECRETSTATUSFLAG' not in body)

    # Asking for a swimmer they aren't linked to must not widen access: the
    # dashboard resolves from the parent's OWN links, so an unknown id falls
    # back to a swimmer they are already entitled to see.
    r = client.get(f'/parent/dashboard?swimmer={theirs_id}')
    body = r.get_data(as_text=True)
    check('IDOR: parent asking for another swimmer gets no new data',
          '2:34.77' not in body, 'other swimmer leaked')
    check('IDOR: parent falls back to their own swimmer', '59.11' in body)

    # A parent must not be able to reach the coach side at all.
    for path in ('/coach/', f'/coach/squad/{squad_id}'):
        r = client.get(path)
        check(f'parent blocked from {path}', r.status_code in (302, 403, 404), r.status_code)

    # --- revocation cuts access immediately ---
    with app.app_context():
        db.session.get(ParentLink, link_id).status = 'revoked'
        db.session.commit()
    r = client.get('/parent/dashboard')
    check('revoked link: parent no longer sees the swimmer\'s time',
          '59.11' not in r.get_data(as_text=True))
    with app.app_context():
        db.session.get(ParentLink, link_id).status = 'active'
        db.session.commit()
    client.get('/logout')

    # --- the swimmer ---
    client.post('/login', data={'email': 'isomine@test.com', 'password': 'test1234'},
                follow_redirects=True)

    r = client.get('/parent/dashboard')
    check('swimmer blocked from the parent dashboard', r.status_code in (302, 403), r.status_code)
    r = client.get('/coach/')
    check('swimmer blocked from the coach dashboard', r.status_code in (302, 403), r.status_code)

    # A swimmer's own pages must not surface another swimmer's swims.
    for path in ('/dashboard', '/history', '/personal-bests'):
        r = client.get(path, follow_redirects=True)
        check(f'{path} does not leak another swimmer\'s time',
              '2:34.77' not in r.get_data(as_text=True), path)

    # A swimmer cannot revoke a parent link that isn't theirs.
    with app.app_context():
        other_link = ParentLink(swimmer_id=theirs_id, invite_token=_secrets.token_urlsafe(24),
                                status='pending')
        db.session.add(other_link)
        db.session.commit()
        other_link_id = other_link.id
    client.post(f'/parent/invite/{other_link_id}/revoke', follow_redirects=True)
    with app.app_context():
        check('swimmer cannot revoke another swimmer\'s parent link',
              db.session.get(ParentLink, other_link_id).status == 'pending',
              db.session.get(ParentLink, other_link_id).status)
    client.get('/logout')

    # --- an unauthenticated visitor gets nothing ---
    anon = app.test_client()
    for path in ('/parent/dashboard', '/coach/', '/dashboard'):
        r = anon.get(path)
        check(f'anonymous blocked from {path}', r.status_code in (302, 401, 403), r.status_code)


# ===========================================================================
# 16. Public pages: every marketing/legal route renders and links resolve
# ===========================================================================

def test_public_pages(app):
    from marketing_content import FEATURES, AUDIENCES, FOOTER_LINKS

    client = app.test_client()

    static_paths = ['/', '/privacy', '/terms', '/cookies', '/data-safety', '/faq',
                    '/login', '/login/coach', '/login/parent', '/signup']
    for path in static_paths:
        r = client.get(path)
        check(f'{path} renders', r.status_code == 200, r.status_code)

    for slug in FEATURES:
        r = client.get(f'/features/{slug}')
        check(f'/features/{slug} renders', r.status_code == 200, r.status_code)
    for who in AUDIENCES:
        r = client.get(f'/for/{who}')
        check(f'/for/{who} renders', r.status_code == 200, r.status_code)

    check('unknown feature slug 404s', client.get('/features/not-a-thing').status_code == 404)
    check('unknown audience 404s', client.get('/for/nobody').status_code == 404)

    # Every footer link must resolve -- a legal page nobody can reach is worse
    # than no legal page, because it looks like one exists.
    for label, href in FOOTER_LINKS:
        check(f'footer link {label} resolves', client.get(href).status_code == 200, href)

    # The landing page must offer the explainers, not just the signup form.
    home = client.get('/').get_data(as_text=True)
    check('landing links to the coach page', '/for/coaches' in home)
    check('landing links to the parent page', '/for/parents' in home)
    check('landing links to a feature deep-dive', '/features/session-builder' in home)
    check('landing no longer shows the hero pill', 'hero-pill' not in home)
    check('landing carries the cookie notice', 'cookiebar' in home)
    check('landing links to terms', '/terms' in home)

    # Parents must be told they cannot self-serve a signup.
    signup = client.get('/signup').get_data(as_text=True)
    check('signup explains the parent route', 'parent link' in signup.lower())

    # The three login doors are cosmetic: all three post to the same endpoint.
    for path in ('/login', '/login/coach', '/login/parent'):
        body = client.get(path).get_data(as_text=True)
        check(f'{path} posts to /login', 'action="/login"' in body, path)


# ===========================================================================

def main():
    print('Building test app (throwaway DB)...')
    from app import create_app
    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    app.config['ANTHROPIC_API_KEY'] = None
    app.config['AI_SCAN_ENABLED'] = False

    suites = [
        ('Time parsing', test_parse_time, False),
        ('Interval vs rest logic', test_interval_logic, False),
        ('Volume caps + program validation', test_volume_caps, False),
        ('Progression engine', test_progression, False),
        ('Input validation', test_validation, False),
        ('Athlete model + weekly reports', test_athlete_model, True),
        ('Training plans (CSS + generator)', test_training_plan, True),
        ('Coach routes (IDOR + PB pool-conflation)', test_coach_routes, True),
        ('Admin routes (CSS/swimmer-type panels, access control)', test_admin_routes, True),
        ('HTTP layer', test_http, True),
        ('Research sources (URL/SSRF hardening)', test_research_sources, False),
        ('Research scout filtering', test_research_scout_filter, False),
        ('Research pipeline (idempotency)', test_research_pipeline, True),
        ('Research routes (coach-gated)', test_research_routes, True),
        ('Event source parsing (Squarespace)', test_event_source_parsing, False),
        ('Event classifier (heuristic)', test_event_classifier_heuristic, False),
        ('Event import route (idempotent)', test_event_import_route, True),
        ('Role isolation (parent/swimmer/coach)', test_role_isolation, True),
        ('Public marketing + legal pages', test_public_pages, True),
    ]
    for name, fn, needs_app in suites:
        print(f'\n== {name} ==')
        try:
            fn(app) if needs_app else fn()
        except Exception:
            global FAIL
            FAIL += 1
            FAILURES.append(f'{name} crashed:\n{traceback.format_exc()}')
            print(f'  SUITE CRASHED: {name}')
            traceback.print_exc()

    print(f'\n{"=" * 50}\n{PASS} passed, {FAIL} failed')
    if FAILURES:
        print('\nFailures:')
        for f in FAILURES:
            print(f'  - {f}')
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
