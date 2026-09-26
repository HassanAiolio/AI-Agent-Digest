import DigestView from "@/components/DigestView";
import { getLatestDigest } from "@/lib/data";
import { viewProps } from "@/lib/viewProps";

export default function Home() {
  const digest = getLatestDigest();
  return <DigestView {...viewProps(digest, false)} />;
}
