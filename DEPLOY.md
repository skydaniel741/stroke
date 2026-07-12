# Deploying STROKE to Render (testing rollout)

Code side is ready (`wsgi.py`, `render.yaml`, gunicorn added, debug disabled by
default). Everything below is manual steps in your browser — none of it can
be done from here.

## 1. Push this code to GitHub

Once you're happy with the changes in this session:

```
git add -A
git commit -m "Prep for Render deploy: gunicorn, wsgi entrypoint, render.yaml"
git push origin main
```

## 2. Create the Render account + deploy

1. Go to render.com, sign up using **strokeswimhq@gmail.com**.
2. Dashboard → **New +** → **Blueprint**.
3. Connect your GitHub account, pick the `dannysky111/stroke` repo. Render
   reads `render.yaml` automatically and proposes the `stroke` web service.
4. Click **Apply**. First deploy will fail or sit unhealthy until you set the
   secret env vars below — that's expected.

## 3. Set environment variables

Render dashboard → your `stroke` service → **Environment**. Add:

| Key | Value |
|---|---|
| `RESEND_API_KEY` | your existing Resend API key from `.env` |
| `EMAIL_FROM` | leave unset for now (falls back to `onboarding@resend.dev`) — set once you verify your own domain in step 6 |
| `ANTHROPIC_API_KEY` | your existing key from `.env` |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | your existing values from `.env` |

`SECRET_KEY`, `FLASK_DEBUG`, `ANTHROPIC_MODEL`, `PYTHON_VERSION` are already
set by `render.yaml`. Save, then **Manual Deploy → Deploy latest commit** to
pick them up.

Your test site will be live at `https://stroke.onrender.com` (or whatever
name Render assigns) within a few minutes.

## 4. Google sign-in on the new URL

Your Google OAuth app is almost certainly still in **Testing** publish status
in Google Cloud Console, which means:
- Only pre-approved testers (Console → APIs & Services → OAuth consent
  screen → **Test users**) can sign in — add each tester's Google email
  there, up to 100.
- Everyone sees an "unverified app" warning screen before continuing — normal
  for testing, not a bug.

Also add the new domain to **APIs & Services → Credentials → your OAuth
client**:
- Authorized redirect URI: `https://stroke.onrender.com/auth/google/callback`
- Authorized JavaScript origin: `https://stroke.onrender.com`

Repeat this once you're on your real domain (step 6).

## 5. Buy a domain

Any registrar works; Cloudflare Registrar sells at wholesale cost (no markup)
and throws in free DNS — a good default if you don't already have a
preference. Namecheap/Porkbun are fine easy alternatives.

## 6. Point the domain at Render + verify email sending

1. Render dashboard → your service → **Settings → Custom Domain** → add your
   domain. Render shows you the exact DNS record to add (usually a `CNAME`
   for a subdomain like `app.yourdomain.com`, or an `A`/`ALIAS` record for
   the bare domain) — free on Render's free tier, and Render issues the
   HTTPS certificate automatically.
2. Add that record at your registrar's DNS settings.
3. Resend dashboard → **Domains** → add your domain → add the SPF/DKIM
   records Resend gives you at your registrar too. Once verified, set
   `EMAIL_FROM` in Render to something like `STROKE <hello@yourdomain.com>`.
4. Update the Google OAuth redirect URI / origin (step 4) to your real
   domain once it's live.

## Known limitations of the free tier (expected, not bugs)

- **No persistent disk**: `stroke.db` resets to whatever's in the git repo
  on every deploy. Fine for early testing where occasional resets are OK;
  when you outgrow that, add a Render persistent disk (paid) or switch
  `DATABASE_URL` to a managed Postgres — no app code changes needed either
  way, `app.py` already reads `DATABASE_URL` from the environment.
- **Cold starts**: the free instance spins down after ~15 minutes of no
  traffic and takes 30-60s to wake on the next request. Testers will see a
  slow first load after idle periods.
