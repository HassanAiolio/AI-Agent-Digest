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
| `HEALTHCHECK_URL` | recommended | Ping URL from a free https://healthchecks.io check (see "How you'll know") |
| `VERCEL_DEPLOY_HOOK_URL` | yes | See below — without it, Vercel won't redeploy the bot's data commits |

**Why a deploy hook is required, not optional:** Vercel's Git integration
holds deployments from commits whose author isn't a recognized account
pending manual approval — the nightly bot's commits (`digest-bot
<actions@users.noreply.github.com>`) hit this every time, so the push
alone silently never deploys (check Vercel → Deployments; bot commits show
"Blocked" while your own commits show "Ready"). A Deploy Hook triggers a
build via a direct API call instead of inferring intent from git
authorship, sidestepping that check entirely.

Create one at Vercel → Project → Settings → Git → Deploy Hooks (name it
anything, branch `main`), then add the generated URL as the
`VERCEL_DEPLOY_HOOK_URL` secret above.

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
   | `FEEDBACK_KEY` | for preference sync | Any long random string (`openssl rand -hex 24`). Without it `/api/feedback` stays disabled |
   | `GITHUB_BRANCH` | no | Defaults to `main` |
   | `NEXT_PUBLIC_NEWSLETTER_URL` | no | A subscribe page (e.g. Buttondown) linked next to the RSS feed |
   | `NEXT_PUBLIC_SITE_URL` | no | Canonical URL for RSS links; defaults to Vercel's production URL |
   | `DIGEST_IMAGE_PROXY` | no | `off` serves thumbnails directly instead of through `next/image` |

## 4. Test one full run before trusting the cron

Locally first (needs Python 3.12+):

```bash
pip install -r pipeline/requirements-dev.txt

# Offline tests (no network, no key) + lint:
pytest pipeline -q && ruff check pipeline

# Real fetch, no Groq:
python pipeline/main.py --no-summarize

# Real fetch + Groq:
GROQ_API_KEY=... python pipeline/main.py
```

Inspect `data/digest.json`, then `npm install && npm run dev` and check
http://localhost:3000 renders it.

To experiment without touching the committed data, point both halves at a
scratch copy: copy `data/` to e.g. `/tmp/digest` (so dedupe and
"previously" links have history), run
`python pipeline/main.py --data-dir /tmp/digest`, then
`DIGEST_DATA_DIR=/tmp/digest npm run dev`.

Then in the cloud: Actions tab → "Nightly digest" → **Run workflow**
(manual dispatch; tick "weekly" to also build the Sunday recap). Confirm the bot commit lands in `data/` and Vercel
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
`images.enabled: false` turns off the og:image thumbnail scraping
(`pipeline/images.py`) if it ever proves too slow or too flaky for a
particular night; the site already renders fine with no thumbnails.

## Morning brief and weekly recap

After summarizing, `pipeline/brief.py` makes one more LLM call over the
night's best items (highlights first, then one per section in turn) and
writes the Morning-Brew-style lede: greeting, three stories with a bold
lead-in and a "why it matters", quick hits, number of the day. Every story
must cite item ids that exist tonight, and the number must appear in its
item's text; anything else is dropped. If the call fails, a plain brief is
built from the top picks, so the section is never missing. The voice lives
in `PROMPT` in `brief.py`; `brief:` in `config.yaml` sets limits or turns
it off.

On Sundays (`weekly.weekday`), `pipeline/weekly.py` reads the last seven
archived editions and writes `data/weekly/<ISO week>.json`, rendered at
`/weekly/`. Run it by hand with `python pipeline/weekly.py --date YYYY-MM-DD`.

## Email delivery

`/feed.xml` carries each edition's full brief and story list, so any
RSS-to-email service turns it into a newsletter with no code. For example
Buttondown → Settings → RSS-to-email → `https://<your-site>/feed.xml`,
daily. Set `NEXT_PUBLIC_NEWSLETTER_URL` to the signup page and the site
links it next to the RSS feed.

## Preference learning (like/dislike)

Every item has ▲/▼ buttons. Clicking one:

1. Saves instantly to `localStorage` and re-sorts/re-ranks what you see
   right away, purely in the browser — for every visitor, no setup.
2. **For the owner only**, fires `POST /api/feedback`, which commits the
   vote into `data/feedback.json` in the repo. Each accepted request is a
   commit made with your token, so the route is locked: it needs
   `FEEDBACK_KEY` set on Vercel and the same key sent by the browser.
   Unlock your browser once by visiting
   `https://<your-site>/?owner=<FEEDBACK_KEY>` — the key is stored in
   `localStorage` and removed from the address bar. Other visitors' votes
   never leave their browser.

At the next pipeline run, `pipeline/preferences.py` reads `feedback.json`,
aggregates your votes into a small per-tag and per-source affinity score
(clamped so one voting streak can't dominate) plus a semantic "taste"
boost — how close each item's embedding is to titles you liked versus
titles you disliked (`pipeline/semantic.py`) — and folds both into each
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
3. **Groq free-tier or model changes.** The free tier is ~8k tokens per
   minute per model, and gpt-oss reasoning tokens count against
   `max_tokens`: a tight budget used to cut the JSON off mid-object (400
   `json_validate_failed`), which caused the raw-abstract nights of
   Aug–Sep 2026. `pipeline/llm.py` now paces from Groq's rate-limit
   headers, keeps reasoning at `low`, retries a truncated reply with a
   bigger budget, and falls back to `groq.fallback_model`. Models do get
   retired (`llama-3.1-8b-instant` returned 404 in Sep 2026): check
   `GET https://api.groq.com/openai/v1/models` and update `config.yaml`.
   If everything fails, the night ships raw abstracts, the run goes red,
   and the site says so.
4. **Feed URL rot.** A lab moves its RSS URL roughly once a year. The source
   fails, gets listed in `failed_sources`, shown on the site, everything else
   continues.
5. **Feedback sync failing** (missing/expired `GITHUB_TOKEN`, wrong
   `GITHUB_REPO`, or a race with the nightly bot's own commit). `/api/feedback`
   retries a few times internally and fails soft either way — like/dislike
   still works locally in the browser, it just won't shape future nights
   until sync is fixed.
6. **Embedding model unavailable** (download failure on a cold cache,
   onnxruntime issue). Semantic dedupe, "previously" links and the taste
   boost are skipped for the night; nothing else changes.
7. **No thumbnail for an item.** `pipeline/images.py` best-effort scrapes
   `og:image` from the item's own page; sites with no such tag, that block
   scraping, or that time out just ship with no image — lowest-severity
   failure mode in the whole pipeline, purely cosmetic.

## How you'll know a night silently failed

Three independent signals, no extra infrastructure:

- GitHub emails you when a workflow run fails (default behavior). A
  *degraded* night — LLM down, zero items, or 3+ sources failing — fails
  the run on purpose, after the data is committed and deployed.
- The site's "updated Nh ago" stamp turns amber past 36h with
  "pipeline may be down" — computed in the browser, so it works even
  though the site is static.
- Optional: the healthchecks.io ping emails you after a *missed* run (and
  right away on a degraded one, via its `/fail` endpoint), which
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
Codeforces, HF Hub) has been stable for years. The published-items ledger,
`data/seen.json`, grows by a few KB per night and self-prunes past 90 days.
(It replaced the binary `seen.sqlite`, which the first run migrates and
deletes automatically, so nightly commits are now readable diffs.)

`/health` on the site charts all of this from the stats each edition
records, so slow drift (a source failing more often, summaries falling
back) is visible before it becomes an outage.

CI (`.github/workflows/ci.yml`) runs ruff + pytest on the pipeline and
lint + typecheck + a full site build on every code push. When a scraper
test fails after a site redesign, save the new page over the fixture in
`pipeline/tests/fixtures/` (trimmed to a few entries), fix the parser, and
the test tells you when it's right.
