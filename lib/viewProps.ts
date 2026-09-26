import type { DigestViewProps } from "@/components/DigestView";
import {
  type Digest,
  editionNumber,
  getArchiveDates,
  getLatestDigest,
  getWeekly,
  getWeeklyIds,
  neighbours,
  readingMinutes,
} from "@/lib/data";

/** Server-side: everything DigestView needs besides the digest itself. */
export function viewProps(digest: Digest, isArchive: boolean): DigestViewProps {
  const latestDate = getLatestDigest().date;
  const weeklyId = getWeeklyIds()[0];
  const weekly = weeklyId ? getWeekly(weeklyId) : null;
  const { prev, next } = neighbours(digest.date);
  return {
    digest,
    isArchive,
    edition: editionNumber(digest.date),
    minutes: readingMinutes(digest),
    prev,
    next,
    latestDate,
    recentDates: getArchiveDates().slice(0, 21),
    weekly: weekly ? { id: weekly.week, title: weekly.title } : null,
  };
}
