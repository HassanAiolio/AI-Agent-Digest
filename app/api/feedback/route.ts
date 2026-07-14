import { NextResponse } from "next/server";

/**
 * Best-effort sync of a like/dislike vote into data/feedback.json in the
 * repo, via GitHub's Contents API — the same "commit generated data" pattern
 * the nightly bot already uses, so pipeline/preferences.py can read it at
 * the next run and fold it into scoring. The client already applied the
 * vote to localStorage before calling this; a failure here just means this
 * one vote won't shape *future* nights, nothing on the page depends on it.
 *
 * Requires GITHUB_TOKEN (a repo-scoped PAT with contents:write) and
 * GITHUB_REPO ("owner/repo") as Vercel env vars. Unconfigured or failing
 * is a soft no-op, never a hard error surfaced to the visitor.
 */

const FILE_PATH = "data/feedback.json";
const MAX_ENTRIES = 2000;

interface FeedbackEntry {
  vote: number;
  tag: string;
  source: string;
  ts: string;
}
type FeedbackStore = Record<string, FeedbackEntry>;

interface VoteBody {
  id: string;
  tag?: string;
  source?: string;
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
  if (!token || !repo) {
    return NextResponse.json({ ok: false, reason: "feedback sync not configured" }, { status: 501 });
  }

  let body: VoteBody;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ ok: false, reason: "invalid body" }, { status: 400 });
  }
  if (!body?.id || typeof body.id !== "string" || ![1, -1, 0].includes(body.vote)) {
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
          tag: body.tag || "",
          source: body.source || "",
          ts: new Date().toISOString(),
        };
      }
      const res = await writeStore(repo, branch, token, capEntries(data), sha);
      if (res.ok) return NextResponse.json({ ok: true });
      if (attempt === maxAttempts) {
        return NextResponse.json({ ok: false, reason: await res.text() }, { status: 502 });
      }
      // Likely a stale sha (someone else committed in between, e.g. the
      // nightly bot) — loop refetches the current sha and retries.
    } catch (e) {
      if (attempt === maxAttempts) {
        return NextResponse.json({ ok: false, reason: String(e) }, { status: 502 });
      }
    }
  }
  return NextResponse.json({ ok: false, reason: "exhausted retries" }, { status: 502 });
}
