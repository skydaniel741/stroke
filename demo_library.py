"""Curated technique/exercise demo catalog for the solo program page.

Each demo is a small inline animated SVG (native SVG animation, no external
assets/video/3D pipeline) plus a short numbered step list. AI does not
generate these -- routes_solo matches a swimmer's primary_stroke and their
AI-recommended dryland categories against `tags` here, same "curated set,
code picks the fit" pattern as the meal/dryland-program catalogs.

Colors use `currentColor` / CSS custom properties so the SVGs inherit the
app's cozy-pastel palette (see :root tokens in static/css/main.css) since
they're inlined into the page, not loaded as external <img> files.
"""

DEMOS = [
    {
        'slug': 'catch-pull',
        'title': 'Catch & pull',
        'kind': 'stroke',
        'tags': ['Freestyle', 'Butterfly', 'IM'],
        'steps': [
            'High-elbow catch out in front, fingertips leading down',
            'Bend the elbow and sweep the hand under the body (the S-curve)',
            'Accelerate the hand back past the hip',
            'Exit thumb-first into a relaxed recovery',
        ],
        'svg': '''<svg viewBox="0 0 200 110" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Catch and pull animation">
  <path d="M20,25 C70,10 70,80 130,90" fill="none" stroke="var(--line, #e4e8f4)" stroke-width="2" stroke-dasharray="4 5"/>
  <circle cx="20" cy="25" r="5" fill="var(--accent, #6f8fe6)" opacity=".35"/>
  <circle r="7" fill="var(--accent, #6f8fe6)">
    <animateMotion dur="2.6s" repeatCount="indefinite" rotate="auto"
      path="M20,25 C70,10 70,80 130,90 C150,94 165,90 172,85"/>
  </circle>
  <circle cx="172" cy="85" r="5" fill="var(--accent, #6f8fe6)" opacity=".35"/>
</svg>''',
    },
    {
        'slug': 'streamline-pushoff',
        'title': 'Streamline push-off',
        'kind': 'stroke',
        'tags': ['Freestyle', 'Backstroke', 'Breaststroke', 'Butterfly', 'IM'],
        'steps': [
            'Push off on your back or side, arms locked overhead',
            'Squeeze the ears, flat line, hands stacked',
            'Hold the line tight until speed drops off',
            'Let your first stroke or kick break the streamline, never before',
        ],
        'svg': '''<svg viewBox="0 0 200 90" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Streamline push-off animation">
  <line x1="18" y1="45" x2="18" y2="70" stroke="var(--line, #e4e8f4)" stroke-width="3"/>
  <g>
    <ellipse cx="0" cy="45" rx="22" ry="6" fill="var(--accent, #6f8fe6)"/>
    <line x1="-22" y1="45" x2="-38" y2="45" stroke="var(--accent, #6f8fe6)" stroke-width="4" stroke-linecap="round"/>
    <animateTransform attributeName="transform" attributeType="XML" type="translate"
      values="30,0; 178,0; 30,0" keyTimes="0;0.7;1" dur="2.8s" repeatCount="indefinite"/>
  </g>
  <path d="M60,45 L100,45 M100,45 L92,40 M100,45 L92,50" stroke="var(--line, #e4e8f4)" stroke-width="1.5" fill="none" opacity=".5"/>
</svg>''',
    },
    {
        'slug': 'plank-shoulder-tap',
        'title': 'Plank shoulder taps',
        'kind': 'dryland',
        'tags': ['Core'],
        'steps': [
            'Strict plank, feet slightly wider than hip width',
            'Tap the opposite shoulder without rotating the hips',
            'Alternate sides, core braced throughout',
            'Slow and controlled beats fast and sloppy',
        ],
        'svg': '''<svg viewBox="0 0 200 90" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Plank shoulder tap animation">
  <line x1="30" y1="55" x2="170" y2="55" stroke="var(--accent, #6f8fe6)" stroke-width="5" stroke-linecap="round"/>
  <circle cx="165" cy="45" r="7" fill="var(--accent, #6f8fe6)"/>
  <circle r="6" fill="var(--ink, #2c2942)" opacity=".8">
    <animate attributeName="cx" values="45;165;45" keyTimes="0;0.5;1" dur="2.2s" repeatCount="indefinite"/>
    <animate attributeName="cy" values="55;35;55" keyTimes="0;0.5;1" dur="2.2s" repeatCount="indefinite"/>
  </circle>
  <line x1="30" y1="55" x2="20" y2="75" stroke="var(--line, #e4e8f4)" stroke-width="3"/>
  <line x1="170" y1="55" x2="180" y2="75" stroke="var(--line, #e4e8f4)" stroke-width="3"/>
</svg>''',
    },
    {
        'slug': 'hip-mobility',
        'title': 'Hip opener flow',
        'kind': 'dryland',
        'tags': ['Mobility'],
        'steps': [
            'Sit with both knees bent, both feet flat on the floor',
            'Rotate both knees to one side, chest stays tall',
            'Hold, feel the stretch through the hip',
            'Rotate through to the other side and repeat',
        ],
        'svg': '''<svg viewBox="0 0 200 100" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Hip mobility animation">
  <circle cx="100" cy="30" r="10" fill="var(--ink, #2c2942)" opacity=".8"/>
  <line x1="100" y1="40" x2="100" y2="65" stroke="var(--ink, #2c2942)" stroke-width="4" opacity=".8"/>
  <g stroke="var(--accent, #6f8fe6)" stroke-width="4" stroke-linecap="round" fill="none">
    <path d="M100,65 Q75,75 60,68">
      <animate attributeName="d" values="M100,65 Q75,75 60,68; M100,65 Q125,75 140,68; M100,65 Q75,75 60,68" dur="3.2s" repeatCount="indefinite"/>
    </path>
    <path d="M100,65 Q125,75 140,68">
      <animate attributeName="d" values="M100,65 Q125,75 140,68; M100,65 Q75,75 60,68; M100,65 Q125,75 140,68" dur="3.2s" repeatCount="indefinite"/>
    </path>
  </g>
</svg>''',
    },
]

_BY_SLUG = {d['slug']: d for d in DEMOS}


def demo_by_slug(slug):
    return _BY_SLUG.get(slug)


def demos_for_stroke(stroke):
    return [d for d in DEMOS if d['kind'] == 'stroke' and stroke in d['tags']]


def demos_for_dryland_category(category):
    return [d for d in DEMOS if d['kind'] == 'dryland' and category in d['tags']]
