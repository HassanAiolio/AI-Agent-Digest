import { allItems, type Digest, getAllDigests, siteUrl } from "@/lib/data";
import { plain } from "@/lib/inline";

// One entry per edition, carrying the whole brief plus the story list, so
// the feed works on its own in a reader — and an RSS-to-email service
// (Buttondown, Mailchimp RSS campaigns…) can turn it into the newsletter.
export const dynamic = "force-static";

const EDITIONS = 20;

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** **bold** → <strong>, everything else escaped. */
function rich(s: string): string {
  return esc(s).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

/** Links always use the permanent /archive/<date>/ URL: "/" shows a
 * different edition tomorrow, and feed items live forever in readers. */
function editionHtml(d: Digest, base: string): string {
  const page = `${base}/archive/${d.date}/`;
  const link = (id: string) => `${page}#item-${id}`;
  const out: string[] = [];
  const b = d.brief;
  if (b) {
    out.push(`<p>${rich(b.greeting)}</p>`);
    for (const s of b.stories) {
      out.push(`<h2>${esc(s.headline)}</h2><p>${rich(s.body)}</p>`);
      if (s.why) out.push(`<p><em>Why it matters:</em> ${esc(s.why)}</p>`);
      if (s.ids[0]) out.push(`<p><a href="${link(s.ids[0])}">Read more →</a></p>`);
    }
    if (b.number) out.push(`<p><strong>${esc(b.number.value)}</strong> — ${esc(b.number.label)}</p>`);
    if (b.quick_hits.length) {
      out.push("<h3>Quick hits</h3><ul>");
      for (const h of b.quick_hits) out.push(`<li><a href="${link(h.id)}">${rich(h.text)}</a></li>`);
      out.push("</ul>");
    }
  }
  for (const section of d.sections) {
    out.push(`<h3>${esc(section.title)}</h3><ul>`);
    for (const it of section.items) {
      out.push(`<li><a href="${esc(it.url)}">${esc(it.title)}</a> — ${esc(it.summary)}</li>`);
    }
    out.push("</ul>");
  }
  if (b?.sign_off) out.push(`<p><em>${esc(b.sign_off)}</em></p>`);
  return out.join("\n");
}

function title(d: Digest): string {
  const when = new Date(d.date + "T12:00:00Z").toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
  const lead = d.brief?.stories[0]?.headline ?? d.highlights?.[0]?.title ?? `${allItems(d).length} stories`;
  return `${when}: ${plain(lead)}`;
}

export function GET() {
  const base = siteUrl();
  const editions = getAllDigests().slice(0, EDITIONS);
  const items = editions
    .map((d) => {
      const url = `${base}/archive/${d.date}/`;
      return `    <item>
      <title>${esc(title(d))}</title>
      <link>${url}</link>
      <guid isPermaLink="true">${url}</guid>
      <pubDate>${new Date(d.generated_at).toUTCString()}</pubDate>
      <description>${esc(d.brief ? plain(d.brief.greeting) : `${allItems(d).length} stories`)}</description>
      <content:encoded><![CDATA[${editionHtml(d, base).replace(/]]>/g, "]]]]><![CDATA[>")}]]></content:encoded>
    </item>`;
    })
    .join("\n");

  const xml = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>Nightly digest</title>
    <link>${base}/</link>
    <atom:link href="${base}/feed.xml" rel="self" type="application/rss+xml"/>
    <description>Overnight signal for engineers: AI/ML, embedded, competitive programming, CS research.</description>
    <language>en</language>
${items}
  </channel>
</rss>
`;
  return new Response(xml, {
    headers: { "Content-Type": "application/rss+xml; charset=utf-8", "Cache-Control": "public, max-age=3600" },
  });
}
