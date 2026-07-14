import { notFound } from "next/navigation";
import DigestView from "@/components/DigestView";
import { getArchiveDates, getDigestByDate } from "@/lib/data";

export function generateStaticParams() {
  return getArchiveDates().map((date) => ({ date }));
}

export const dynamicParams = false;

export default async function ArchivedDigest({
  params,
}: {
  params: Promise<{ date: string }>;
}) {
  const { date } = await params;
  const digest = getDigestByDate(date);
  if (!digest) notFound();
  return <DigestView digest={digest} isArchive />;
}
