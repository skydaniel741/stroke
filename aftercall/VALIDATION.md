# AfterCall — 7-day validation test

Goal: prove a NZ trades business will pay for after-hours call answering BEFORE
spending anything. Total spend this week: $0.

## The test

**Day 1–2 — verify the problem locally (free)**
- Build a list of 50 trades businesses (plumbers, electricians, drainlayers,
  arborists, locksmiths) in Wellington + one secondary city from Google Maps.
- Ring 25 of them at 7:00–8:30pm. Record: answered / voicemail / dead end.
- This is your own missed-call statistic for the pitch. If fewer than 30% miss
  the call, the problem is weaker than the research says — that matters.

**Day 3–6 — sell the outcome (free)**
- Call 30 businesses during work hours (8–9am is when tradies answer, they're
  driving). Script below. Offer: 14-day free trial, set up for them, $299/mo
  after, cancel anytime, founding rate locked.
- Walk into 5–10 trade counters (Plumbing World, Mico) and talk to whoever's
  there. Ask who runs solo. Get names.
- Send 30 DMs/emails to trades businesses that advertise "24/7" but went to
  voicemail in your Day 1 test — that's the sharpest opener there is:
  "I rang your 24/7 line at 7:40pm Tuesday. It went to voicemail. I build the
  thing that catches those calls — 2-minute demo: [link]"
- Show the live demo (/demo) on your phone during walk-ins.

**Day 7 — count.**

## Go / no-go (decided upfront, no moving the line)

- **GO**: ≥5 of ~60 contacted agree to the free trial AND ≥2 say words to the
  effect of "if it catches jobs I'll pay $299." Then and only then spend:
  Twilio number + Vapi/Pipecat minutes ≈ NZ$50–150 for month one.
- **NO-GO**: <3 trial agreements. Write down every objection verbatim. One
  permitted pivot within the same customer (e.g. quote-follow-up texts instead
  of call answering — same tradies, same wallet), retest 7 days. No idea-hopping
  beyond that.

## Phone script (30 seconds)

"Hey, is this the owner? — I'll be quick. When you're on the tools or it's
after six, where do your calls go? ... Right. Research says about 4 in 10
after-hours calls to trades go unanswered and most of those people just ring
the next guy on Google. I've built an AI receptionist that answers as your
business, sorts real emergencies from tyre-kickers, and texts you the job with
the caller's name, number and address. I'm giving 5 Wellington trades a free
2-week trial — I set it all up, you just divert your phone. Worth a look?"

Objection: "AI answering my phone? Nah." → "Fair. It's better than voicemail,
not better than you. Want to hear it? Ring this number now and try to stump
it." (Give demo line once live.)

## Cost sheet (under the $500 cap)

| Item | NZD |
|---|---|
| Domain (aftercall.nz or similar) | ~$30/yr |
| Twilio NZ number | ~$10/mo |
| Voice minutes (Vapi ~US$0.05–0.15/min, or self-host Pipecat + Claude to cut this) | ~$30–80/mo at trial volume |
| Anthropic API | ~$10–20/mo |
| **Total to first paying client** | **< NZ$150** |

## Next 3 steps to scale (only after 3+ paying)

1. Swap the browser demo brain onto a real phone line: Pipecat (open-source,
   Twilio-native) or Vapi if speed matters more than margin. Same system
   prompt, same lead pipeline — the code in `ai.py` is the product.
2. Real SMS via Twilio to the owner (escalation + 7:30am digest), remove the
   "prototype" labels, per-client config (business name, trade, service area).
3. Referral loop: every client's invoice includes "know another tradie drowning
   in missed calls? A month free for both of you." Trades talk to trades.
