import fs from "node:fs";
import path from "node:path";

const dataDir = process.env.DIGEST_DATA_DIR || path.join(process.cwd(), "data");

// Next.js allows at most 50 remotePatterns.
const MAX_PROXIED_HOSTS = 48;

/** The busiest thumbnail hosts in the committed data, so next/image can
 * resize and serve them from this domain — readers never hit the third-
 * party site (no IP/referrer leak, no mixed content, no hotlinking) —
 * without turning /_next/image into an open proxy for arbitrary URLs.
 * Rarer hosts past the cap render as a plain no-referrer <img>. */
function imageHosts() {
  const hosts = new Map();
  const files = [path.join(dataDir, "digest.json")];
  const archive = path.join(dataDir, "archive");
  if (fs.existsSync(archive)) {
    for (const f of fs.readdirSync(archive)) if (f.endsWith(".json")) files.push(path.join(archive, f));
  }
  for (const file of files) {
    if (!fs.existsSync(file)) continue;
    try {
      const doc = JSON.parse(fs.readFileSync(file, "utf-8"));
      for (const s of doc.sections ?? []) {
        for (const it of s.items ?? []) {
          if (!it.image) continue;
          try {
            const u = new URL(it.image);
            if (u.protocol === "https:") hosts.set(u.hostname, (hosts.get(u.hostname) ?? 0) + 1);
          } catch {
            /* malformed URL — the card just renders without a thumbnail */
          }
        }
      }
    } catch {
      /* unreadable file — skip */
    }
  }
  return [...hosts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, MAX_PROXIED_HOSTS)
    .map(([h]) => h)
    .sort();
}

const proxied = imageHosts();

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Was `output: "export"` (fully static) until /api/feedback needed a real
  // serverless function. Vercel still prerenders every page at build time.
  trailingSlash: true,
  env: {
    // Inlined into the client bundle so ItemRow knows which thumbnails
    // next/image will accept.
    NEXT_PUBLIC_IMAGE_HOSTS: proxied.join(","),
  },
  images: {
    remotePatterns: proxied.map((hostname) => ({ protocol: "https", hostname })),
    formats: ["image/avif", "image/webp"],
    minimumCacheTTL: 60 * 60 * 24 * 30,
    // Escape hatch if Vercel's image-optimization quota ever becomes a problem.
    unoptimized: process.env.DIGEST_IMAGE_PROXY === "off",
  },
};

export default nextConfig;
