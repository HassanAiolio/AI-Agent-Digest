import fs from "node:fs";
import path from "node:path";

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
  key_points: string[];
  tag: string;
  highlight: boolean;
}

export interface DigestSection {
  id: string;
  title: string;
  tier: number;
  items: DigestItem[];
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
  };
  highlights: DigestItem[];
  sections: DigestSection[];
}

const DATA_DIR = path.join(process.cwd(), "data");

export function getLatestDigest(): Digest {
  const raw = fs.readFileSync(path.join(DATA_DIR, "digest.json"), "utf-8");
  return JSON.parse(raw) as Digest;
}

export function getArchiveDates(): string[] {
  const dir = path.join(DATA_DIR, "archive");
  if (!fs.existsSync(dir)) return [];
  return fs
    .readdirSync(dir)
    .filter((f) => f.endsWith(".json"))
    .map((f) => f.replace(/\.json$/, ""))
    .sort()
    .reverse();
}

export function getDigestByDate(date: string): Digest | null {
  const file = path.join(DATA_DIR, "archive", `${date}.json`);
  if (!fs.existsSync(file)) return null;
  return JSON.parse(fs.readFileSync(file, "utf-8")) as Digest;
}
