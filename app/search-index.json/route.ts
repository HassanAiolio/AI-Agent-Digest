import { NextResponse } from "next/server";
import { getAllDigests } from "@/lib/data";

// Built once per deploy, served as a static file. The palette fetches it the
// first time it opens, so readers who never search never download it.
export const dynamic = "force-static";

export interface SearchEntry {
  i: string; // item id
  t: string; // title
  s: string; // summary
  o: string; // source
  g: string; // tag
  d: string; // edition date
  c: string; // section title
}

export function GET() {
  const seen = new Set<string>();
  const entries: SearchEntry[] = [];
  for (const digest of getAllDigests()) {
    for (const section of digest.sections) {
      for (const it of section.items) {
        if (seen.has(it.id)) continue; // keep the newest edition an item appeared in
        seen.add(it.id);
        entries.push({
          i: it.id,
          t: it.title,
          s: it.summary.slice(0, 240),
          o: it.source,
          g: it.tag,
          d: digest.date,
          c: section.title,
        });
      }
    }
  }
  return NextResponse.json(entries, {
    headers: { "Cache-Control": "public, max-age=3600, stale-while-revalidate=86400" },
  });
}
