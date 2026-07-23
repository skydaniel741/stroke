"""Content for the public marketing pages.

Everything a visitor can read before they have an account lives here rather
than in fifteen near-identical templates: the per-feature deep-dive pages
(/features/<slug>), the three audience pages (/for/<who>) and the FAQ. Two
templates render all of it, so adding a page is a dict entry, not a file.

Rule for this file: nothing in here may promise something the app doesn't do.
If a feature is described here it exists in routes_coach / routes_solo /
routes_parent today.
"""

# ---------------------------------------------------------------------------
# Feature deep-dives -- reached by clicking a card on the landing page rather
# than being dumped straight onto /signup.
# ---------------------------------------------------------------------------

FEATURES = {
    'attendance': {
        'eyebrow': 'For coaches',
        'title': 'Take attendance. The set logs itself.',
        'lede': "The write-up after practice is the part that never gets done. So STROKE does it from the roll: mark who's on deck, and today's set is filed as a completed session against every swimmer who was there.",
        'audience': 'coaches',
        'sections': [
            {
                'h': 'What actually happens',
                'body': "You open the squad, tap the swimmers who turned up, and save. Every present swimmer gets that day's session written to their own training history, with the set attached. Absences are recorded too, so the attendance picture builds itself over a season instead of living in a notebook.",
            },
            {
                'h': 'Why it is built this way',
                'body': "Most team apps treat attendance and training as two separate jobs, which means a coach does the same practice twice: once on the roll, once in the log. Attendance is the only moment a coach reliably has a phone in hand, so that is the moment we hang everything else off.",
            },
            {
                'h': 'What you get out of it',
                'body': "Consistency data you did not have to collect. Sessions attended per swimmer, per week, sitting next to their times, so when a swimmer's times stall you can see whether they have actually been in the water.",
            },
        ],
        'facts': [
            ('One tap', 'per swimmer, per session'),
            ('Auto-logged', 'the set writes to every attendee'),
            ('Both ways', 'presences and absences are kept'),
        ],
        'cta': ('Set up your squad', '/signup?as=coach'),
        'related': ['session-builder', 'team-analytics'],
    },
    'session-builder': {
        'eyebrow': 'For coaches',
        'title': 'Build a set once. Use it all season.',
        'lede': 'Write a set the way you would write it on the whiteboard, save it to your library, and assign it to a whole squad or a single swimmer with a date on it.',
        'audience': 'coaches',
        'sections': [
            {
                'h': 'Sets that understand swimming',
                'body': "A block is reps x distance x stroke on an interval, not free text. Because the app knows what those numbers mean, it can total the volume, work out the send-off versus the rest, and tell you when a set does not add up: an interval that leaves no rest for the swimmers who will actually be doing it, or a session whose volume is a long way off what that group has been handling.",
            },
            {
                'h': 'A library, not a pile of documents',
                'body': "Every set you build is saved and categorised, so next season's threshold week is a search rather than a rewrite. Sets can be printed as a clean deck sheet for the pool wall, since a laminated page still beats a phone in a wet hand.",
            },
            {
                'h': 'Assign it where it needs to go',
                'body': "Push a set to a whole squad for a dated session, or to one swimmer who is coming back from injury and needs something different that morning. Attach it to a calendar entry and it shows up on the squad's schedule.",
            },
        ],
        'facts': [
            ('Structured blocks', 'reps, distance, stroke, interval'),
            ('Volume + rest checks', 'flags sets that do not add up'),
            ('Printable', 'deck sheets for the pool wall'),
        ],
        'cta': ('Build your first set', '/signup?as=coach'),
        'related': ['attendance', 'squad-calendar'],
    },
    'results-scanner': {
        'eyebrow': 'For coaches',
        'title': 'Photograph the board. Every time gets filed.',
        'lede': "After a test set, the times are on a whiteboard and nowhere else. Take a photo of it and STROKE reads the names and times off the board and files each one against the right swimmer.",
        'audience': 'coaches',
        'sections': [
            {
                'h': 'How it reads the board',
                'body': "The photo goes to an AI model that pulls out the rows: swimmer, event or distance, and time. Names are matched against your roster, so 'J Smith' on the board lands on the Jack Smith in your squad.",
            },
            {
                'h': 'You confirm before anything is saved',
                'body': "Handwriting on a wet whiteboard is handwriting on a wet whiteboard. Nothing is written to a swimmer's record until you have seen the parsed rows and confirmed them, so a misread 1:02.4 gets fixed before it becomes a personal best that never happened.",
            },
            {
                'h': 'What it turns into',
                'body': "Each confirmed row becomes a timed swim on that swimmer's record: searchable, scored to World Aquatics points, and counted toward their personal bests, exactly as if it had been typed in by hand.",
            },
        ],
        'facts': [
            ('Photo in', 'one board, whole squad'),
            ('Roster-matched', 'names resolve to real swimmers'),
            ('Confirm first', 'nothing saves until you approve it'),
        ],
        'cta': ('Try it with your squad', '/signup?as=coach'),
        'related': ['team-analytics', 'wa-points'],
    },
    'team-analytics': {
        'eyebrow': 'For coaches',
        'title': 'The whole squad, not one swimmer at a time.',
        'lede': 'Volume, attendance, times and points across the squad, so the swimmer who has quietly stopped improving is visible before their parents ask about it.',
        'audience': 'coaches',
        'sections': [
            {
                'h': 'Squad-wide first',
                'body': "Most swim software makes you click into one athlete to learn anything. The coach dashboard starts at the squad: who is trending up, who is flat, who has missed sessions, and how the group's training volume has moved week to week.",
            },
            {
                'h': 'Times read in context',
                'body': "A raw time does not tell you much across an age group. Every time is also scored to World Aquatics points, which puts a 13-year-old's 200 breaststroke and a senior's 50 free on one comparable scale, and lets you watch a swimmer's points climb across a season.",
            },
            {
                'h': 'A plain-language read',
                'body': "An AI summary describes what the numbers are doing in the tone you pick: encouraging, balanced or direct. It is a starting point for a conversation on deck, not a verdict, and it never sees more than the training data your squad has already logged.",
            },
        ],
        'facts': [
            ('Squad-level', 'volume, attendance and points together'),
            ('Comparable', 'World Aquatics points across ages'),
            ('Explained', 'a written read, in your coaching tone'),
        ],
        'cta': ('See it with your squad', '/signup?as=coach'),
        'related': ['wa-points', 'attendance'],
    },
    'parent-view': {
        'eyebrow': 'For coaches and parents',
        'title': 'Parents ask. Now they can just look.',
        'lede': 'A coach or swimmer sends one link. The parent gets a read-only page showing that swimmer and nobody else.',
        'audience': 'parents',
        'sections': [
            {
                'h': 'What a parent sees',
                'body': "Their swimmer's recent times and personal bests, whether those times are improving, attendance over recent sessions, and the upcoming squad schedule. Enough to follow the season without messaging the coach on a Sunday night.",
            },
            {
                'h': 'What a parent cannot see',
                'body': "Anything belonging to another swimmer. The coach's private notes about their child. Any status flag the coach has set. The parent view is read-only by construction, not by convention: there is no edit path in it at all.",
            },
            {
                'h': 'The link is controlled and revocable',
                'body': "A parent link is generated by the swimmer or their coach, used once to claim a parent account, and can be revoked at any time. Revoking it cuts the access immediately.",
            },
        ],
        'facts': [
            ('One swimmer', 'the link grants access to that child only'),
            ('Read-only', 'no edit path exists in the parent view'),
            ('Revocable', 'access ends the moment the link is revoked'),
        ],
        'cta': ('Read the guide for swimmers and parents', '/for/swimmers-and-parents'),
        'related': ['attendance', 'data-safety'],
    },
    'squad-calendar': {
        'eyebrow': 'For coaches',
        'title': 'Practices, meets and the set that goes with them.',
        'lede': 'A squad schedule that carries the session, not just the time and place.',
        'audience': 'coaches',
        'sections': [
            {
                'h': 'AM and PM, the way squads actually run',
                'body': "Sessions are scheduled per squad with a morning or evening slot, because a senior group training twice a day is the normal case and not an edge case.",
            },
            {
                'h': 'The set travels with the entry',
                'body': "Attach a set from your library to a calendar entry and swimmers see what is coming, while attendance on the day logs that same set for everyone present.",
            },
            {
                'h': 'Meets on the same calendar',
                'body': "Competitions sit alongside practices so a taper is visible as a shape in the schedule rather than something you hold in your head. Club meet calendars can be imported in bulk instead of typed in one at a time.",
            },
        ],
        'facts': [
            ('AM / PM', 'double days are first-class'),
            ('Sets attached', 'the schedule carries the session'),
            ('Meets included', 'competitions on the same view'),
        ],
        'cta': ('Set up your calendar', '/signup?as=coach'),
        'related': ['session-builder', 'announcements'],
    },
    'wa-points': {
        'eyebrow': 'For everyone',
        'title': 'World Aquatics points on every time you log.',
        'lede': 'One scale that makes a sprinter and a distance swimmer, a 12-year-old and a senior, comparable to each other and to themselves last season.',
        'audience': 'swimmers',
        'sections': [
            {
                'h': 'Why points and not just times',
                'body': "A time only means something next to the same swimmer's other times in the same event. Points normalise against a reference performance for that event, sex and course, so improvement across different events becomes one number that goes up.",
            },
            {
                'h': 'Automatic, on everything',
                'body': "Every time logged in STROKE gets scored: typed in by a swimmer, filed by a coach off the results board, or imported. Long course and short course are handled separately, as they must be.",
            },
            {
                'h': 'Try it before you sign up',
                'body': "There is a points calculator on the landing page that needs no account. Put a time in and see what it scores.",
            },
        ],
        'facts': [
            ('Every time', 'scored automatically'),
            ('LCM and SCM', 'courses kept separate'),
            ('No account needed', 'to try the calculator'),
        ],
        'cta': ('Try the calculator', '/#top'),
        'related': ['team-analytics', 'solo-training'],
    },
    'announcements': {
        'eyebrow': 'For coaches',
        'title': 'One place to tell the squad something.',
        'lede': 'Post once to the whole squad instead of chasing three group chats.',
        'audience': 'coaches',
        'sections': [
            {
                'h': 'Where it lands',
                'body': "An announcement appears on the dashboard of every swimmer in that squad, so pool closures and meet entry deadlines are somewhere findable rather than buried forty messages up a chat thread.",
            },
            {
                'h': 'Coach to squad, not a group chat',
                'body': "There is no reply-all. This is a noticeboard, deliberately, because the alternative is a channel nobody can mute and everybody eventually ignores.",
            },
        ],
        'facts': [
            ('Squad-scoped', 'posts go to one squad'),
            ('On the dashboard', 'not in a chat thread'),
        ],
        'cta': ('Start your squad', '/signup?as=coach'),
        'related': ['squad-calendar', 'attendance'],
    },
    'solo-training': {
        'eyebrow': 'For swimmers',
        'title': 'Training on your own, with a plan built around your times.',
        'lede': 'No squad required. Log your swims, get a multi-week plan generated from your own times, and ask an AI coach the nutrition and dryland questions you would otherwise google at midnight.',
        'audience': 'swimmers',
        'sections': [
            {
                'h': 'A plan from your actual times',
                'body': "The plan generator works from what you have logged: your times set the paces, and the weeks are structured rather than a list of random sets. Change your target event or your available days and it rebuilds.",
            },
            {
                'h': 'Your log, your history',
                'body': "Times, splits, personal bests and World Aquatics points, kept season over season. Personal bests are tracked per course, so a short course best never quietly overwrites a long course one.",
            },
            {
                'h': 'An AI coach for the other half',
                'body': "Nutrition and dryland questions answered in context of what you have been swimming. It is training guidance, not medical advice, and it says so.",
            },
        ],
        'facts': [
            ('Plan built from', 'your logged times'),
            ('Season history', 'times, splits, PBs, points'),
            ('AI coach', 'nutrition and dryland'),
        ],
        'cta': ('Start training', '/signup'),
        'related': ['wa-points', 'data-safety'],
    },
}


# ---------------------------------------------------------------------------
# Audience pages -- where the "I'm a coach / parent / swimmer" pills go.
# Same renderer, plus a list of feature cards.
# ---------------------------------------------------------------------------

AUDIENCES = {
    'coaches': {
        'eyebrow': 'For coaches',
        'title': 'Your admin, folded into the session.',
        'lede': 'STROKE is built around the three things a swim coach already does every day: take the roll, run a set, and record what came out of it. Nothing here asks you to do a fourth thing.',
        'audience': 'coaches',
        'sections': [
            {
                'h': 'The problem it is actually solving',
                'body': "Coaching admin fails at a predictable point: after practice, when the session needs writing up and the times need typing in. Squads end up with attendance in one book, sets in another, times in a spreadsheet, and no way to put them next to each other. STROKE collapses that into the two moments you are already holding a phone: the roll, and the results board.",
            },
            {
                'h': 'What you can see that you could not before',
                'body': "Attendance next to times. A swimmer whose times have flattened, alongside the fact that they have made four of the last ten sessions. Squad-wide volume against the week you planned. World Aquatics points that let you compare across an age group instead of within one event.",
            },
            {
                'h': 'Parents, handled',
                'body': "Send a parent a read-only link to their own child and the Sunday-night messages mostly stop. They see times, personal bests, attendance and what is coming up. They never see another swimmer, and they never see your private notes.",
            },
            {
                'h': 'What it costs and what happens to your data',
                'body': "Free while we build with early coaches, no card. Your squad's data is yours, is never sold, and is never used to advertise to anyone. The full detail is on the data safety page.",
            },
        ],
        'facts': [
            ('One tap', 'attendance logs the set'),
            ('One photo', 'files a whole test set'),
            ('Free', 'while we build with early coaches'),
        ],
        'cta': ('Start your squad free', '/signup?as=coach'),
        'features': ['attendance', 'session-builder', 'results-scanner', 'team-analytics', 'squad-calendar', 'announcements'],
    },
    # One page for the whole non-coach side. Splitting parents and swimmers
    # into two pages contradicted the account model: a swimming parent is one
    # person with one login, so making them choose a door was asking a
    # question the product had already answered.
    'swimmers-and-parents': {
        'eyebrow': 'For swimmers and parents',
        'title': 'One account for the swimmer, and for the person driving them to training.',
        'lede': "Swimmers log their training and watch a season add up. Parents get a read-only view of their own swimmer, by invitation. If you are both, and plenty of swimming parents are, it is the same login.",
        'audience': 'swimmers-and-parents',
        'sections': [
            {
                'h': 'If you swim',
                'body': "Log your times, splits and personal bests and keep them season after season, scored to World Aquatics points so improvement across different events is one number. In a squad, your coach's sessions and announcements land on your dashboard and the sets you swim get logged when your coach takes the roll. On your own, you get a multi-week plan generated from your own times and an AI coach for nutrition and dryland questions.",
            },
            {
                'h': 'If you are a parent',
                'body': "You do not sign up on your own. Your swimmer, or their coach, sends you a parent link, and opening it connects you to that one swimmer. You then see their best time for each event with a plain read on whether it is improving, steady or slipping, their recent swims, their attendance, what is on next, and a short written summary of the week where the coach has approved one.",
            },
            {
                'h': 'If you are both, you need one account, not two',
                'body': "A masters swimmer with a daughter in the club is one person. Open the parent link while you are already signed in, confirm it, and the parent view is added to the account you have: your own training stays exactly where it is, and you switch between the two from the sidebar. It works the other way too, so a parent who takes up swimming can turn on their own training without starting again. The same holds if you coach.",
            },
            {
                'h': 'What a parent cannot see, and why',
                'body': "Never another swimmer in the squad, including times, attendance or names. Never the coach's private notes about your child, or any injury or availability flag they have set. Those exist so a coach can be candid in their own working notes, and a parent view that exposed them would quietly end that candour, which would be worse for the swimmer. The parent view is also read-only by construction: there is no edit path in it at all.",
            },
            {
                'h': "Who can see a swimmer's data",
                'body': "Your coach, if you are in a squad. Any parent you have been linked to. Other swimmers only if you explicitly opt in to the leaderboard, which is off by default. Nobody else. A parent link can be revoked at any time by the swimmer or their coach, and access ends immediately.",
            },
        ],
        'facts': [
            ('One account', 'swim, parent, or both'),
            ('Invite only', 'parent access comes from the coach or swimmer'),
            ('Your child only', 'never another swimmer in the squad'),
        ],
        'cta': ('Create your account', '/signup'),
        'features': ['solo-training', 'parent-view', 'wa-points'],
    },
}

# Old two-page split, kept so existing links and any shared URLs still land
# somewhere sensible instead of 404ing.
AUDIENCE_ALIASES = {
    'parents': 'swimmers-and-parents',
    'swimmers': 'swimmers-and-parents',
}


# ---------------------------------------------------------------------------
# FAQ -- grouped, and deliberately answering the awkward questions too.
# ---------------------------------------------------------------------------

FAQ = [
    {
        'group': 'Getting started',
        'items': [
            ('Who is STROKE for?',
             "Three groups, with a different view each. Coaches run squads: roster, attendance, sets, times and analytics. Parents get a read-only view of their own swimmer, by invitation. Swimmers log their own training, in a squad or on their own."),
            ('What does it cost?',
             "Creating an account and logging your own swims is free. The coach tier is free while we are building with early squads, with no card required. Solo, the paid tier for swimmers training without a coach, is NZ$12 a month and adds generated training plans, the analytics page and the AI coach."),
            ('Do I need my club to sign up first?',
             "No. A coach can set up a squad on their own, and a swimmer can create an account and start logging without any club involvement."),
            ('How do I move our existing roster in?',
             "Export your roster from whatever you use now and import the CSV. You do not need to match our column names: the importer reads your file, works out which column is which, and shows you a preview to confirm before anything is written."),
        ],
    },
    {
        'group': 'Coaches',
        'items': [
            ('How does attendance log a set?',
             "You mark who was present. The set attached to that day's session is then written as a completed session against each swimmer who was there, so nothing needs typing up afterwards."),
            ('How accurate is the results-board scanner?',
             "It reads most clearly written boards well, and it will misread some handwriting, especially wet handwriting. That is why nothing is saved until you have reviewed the parsed rows and confirmed them."),
            ('Can I run more than one squad?',
             "Yes. Multiple squads, or a whole club, from the same dashboard."),
            ('Can other coaches see my squad?',
             "No. Squad data is scoped to the coach who owns the squad and, where a club is set up, that club's structure. A coach at another club cannot see your roster, times or notes."),
            ('Are my private notes about a swimmer visible to them or their parents?',
             "No. Coach notes and status flags are coach-only. They are not shown in the swimmer's own view or in the parent view. This is enforced in the code that builds those pages, not left to the interface to hide."),
        ],
    },
    {
        'group': 'Parents',
        'items': [
            ('How do I get access?',
             "Your swimmer or their coach sends you a parent link from the roster. Opening it connects you to that swimmer. There is no way to sign up as a parent and then go looking for a child."),
            ('I swim or coach myself. Do I need a separate parent account?',
             "No. Open the parent link while signed in to the account you already have, confirm it, and the parent view is added alongside your own training. You switch between the two from the sidebar, and nothing about your own account changes. It works the other way as well: a parent-only account can start logging its own swims at any time."),
            ('Can I be linked to more than one child?',
             "Yes. One account can hold links to several swimmers, and you pick which one you are looking at from the parent dashboard."),
            ('Can I see the rest of the squad?',
             "No. A parent account can only ever see the swimmers it has been explicitly linked to. Other swimmers' times, attendance and names are not reachable from the parent view."),
            ('Can I see what the coach has written about my child?',
             "You see the times, personal bests, attendance and upcoming schedule, plus a written weekly summary where the coach has reviewed and approved one. You do not see the coach's private working notes or injury and availability flags."),
            ('Can I edit anything?',
             "No. The parent view is read-only."),
            ('My child is under 13. What are the rules?',
             "Where a squad requires it, a coach can mark an invite as needing guardian consent, and the swimmer's account is not activated until a parent or guardian confirms. As a parent or guardian you can ask us at any time to show you what we hold about your child, correct it, or delete it."),
        ],
    },
    {
        'group': 'Swimmers',
        'items': [
            ('Who can see my times?',
             "Your coach, if you are in a squad. Any parent you have sent a parent link to. Other swimmers only if you explicitly opt in to the leaderboard, which is off by default. Nobody else."),
            ('Can I revoke a parent link?',
             "Yes, at any time, from your parent link settings. Access ends immediately."),
            ('If I leave the squad, do I lose my times?',
             "No. Your training record belongs to your account, not to the squad."),
            ('Does the AI coach give medical or dietary advice?',
             "No. It gives general training, nutrition and dryland guidance in the context of your logged swimming. It is not a substitute for a doctor, physiotherapist or registered dietitian, and it will tell you when a question is one for a professional."),
        ],
    },
    {
        'group': 'Data, privacy and cookies',
        'items': [
            ('Do you sell my data?',
             "No. We do not sell personal information, and we do not use it for third-party advertising. There is no advertising in STROKE."),
            ('What cookies do you use?',
             "A session cookie that keeps you signed in, and, if you tick 'remember me', a longer-lived cookie for that. That is the whole list. No advertising cookies, no cross-site tracking, no third-party analytics that follow you around the web. Details are on the cookie policy."),
            ('Where is our data stored?',
             "On managed cloud infrastructure. Passwords are stored as bcrypt hashes and never in a readable form, so nobody at STROKE can see your password."),
            ('Does the AI train on our squad data?',
             "No. Squad data sent to the AI provider to generate a summary or a plan is used to answer that request and is not used to train anybody's models."),
            ('How do I get my data out, or delete it?',
             "Email privacy@stroke.app and ask. You have the right to see what we hold, correct it, get a copy of it, and have it deleted. Personal bests can also be exported from the app at any time."),
            ('Which privacy law applies?',
             "We are based in New Zealand, so the Privacy Act 2020 and its information privacy principles apply to us. Where a user is in the UK or EU, we also handle their data consistently with the GDPR."),
        ],
    },
]


# ---------------------------------------------------------------------------
# Footer -- one definition, used by every public page.
# ---------------------------------------------------------------------------

FOOTER_LINKS = [
    ('For coaches', '/for/coaches'),
    ('For swimmers and parents', '/for/swimmers-and-parents'),
    ('FAQ', '/faq'),
    ('Privacy', '/privacy'),
    ('Terms', '/terms'),
    ('Cookies', '/cookies'),
    ('Data safety', '/data-safety'),
]
