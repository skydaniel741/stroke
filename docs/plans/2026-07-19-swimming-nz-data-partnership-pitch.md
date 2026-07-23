# Swimming NZ data partnership — outreach draft

Date: 2026-07-19
Status: Draft for Danny to review, personalize, and send (not sent by Claude).

## Context

STROKE's coaches asked for a way to look up a swimmer's official race times/PBs on demand (e.g. "what's Daniel's 100 Free PB?") without manually digging through meet results. Research this session found:

- Swimming NZ's own results tooling is search-by-stroke-and-date-range, not swimmer-name search, and the live site wasn't reachable to confirm current state.
- The two sites with real per-swimmer profile pages and name search (Swimrankings.net, SwimCloud) both actively block automated/bot access (403 responses).
- Meet Mobile has no public API and gates full results behind a paid subscription.
- Mytogs (an existing NZ swim-times app) advertises a partnership with Swimming NZ for its data — suggesting the legitimate path other apps in this space have taken is a direct data-sharing arrangement, not scraping.

Given that, scraping isn't a reliable or appropriate foundation. A direct conversation with Swimming NZ is the right next step. Below is a draft pitch — fill in the bracketed specifics before sending.

## Draft email / one-pager

---

**Subject: Partnership enquiry — official times data for STROKE (NZ swim club software)**

Hi [Swimming NZ contact name / "team" if unknown],

I'm Danny, building STROKE — software for NZ swim coaches to run their squads: attendance, training sets, and now performance tracking for their swimmers. It's used by [X coaches / clubs — fill in current real numbers, or omit this line if pre-launch].

One thing coaches keep asking for: an easy way to check a swimmer's official race times without digging through meet results by hand. Right now that means manually searching your results database or a meet's results PDF — doable, but slow, especially for a coach checking several swimmers at once.

I'd like to explore a data-sharing arrangement so STROKE can show a swimmer's official SNZ times directly to their own coach, properly attributed back to Swimming NZ as the source. Specifically, I'm hoping to discuss:

- **Scope**: read-only access to public competition results (times, events, meets) — not registration, contact, or any other swimmer data.
- **Shape**: whichever is easiest on your side — a lookup API (name/event → times), a periodic bulk export we sync, or even just a documented, rate-limited way to query your existing results database programmatically.
- **Attribution**: happy to credit Swimming NZ as the data source wherever times are shown, and/or link back to your results database.

For context on why this might be worth your time too: coaches using STROKE would be pulling up your official database more often (via the coach's own lookups), and it's one more way NZ swimming data gets used to help coaches do their job, rather than swimmers/coaches relying on incomplete or unofficial trackers.

Happy to jump on a call or send more detail on STROKE if useful. What's the right team/process for a request like this?

Thanks,
Danny
[contact info]
[stroke website/link if public]

---

## Notes for Danny before sending

- Fill in real usage numbers (or cut that sentence) — don't overstate scale you don't have yet; a small/early product framing is fine and honest.
- If you don't know the right contact at Swimming NZ, their general enquiries address or a "Partnerships"/"Technology" contact (if listed on their site) is the right starting point — worth checking swimming.org.nz directly once it's reachable again, since I couldn't load it during this session's research.
- Consider mentioning Mytogs by name if you want to signal "there's precedent for this" — or leave it out if you'd rather not reference a competitor/adjacent product directly.
- If Swimming NZ says no or goes quiet, the fallback options discussed this session (a best-effort agent against whatever's reachable, or a coach-assisted manual-entry flow) are still on the table — see this session's brainstorming for that context.
