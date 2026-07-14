# Nightly digest

Self-hosted nightly scout for AI/ML, embedded systems, competitive
programming, and CS research. Zero recurring cost: GitHub Actions cron →
Python pipeline (fetch → dedupe → score → Groq summarize) → commit JSON →
Vercel rebuilds the static site.

Summaries are structured, not just one-liners: each item gets a short
factual blurb, an optional content tag (Release, Research, Contest, Repo,
Analysis, News), and optional key-fact bullets (numbers, dates, license,
benchmarks) pulled out only when the source text actually has them — so
opinion pieces stay a plain sentence and releases get the hard facts up
front. The night's top-scoring items across all sections also surface in
a "top picks" bar at the top of the page, so a 20-second skim covers the
important stuff without clicking through.

See SETUP.md for installation, testing, and failure modes.
Tune sources and relevance in pipeline/config.yaml.
