# Overnight report — Florence Workforce Economist

**Window:** 2026-06-01 night → 2026-06-02 morning. All work pushed to `main`
(deploying live), each commit verified green before push.

## What shipped (9 commits, #213–#221)

**Stripe (you'd just opened the account)**
- **#213** — Stripe URLs are now env-driven (no hardcoded `REPLACE_WITH_REAL_URL`).
  Set `STRIPE_SUBSCRIPTION_URL` / `STRIPE_PLACEMENT_URL` / `STRIPE_CHECKOUT_URL`
  (Payment Links — public, not secret). Both calculator CTAs fall back to a
  `FLORENCE_CONTACT_EMAIL` mailto when unset, so there's never a dead button.
  All documented in `.streamlit/secrets.toml.example`.

**Hardening (so nothing regressed overnight)**
- **#214** — committed `tests/` suite: 22 module unit tests + an all-21-views
  smoke + a word-boundary compliance scan. Runs under pytest *or* as plain
  scripts (`python3 tests/test_modules.py`). It immediately caught a real
  pre-existing bug — `hospital_table` clobbered the nav variable and crashed
  every later view; fixed.

**Outreach quality**
- **#215** — full follow-up **email sequence** (intro → follow-up → share-
  availability → breakup), not just the intro. Popup step-selector defaults to
  where the cadence is; the whole sequence ships in the bundle/pack.
- **#216** — **AI-personalized opener** (`ai_opener.py`), dormant on
  `ANTHROPIC_API_KEY`, deterministic local-data fallback, AI output
  compliance-checked before use.

**Workflow**
- **#217** — territory / **"My book"** ownership (`ownership.py`): assign systems
  to reps; My-book filter on Today + Priority queue.
- **#218** — **snooze / reminders** (`reminders.py`): defer an account 3/7/14/30
  days; it drops off Today until its date.
- **#219** — **priority map** (`geo.py`): top targets on a US map in Today.

**Polish**
- **#220** — **account dossier** (`dossier.py`): one-page, on-brand, print-clean
  HTML handoff (hero + contact + call script + outreach intro + timeline),
  HTML-escaped. Download in the popup.
- **#221** — **per-rep weekly digest** in the Funnel view (7/14/30-day window;
  outreach / replies / calls-notes / hires; "my week" callout).

## Verification
- Every commit: `py_compile` + the relevant unit tests + the all-views smoke
  (all 21 nav views render with zero exceptions).
- Final live check: opened a system's docs popup in the running app — owner
  line, cadence, outcome buttons, snooze, and the email/call-script expanders
  all render cleanly, no errors.
- Compliance suite green: no FICA/visa/tax/immigration on email, mailpiece, or
  call script (word-boundary, so "verification" no longer false-positives).

## What needs YOU (unchanged — I never touch keys/accounts)
- **Google OAuth** client + `[auth]` secrets → sign-in turns on, gated to
  `florenceeducation.com`.
- **Stripe** Payment Link URLs → the env vars above.
- **Streak** `STREAK_API_KEY` + `STREAK_PIPELINE_KEY`; **Gmail** `GMAIL_TOKEN_FILE`
  (gmail.compose) for drafts; optional **`ANTHROPIC_API_KEY`** for AI openers,
  **`EMAIL_VERIFY_URL`** for paid email verification.
All of the above are dormant/no-op until set — the app runs fully without them.

## What I'd do next (didn't start — your call)
1. Wire the dossier + call script into the **bulk pack** too (per-system folders).
2. **Calendar/scheduling** link in the meeting ask (Calendly-style) once you pick a tool.
3. **Email open/click tracking** — needs a sending domain; revisit after Gmail drafts.
4. A nightly **cron** that emails each rep their "Today" worklist + weekly digest.

Run the tests anytime: `python3 tests/test_modules.py && python3 tests/test_app_smoke.py`
