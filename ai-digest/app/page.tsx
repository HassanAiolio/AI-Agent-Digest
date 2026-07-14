import DigestView from "@/components/DigestView";
import { getLatestDigest } from "@/lib/data";

export default function Home() {
  const digest = getLatestDigest();
  return <DigestView digest={digest} />;
}
