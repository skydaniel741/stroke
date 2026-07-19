"""The named-workout library the training-plan generator composes from.

Templates are code, not DB rows (precedent: nutrition_data.py). Each template
stores ZONE placeholders instead of times -- plan_logic.resolve_template turns
them into real target times and send-offs from the swimmer's CSS, producing
blocks in the exact SavedSet.sets_data shape the rest of the app understands.

Block keys:
  section   'Warm up' / 'Pre set' / 'Main set' / 'Sub set' / 'Cool down'
  reps/dist/stroke/modifier  as everywhere else in the app
  zone      recovery / endurance / tempo / threshold / vo2max (drives pace)
  max_effort  True for time-trial reps (no target pace -- swim it flat out)
  rest_mode 'interval' (send-off, the default for repeat sets) or 'rest'
            (fixed gap: continuous swims, drill work, trial recovery)
  rest_fixed  explicit rest seconds when rest_mode == 'rest' (else derived)
  note      coach guidance, target time appended at resolve time

Template keys:
  key / name / slot / phases / min_level / description / blocks
  scale_block_indexes  which blocks' reps grow or shrink to hit the session's
                       target meters (never warm up / cool down)

Slots: technique / threshold / sprint / endurance / css_test -- these map to
the fixed weekly rhythm (Runna model: same slots every week, contents rotate).
"""

LEVEL_ORDER = ['Beginner', 'Intermediate', 'Advanced', 'Competitive']


def _wu(dist=400):
    return {'section': 'Warm up', 'reps': 1, 'dist': dist, 'stroke': 'FR', 'modifier': '',
            'zone': 'recovery', 'rest_mode': 'rest', 'rest_fixed': 30, 'note': 'easy, loosen out'}


def _cd(dist=200):
    return {'section': 'Cool down', 'reps': 1, 'dist': dist, 'stroke': 'FR', 'modifier': '',
            'zone': 'recovery', 'rest_mode': 'rest', 'rest_fixed': 0, 'note': 'very easy swim down'}


TEMPLATES = [
    # ------------------------------------------------------------------
    # THRESHOLD (CSS) -- the plan's quality backbone
    # ------------------------------------------------------------------
    {
        'key': 'css_100s_straight', 'name': 'CSS 100s', 'slot': 'threshold',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': 'Straight 100s right on CSS pace with a short send-off. The bread-and-butter threshold set.',
        'blocks': [
            _wu(),
            {'section': 'Pre set', 'reps': 4, 'dist': 50, 'stroke': 'FR', 'modifier': 'Drill',
             'zone': 'recovery', 'note': 'drill of choice, focus on length'},
            {'section': 'Main set', 'reps': 8, 'dist': 100, 'stroke': 'FR', 'modifier': '',
             'zone': 'threshold', 'note': 'hold CSS pace, even effort'},
            _cd(),
        ],
        'scale_block_indexes': [2],
    },
    {
        'key': 'over_unders_100s', 'name': 'Over and Unders', 'slot': 'threshold',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': 'Alternating 100s just over and just under CSS. Teaches the body to clear lactate at pace.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 5, 'dist': 100, 'stroke': 'FR', 'modifier': '',
             'zone': 'tempo', 'note': 'ODD reps: just slower than CSS'},
            {'section': 'Main set', 'reps': 5, 'dist': 100, 'stroke': 'FR', 'modifier': '',
             'zone': 'vo2max', 'note': 'EVEN reps: just faster than CSS'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'broken_200s', 'name': 'Broken 200s', 'slot': 'threshold',
        'phases': ('build',), 'min_level': 'Intermediate',
        'description': '200s at CSS with a tight turnaround. Long enough to hurt, short enough to hold form.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 5, 'dist': 200, 'stroke': 'FR', 'modifier': '',
             'zone': 'threshold', 'note': 'hold CSS, no fade on the back 100'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'threshold_ladder_down', 'name': 'Cut Down Ladder', 'slot': 'threshold',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': '400-300-200-100 at CSS. The reps get shorter, the pace stays honest.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 1, 'dist': 400, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': 'settle into CSS rhythm'},
            {'section': 'Main set', 'reps': 1, 'dist': 300, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': 'same pace, sharper focus'},
            {'section': 'Main set', 'reps': 1, 'dist': 200, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': 'hold it'},
            {'section': 'Main set', 'reps': 2, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': 'finish strong at CSS'},
            _cd(),
        ],
        'scale_block_indexes': [4],
    },
    {
        'key': 'tight_50s', 'name': '50s on a Tight Turnaround', 'slot': 'threshold',
        'phases': ('base', 'build', 'taper'), 'min_level': 'Beginner',
        'description': 'Lots of 50s at CSS with minimal rest. Threshold work disguised as a sprint set.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 16, 'dist': 50, 'stroke': 'FR', 'modifier': '',
             'zone': 'threshold', 'note': 'hold CSS pace every rep, short rest'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'two_rounds_100s', 'name': 'Two Rounds of 100s', 'slot': 'threshold',
        'phases': ('build',), 'min_level': 'Intermediate',
        'description': '2 rounds of 6x100 at CSS with an easy 100 between rounds. Volume at pace.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 6, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold',
             'round_reps': 2, 'note': '2 rounds; easy 100 between rounds'},
            {'section': 'Sub set', 'reps': 1, 'dist': 100, 'stroke': 'FR', 'modifier': '',
             'zone': 'recovery', 'rest_mode': 'rest', 'rest_fixed': 20, 'note': 'easy between rounds'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'descend_300s', 'name': 'Descending 300s', 'slot': 'threshold',
        'phases': ('base', 'build'), 'min_level': 'Advanced',
        'description': '3x300 descending: endurance pace, tempo, then right on CSS. Pace control under fatigue.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 1, 'dist': 300, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': '1 of 3: controlled'},
            {'section': 'Main set', 'reps': 1, 'dist': 300, 'stroke': 'FR', 'modifier': '', 'zone': 'tempo', 'note': '2 of 3: comfortably hard'},
            {'section': 'Main set', 'reps': 1, 'dist': 300, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': '3 of 3: on CSS'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2, 3],
    },
    {
        'key': 'negative_split_200s', 'name': 'Negative Split 200s', 'slot': 'threshold',
        'phases': ('build',), 'min_level': 'Advanced',
        'description': '200s where the second 100 must be the faster one. Back-half discipline.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 4, 'dist': 200, 'stroke': 'FR', 'modifier': '',
             'zone': 'threshold', 'note': 'second 100 faster than the first, average CSS'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'broken_400s', 'name': 'Broken 400s', 'slot': 'threshold',
        'phases': ('build',), 'min_level': 'Advanced',
        'description': '400s at CSS broken only by the send-off clock. Race-length threshold repeats.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 3, 'dist': 400, 'stroke': 'FR', 'modifier': '',
             'zone': 'threshold', 'note': 'even pace, think 100 at a time'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'threshold_150s', 'name': 'Threshold 150s', 'slot': 'threshold',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': '150s at CSS -- the awkward distance that keeps you honest between the 100 and the 200.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 6, 'dist': 150, 'stroke': 'FR', 'modifier': '',
             'zone': 'threshold', 'note': 'hold CSS through the third 50'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },

    # ------------------------------------------------------------------
    # SPRINT / RACE PACE
    # ------------------------------------------------------------------
    {
        'key': 'sprint_pyramid', 'name': 'Sprint Pyramid', 'slot': 'sprint',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': '25-50-75-50-25 fast with full recovery. Speed without the sting of long reps.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 2, 'dist': 25, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max', 'note': 'fast, long walls'},
            {'section': 'Main set', 'reps': 2, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max', 'note': 'build to max'},
            {'section': 'Main set', 'reps': 2, 'dist': 75, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max', 'note': 'hold speed to the end'},
            {'section': 'Main set', 'reps': 2, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max', 'note': 'back down, stay sharp'},
            {'section': 'Main set', 'reps': 2, 'dist': 25, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max', 'note': 'fastest of the day'},
            _cd(),
        ],
        'scale_block_indexes': [2, 4],
    },
    {
        'key': 'race_pace_25s', 'name': 'Race Pace 25s', 'slot': 'sprint',
        'phases': ('build', 'taper'), 'min_level': 'Intermediate',
        'description': 'USRPT-style 25s at goal race pace with short rest. Teach the body exactly one speed: race speed.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 16, 'dist': 25, 'stroke': 'FR', 'modifier': '',
             'zone': 'vo2max', 'note': 'hit your race-pace split every rep; miss two in a row, stop the set'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'max_50s', 'name': 'Max Effort 50s', 'slot': 'sprint',
        'phases': ('build', 'taper'), 'min_level': 'Beginner',
        'description': 'A handful of genuinely all-out 50s with lots of rest. Quality over quantity.',
        'blocks': [
            _wu(),
            {'section': 'Pre set', 'reps': 4, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': 'build each 50'},
            {'section': 'Main set', 'reps': 6, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max',
             'rest_mode': 'rest', 'rest_fixed': 60, 'note': 'ALL OUT, full recovery between'},
            _cd(),
        ],
        'scale_block_indexes': [2],
    },
    {
        'key': 'broken_race_sim', 'name': 'Broken Race Simulation', 'slot': 'sprint',
        'phases': ('build', 'taper'), 'min_level': 'Intermediate',
        'description': 'Your race, chopped into 50s with 10s rest. Adds up to the full distance at target speed.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 4, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max',
             'rest_mode': 'rest', 'rest_fixed': 10, 'round_reps': 2,
             'note': 'race pace; 10s only between 50s, easy 200 between rounds'},
            {'section': 'Sub set', 'reps': 1, 'dist': 200, 'stroke': 'FR', 'modifier': '',
             'zone': 'recovery', 'rest_mode': 'rest', 'rest_fixed': 60, 'note': 'easy between rounds'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'speed_ladder', 'name': 'Speed Ladder', 'slot': 'sprint',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': '25s, 50s, 75s in rounds, each rep faster than the last. Turnover and rhythm work.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 4, 'dist': 25, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max', 'note': 'descend 1-4'},
            {'section': 'Main set', 'reps': 4, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max', 'note': 'descend 1-4'},
            {'section': 'Main set', 'reps': 2, 'dist': 75, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max', 'note': 'both fast'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'stroke_sprint_25s', 'name': 'Stroke Sprint 25s', 'slot': 'sprint',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': 'Fast 25s alternating your stroke and freestyle. Speed that transfers to your race.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 8, 'dist': 25, 'stroke': 'IM', 'modifier': '', 'zone': 'vo2max',
             'note': 'odds: your stroke fast; evens: free fast'},
            {'section': 'Main set', 'reps': 8, 'dist': 25, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max',
             'note': 'all free, best turnover'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'power_kick_sprints', 'name': 'Power Kick Sprints', 'slot': 'sprint',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': 'Fast kick 25s plus sprint swim 25s. Legs first, then put it together.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 8, 'dist': 25, 'stroke': 'FR', 'modifier': 'Kick', 'zone': 'vo2max',
             'note': 'max effort kick, board optional'},
            {'section': 'Main set', 'reps': 8, 'dist': 25, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max',
             'note': 'sprint swim, carry the leg drive'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'build_75s', 'name': '75s Build to Max', 'slot': 'sprint',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': '75s that start controlled and end flat out. Practice shifting gears mid-rep.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 8, 'dist': 75, 'stroke': 'FR', 'modifier': '', 'zone': 'tempo',
             'note': '25 smooth, 25 strong, 25 sprint'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'lactate_100s', 'name': 'Lactate 100s', 'slot': 'sprint',
        'phases': ('build',), 'min_level': 'Advanced',
        'description': 'A few brutal all-out 100s with huge rest. Maximum speed endurance stimulus.',
        'blocks': [
            _wu(500),
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max',
             'rest_mode': 'rest', 'rest_fixed': 180, 'note': 'ALL OUT; walk the wall, shake out, full reset'},
            _cd(300),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'fifteens_speed', 'name': 'First 15s Fast', 'slot': 'sprint',
        'phases': ('build', 'taper'), 'min_level': 'Beginner',
        'description': '25s where only the first 15m is max effort, easy to the wall. Pure speed, low cost -- taper friendly.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 12, 'dist': 25, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max',
             'rest_mode': 'rest', 'rest_fixed': 30, 'note': 'explode off the wall, max 15m, cruise in'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },

    # ------------------------------------------------------------------
    # ENDURANCE / LONG AEROBIC
    # ------------------------------------------------------------------
    {
        'key': 'pyramid_100_300', 'name': 'Pyramid', 'slot': 'endurance',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': '100-200-300-200-100 at endurance pace. A classic aerobic ladder up and back down.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 1, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': 'find your rhythm'},
            {'section': 'Main set', 'reps': 1, 'dist': 200, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': 'settle in'},
            {'section': 'Main set', 'reps': 1, 'dist': 300, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': 'the top: hold form'},
            {'section': 'Main set', 'reps': 1, 'dist': 200, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': 'coming down, same pace'},
            {'section': 'Main set', 'reps': 1, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': 'finish smooth'},
            _cd(),
        ],
        'scale_block_indexes': [2, 4],
    },
    {
        'key': 'steady_400s', 'name': 'Steady 400s', 'slot': 'endurance',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': 'Long reps at endurance pace. Time in the water at an honest aerobic effort.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 3, 'dist': 400, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'even pace, count your strokes per length'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'broken_800', 'name': 'Broken 800', 'slot': 'endurance',
        'phases': ('build',), 'min_level': 'Advanced',
        'description': '800 broken into 200s on a short turnaround. Distance-swim rhythm without the monotony.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 4, 'dist': 200, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'round_reps': 2, 'note': '2 rounds of a broken 800; think of each round as one swim'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'distance_ladder_up', 'name': 'Ladder Up', 'slot': 'endurance',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': '50-100-150-200 climbing ladder at endurance pace, repeated. Progressive without being punishing.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 1, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'round_reps': 2, 'note': 'rounds of 50-100-150-200'},
            {'section': 'Main set', 'reps': 1, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'round_reps': 2, 'note': ''},
            {'section': 'Main set', 'reps': 1, 'dist': 150, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'round_reps': 2, 'note': ''},
            {'section': 'Main set', 'reps': 1, 'dist': 200, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'round_reps': 2, 'note': 'strongest at the top'},
            _cd(),
        ],
        'scale_block_indexes': [3, 4],
    },
    {
        'key': 'steady_500s', 'name': '500s Steady', 'slot': 'endurance',
        'phases': ('base', 'build'), 'min_level': 'Advanced',
        'description': 'Long 500s at endurance pace. The long run of swimming.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 3, 'dist': 500, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'relaxed breathing pattern, even splits'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'mixed_stroke_aerobic', 'name': 'Mixed Stroke 100s', 'slot': 'endurance',
        'phases': ('base',), 'min_level': 'Beginner',
        'description': 'Aerobic 100s rotating strokes. Balanced fitness and a break from black-line freestyle.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': 'free, smooth'},
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'IM', 'modifier': '', 'zone': 'endurance', 'note': 'IM or stroke of choice'},
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': 'free, finish smooth'},
            _cd(),
        ],
        'scale_block_indexes': [1, 3],
    },
    {
        'key': 'pull_300s', 'name': 'Pull 300s', 'slot': 'endurance',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': '300s with a pull buoy at endurance pace. Upper-body aerobic work and body position.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 4, 'dist': 300, 'stroke': 'FR', 'modifier': 'Pull', 'zone': 'endurance',
             'note': 'long strokes, steady breathing every 3 or 5'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'endurance_200s', 'name': 'Endurance 200s', 'slot': 'endurance',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': '200s at endurance pace with a comfortable send-off. Aerobic volume, honest but sustainable.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 6, 'dist': 200, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'same time every rep; boring is the goal'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'continuous_build_600', 'name': 'Continuous Build 600s', 'slot': 'endurance',
        'phases': ('build',), 'min_level': 'Intermediate',
        'description': '600s swum as 200 smooth / 200 steady / 200 strong. A progressive long swim, Runna-style.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 2, 'dist': 600, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'rest_mode': 'rest', 'rest_fixed': 60,
             'note': 'each 600: first 200 easy, middle 200 endurance, last 200 tempo'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'aerobic_50s_volume', 'name': 'Aerobic 50s', 'slot': 'endurance',
        'phases': ('base',), 'min_level': 'Beginner',
        'description': 'A big pile of easy-rhythm 50s. Low-pressure volume for base building.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 20, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'metronome swimming: identical splits'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },

    # ------------------------------------------------------------------
    # TECHNIQUE / EASY
    # ------------------------------------------------------------------
    {
        'key': 'drill_swim_50s', 'name': 'Drill-Swim 50s', 'slot': 'technique',
        'phases': ('base', 'build', 'taper'), 'min_level': 'Beginner',
        'description': '50s alternating drill and swim. The classic technique staple.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 8, 'dist': 50, 'stroke': 'FR', 'modifier': 'Drill', 'zone': 'recovery',
             'note': 'odds: drill of choice (catch-up, single arm, fist)'},
            {'section': 'Main set', 'reps': 8, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'evens: swim, apply the drill feeling'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'kick_drill_swim_rounds', 'name': 'Kick-Drill-Swim Rounds', 'slot': 'technique',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': 'Rounds of kick, drill, then swim. Builds each stroke from the legs up.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 2, 'dist': 50, 'stroke': 'FR', 'modifier': 'Kick', 'zone': 'recovery', 'round_reps': 3, 'note': '3 rounds: kick with purpose'},
            {'section': 'Main set', 'reps': 2, 'dist': 50, 'stroke': 'FR', 'modifier': 'Drill', 'zone': 'recovery', 'round_reps': 3, 'note': 'drill slow and exact'},
            {'section': 'Main set', 'reps': 2, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'round_reps': 3, 'note': 'swim: put it together'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2, 3],
    },
    {
        'key': 'stroke_count_50s', 'name': 'Stroke Count 50s', 'slot': 'technique',
        'phases': ('base', 'build', 'taper'), 'min_level': 'Intermediate',
        'description': '50s holding your lowest comfortable stroke count. Distance per stroke over speed.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 12, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'count strokes per length; hold your best number, not your fastest time'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'snorkel_alignment', 'name': 'Snorkel Alignment Set', 'slot': 'technique',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': 'Snorkel 100s focused on head position and a symmetrical catch. No breathing distraction.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 6, 'dist': 100, 'stroke': 'FR', 'modifier': 'Snorkel', 'zone': 'endurance',
             'note': 'head still, hips high, even catch both sides'},
            {'section': 'Main set', 'reps': 4, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'no snorkel: keep the alignment'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'fins_technique_100s', 'name': 'Fins Technique 100s', 'slot': 'technique',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': '100s with fins at an easy pace. The extra speed lets you feel a better body position.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 8, 'dist': 100, 'stroke': 'FR', 'modifier': 'Drill', 'zone': 'recovery',
             'note': 'fins on: 25 drill / 75 swim, exaggerate the glide'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'scull_and_swim', 'name': 'Scull and Swim', 'slot': 'technique',
        'phases': ('base',), 'min_level': 'Intermediate',
        'description': 'Sculling 25s paired with swim 75s. Feel for the water, then use it.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 6, 'dist': 25, 'stroke': 'FR', 'modifier': 'Drill', 'zone': 'recovery',
             'rest_mode': 'rest', 'rest_fixed': 15, 'note': 'scull: front, mid, rear -- rotate'},
            {'section': 'Main set', 'reps': 6, 'dist': 75, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'swim: feel the pressure you just built'},
            _cd(),
        ],
        'scale_block_indexes': [2],
    },
    {
        'key': 'easy_recovery_mix', 'name': 'Recovery Mix', 'slot': 'technique',
        'phases': ('base', 'build', 'taper'), 'min_level': 'Beginner',
        'description': 'A genuinely easy session: mixed strokes, drills, no clock-watching. Absorb the week.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 6, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'recovery',
             'note': 'mix strokes freely, everything silky'},
            {'section': 'Main set', 'reps': 6, 'dist': 50, 'stroke': 'FR', 'modifier': 'Drill', 'zone': 'recovery',
             'note': 'favourite drills, zero effort'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'im_transition_drills', 'name': 'IM Transition Set', 'slot': 'technique',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': '75s across the IM transitions (fly-back, back-breast, breast-free). Turns and switches.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 9, 'dist': 75, 'stroke': 'IM', 'modifier': '', 'zone': 'endurance',
             'note': 'rotate: fly-back-back / back-breast-breast / breast-free-free'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'catch_up_freestyle', 'name': 'Catch-Up Freestyle Set', 'slot': 'technique',
        'phases': ('base', 'build', 'taper'), 'min_level': 'Beginner',
        'description': 'Catch-up drill 50s into smooth swim 100s. Front-quadrant timing.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 6, 'dist': 50, 'stroke': 'FR', 'modifier': 'Drill', 'zone': 'recovery',
             'note': 'catch-up: hands meet out front every stroke'},
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'swim: keep the long front end'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },

    # ------------------------------------------------------------------
    # THRESHOLD -- second wave
    # ------------------------------------------------------------------
    {
        'key': 'css_75s', 'name': 'CSS 75s', 'slot': 'threshold',
        'phases': ('base', 'build', 'taper'), 'min_level': 'Beginner',
        'description': '75s at CSS pace. Shorter than the classic 100s, so the pace stays honest longer.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 10, 'dist': 75, 'stroke': 'FR', 'modifier': '',
             'zone': 'threshold', 'note': 'hold CSS pace, strong walls'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'alternating_100_50', 'name': '100s and 50s', 'slot': 'threshold',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': 'Alternating 100 at CSS and 50 at tempo. The 50 keeps you moving between efforts.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 5, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': 'odd swims: on CSS'},
            {'section': 'Main set', 'reps': 5, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'tempo', 'note': 'even swims: smooth tempo'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'threshold_pyramid', 'name': 'Threshold Pyramid', 'slot': 'threshold',
        'phases': ('build',), 'min_level': 'Intermediate',
        'description': '50-100-150-200-150-100-50, all at CSS. The climb tests pacing, the descent tests grit.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 1, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': 'settle in'},
            {'section': 'Main set', 'reps': 1, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': ''},
            {'section': 'Main set', 'reps': 1, 'dist': 150, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': ''},
            {'section': 'Main set', 'reps': 1, 'dist': 200, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': 'the top: same pace'},
            {'section': 'Main set', 'reps': 1, 'dist': 150, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': ''},
            {'section': 'Main set', 'reps': 1, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': ''},
            {'section': 'Main set', 'reps': 2, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': 'finish sharp'},
            _cd(),
        ],
        'scale_block_indexes': [7],
    },
    {
        'key': 'css_stroke_100s', 'name': 'Stroke Threshold 100s', 'slot': 'threshold',
        'phases': ('build',), 'min_level': 'Intermediate',
        'description': '100s of your best stroke at threshold effort, sandwiched by freestyle at CSS.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': 'free on CSS'},
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'IM', 'modifier': '', 'zone': 'threshold', 'note': 'your stroke or IM, matched effort'},
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': 'free again, hold the pace'},
            _cd(),
        ],
        'scale_block_indexes': [1, 3],
    },
    {
        'key': 'locomotive_400', 'name': 'Locomotive', 'slot': 'threshold',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': '100s alternating tempo and threshold in an unbroken chain. Gear changes without rest.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 6, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'tempo', 'note': 'odds: strong tempo'},
            {'section': 'Main set', 'reps': 6, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': 'evens: on CSS, no let-up'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'css_200_100_50', 'name': '200-100-50 Rounds', 'slot': 'threshold',
        'phases': ('build',), 'min_level': 'Intermediate',
        'description': 'Rounds of 200-100-50 at CSS with the 50 fastest. Finishing speed on tired arms.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 1, 'dist': 200, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'round_reps': 3, 'note': '3 rounds: 200 on CSS'},
            {'section': 'Main set', 'reps': 1, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'round_reps': 3, 'note': '100 on CSS'},
            {'section': 'Main set', 'reps': 1, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max', 'round_reps': 3, 'note': '50 faster than CSS'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'pull_threshold_200s', 'name': 'Pull Threshold 200s', 'slot': 'threshold',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': '200s with a buoy at threshold effort. Big aerobic upper-body work, hips high.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 4, 'dist': 200, 'stroke': 'FR', 'modifier': 'Pull', 'zone': 'threshold', 'note': 'long strokes, hold the effort'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'css_broken_100s', 'name': 'Broken 100s (50+50)', 'slot': 'threshold',
        'phases': ('build', 'taper'), 'min_level': 'Beginner',
        'description': '100s split into 50+50 with 5 seconds at the wall. Faster than straight 100s -- confidence at pace.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 12, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold',
             'note': 'pairs make a broken 100: 5s at the wall mid-way, hold CSS or better'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'css_ladder_up_down', 'name': 'Up the Ladder, Down the Pace', 'slot': 'threshold',
        'phases': ('build',), 'min_level': 'Advanced',
        'description': '100-200-300 with pace tightening as the reps get longer. Backwards on purpose.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 1, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'round_reps': 2, 'note': '2 rounds: 100 relaxed'},
            {'section': 'Main set', 'reps': 1, 'dist': 200, 'stroke': 'FR', 'modifier': '', 'zone': 'tempo', 'round_reps': 2, 'note': '200 at tempo'},
            {'section': 'Main set', 'reps': 1, 'dist': 300, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'round_reps': 2, 'note': '300 on CSS -- the hard one'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'css_50s_100s_50s', 'name': 'Sandwich Set', 'slot': 'threshold',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': '50s at CSS around a middle block of 100s. Same pace, different pressure.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 6, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': 'find CSS rhythm'},
            {'section': 'Main set', 'reps': 5, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': 'hold it for double the distance'},
            {'section': 'Main set', 'reps': 6, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'note': 'back to 50s -- should feel quick now'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2, 3],
    },
    {
        'key': 'im_threshold_100s', 'name': 'IM Threshold 100s', 'slot': 'threshold',
        'phases': ('build',), 'min_level': 'Advanced',
        'description': '100 IMs at threshold effort with freestyle 100s to reset between blocks.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'IM', 'modifier': '', 'zone': 'threshold', 'note': 'IM order, no coasting the back half'},
            {'section': 'Main set', 'reps': 2, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': 'free, reset the breathing'},
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'IM', 'modifier': '', 'zone': 'threshold', 'note': 'second block, match the first'},
            _cd(),
        ],
        'scale_block_indexes': [1, 3],
    },
    {
        'key': 'best_average_100s', 'name': 'Best Average 100s', 'slot': 'threshold',
        'phases': ('build',), 'min_level': 'Intermediate',
        'description': 'Classic best-average: every 100 as fast as you can repeat, judged on the slowest.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 8, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold',
             'note': 'best average -- your score is your SLOWEST rep, so pace like it matters'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'css_descend_100s', 'name': 'Descend by Fours', 'slot': 'threshold',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': '100s in sets of four, descending 1-4 to CSS. Teaches what each gear feels like.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'tempo', 'round_reps': 3,
             'note': '3 rounds of 4: descend 1-4, last one at CSS or quicker'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'kick_threshold_mix', 'name': 'Kick-Into-Swim Threshold', 'slot': 'threshold',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': 'Hard kick 50s straight into threshold swim 100s. Teaches the legs to work tired.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 2, 'dist': 50, 'stroke': 'FR', 'modifier': 'Kick', 'zone': 'tempo', 'round_reps': 4, 'note': '4 rounds: 2x50 strong kick'},
            {'section': 'Main set', 'reps': 2, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold', 'round_reps': 4, 'note': 'straight into 2x100 on CSS'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'steady_state_20min', 'name': 'Steady State Blocks', 'slot': 'threshold',
        'phases': ('base',), 'min_level': 'Intermediate',
        'description': 'Long unbroken swims just under CSS. The engine-room set: sustained, controlled, honest.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 2, 'dist': 800, 'stroke': 'FR', 'modifier': '', 'zone': 'tempo',
             'rest_mode': 'rest', 'rest_fixed': 60, 'note': 'continuous, a touch under CSS, minimal rest between'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'over_unders_200s', 'name': 'Over-Under 200s', 'slot': 'threshold',
        'phases': ('build',), 'min_level': 'Advanced',
        'description': '200s alternating tempo and vo2max halves inside the rep. Lactate shuttling at race length.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 5, 'dist': 200, 'stroke': 'FR', 'modifier': '', 'zone': 'threshold',
             'note': 'each 200: first 100 just over CSS, second 100 just under -- average CSS'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'hypoxic_threshold', 'name': 'Breathing Ladder 100s', 'slot': 'threshold',
        'phases': ('base', 'build'), 'min_level': 'Advanced',
        'description': '100s at tempo with a climbing breathing pattern (3-5-7 by 25). Control under load.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 9, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'tempo',
             'note': 'breathe every 3 / 5 / 7 / free choice by 25; never sacrifice stroke length'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },

    # ------------------------------------------------------------------
    # SPRINT / RACE PACE -- second wave
    # ------------------------------------------------------------------
    {
        'key': 'flying_25s', 'name': 'Flying 25s', 'slot': 'sprint',
        'phases': ('build', 'taper'), 'min_level': 'Beginner',
        'description': '25s with a running start off a push -- pure top-end speed with full recovery.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 10, 'dist': 25, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max',
             'rest_mode': 'rest', 'rest_fixed': 45, 'note': 'build into the flags, then FLY the 25'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'race_pace_50s', 'name': 'Race Pace 50s', 'slot': 'sprint',
        'phases': ('build', 'taper'), 'min_level': 'Intermediate',
        'description': '50s at your goal race split with generous rest. The set that makes goal pace familiar.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 10, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max',
             'rest_mode': 'rest', 'rest_fixed': 40, 'note': 'hit your goal race split every rep -- stop the set if you miss two'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'sprint_stroke_50s', 'name': 'Stroke Sprint 50s', 'slot': 'sprint',
        'phases': ('build',), 'min_level': 'Intermediate',
        'description': 'Fast 50s of your race stroke with full recovery. Speed in the stroke you race.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 8, 'dist': 50, 'stroke': 'IM', 'modifier': '', 'zone': 'vo2max',
             'rest_mode': 'rest', 'rest_fixed': 50, 'note': 'your stroke, near max, perfect walls'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'dead_sprint_dozen', 'name': 'The Dozen', 'slot': 'sprint',
        'phases': ('build',), 'min_level': 'Beginner',
        'description': 'Twelve 25s: four fast, four faster, four fastest. A simple ladder to max speed.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 4, 'dist': 25, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max', 'rest_mode': 'rest', 'rest_fixed': 20, 'note': 'fast'},
            {'section': 'Main set', 'reps': 4, 'dist': 25, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max', 'rest_mode': 'rest', 'rest_fixed': 30, 'note': 'faster'},
            {'section': 'Main set', 'reps': 4, 'dist': 25, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max', 'rest_mode': 'rest', 'rest_fixed': 45, 'note': 'fastest of the day'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'sprint_75_25', 'name': '75 Easy 25 Blast', 'slot': 'sprint',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': '100s swum as 75 smooth + 25 sprint. Sprinting with a tired-ish body, low total stress.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 8, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': '75 relaxed, last 25 absolutely flat out into the wall'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'gear_change_50s', 'name': 'Gear Change 50s', 'slot': 'sprint',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': '50s switching speed mid-rep on a signal: cruise-sprint-cruise. Race-style surges.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 12, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'tempo',
             'note': 'rotate: sprint first 15m / sprint middle 20m / sprint last 15m'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'broken_200_race', 'name': 'Broken 200 (4x50)', 'slot': 'sprint',
        'phases': ('build', 'taper'), 'min_level': 'Intermediate',
        'description': 'A 200 race broken into 4x50 with 10s rest, at target 200 pace. The classic race rehearsal.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 4, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max',
             'rest_mode': 'rest', 'rest_fixed': 10, 'round_reps': 3,
             'note': '3 broken 200s: 10s only at each wall, easy swim between rounds'},
            {'section': 'Sub set', 'reps': 1, 'dist': 200, 'stroke': 'FR', 'modifier': '', 'zone': 'recovery',
             'rest_mode': 'rest', 'rest_fixed': 90, 'note': 'easy between rounds'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'kick_sprint_ladder', 'name': 'Kick Sprint Ladder', 'slot': 'sprint',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': '25-50-25 max kick rounds. Legs are the first thing to go in a race -- train them last to go.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 1, 'dist': 25, 'stroke': 'FR', 'modifier': 'Kick', 'zone': 'vo2max', 'rest_mode': 'rest', 'rest_fixed': 20, 'round_reps': 4, 'note': '4 rounds: 25 max kick'},
            {'section': 'Main set', 'reps': 1, 'dist': 50, 'stroke': 'FR', 'modifier': 'Kick', 'zone': 'vo2max', 'rest_mode': 'rest', 'rest_fixed': 30, 'round_reps': 4, 'note': '50 max kick'},
            {'section': 'Main set', 'reps': 1, 'dist': 25, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max', 'rest_mode': 'rest', 'rest_fixed': 30, 'round_reps': 4, 'note': '25 sprint SWIM off the kick'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'last_15_finish', 'name': 'Finish Practice', 'slot': 'sprint',
        'phases': ('build', 'taper'), 'min_level': 'Beginner',
        'description': '50s easy into a max-effort final 15m and a no-breath finish. Races are won at the wall.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 10, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'easy 35m, then MAX last 15m: head down, no breath, full-speed touch'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'sprint_pairs', 'name': 'Sprint Pairs', 'slot': 'sprint',
        'phases': ('build',), 'min_level': 'Intermediate',
        'description': 'Paired 25s: one drag (fists/head-up), one free sprint. Contrast makes the fast one faster.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 6, 'dist': 25, 'stroke': 'FR', 'modifier': 'Drill', 'zone': 'tempo', 'rest_mode': 'rest', 'rest_fixed': 15, 'note': 'odds: fist or head-up sprint'},
            {'section': 'Main set', 'reps': 6, 'dist': 25, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max', 'rest_mode': 'rest', 'rest_fixed': 40, 'note': 'evens: normal stroke -- feel the free speed'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'vo2_150s', 'name': 'VO2 150s', 'slot': 'sprint',
        'phases': ('build',), 'min_level': 'Advanced',
        'description': '150s faster than CSS with long rest. Maximum aerobic power, horrible and effective.',
        'blocks': [
            _wu(500),
            {'section': 'Main set', 'reps': 5, 'dist': 150, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max',
             'rest_mode': 'rest', 'rest_fixed': 120, 'note': 'faster than CSS the whole way; full rest, full effort'},
            _cd(300),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'usrpt_50s_stroke', 'name': 'USRPT Stroke 50s', 'slot': 'sprint',
        'phases': ('build',), 'min_level': 'Advanced',
        'description': 'Race-pace 50s of your stroke, short rest, stop on second miss. Specificity all the way.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 12, 'dist': 50, 'stroke': 'IM', 'modifier': '', 'zone': 'vo2max',
             'rest_mode': 'rest', 'rest_fixed': 20, 'note': 'your stroke at 200-race pace; two misses in a row ends the set -- that is the point'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'relay_style_100s', 'name': 'Relay Takeover 100s', 'slot': 'sprint',
        'phases': ('build', 'taper'), 'min_level': 'Intermediate',
        'description': 'A handful of near-max 100s with big rest, each one raced like a relay leg.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max',
             'rest_mode': 'rest', 'rest_fixed': 150, 'note': 'race it: fast breakout, hold your technique when it burns'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'fly_free_sprints', 'name': 'Fly-Free Sprints', 'slot': 'sprint',
        'phases': ('base', 'build'), 'min_level': 'Advanced',
        'description': '25 fly + 25 free continuous sprints. Fly builds power, free banks it.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 8, 'dist': 50, 'stroke': 'FL', 'modifier': '', 'zone': 'vo2max',
             'rest_mode': 'rest', 'rest_fixed': 45, 'note': 'first 25 fly strong, second 25 free sprint -- no pause at the switch'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'breakout_25s', 'name': 'Breakout 25s', 'slot': 'sprint',
        'phases': ('base', 'build', 'taper'), 'min_level': 'Beginner',
        'description': '25s built around the underwater and breakout: streamline, kicks, first three strokes.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 12, 'dist': 25, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max',
             'rest_mode': 'rest', 'rest_fixed': 30, 'note': 'best streamline, 3-5 dolphin kicks, explode through the breakout, easy to the wall'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'back_sprint_50s', 'name': 'Backstroke Sprint 50s', 'slot': 'sprint',
        'phases': ('build',), 'min_level': 'Intermediate',
        'description': 'Fast backstroke 50s with full rest. Underwaters count double on your back.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 8, 'dist': 50, 'stroke': 'BK', 'modifier': '', 'zone': 'vo2max',
             'rest_mode': 'rest', 'rest_fixed': 50, 'note': 'max underwaters off every wall, high tempo on top'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },

    # ------------------------------------------------------------------
    # ENDURANCE -- second wave
    # ------------------------------------------------------------------
    {
        'key': 'endurance_300s', 'name': 'Endurance 300s', 'slot': 'endurance',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': '300s at endurance pace. Long enough to demand rhythm, short enough to stay honest.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 4, 'dist': 300, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'even 100 splits -- check the clock each 100'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'negative_split_400s', 'name': 'Negative Split 400s', 'slot': 'endurance',
        'phases': ('build',), 'min_level': 'Advanced',
        'description': '400s with the second 200 faster. Back-half strength for distance racing.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 3, 'dist': 400, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'second 200 faster than the first -- start conservative on purpose'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'cruise_intervals_150s', 'name': 'Cruise 150s', 'slot': 'endurance',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': '150s at a steady cruise. The friendly volume set for base weeks.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 8, 'dist': 150, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'same time every rep, breathing controlled'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'descending_ladder_long', 'name': 'Descending Ladder', 'slot': 'endurance',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': '400-300-200-100 at endurance pace, each rep slightly quicker than the last.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 1, 'dist': 400, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': 'the long one: relaxed'},
            {'section': 'Main set', 'reps': 1, 'dist': 300, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': 'a touch quicker'},
            {'section': 'Main set', 'reps': 1, 'dist': 200, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': 'quicker again'},
            {'section': 'Main set', 'reps': 2, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'tempo', 'note': 'finish at tempo'},
            _cd(),
        ],
        'scale_block_indexes': [4],
    },
    {
        'key': 'pull_paddle_400s', 'name': 'Pull 400s', 'slot': 'endurance',
        'phases': ('base', 'build'), 'min_level': 'Advanced',
        'description': 'Long pull reps with buoy (paddles optional). Strength-endurance for the catch.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 3, 'dist': 400, 'stroke': 'FR', 'modifier': 'Pull', 'zone': 'endurance',
             'note': 'buoy (+ paddles if you have them): long, powerful strokes'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'aerobic_kick_200s', 'name': 'Kick Endurance 200s', 'slot': 'endurance',
        'phases': ('base',), 'min_level': 'Intermediate',
        'description': '200 kicks at steady effort. Nobody loves it; every distance swimmer needs it.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 4, 'dist': 200, 'stroke': 'FR', 'modifier': 'Kick', 'zone': 'endurance',
             'note': 'board optional; steady, no dead spots'},
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'swim: enjoy how light your arms feel'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'alternating_free_stroke_200s', 'name': 'Free-Stroke 200s', 'slot': 'endurance',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': '200s alternating freestyle and your stroke. Aerobic depth without monotony.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 3, 'dist': 200, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': 'odds: free'},
            {'section': 'Main set', 'reps': 3, 'dist': 200, 'stroke': 'IM', 'modifier': '', 'zone': 'endurance', 'note': 'evens: IM or your stroke'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'the_grid_50s', 'name': 'The Grid', 'slot': 'endurance',
        'phases': ('base',), 'min_level': 'Beginner',
        'description': 'Blocks of aerobic 50s with a tempo 50 closing each block. Structure keeps the mind busy.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 5, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'round_reps': 4,
             'note': '4 blocks of 5x50: reps 1-4 steady, rep 5 at tempo'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'long_smooth_1000', 'name': 'The Long Smooth One', 'slot': 'endurance',
        'phases': ('base', 'build'), 'min_level': 'Advanced',
        'description': 'One long continuous swim at endurance pace. Swimming\'s long run: rhythm, patience, time.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 1, 'dist': 1500, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'rest_mode': 'rest', 'rest_fixed': 60, 'note': 'continuous; settle in and hold your stroke count'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'progressive_400s', 'name': 'Progressive 400s', 'slot': 'endurance',
        'phases': ('build',), 'min_level': 'Intermediate',
        'description': '400s that build by 100: easy, steady, strong, fast. Runna\'s progressive long run, in water.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 3, 'dist': 400, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'each 400: 100 easy / 100 steady / 100 strong / 100 at tempo'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'im_endurance_200s', 'name': 'IM Endurance 200s', 'slot': 'endurance',
        'phases': ('base', 'build'), 'min_level': 'Advanced',
        'description': '200 IMs at aerobic effort. Four strokes share the load, the engine does the work.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 5, 'dist': 200, 'stroke': 'IM', 'modifier': '', 'zone': 'endurance',
             'note': 'smooth IM, transitions crisp, no stroke gets dropped'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'fartlek_100s', 'name': 'Fartlek 100s', 'slot': 'endurance',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': 'Aerobic 100s with one self-chosen fast 25 hidden in each. Playful speed inside volume.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 10, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'pick a different 25 to attack in each 100 -- the rest stays smooth'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'double_distance_ladder', 'name': 'Doubling Ladder', 'slot': 'endurance',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': '50-100-200-400 doubling ladder at endurance pace. Each rep earns the next.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 1, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'round_reps': 2, 'note': '2 rounds up the ladder'},
            {'section': 'Main set', 'reps': 1, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'round_reps': 2, 'note': ''},
            {'section': 'Main set', 'reps': 1, 'dist': 200, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'round_reps': 2, 'note': ''},
            {'section': 'Main set', 'reps': 1, 'dist': 400, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'round_reps': 2, 'note': 'the earn-it rep'},
            _cd(),
        ],
        'scale_block_indexes': [3],
    },
    {
        'key': 'open_water_sim', 'name': 'Open Water Simulator', 'slot': 'endurance',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': 'Continuous 600s with sighting every 6th stroke and surges. Pool practice for open water.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 2, 'dist': 600, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'rest_mode': 'rest', 'rest_fixed': 45, 'note': 'sight (eyes forward) every 6 strokes; surge 25m at each 200 mark'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'breaststroke_endurance', 'name': 'Breaststroke 100s', 'slot': 'endurance',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': 'Aerobic breaststroke 100s between freestyle blocks. Timing work you can hold all day.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': 'free, steady'},
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'BR', 'modifier': '', 'zone': 'endurance', 'note': 'breast: glide fully, kick finishes every stroke'},
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': 'free, finish smooth'},
            _cd(),
        ],
        'scale_block_indexes': [1, 3],
    },
    {
        'key': 'clock_watcher_200s', 'name': 'Clock Watcher 200s', 'slot': 'endurance',
        'phases': ('build',), 'min_level': 'Beginner',
        'description': '200s where you predict your time before each rep. Pace awareness is a trainable skill.',
        'blocks': [
            _wu(),
            {'section': 'Main set', 'reps': 5, 'dist': 200, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'call your time before you push off; within 2 seconds = a win'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },

    # ------------------------------------------------------------------
    # TECHNIQUE / EASY -- second wave
    # ------------------------------------------------------------------
    {
        'key': 'single_arm_focus', 'name': 'Single Arm Set', 'slot': 'technique',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': 'Single-arm 50s into whole-stroke 50s. Isolates the catch one side at a time.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 8, 'dist': 50, 'stroke': 'FR', 'modifier': 'Drill', 'zone': 'recovery',
             'note': '25 left arm / 25 right arm, other arm at your side'},
            {'section': 'Main set', 'reps': 6, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'whole stroke: feel both catches match'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'fist_swimming', 'name': 'Fist Swimming', 'slot': 'technique',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': 'Closed-fist 50s then open hands. Your forearm is half the paddle -- feel it.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 6, 'dist': 50, 'stroke': 'FR', 'modifier': 'Drill', 'zone': 'recovery', 'note': 'fists closed: press with the forearm'},
            {'section': 'Main set', 'reps': 6, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': 'hands open: giant paddles now'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'six_kick_switch', 'name': 'Six-Kick Switch', 'slot': 'technique',
        'phases': ('base',), 'min_level': 'Beginner',
        'description': 'Six kicks on the side, switch, repeat -- into full stroke. Rotation from the hips.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 8, 'dist': 50, 'stroke': 'FR', 'modifier': 'Drill', 'zone': 'recovery',
             'note': '6 kicks on your side, one stroke, switch sides'},
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'swim: exaggerate the rotation you just drilled'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'underwater_work', 'name': 'Underwater Kick Set', 'slot': 'technique',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': 'Dolphin kick 25s underwater (as far as comfortable) into easy swim. The fifth stroke.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 8, 'dist': 25, 'stroke': 'FL', 'modifier': 'Kick', 'zone': 'recovery',
             'rest_mode': 'rest', 'rest_fixed': 30, 'note': 'streamline dolphin kick underwater to 10-15m, easy swim to the wall'},
            {'section': 'Main set', 'reps': 6, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'swim with a proper underwater off every wall'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'turn_clinic', 'name': 'Turn Clinic', 'slot': 'technique',
        'phases': ('base', 'build', 'taper'), 'min_level': 'Beginner',
        'description': '75s built around the turn: attack the wall, tight tuck, explosive push-off.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 10, 'dist': 75, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'accelerate INTO each wall, fast feet, streamline past the flags'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'backstroke_technique', 'name': 'Backstroke Lines', 'slot': 'technique',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': 'Backstroke drill-swim 50s: head still, hips up, pinky-first entry.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 6, 'dist': 50, 'stroke': 'BK', 'modifier': 'Drill', 'zone': 'recovery',
             'note': 'double-arm back or 6-kick-switch on your back'},
            {'section': 'Main set', 'reps': 6, 'dist': 50, 'stroke': 'BK', 'modifier': '', 'zone': 'endurance',
             'note': 'swim: still head, steady hips'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'breast_timing_set', 'name': 'Breaststroke Timing', 'slot': 'technique',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': 'Pull-kick-glide separation drills into whole-stroke breast. Timing is everything.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 6, 'dist': 50, 'stroke': 'BR', 'modifier': 'Drill', 'zone': 'recovery',
             'note': '2 kicks 1 pull, exaggerate the glide'},
            {'section': 'Main set', 'reps': 6, 'dist': 50, 'stroke': 'BR', 'modifier': '', 'zone': 'endurance',
             'note': 'swim: finish the kick before the pull begins'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'fly_rhythm_set', 'name': 'Butterfly Rhythm', 'slot': 'technique',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': 'Short fly reps that stay pretty. Fly falls apart quietly -- keep every rep honest.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 8, 'dist': 25, 'stroke': 'FL', 'modifier': 'Drill', 'zone': 'recovery',
             'rest_mode': 'rest', 'rest_fixed': 20, 'note': 'single-arm fly or 2-kick-1-pull'},
            {'section': 'Main set', 'reps': 8, 'dist': 25, 'stroke': 'FL', 'modifier': '', 'zone': 'endurance',
             'rest_mode': 'rest', 'rest_fixed': 20, 'note': 'whole stroke, chest press, easy speed -- stop if it gets ugly'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'breathing_pattern_set', 'name': 'Breathing Patterns', 'slot': 'technique',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': 'Easy 100s rotating breathing patterns. Bilateral comfort pays off on race day.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 8, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'recovery',
             'note': 'by 25: breathe every 2 / every 3 / every 4 / choice -- stay long'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'streamline_focus', 'name': 'Streamline Project', 'slot': 'technique',
        'phases': ('base', 'taper'), 'min_level': 'Beginner',
        'description': 'Every wall is a rep: push-offs past the flags, tight lines, no exceptions.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 12, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'recovery',
             'note': 'squeeze ears, hand on hand, ride the glide past the flags before stroke one'},
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'swim: count strokes saved by better walls'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'taper_sharpener', 'name': 'Taper Sharpener', 'slot': 'technique',
        'phases': ('taper',), 'min_level': 'Beginner',
        'description': 'The classic pre-race session: easy swimming, a few builds, a couple of race-pace touches.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 6, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'recovery', 'note': 'silky, long'},
            {'section': 'Main set', 'reps': 4, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'tempo', 'note': 'build to strong'},
            {'section': 'Main set', 'reps': 2, 'dist': 25, 'stroke': 'FR', 'modifier': '', 'zone': 'vo2max',
             'rest_mode': 'rest', 'rest_fixed': 60, 'note': 'two race-pace touches, then done -- resist doing more'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'sculling_menu', 'name': 'Sculling Menu', 'slot': 'technique',
        'phases': ('base',), 'min_level': 'Intermediate',
        'description': 'Front, mid and rear scull rotations with swim between. Feel is built, not born.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 3, 'dist': 50, 'stroke': 'FR', 'modifier': 'Drill', 'zone': 'recovery',
             'rest_mode': 'rest', 'rest_fixed': 20, 'round_reps': 3, 'note': '3 rounds: front scull / mid scull / rear scull'},
            {'section': 'Main set', 'reps': 2, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'round_reps': 3, 'note': 'swim: press where you just sculled'},
            _cd(),
        ],
        'scale_block_indexes': [2],
    },
    {
        'key': 'smooth_operator', 'name': 'Smooth Operator', 'slot': 'technique',
        'phases': ('base', 'build', 'taper'), 'min_level': 'Beginner',
        'description': 'A genuinely easy mixed swim. Some sessions exist so the hard ones can work.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 8, 'dist': 75, 'stroke': 'FR', 'modifier': '', 'zone': 'recovery',
             'note': '25 free / 25 back / 25 choice, all easy'},
            {'section': 'Main set', 'reps': 4, 'dist': 50, 'stroke': 'FR', 'modifier': 'Drill', 'zone': 'recovery',
             'note': 'favourite drill, zero clock pressure'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },
    {
        'key': 'stroke_golf', 'name': 'Swim Golf', 'slot': 'technique',
        'phases': ('base', 'build'), 'min_level': 'Intermediate',
        'description': 'Score = strokes + seconds per 50. Lower the score without swimming harder.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 12, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'swim golf: add stroke count to seconds; beat your score with LENGTH, not effort'},
            _cd(),
        ],
        'scale_block_indexes': [1],
    },
    {
        'key': 'kick_conditioning_mix', 'name': 'Kick Conditioning Mix', 'slot': 'technique',
        'phases': ('base', 'build'), 'min_level': 'Beginner',
        'description': 'A kick-heavy session mixing strokes and positions. Strong legs fix many sins.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 4, 'dist': 50, 'stroke': 'FR', 'modifier': 'Kick', 'zone': 'recovery', 'note': 'flutter, board or streamline'},
            {'section': 'Main set', 'reps': 4, 'dist': 50, 'stroke': 'BK', 'modifier': 'Kick', 'zone': 'recovery', 'note': 'on your back, hands by hips'},
            {'section': 'Main set', 'reps': 4, 'dist': 50, 'stroke': 'FL', 'modifier': 'Kick', 'zone': 'recovery', 'note': 'dolphin on front or side'},
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance', 'note': 'swim it home'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2, 3],
    },
    {
        'key': 'distance_per_stroke', 'name': 'Distance Per Stroke', 'slot': 'technique',
        'phases': ('base', 'build', 'taper'), 'min_level': 'Beginner',
        'description': 'Descending stroke-count 50s. Fewer strokes at the same speed = free speed later.',
        'blocks': [
            _wu(300),
            {'section': 'Main set', 'reps': 10, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'recovery',
             'note': 'drop one stroke per 50 until it breaks down, then hold your best count'},
            {'section': 'Main set', 'reps': 4, 'dist': 100, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'swim at your best count, normal speed'},
            _cd(),
        ],
        'scale_block_indexes': [1, 2],
    },

    # ------------------------------------------------------------------
    # CSS TEST -- the benchmark session (also the retest)
    # ------------------------------------------------------------------
    {
        'key': 'css_test', 'name': 'CSS Test (400 + 200)', 'slot': 'css_test',
        'phases': ('base', 'build', 'taper'), 'min_level': 'Beginner',
        'description': 'The benchmark: a max-effort 400 and 200 freestyle. Sets the pace targets for every session in your plan.',
        'blocks': [
            _wu(400),
            {'section': 'Pre set', 'reps': 4, 'dist': 50, 'stroke': 'FR', 'modifier': '', 'zone': 'endurance',
             'note': 'build each 50, last one strong'},
            {'section': 'Main set', 'reps': 1, 'dist': 400, 'stroke': 'FR', 'modifier': '', 'max_effort': True,
             'rest_mode': 'rest', 'rest_fixed': 300,
             'note': '400 TIME TRIAL: max effort, pace it like a race. Log it as "400m Freestyle" with your time'},
            {'section': 'Sub set', 'reps': 1, 'dist': 200, 'stroke': 'FR', 'modifier': '', 'zone': 'recovery',
             'rest_mode': 'rest', 'rest_fixed': 120, 'note': 'very easy, full recovery before the 200'},
            {'section': 'Main set', 'reps': 1, 'dist': 200, 'stroke': 'FR', 'modifier': '', 'max_effort': True,
             'rest_mode': 'rest', 'rest_fixed': 60,
             'note': '200 TIME TRIAL: max effort. Log it as "200m Freestyle" with your time'},
            _cd(300),
        ],
        'scale_block_indexes': [],
    },
]


def templates_for(slot, phase=None, level=None):
    """All templates usable for a slot, filtered by plan phase and swimmer
    level. Mirrors demo_library-style filter helpers."""
    max_idx = LEVEL_ORDER.index(level) if level in LEVEL_ORDER else 1
    out = []
    for t in TEMPLATES:
        if t['slot'] != slot:
            continue
        if phase and phase not in t['phases']:
            continue
        if LEVEL_ORDER.index(t['min_level']) > max_idx:
            continue
        out.append(t)
    return out


def get_template(key):
    for t in TEMPLATES:
        if t['key'] == key:
            return t
    return None
