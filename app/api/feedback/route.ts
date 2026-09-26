import { timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server";

/**
 * Owner-only sync of a like/dislike vote into data/feedback.json in the
 * repo, via GitHub's Contents API — the same "commit generated data" pattern
 * the nightly bot uses, so pipeline/preferences.py can read it at the next
 * run and fold it into scoring.
 *
 * Every accepted request is a commit made with a repo-scoped token, so this
 * route is locked down:
 *   - FEEDBACK_KEY must be set, and the request must carry it in the
 *     x-feedback-key header (compared in constant time). Unset = disabled.
 *     Visitors' votes still re-rank their own page via localStorage; only
 *     the owner's votes train the pipeline.
 *   - The Origin header, when present, must match this deployment's host.
 *   - Every field is type-, length- and pattern-checked before it's written.
 *
 * Requires GITHUB_TOKEN (fine-grained PAT, contents:write on this repo),
 * GITHUB_REPO ("owner/repo") and FEEDBACK_KEY as Vercel env vars.
 */

const FILE_PATH = "data/feedback.json";
const MAX_ENTRIES = 2000;
const TAGS = new Set(["", "Release", "Research", "Contest", "Repo", "Analysis", "News"]);

interface FeedbackEntry {
  vote: number;
  tag: string;
  source: string;
  title: string;
  ts: string;
}
type FeedbackStore = Record<string, FeedbackEntry>;

interface VoteBody {
  id: string;
  tag: string;
  source: string;
  title: string;
  vote: 1 | -1 | 0;
}

function contentsUrl(repo: string) {
  return `https://api.github.com/repos/${repo}/contents/${FILE_PATH}`;
}

function githubHeaders(token: string) {
  return {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "Content-Type": "application/json",
  };
}

function keyMatches(given: string | null, expected: string): boolean {
  if (!given) return false;
  const a = Buffer.from(given);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

function sameOrigin(req: Request): boolean {
  const origin = req.headers.get("origin");
  if (!origin) return true; // same-origin fetches from some browsers omit it; the key still gates
  try {
    return new URL(origin).host === req.headers.get("host");
  } catch {
    return false;
  }
}

function parseBody(raw: unknown): VoteBody | null {
  if (!raw || typeof raw !== "object") return null;
  const b = raw as Record<string, unknown>;
  const str = (v: unknown, max: number) => (typeof v === "string" && v.length <= max ? v : null);
  const id = str(b.id, 64);
  const tag = str(b.tag ?? "", 20);
  const source = str(b.source ?? "", 80);
  const title = str(b.title ?? "", 300);
  if (!id || !/^[0-9a-f]{40}$/.test(id)) return null;
  if (tag === null || !TAGS.has(tag) || source === null || title === null) return null;
  if (b.vote !== 1 && b.vote !== -1 && b.vote !== 0) return null;
  return { id, tag, source, title, vote: b.vote };
}

async function readStore(repo: string, branch: string, token: string) {
  const res = await fetch(`${contentsUrl(repo)}?ref=${branch}`, {
    headers: githubHeaders(token),
    cache: "no-store",
  });
  if (res.status === 404) return { data: {} as FeedbackStore, sha: undefined as string | undefined };
  if (!res.ok) throw new Error(`github read failed: ${res.status}`);
  const json = (await res.json()) as { content: string; sha: string };
  let data: FeedbackStore = {};
  try {
    data = JSON.parse(Buffer.from(json.content, "base64").toString("utf-8"));
  } catch {
    data = {};
  }
  return { data, sha: json.sha };
}

function writeStore(repo: string, branch: string, token: string, data: FeedbackStore, sha?: string) {
  return fetch(contentsUrl(repo), {
    method: "PUT",
    headers: githubHeaders(token),
    body: JSON.stringify({
      message: "feedback: sync vote",
      content: Buffer.from(JSON.stringify(data, null, 2)).toString("base64"),
      branch,
      sha,
      committer: { name: "digest-bot", email: "actions@users.noreply.github.com" },
    }),
  });
}

function capEntries(data: FeedbackStore): FeedbackStore {
  const entries = Object.entries(data);
  if (entries.length <= MAX_ENTRIES) return data;
  entries.sort((a, b) => a[1].ts.localeCompare(b[1].ts));
  return Object.fromEntries(entries.slice(entries.length - MAX_ENTRIES));
}

export async function POST(req: Request) {
  const token = process.env.GITHUB_TOKEN;
  const repo = process.env.GITHUB_REPO;
  const ownerKey = process.env.FEEDBACK_KEY;
  if (!token || !repo || !ownerKey) {
    return NextResponse.json({ ok: false, reason: "feedback sync not configured" }, { status: 501 });
  }
  if (!sameOrigin(req)) {
    return NextResponse.json({ ok: false, reason: "cross-origin" }, { status: 403 });
  }
  if (!keyMatches(req.headers.get("x-feedback-key"), ownerKey)) {
    return NextResponse.json({ ok: false, reason: "unauthorized" }, { status: 401 });
  }

  let body: VoteBody | null;
  try {
    const text = await req.text();
    body = text.length > 2000 ? null : parseBody(JSON.parse(text));
  } catch {
    body = null;
  }
  if (!body) {
    return NextResponse.json({ ok: false, reason: "invalid vote" }, { status: 400 });
  }

  const branch = process.env.GITHUB_BRANCH || "main";
  const maxAttempts = 3;

  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
      const { data, sha } = await readStore(repo, branch, token);
      if (body.vote === 0) {
        delete data[body.id];
      } else {
        data[body.id] = {
          vote: body.vote,
          tag: body.tag,
          source: body.source,
          title: body.title,
          ts: new Date().toISOString(),
        };
      }
      const res = await writeStore(repo, branch, token, capEntries(data), sha);
      if (res.ok) return NextResponse.json({ ok: true });
      if (attempt === maxAttempts) {
        return NextResponse.json({ ok: false, reason: `github write failed: ${res.status}` }, { status: 502 });
      }
      // Likely a stale sha (the nightly bot committed in between) — loop
      // refetches the current sha and retries.
    } catch {
      if (attempt === maxAttempts) {
        return NextResponse.json({ ok: false, reason: "github unreachable" }, { status: 502 });
      }
    }
  }
  return NextResponse.json({ ok: false, reason: "exhausted retries" }, { status: 502 });
}
