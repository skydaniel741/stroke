"""Curated swimmer-nutrition dataset for the solo nutrition section.

Grounded in standard sports-nutrition timing guidance:
- Pre-training: a carb-forward meal 2-3 h before, or fast carbs 30-60 min before;
  keep fat/fibre low close to the session.
- Post-training: 30-60 g carbs + 15-30 g protein within ~60 min to refuel and repair.
- Race day: familiar, high-carb, easy-to-digest food; nothing new.
- Everyday: balanced plates that hit a swimmer's daily carb + protein needs.

Static content (no DB) so the section always renders. Each meal carries a full
recipe plus the stats the UI shows: prep/cook time, calories, macros, timing.
Photos are downloaded locally under static/images/ (not hotlinked), `photo` is
a path relative to the static folder, passed through `url_for('static', ...)`
in the template.
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
        'name': 'Peanut Butter Overnight Oats',
        'photo': 'images/nutrition/pb-overnight-oats.jpg',
        'timing': 'Eat 2 to 3 hours before training',
        'prep_min': 5, 'cook_min': 0, 'calories': 430,
        'protein_g': 16, 'carbs_g': 60, 'fat_g': 13,
        'why': 'Slow-release oats top up glycogen while banana adds quick carbs, energy that lasts a full session without weighing you down. The fat from peanut butter is small enough not to slow digestion if you eat this a couple of hours out.',
        'tip': 'Make a batch of 3-4 jars on Sunday night so pre-training breakfast is grab-and-go all week.',
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
        'name': 'Chicken & Rice Power Bowl',
        'photo': 'images/nutrition/chicken-rice-bowl-pre.jpg',
        'timing': 'Eat 3 hours before training',
        'prep_min': 10, 'cook_min': 20, 'calories': 520,
        'protein_g': 35, 'carbs_g': 68, 'fat_g': 9,
        'why': 'A classic pre-session plate: plenty of easy carbs from white rice, lean protein from chicken, and low fat so it clears your stomach in time. White rice over brown here on purpose, less fibre means less GI risk mid-set.',
        'tip': 'If training is earlier than 3 hours out, swap in half the rice and skip the spinach to speed up digestion.',
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
        'name': 'Banana & Honey Toast',
        'photo': 'images/nutrition/banana-honey-toast.jpg',
        'timing': 'Quick carbs 30 to 60 min before',
        'prep_min': 4, 'cook_min': 2, 'calories': 260,
        'protein_g': 6, 'carbs_g': 50, 'fat_g': 3,
        'why': 'When the session is close, you want fast carbs and almost no fat or fibre. Toast + banana + honey digests quickly and tops off the tank without the sluggish feeling a heavier meal would cause.',
        'tip': 'White bread digests faster than wholegrain this close to a session, save the wholegrain loaf for everyday meals.',
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
    {
        'id': 'oatmeal-berry-bowl', 'category': 'pre',
        'name': 'Berry & Honey Porridge',
        'photo': 'images/nutrition/oatmeal-berry-bowl.jpg',
        'timing': 'Eat 2 hours before an early session',
        'prep_min': 5, 'cook_min': 8, 'calories': 380,
        'protein_g': 12, 'carbs_g': 64, 'fat_g': 7,
        'why': 'Warm porridge is gentle on an early-morning stomach, and berries add fast carbs plus antioxidants without any heavy fat to digest. A good option when a jar of overnight oats didn\'t get prepped the night before.',
        'tip': 'Frozen berries work fine here and are cheaper. Just add them straight to the pan for the last minute of cooking.',
        'ingredients': [
            '60 g rolled oats', '250 ml milk or water', '1 handful mixed berries',
            '1 tbsp honey', 'Pinch of salt',
        ],
        'steps': [
            'Simmer oats in milk or water for 6 to 8 minutes, stirring occasionally.',
            'Spoon into a bowl and top with berries.',
            'Drizzle with honey and a pinch of salt.',
        ],
    },
    # ---------------- AFTER TRAINING ----------------
    {
        'id': 'recovery-choc-milk', 'category': 'post',
        'name': 'Chocolate Milk Recovery Shake',
        'photo': 'images/nutrition/recovery-choc-milk.jpg',
        'timing': 'Within 30 min of finishing',
        'prep_min': 3, 'cook_min': 0, 'calories': 320,
        'protein_g': 20, 'carbs_g': 45, 'fat_g': 6,
        'why': 'One of the most researched recovery options, a near-perfect 2:1 carb-to-protein ratio to restock glycogen and kick-start muscle repair while your body is most receptive, often called the "anabolic window."',
        'tip': 'Keep a bottle of ready-made chocolate milk in your bag for the days you can\'t get to a blender straight after the pool.',
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
        'name': 'Greek Yogurt Berry Bowl',
        'photo': 'images/nutrition/greek-yogurt-berry-bowl.jpg',
        'timing': 'Within 60 min of finishing',
        'prep_min': 5, 'cook_min': 0, 'calories': 340,
        'protein_g': 24, 'carbs_g': 42, 'fat_g': 7,
        'why': 'Greek yogurt is packed with protein for repair, berries and honey bring the carbs and antioxidants, and granola adds crunch and more fuel, an easy no-cook option for after an evening session.',
        'tip': 'Use full-fat Greek yogurt if you\'re training twice a day, the extra calories are useful, not something to avoid.',
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
        'name': 'Salmon & Sweet Potato Plate',
        'photo': 'images/nutrition/salmon-sweet-potato.jpg',
        'timing': 'A proper recovery meal, 1 to 2 h after',
        'prep_min': 10, 'cook_min': 25, 'calories': 560,
        'protein_g': 38, 'carbs_g': 48, 'fat_g': 22,
        'why': 'Salmon brings protein plus omega-3s that help calm training inflammation; sweet potato reloads glycogen with steady-release carbs. A good choice for the main meal after your hardest session of the day.',
        'tip': 'Roast a tray of extra sweet potato at the same time. It reheats well for tomorrow\'s lunch.',
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
        'name': 'Tuna & Egg Protein Wrap',
        'photo': 'images/nutrition/tuna-egg-wrap.jpg',
        'timing': 'Fast recovery, within 45 min',
        'prep_min': 8, 'cook_min': 0, 'calories': 400,
        'protein_g': 34, 'carbs_g': 38, 'fat_g': 12,
        'why': 'Portable and protein-dense, tuna and egg repair muscle, the wrap and sweetcorn restock carbs. Easy to bag up for after a session when you\'re heading straight from the pool deck to school or work.',
        'tip': 'Boil a batch of eggs at the start of the week so this takes under five minutes to put together.',
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
    {
        'id': 'turkey-sweet-potato-hash', 'category': 'post',
        'name': 'Turkey & Sweet Potato Hash',
        'photo': 'images/nutrition/turkey-sweet-potato-hash.jpg',
        'timing': 'A hearty recovery meal, 1 to 2 h after',
        'prep_min': 10, 'cook_min': 20, 'calories': 520,
        'protein_g': 36, 'carbs_g': 44, 'fat_g': 18,
        'why': 'Lean turkey supplies the protein your muscles need to rebuild, while pan-fried sweet potato and peppers restock carbs and micronutrients in one skillet, a one-pan meal for busy training weeks.',
        'tip': 'Double the batch and portion into containers. It reheats better than most recovery meals for a next-day lunch.',
        'ingredients': [
            '150 g turkey mince', '1 medium sweet potato, diced', '1/2 red pepper, diced',
            '1 tsp olive oil', 'Paprika, salt & pepper', 'Handful of spinach',
        ],
        'steps': [
            'Par-boil the sweet potato for 5 minutes, then drain.',
            'Brown the turkey mince in olive oil with paprika.',
            'Add the sweet potato and pepper, fry until golden.',
            'Stir through spinach until wilted and serve.',
        ],
    },
    # ---------------- RACE DAY ----------------
    {
        'id': 'race-pancakes', 'category': 'race',
        'name': 'Race-Morning Banana Pancakes',
        'photo': 'images/nutrition/race-pancakes.jpg',
        'timing': '3 hours before your first race',
        'prep_min': 10, 'cook_min': 10, 'calories': 480,
        'protein_g': 18, 'carbs_g': 74, 'fat_g': 10,
        'why': 'A high-carb, familiar breakfast lays your race-day fuel foundation early, carb-loaded but gentle enough to settle well before warm-up. Never trial a brand-new breakfast on a race day; this is deliberately simple.',
        'tip': 'Practice this exact breakfast before a normal training morning at least once so your stomach already knows it agrees with you.',
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
        'name': 'Between-Heats Bagel',
        'photo': 'images/nutrition/race-bagel.jpg',
        'timing': 'Small top-up 60 to 90 min between swims',
        'prep_min': 4, 'cook_min': 2, 'calories': 300,
        'protein_g': 10, 'carbs_g': 52, 'fat_g': 6,
        'why': 'Between heats you need quick, easy carbs that top up energy without filling you up. A jam-and-nut-butter bagel is fast fuel that sits light in the stomach before your next swim.',
        'tip': 'Pack this pre-made in your meet bag, don\'t rely on finding food at the venue between sessions.',
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
        'name': 'Pre-Final Chicken & White Rice',
        'photo': 'images/nutrition/race-rice-chicken.jpg',
        'timing': '2.5 to 3 h before an afternoon final',
        'prep_min': 10, 'cook_min': 20, 'calories': 500,
        'protein_g': 34, 'carbs_g': 66, 'fat_g': 8,
        'why': 'Plain, tested and easy on the stomach: white rice for fast-available carbs, chicken for protein, minimal fat and fibre so nothing surprises you on race day.',
        'tip': 'Ask the meet hotel or venue café in advance if plain rice and chicken are on the menu, don\'t assume you can improvise this on the day.',
        'ingredients': [
            '150 g cooked white rice', '120 g chicken breast', '1 tsp olive oil',
            'Pinch of salt', 'Optional: cucumber on the side',
        ],
        'steps': [
            'Cook the chicken simply in a little oil with salt.',
            'Serve over warm white rice.',
            'Keep it plain, race day is not the day for new sauces.',
        ],
    },
    {
        'id': 'race-pasta-night', 'category': 'race',
        'name': 'Night-Before Pasta with Chicken',
        'photo': 'images/nutrition/race-pasta-night.jpg',
        'timing': 'The evening before a big meet',
        'prep_min': 10, 'cook_min': 15, 'calories': 620,
        'protein_g': 32, 'carbs_g': 88, 'fat_g': 12,
        'why': 'The classic carb-load dinner, plain pasta with lean chicken tops off glycogen stores overnight without anything rich or unfamiliar that could upset your stomach on race morning.',
        'tip': 'Eat this at a normal dinner time, not right before bed. You want it mostly digested before you sleep.',
        'ingredients': [
            '100 g dry pasta', '120 g chicken breast', '1 tbsp olive oil',
            'Tomato passata', 'Basil, salt & pepper', 'Parmesan to serve',
        ],
        'steps': [
            'Cook pasta according to packet instructions.',
            'Pan-fry the chicken in olive oil, then slice.',
            'Warm the passata with basil and seasoning.',
            'Toss the pasta through the sauce and top with chicken and parmesan.',
        ],
    },
    # ---------------- EVERYDAY ----------------
    {
        'id': 'everyday-salmon-quinoa', 'category': 'everyday',
        'name': 'Salmon, Quinoa & Greens',
        'photo': 'images/nutrition/everyday-salmon-quinoa.jpg',
        'timing': 'Balanced dinner any day',
        'prep_min': 10, 'cook_min': 20, 'calories': 540,
        'protein_g': 36, 'carbs_g': 46, 'fat_g': 22,
        'why': 'A complete daily plate, protein, complex carbs, healthy fats and greens, that hits a swimmer\'s recovery and micronutrient needs without needing to be timed around a specific session.',
        'tip': 'Cook a big batch of quinoa on a rest day and freeze portions. It cuts this down to a 10-minute dinner.',
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
        'name': 'Beef & Veg Noodle Stir-Fry',
        'photo': 'images/nutrition/everyday-veg-stir-fry.jpg',
        'timing': 'Carb-loaded dinner on heavy days',
        'prep_min': 12, 'cook_min': 12, 'calories': 580,
        'protein_g': 32, 'carbs_g': 70, 'fat_g': 16,
        'why': 'High-carb noodles refill glycogen after big sessions, lean beef repairs muscle, and a rainbow of veg covers the vitamins that keep training consistent through a heavy block.',
        'tip': 'Prep the veg and sauce the night before, high heat, quick stir-frying is the part that actually takes no time.',
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
    {
        'id': 'everyday-egg-avocado-toast', 'category': 'everyday',
        'name': 'Egg & Avocado Toast',
        'photo': 'images/nutrition/everyday-egg-avocado-toast.jpg',
        'timing': 'Balanced breakfast any day',
        'prep_min': 8, 'cook_min': 6, 'calories': 420,
        'protein_g': 20, 'carbs_g': 36, 'fat_g': 21,
        'why': 'Eggs and avocado bring steady protein and good fats to start the day, while wholegrain toast supplies the fibre and carbs a light training morning still needs, best saved for rest days or light sessions given the fat content.',
        'tip': 'Not the right choice within 2 hours of a hard session, save it for mornings with no training or an easy recovery swim.',
        'ingredients': [
            '2 slices wholegrain bread', '2 eggs', '1/2 avocado, mashed',
            'Chilli flakes, salt & pepper', 'Squeeze of lemon',
        ],
        'steps': [
            'Toast the bread.',
            'Mash the avocado with lemon, salt and pepper, spread over toast.',
            'Fry or poach the eggs and place on top.',
            'Finish with a pinch of chilli flakes.',
        ],
    },
    {
        'id': 'everyday-chickpea-bowl', 'category': 'everyday',
        'name': 'Chickpea & Veg Grain Bowl',
        'photo': 'images/nutrition/everyday-chickpea-bowl.jpg',
        'timing': 'A lighter balanced lunch any day',
        'prep_min': 10, 'cook_min': 15, 'calories': 460,
        'protein_g': 20, 'carbs_g': 62, 'fat_g': 14,
        'why': 'A plant-forward option that still hits swimmer targets, chickpeas and grains bring steady carbs and protein, and the veg covers fibre and micronutrients on lighter training days.',
        'tip': 'Swap the roasted veg with whatever\'s in the fridge. This recipe is forgiving and works with almost any vegetable combination.',
        'ingredients': [
            '150 g cooked chickpeas', '80 g cooked brown rice or couscous', 'Roasted veg (courgette, pepper, red onion)',
            '1 tbsp tahini or olive oil', 'Lemon juice, cumin, salt & pepper',
        ],
        'steps': [
            'Roast the veg with a little oil and cumin until tender.',
            'Warm the chickpeas and grain.',
            'Combine everything in a bowl.',
            'Drizzle with tahini or olive oil and lemon juice.',
        ],
    },
    {
        'id': 'rice-cakes-pb-banana', 'category': 'pre',
        'name': 'Rice Cakes, Peanut Butter & Banana',
        'photo': 'images/nutrition/rice-cakes-pb-banana.jpg',
        'timing': 'Grab 45-60 min before training',
        'prep_min': 3, 'cook_min': 0, 'calories': 300,
        'protein_g': 8, 'carbs_g': 48, 'fat_g': 9,
        'why': "The classic pool-bag snack when you don't have time for a real meal. Rice cakes are almost pure fast carbs, the banana tops up quick energy, and a thin layer of peanut butter keeps it from spiking and crashing you.",
        'tip': 'Keep a pack of rice cakes in your kit bag so you always have a pre-set option, even on a rushed day.',
        'ingredients': ['2-3 plain rice cakes', '1 tbsp peanut butter', '1 banana, sliced', 'Drizzle of honey (optional)'],
        'steps': [
            'Spread a thin layer of peanut butter on each rice cake.',
            'Top with banana slices.',
            'Add a drizzle of honey if you want a bit more quick carb.',
            'Eat about an hour out so it settles before you dive in.',
        ],
    },
    {
        'id': 'cottage-cheese-berries', 'category': 'post',
        'name': 'Cottage Cheese & Berry Bowl',
        'photo': 'images/nutrition/cottage-cheese-berries.jpg',
        'timing': 'Within the hour after training',
        'prep_min': 4, 'cook_min': 0, 'calories': 320,
        'protein_g': 28, 'carbs_g': 34, 'fat_g': 6,
        'why': "A big hit of slow-digesting protein with barely any effort. Cottage cheese is loaded with casein, so it keeps feeding your muscles for hours, and the berries and honey refill glycogen while you cool down.",
        'tip': "If you find cottage cheese bland, blend it smooth first, it turns into a thick, almost mousse-like base.",
        'ingredients': ['200 g cottage cheese', 'Handful of mixed berries', '1 tbsp honey', 'Sprinkle of granola or oats'],
        'steps': [
            'Spoon the cottage cheese into a bowl.',
            'Top with berries and a drizzle of honey.',
            'Scatter granola or oats over the top for crunch and extra carbs.',
        ],
    },
    {
        'id': 'trail-mix-jar', 'category': 'everyday',
        'name': 'Swimmer Trail Mix',
        'photo': 'images/nutrition/trail-mix-jar.jpg',
        'timing': 'Between-session or school/work snack',
        'prep_min': 5, 'cook_min': 0, 'calories': 380,
        'protein_g': 12, 'carbs_g': 40, 'fat_g': 20,
        'why': "A calorie-dense grab bag for swimmers who struggle to eat enough between sessions. Nuts bring energy and healthy fat, dried fruit refills carbs, and it keeps in your bag for days without going off.",
        'tip': 'Batch a big jar on Sunday and portion into small bags, then you always have a snack that actually has calories in it.',
        'ingredients': ['Almonds & cashews', 'Dried mango or raisins', 'Dark chocolate chips', 'Pumpkin seeds', 'A few pretzels for salt'],
        'steps': [
            'Tip everything into a large jar in roughly equal parts.',
            'Shake to mix.',
            'Portion into snack bags for grab-and-go.',
        ],
    },
]

# Recommended supplements, categories sports dietitians commonly suggest for
# training swimmers, each with real, third-party-tested brand picks so a swimmer
# knows *what to actually buy*, not just the category. Brands here are chosen for
# NSF Certified for Sport / Informed Sport certification (the standard drug-tested
# athletes are told to look for). Informational only; not medical advice, and
# drug-tested athletes should always confirm current certification themselves.
#
# `evidence` = how strong the research backing is (rated so the UI can sort the
# best-supported options first). `brands` = the actual product picks.
PRODUCTS = [
    {
        'id': 'creatine',
        'name': 'Creatine Monohydrate',
        'photo': 'images/products/creatine.jpg',
        'category': 'Performance',
        'evidence': 'strong',
        'why': "The one supplement with the clearest research win for swimmers. A 2025 meta-analysis found creatine was the only one to show a real performance bump, it helps most with the repeat-sprint and power work sprinters live on.",
        'use_case': 'Daily, 3-5 g, any time (consistency matters more than timing)',
        'detail': "Plain creatine monohydrate is all you need, the fancier forms aren't worth the extra money. 3-5 g every day, and you don't have to 'load' it.",
        'brands': ['Thorne Creatine (NSF Certified for Sport)', 'Klean Athlete Creatine (NSF)', 'Transparent Labs Creatine HMB'],
    },
    {
        'id': 'electrolyte-tabs',
        'name': 'Electrolyte Hydration',
        'photo': 'images/products/electrolyte-tabs.jpg',
        'category': 'Hydration',
        'evidence': 'moderate',
        'why': "Long or hot sessions and double days sweat out sodium and potassium that plain water doesn't replace. Electrolytes in your bottle help you actually hold onto the fluid you drink instead of it running straight through you.",
        'use_case': 'Doubles, hot pools, or long open-water sessions',
        'detail': "Aim for 300-500 mg sodium per serving, that's the range hydration research targets for hard sweaters. Drop it in at the start of a long session, not once you're already flat.",
        'brands': ['Transparent Labs Hydrate (Informed Sport)', 'Thorne Catalyte (NSF)', 'Kaged Hydra-Charge'],
    },
    {
        'id': 'whey-protein',
        'name': 'Whey Protein',
        'photo': 'images/products/whey-protein.jpg',
        'category': 'Recovery',
        'evidence': 'strong',
        'why': "A fast, easy way to hit your post-session protein target when a full meal isn't practical straight after training. Mixes in seconds and digests quick during the recovery window.",
        'use_case': 'Post-training recovery shakes',
        'detail': "One scoop (roughly 20-25 g protein) with milk covers most of a session's recovery. Isolate digests faster than concentrate if hard sets leave your stomach touchy.",
        'brands': ['Klean Athlete Klean Protein Isolate (NSF)', 'Myprotein Impact Whey', 'Transparent Labs Whey Isolate (Informed Sport)'],
    },
    {
        'id': 'omega-3-fish-oil',
        'name': 'Omega-3 Fish Oil',
        'photo': 'images/products/omega-3-fish-oil.jpg',
        'category': 'Everyday health',
        'evidence': 'moderate',
        'why': "Recommended by sports dietitians to support joint and heart health across a heavy block, especially if you don't eat oily fish a few times a week.",
        'use_case': 'Daily, with a meal',
        'detail': "General athlete guidance sits around 1-2 g combined EPA/DHA a day, check the label since it varies a lot. Take it with food so it doesn't repeat on you.",
        'brands': ['Thorne Super EPA (NSF)', 'Nordic Naturals Ultimate Omega Sport (Informed Sport)', 'Klean Athlete Klean Omega'],
    },
    {
        'id': 'vitamin-d3',
        'name': 'Vitamin D3',
        'photo': 'images/products/vitamin-d3.jpg',
        'category': 'Everyday health',
        'evidence': 'moderate',
        'why': "Indoor swimmers get barely any sun, and low vitamin D is one of the most common things flagged in athlete bloodwork. It backs up bone and immune health.",
        'use_case': 'Daily, especially in winter',
        'detail': "A blood test is the only way to know your real level. Many sports doctors suggest 1000-2000 IU a day as maintenance for indoor athletes, but get tested before assuming you need more.",
        'brands': ['Thorne Vitamin D/K2 (NSF)', 'Klean Athlete Vitamin D3'],
    },
    {
        'id': 'magnesium',
        'name': 'Magnesium',
        'photo': 'images/products/magnesium.jpg',
        'category': 'Recovery',
        'evidence': 'emerging',
        'why': "Often reached for to help with cramping and sleep during heavy-volume weeks, when what you lose through sweat starts to add up.",
        'use_case': 'Evenings, during high-volume weeks',
        'detail': "Glycinate or citrate absorb better and sit gentler on your gut than magnesium oxide.",
        'brands': ['Thorne Magnesium Bisglycinate', 'Pure Encapsulations Magnesium Glycinate'],
    },
    {
        'id': 'tart-cherry-juice',
        'name': 'Tart Cherry Juice',
        'photo': 'images/products/tart-cherry-juice.jpg',
        'category': 'Recovery',
        'evidence': 'emerging',
        'why': "Studied in endurance athletes for easing muscle soreness and helping sleep, a natural option worth a try around your hardest days.",
        'use_case': 'Evening after a hard or high-volume session',
        'detail': "The research uses concentrated tart (Montmorency) cherry juice, around 250-350 ml a day near heavy training. Regular sweet cherry juice doesn't show the same effect.",
        'brands': ['CherryActive / CherryPharm Concentrate', 'Cheribundi Tart Cherry'],
    },
]


def meals_by_category():
    grouped = {c['key']: [] for c in CATEGORIES}
    for m in MEALS:
        grouped.setdefault(m['category'], []).append(m)
    return grouped


_BY_ID = {m['id']: m for m in MEALS}


def meal_by_id(meal_id):
    return _BY_ID.get(meal_id)


_PRODUCT_BY_ID = {p['id']: p for p in PRODUCTS}


def product_by_id(product_id):
    return _PRODUCT_BY_ID.get(product_id)
