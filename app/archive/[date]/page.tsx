import type { Metadata } from "next";
import { notFound } from "next/navigation";
import DigestView from "@/components/DigestView";
import { getArchiveDates, getDigestByDate } from "@/lib/data";
import { plain } from "@/lib/inline";
import { viewProps } from "@/lib/viewProps";

export function generateStaticParams() {
  return getArchiveDates().map((date) => ({ date }));
}

export const dynamicParams = false;

export async function generateMetadata({ params }: { params: Promise<{ date: string }> }): Promise<Metadata> {
  const { date } = await params;
  const digest = getDigestByDate(date);
  const lead = digest?.brief?.stories[0]?.headline;
  return {
    title: lead ? `${date}: ${lead}` : date,
    description: digest?.brief ? plain(digest.brief.greeting) : undefined,
  };
}

export default async function ArchivedDigest({ params }: { params: Promise<{ date: string }> }) {
  const { date } = await params;
  const digest = getDigestByDate(date);
  if (!digest) notFound();
  return <DigestView {...viewProps(digest, true)} />;
}
