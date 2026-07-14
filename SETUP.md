# Setup

One repo does everything. GitHub Actions runs the Python pipeline nightly,
commits the results to `data/`, and that push triggers Vercel to rebuild the
static Next.js site from the committed JSON. There is no server anywhere.

## 1. Repo

Push this directory to a GitHub repo (private is fine; Actions cron works on
both, and the free minutes on private repos are far more than this needs —
each run takes 2-5 minutes).

## 2. Secrets (GitHub → repo → Settings → Secrets and variables → Actions)

| Secret | Required | What it is |
|---|---|---|
| `GEMINI_API_KEY` | yes | From https://aistudio.google.com/apikey (free tier) |
| `HEALTHCHECK_URL` | no | Ping URL from a free https://healthchecks.io check |

That's the full list. No Vercel token is needed: Vercel's Git integration
deploys on every push to `main`, including the bot's nightly data commit.

Nothing goes in Vercel's env vars. The site reads committed JSON at build
time; it makes zero API calls.

## 3. Vercel

1. vercel.com → Add New Project → import the repo.
2. Framework preset: Next.js (auto-detected). Root directory: repo root.
   No build settings to change.
3. Deploy. The seed data in `data/digest.json` renders immediately, so you
   can verify the site before the pipeline ever runs.

## 4. Test one full run before trusting the cron

Locally first (needs Python 3.12+):

```bash
pip install -r pipeline/requirements.txt

# Offline logic test (no network, no key):
python pipeline/test_pipeline.py

# Real fetch, no Gemini:
python pipeline/main.py --no-summarize

# Real fetch + Gemini:
GEMINI_API_KEY=... python pipeline/main.py
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
`include_threshold` or add keywords.

## Failure modes, ranked by likelihood

1. **GitHub trending scraper** (`pipeline/fetchers/github_trending.py`).
   No official API exists; this parses HTML and raises loudly when it parses
   zero rows. Effect: no repos section that night. Fix: update `_parse_page()`.
2. **Anthropic news scraper** (`fetchers/anthropic_news.py`). Same deal,
   no official RSS. Fix: update `_parse()`.
3. **Gemini free-tier quota changes.** Google has shrunk free quotas before.
   The pipeline degrades to truncated abstracts and the site shows
   "summaries: raw abstracts (Gemini unavailable)" so you notice without
   reading logs.
4. **Feed URL rot.** A lab moves its RSS URL roughly once a year. The source
   fails, gets listed in `failed_sources`, shown on the site, everything else
   continues.

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
