# Setup

One repo does everything. GitHub Actions runs the Python pipeline nightly,
commits the results to `data/`, and that push triggers Vercel to rebuild the
Next.js site from the committed JSON. Almost everything is static; the one
exception is `/api/feedback`, a small Vercel serverless function that lets
the site commit your like/dislike votes back to the repo so the next
pipeline run can learn from them (see "Preference learning" below).

## 1. Repo

Push this directory to a GitHub repo (private is fine; Actions cron works on
both, and the free minutes on private repos are far more than this needs —
each run takes 2-5 minutes).

## 2. Secrets (GitHub → repo → Settings → Secrets and variables → Actions)

| Secret | Required | What it is |
|---|---|---|
| `GROQ_API_KEY` | yes | From https://console.groq.com/keys (free tier) |
| `HEALTHCHECK_URL` | no | Ping URL from a free https://healthchecks.io check |

No Vercel token is needed for deploys: Vercel's Git integration deploys on
every push to `main`, including the bot's nightly data commit.

## 3. Vercel

1. vercel.com → Add New Project → import the repo.
2. Framework preset: Next.js (auto-detected). Root directory: repo root.
   No build settings to change.
3. Deploy. The seed data in `data/digest.json` renders immediately, so you
   can verify the site before the pipeline ever runs.
4. **Env vars** (Vercel → Project → Settings → Environment Variables) — only
   needed for like/dislike sync; the site works without them, votes just
   stay local to your browser:

   | Variable | Required | What it is |
   |---|---|---|
   | `GITHUB_TOKEN` | for preference sync | A GitHub personal access token (fine-grained, scoped to just this repo, "Contents: Read and write" permission) |
   | `GITHUB_REPO` | for preference sync | `"owner/repo"`, e.g. `HassanAiolio/AI-Agent-Digest` |
   | `GITHUB_BRANCH` | no | Defaults to `main` |

## 4. Test one full run before trusting the cron

Locally first (needs Python 3.12+):

```bash
pip install -r pipeline/requirements.txt

# Offline logic test (no network, no key):
python pipeline/test_pipeline.py

# Real fetch, no Groq:
python pipeline/main.py --no-summarize

# Real fetch + Groq:
GROQ_API_KEY=... python pipeline/main.py
```

Inspect `data/digest.json`, then `npm install && npm run dev` and check
http://localhost:3000 renders it.

Then in the cloud: Actions tab → "Nightly digest" → **Run workflow**
(manual dispatch). Confirm the bot commit lands in `data/` and Vercel
deploys it. Only then trust the cron.

## 5. Tuning

Everything editorial lives in `pipeline/config.yaml`: sources, section caps,
keyword weights, the negative-keyword list that filters funding/corporate
news, thresholds. Getting too much noise from Hacker News → raise
`route_threshold` or `min_points`. A section always empty → lower
`include_threshold` or add keywords. `highlights.count` controls how many
top-scoring items surface in the "top picks" bar at the top of the page
(set to 0 to disable it). `groq.model` picks which Groq-hosted model
summarizes — check https://console.groq.com/docs/models for current
options and swap freely; the pipeline doesn't care which one you use.

## Preference learning (like/dislike)

Every item has ▲/▼ buttons. Clicking one:

1. Saves instantly to `localStorage` and re-sorts/re-ranks what you see
   right away, purely in the browser — works even if the sync below is
   never configured.
2. Fires a best-effort `POST /api/feedback`, which commits the vote into
   `data/feedback.json` in the repo (same "commit generated data" pattern
   as the nightly bot). If `GITHUB_TOKEN`/`GITHUB_REPO` aren't set, or the
   request fails, this step silently no-ops — your local vote still stands.

At the next pipeline run, `pipeline/preferences.py` reads `feedback.json`,
aggregates your votes into a small per-tag and per-source affinity score
(clamped so one voting streak can't dominate), and folds it into each
item's score *after* scoring/routing and summarization — so it only
reorders what already cleared the relevance bar and got a tag from Groq.
A disliked source/tag sinks in its section and is less likely to be
picked as a highlight; it's never silently excluded from the digest
entirely. Tune the weights in `pipeline/preferences.py` (`TAG_WEIGHT`,
`SOURCE_WEIGHT`, `CLAMP`) if you want the learning to be more or less
aggressive.

## Failure modes, ranked by likelihood

1. **GitHub trending scraper** (`pipeline/fetchers/github_trending.py`).
   No official API exists; this parses HTML and raises loudly when it parses
   zero rows. Effect: no repos section that night. Fix: update `_parse_page()`.
2. **Anthropic news scraper** (`fetchers/anthropic_news.py`). Same deal,
   no official RSS. Fix: update `_parse()`.
3. **Groq free-tier quota/rate-limit changes.** Free tiers get adjusted.
   The pipeline degrades to truncated abstracts and the site shows
   "summaries: raw abstracts (Groq unavailable)" so you notice without
   reading logs.
4. **Feed URL rot.** A lab moves its RSS URL roughly once a year. The source
   fails, gets listed in `failed_sources`, shown on the site, everything else
   continues.
5. **Feedback sync failing** (missing/expired `GITHUB_TOKEN`, wrong
   `GITHUB_REPO`, or a race with the nightly bot's own commit). `/api/feedback`
   retries a few times internally and fails soft either way — like/dislike
   still works locally in the browser, it just won't shape future nights
   until sync is fixed.

## How you'll know a night silently failed

Three independent signals, no extra infrastructure:

- GitHub emails you when a workflow run fails (default behavior).
- The site's "updated Nh ago" stamp turns amber past 36h with
  "pipeline may be down" — computed in the browser, so it works even
  though the site is static.
- Optional: the healthchecks.io ping emails you after a *missed* run, which
  catches the one case the other two don't — GitHub silently disabling the
  cron. GitHub disables scheduled workflows after 60 days without repo
  activity; the nightly bot commit normally resets that clock, but a
  long-broken pipeline stops committing and eventually gets its schedule
  turned off. The dead-man's switch is the only thing that catches that,
  so the free healthchecks.io check is worth the two minutes.

## Maintenance expectations

Realistic solo load: patch one scraper selector every couple of months,
occasionally re-tune keywords in `config.yaml`, and once in a while update
a moved feed URL. Everything on official APIs (arXiv, HN Algolia,
Codeforces, HF Hub) has been stable for years. The `data/seen.sqlite` file
grows by a few KB per night and self-prunes past 90 days.
