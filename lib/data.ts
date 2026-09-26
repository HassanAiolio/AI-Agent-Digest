import fs from "node:fs";
import path from "node:path";

export interface RelatedRef {
  title: string;
  url: string;
  date: string;
  id: string;
}

export interface DigestItem {
  title: string;
  url: string;
  source: string;
  section: string;
  published: string | null;
  points: number | null;
  score: number;
  id: string;
  summary: string;
  detail: string;
  key_points: string[];
  tag: string;
  highlight: boolean;
  image: string;
  related?: RelatedRef | Record<string, never>;
}

export interface DigestSection {
  id: string;
  title: string;
  tier: number;
  items: DigestItem[];
}

export interface BriefStory {
  kicker: string;
  headline: string;
  body: string;
  why: string;
  ids: string[];
}

export interface Brief {
  greeting: string;
  stories: BriefStory[];
  quick_hits: { text: string; id: string }[];
  number: { value: string; label: string; id: string } | null;
  sign_off: string;
  generated: "llm" | "fallback";
}

export interface UpcomingEvent {
  id: string;
  title: string;
  url: string;
  source: string;
  starts: string | null;
  detail: string;
}

export interface Faithfulness {
  checked: number;
  supported: number;
  dropped: number;
  unverifiable: number;
  summaries_reverted: number;
  rate: number | null;
}

export interface Digest {
  date: string;
  generated_at: string;
  stats: {
    fetched?: number;
    new_after_dedupe?: number;
    published?: number;
    failed_sources?: string[];
    summarizer?: string;
    faithfulness?: Faithfulness;
    brief?: string;
  };
  brief?: Brief | null;
  upcoming?: UpcomingEvent[];
  highlights: DigestItem[];
  sections: DigestSection[];
}

export interface WeeklyRef {
  id: string;
  title: string;
  url: string;
  date: string;
  source: string;
  section: string;
}

export interface Weekly {
  week: string;
  start: string;
  end: string;
  title: string;
  intro: string;
  themes: { headline: string; body: string; items: WeeklyRef[] }[];
  numbers: { value: string; label: string; item: WeeklyRef }[];
  watch: string;
  item_count: number;
}

// DIGEST_DATA_DIR lets a local dev server render a scratch copy of data/
// (e.g. a test pipeline run) without touching the committed files.
const DATA_DIR = process.env.DIGEST_DATA_DIR || path.join(process.cwd(), "data");

function readJson<T>(file: string): T | null {
  if (!fs.existsSync(file)) return null;
  return JSON.parse(fs.readFileSync(file, "utf-8")) as T;
}

export function getLatestDigest(): Digest {
  return readJson<Digest>(path.join(DATA_DIR, "digest.json"))!;
}

/** Newest first. */
export function getArchiveDates(): string[] {
  const dir = path.join(DATA_DIR, "archive");
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => /^\d{4}-\d{2}-\d{2}\.json$/.test(f))
    .map((f) => f.replace(/\.json$/, ""))
    .sort()
    .reverse();
}

export function getDigestByDate(date: string): Digest | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) return null;
  return readJson<Digest>(path.join(DATA_DIR, "archive", `${date}.json`));
}

let allCache: Digest[] | null = null;

/** Every archived edition, newest first. Read once per build. */
export function getAllDigests(): Digest[] {
  if (!allCache) {
    allCache = getArchiveDates()
      .map((d) => getDigestByDate(d))
      .filter((d): d is Digest => d !== null);
  }
  return allCache;
}

/** 1-based issue number, counting from the first archived edition. */
export function editionNumber(date: string): number {
  const dates = getArchiveDates();
  const idx = dates.indexOf(date);
  return idx === -1 ? dates.length + 1 : dates.length - idx;
}

export function neighbours(date: string): { prev: string | null; next: string | null } {
  const dates = getArchiveDates(); // newest first
  const idx = dates.indexOf(date);
  if (idx === -1) return { prev: dates[0] ?? null, next: null };
  return { prev: dates[idx + 1] ?? null, next: dates[idx - 1] ?? null };
}

/** Newest first, e.g. ["2026-W39", "2026-W38"]. */
export function getWeeklyIds(): string[] {
  const dir = path.join(DATA_DIR, "weekly");
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => /^\d{4}-W\d{2}\.json$/.test(f))
    .map((f) => f.replace(/\.json$/, ""))
    .sort()
    .reverse();
}

export function getWeekly(week: string): Weekly | null {
  if (!/^\d{4}-W\d{2}$/.test(week)) return null;
  return readJson<Weekly>(path.join(DATA_DIR, "weekly", `${week}.json`));
}

export function allItems(d: Digest): DigestItem[] {
  return d.sections.flatMap((s) => s.items);
}

/** Minutes to read the brief plus every card's summary, at ~230 wpm. */
export function readingMinutes(d: Digest): number {
  const words = (s: string) => (s ? s.split(/\s+/).length : 0);
  let n = 0;
  if (d.brief) {
    n += words(d.brief.greeting) + words(d.brief.sign_off);
    for (const s of d.brief.stories) n += words(s.headline) + words(s.body) + words(s.why);
    for (const h of d.brief.quick_hits) n += words(h.text);
  }
  for (const it of allItems(d)) n += words(it.title) + words(it.summary) + it.key_points.length * 4;
  return Math.max(1, Math.round(n / 230));
}

export function siteUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_SITE_URL;
  if (explicit) return explicit.replace(/\/$/, "");
  // Set automatically by Vercel on every deployment.
  const vercel = process.env.VERCEL_PROJECT_PRODUCTION_URL;
  return vercel ? `https://${vercel}` : "http://localhost:3000";
}
