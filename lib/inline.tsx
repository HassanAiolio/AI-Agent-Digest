import { Fragment, type ReactNode } from "react";

/** Renders the one bit of markup the brief uses — **bold** — as <strong>,
 * everything else as plain text. The text comes from an LLM that read
 * scraped pages, so this deliberately never touches dangerouslySetInnerHTML:
 * anything that isn't a ** pair stays an inert string. */
export function Inline({ text }: { text: string }): ReactNode {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return parts.map((part, i) =>
    part.startsWith("**") && part.endsWith("**") && part.length > 4 ? (
      <strong key={i}>{part.slice(2, -2)}</strong>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    ),
  );
}

/** Same text with the markup removed, for RSS titles, aria labels, etc. */
export function plain(text: string): string {
  return text.replace(/\*\*([^*]+)\*\*/g, "$1");
}
