"use client";
import { useEffect, useState } from "react";

// Client-side staleness check. The site is rebuilt only when the pipeline
// succeeds, so a stale generated_at is the on-page signal that a night failed.
export default function Freshness({ generatedAt }: { generatedAt: string }) {
  const [ageHours, setAgeHours] = useState<number | null>(null);

  useEffect(() => {
    const t = new Date(generatedAt).getTime();
    if (!Number.isNaN(t)) {
      setAgeHours((Date.now() - t) / 3_600_000);
    }
  }, [generatedAt]);

  if (ageHours === null) return <span>updated {generatedAt.slice(0, 16).replace("T", " ")} UTC</span>;
  const label =
    ageHours < 1 ? "updated <1h ago" : `updated ${Math.round(ageHours)}h ago`;
  return (
    <span className={ageHours > 36 ? "stale" : undefined}>
      {label}
      {ageHours > 36 ? " — pipeline may be down" : ""}
    </span>
  );
}
