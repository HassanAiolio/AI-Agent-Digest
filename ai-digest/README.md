# Nightly digest

Self-hosted nightly scout for AI/ML, embedded systems, competitive
programming, and CS research. Zero recurring cost: GitHub Actions cron →
Python pipeline (fetch → dedupe → score → Gemini summarize) → commit JSON →
Vercel rebuilds the static site.

See SETUP.md for installation, testing, and failure modes.
Tune sources and relevance in pipeline/config.yaml.
