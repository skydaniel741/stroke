"""Curated swimmer-nutrition dataset for the solo nutrition section.

Grounded in standard sports-nutrition timing guidance:
- Pre-training: a carb-forward meal 2-3 h before, or fast carbs 30-60 min before;
  keep fat/fibre low close to the session.
- Post-training: 30-60 g carbs + 15-30 g protein within ~60 min to refuel and repair.
- Race day: familiar, high-carb, easy-to-digest food; nothing new.
- Everyday: balanced plates that hit a swimmer's daily carb + protein needs.

Static content (no DB) so the section always renders. Each meal carries a full
recipe plus the stats the UI shows: prep/cook time, calories, macros, timing.
"""

CATEGORIES = [
    {'key': 'pre', 'label': 'Before training', 'blurb': 'Fuel up without sitting heavy'},
    {'key': 'post', 'label': 'After training', 'blurb': 'Refuel & repair within the hour'},
    {'key': 'race', 'label': 'Race day', 'blurb': 'Familiar, high-carb, easy to digest'},
    {'key': 'everyday', 'label': 'Everyday meals', 'blurb': 'Balanced plates for daily needs'},
]

MEALS = [
    # ---------------- BEFORE TRAINING ----------------
    {
        'id': 'pb-overnight-oats', 'category': 'pre',
        'name': 'Peanut Butter Overnight Oats', 'emoji': '🥣',
        'gradient': 'linear-gradient(135deg,#f6d365,#fda085)',
        'timing': 'Eat 2–3 hours before training',
        'prep_min': 5, 'cook_min': 0, 'calories': 430,
        'protein_g': 16, 'carbs_g': 60, 'fat_g': 13,
        'why': 'Slow-release oats top up glycogen while banana adds quick carbs — energy that lasts a full session without weighing you down.',
        'ingredients': [
            '60 g rolled oats', '200 ml milk (or soy milk)', '1 tbsp peanut butter',
            '1 banana, sliced', '1 tsp honey', 'Pinch of cinnamon',
        ],
        'steps': [
            'Stir oats, milk, peanut butter and cinnamon in a jar.',
            'Add half the banana and the honey, stir through.',
            'Cover and refrigerate overnight (or at least 2 hours).',
            'Top with the rest of the banana before eating.',
        ],
    },
    {
        'id': 'chicken-rice-bowl-pre', 'category': 'pre',
        'name': 'Chicken & Rice Power Bowl', 'emoji': '🍚',
        'gradient': 'linear-gradient(135deg,#a8edea,#fed6e3)',
        'timing': 'Eat 3 hours before training',
        'prep_min': 10, 'cook_min': 20, 'calories': 520,
        'protein_g': 35, 'carbs_g': 68, 'fat_g': 9,
        'why': 'A classic pre-session plate: plenty of easy carbs from white rice, lean protein from chicken, and low fat so it clears your stomach in time.',
        'ingredients': [
            '150 g cooked white rice', '120 g chicken breast', '1 tsp olive oil',
            'Handful of spinach', 'Soy sauce & lemon to taste',
        ],
        'steps': [
            'Season the chicken and pan-fry in olive oil until cooked through (~6 min each side).',
            'Warm the rice and wilt the spinach through it.',
            'Slice the chicken over the rice.',
            'Finish with a splash of soy sauce and lemon.',
        ],
    },
    {
        'id': 'banana-honey-toast', 'category': 'pre',
        'name': 'Banana & Honey Toast', 'emoji': '🍌',
        'gradient': 'linear-gradient(135deg,#fddb92,#d1fdff)',
        'timing': 'Quick carbs 30–60 min before',
        'prep_min': 4, 'cook_min': 2, 'calories': 260,
        'protein_g': 6, 'carbs_g': 50, 'fat_g': 3,
        'why': 'When the session is close, you want fast carbs and almost no fat or fibre. Toast + banana + honey digests quickly and tops off the tank.',
        'ingredients': [
            '2 slices wholegrain or white bread', '1 banana, sliced',
            '1 tbsp honey', 'Pinch of cinnamon',
        ],
        'steps': [
            'Toast the bread.',
            'Lay banana slices over the top.',
            'Drizzle with honey and dust with cinnamon.',
        ],
    },
    # ---------------- AFTER TRAINING ----------------
    {
        'id': 'recovery-choc-milk', 'category': 'post',
        'name': 'Chocolate Milk Recovery Shake', 'emoji': '🥛',
        'gradient': 'linear-gradient(135deg,#c79081,#dfa579)',
        'timing': 'Within 30 min of finishing',
        'prep_min': 3, 'cook_min': 0, 'calories': 320,
        'protein_g': 20, 'carbs_g': 45, 'fat_g': 6,
        'why': 'One of the most researched recovery options — a near-perfect 2:1 carb-to-protein ratio to restock glycogen and kick-start muscle repair while your body is most receptive.',
        'ingredients': [
            '300 ml milk', '2 tbsp cocoa powder', '1 tsp honey or sugar',
            '1 banana', 'Optional: 1 scoop whey protein',
        ],
        'steps': [
            'Blend milk, cocoa, honey and banana until smooth.',
            'Add whey if you want extra protein.',
            'Drink straight after getting out of the pool.',
        ],
    },
    {
        'id': 'greek-yogurt-berry-bowl', 'category': 'post',
        'name': 'Greek Yogurt Berry Bowl', 'emoji': '🫐',
        'gradient': 'linear-gradient(135deg,#a1c4fd,#c2e9fb)',
        'timing': 'Within 60 min of finishing',
        'prep_min': 5, 'cook_min': 0, 'calories': 340,
        'protein_g': 24, 'carbs_g': 42, 'fat_g': 7,
        'why': 'Greek yogurt is packed with protein for repair, berries and honey bring the carbs and antioxidants, and granola adds crunch and more fuel.',
        'ingredients': [
            '200 g Greek yogurt', '1 handful mixed berries', '30 g granola',
            '1 tbsp honey', '1 tbsp chopped nuts',
        ],
        'steps': [
            'Spoon the yogurt into a bowl.',
            'Top with berries, granola and nuts.',
            'Drizzle honey over the top.',
        ],
    },
    {
        'id': 'salmon-sweet-potato', 'category': 'post',
        'name': 'Salmon & Sweet Potato Plate', 'emoji': '🐟',
        'gradient': 'linear-gradient(135deg,#ff9a9e,#fecfef)',
        'timing': 'A proper recovery meal, 1–2 h after',
        'prep_min': 10, 'cook_min': 25, 'calories': 560,
        'protein_g': 38, 'carbs_g': 48, 'fat_g': 22,
        'why': 'Salmon brings protein plus omega-3s that help calm training inflammation; sweet potato reloads glycogen with steady-release carbs.',
        'ingredients': [
            '1 salmon fillet (~130 g)', '1 medium sweet potato', '1 tsp olive oil',
            'Broccoli or greens', 'Lemon, salt & pepper',
        ],
        'steps': [
            'Cube the sweet potato, toss in oil and roast at 200°C for ~25 min.',
            'Season the salmon and bake or pan-sear for the last 12 min.',
            'Steam the greens.',
            'Plate up and finish with a squeeze of lemon.',
        ],
    },
    {
        'id': 'tuna-egg-wrap', 'category': 'post',
        'name': 'Tuna & Egg Protein Wrap', 'emoji': '🌯',
        'gradient': 'linear-gradient(135deg,#84fab0,#8fd3f4)',
        'timing': 'Fast recovery, within 45 min',
        'prep_min': 8, 'cook_min': 0, 'calories': 400,
        'protein_g': 34, 'carbs_g': 38, 'fat_g': 12,
        'why': 'Portable and protein-dense — tuna and egg repair muscle, the wrap and sweetcorn restock carbs. Easy to bag up for after a session.',
        'ingredients': [
            '1 large wholemeal wrap', '1 tin tuna (in spring water)', '1 boiled egg',
            '2 tbsp sweetcorn', '1 tbsp light mayo', 'Handful of salad leaves',
        ],
        'steps': [
            'Flake the tuna and mix with mayo and sweetcorn.',
            'Lay leaves on the wrap, add the tuna mix.',
            'Slice the egg on top.',
            'Roll up tightly and slice in half.',
        ],
    },
    # ---------------- RACE DAY ----------------
    {
        'id': 'race-pancakes', 'category': 'race',
        'name': 'Race-Morning Banana Pancakes', 'emoji': '🥞',
        'gradient': 'linear-gradient(135deg,#f6d365,#fda085)',
        'timing': '3 hours before your first race',
        'prep_min': 10, 'cook_min': 10, 'calories': 480,
        'protein_g': 18, 'carbs_g': 74, 'fat_g': 10,
        'why': 'A high-carb, familiar breakfast lays your race-day fuel foundation early — carb-loaded but gentle enough to settle well before warm-up.',
        'ingredients': [
            '1 cup oat or plain flour', '1 egg', '250 ml milk', '1 banana',
            '1 tsp baking powder', 'Maple syrup & berries to serve',
        ],
        'steps': [
            'Blend flour, egg, milk, banana and baking powder into a batter.',
            'Cook spoonfuls in a non-stick pan, ~1 min each side.',
            'Stack and top with berries and a little maple syrup.',
            'Eat calmly ~3 hours before you race.',
        ],
    },
    {
        'id': 'race-bagel', 'category': 'race',
        'name': 'Between-Heats Bagel', 'emoji': '🥯',
        'gradient': 'linear-gradient(135deg,#fddb92,#d1fdff)',
        'timing': 'Small top-up 60–90 min between swims',
        'prep_min': 4, 'cook_min': 2, 'calories': 300,
        'protein_g': 10, 'carbs_g': 52, 'fat_g': 6,
        'why': 'Between heats you need quick, easy carbs that top up energy without filling you up. A jam-and-nut-butter bagel is fast fuel that sits light.',
        'ingredients': [
            '1 plain bagel', '1 tbsp jam', '1 tsp peanut butter (thin layer)',
        ],
        'steps': [
            'Lightly toast the bagel.',
            'Spread a thin layer of peanut butter, then jam.',
            'Eat between races, then sip water/electrolytes.',
        ],
    },
    {
        'id': 'race-rice-chicken', 'category': 'race',
        'name': 'Pre-Final Chicken & White Rice', 'emoji': '🍗',
        'gradient': 'linear-gradient(135deg,#a8edea,#fed6e3)',
        'timing': '2.5–3 h before an afternoon final',
        'prep_min': 10, 'cook_min': 20, 'calories': 500,
        'protein_g': 34, 'carbs_g': 66, 'fat_g': 8,
        'why': 'Plain, tested and easy on the stomach: white rice for fast-available carbs, chicken for protein, minimal fat and fibre so nothing surprises you on race day.',
        'ingredients': [
            '150 g cooked white rice', '120 g chicken breast', '1 tsp olive oil',
            'Pinch of salt', 'Optional: cucumber on the side',
        ],
        'steps': [
            'Cook the chicken simply in a little oil with salt.',
            'Serve over warm white rice.',
            'Keep it plain — race day is not the day for new sauces.',
        ],
    },
    # ---------------- EVERYDAY ----------------
    {
        'id': 'everyday-salmon-quinoa', 'category': 'everyday',
        'name': 'Salmon, Quinoa & Greens', 'emoji': '🥗',
        'gradient': 'linear-gradient(135deg,#84fab0,#8fd3f4)',
        'timing': 'Balanced dinner any day',
        'prep_min': 10, 'cook_min': 20, 'calories': 540,
        'protein_g': 36, 'carbs_g': 46, 'fat_g': 22,
        'why': 'A complete daily plate — protein, complex carbs, healthy fats and greens — that hits a swimmer\'s recovery and micronutrient needs.',
        'ingredients': [
            '1 salmon fillet', '80 g quinoa (dry)', 'Handful of greens',
            '1 tsp olive oil', 'Lemon, garlic, salt & pepper',
        ],
        'steps': [
            'Cook the quinoa per packet (~15 min).',
            'Pan-sear the salmon in olive oil, skin-side first.',
            'Sauté greens with garlic.',
            'Plate quinoa, greens and salmon; finish with lemon.',
        ],
    },
    {
        'id': 'everyday-veg-stir-fry', 'category': 'everyday',
        'name': 'Beef & Veg Noodle Stir-Fry', 'emoji': '🍜',
        'gradient': 'linear-gradient(135deg,#ff9a9e,#fad0c4)',
        'timing': 'Carb-loaded dinner on heavy days',
        'prep_min': 12, 'cook_min': 12, 'calories': 580,
        'protein_g': 32, 'carbs_g': 70, 'fat_g': 16,
        'why': 'High-carb noodles refill glycogen after big sessions, lean beef repairs muscle, and a rainbow of veg covers the vitamins that keep training consistent.',
        'ingredients': [
            '150 g egg noodles', '120 g lean beef strips', 'Mixed veg (peppers, broccoli, carrot)',
            '1 tbsp soy sauce', '1 tsp sesame oil', '1 clove garlic', 'Thumb of ginger',
        ],
        'steps': [
            'Cook the noodles and set aside.',
            'Stir-fry beef in sesame oil over high heat, then remove.',
            'Fry garlic, ginger and veg until just tender.',
            'Return beef and noodles, add soy sauce, toss and serve.',
        ],
    },
]


def meals_by_category():
    grouped = {c['key']: [] for c in CATEGORIES}
    for m in MEALS:
        grouped.setdefault(m['category'], []).append(m)
    return grouped
