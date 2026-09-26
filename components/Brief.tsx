"use client";
import type { Brief as BriefData, DigestItem } from "@/lib/data";
import { Inline } from "@/lib/inline";

interface BriefProps {
  brief: BriefData;
  itemsById: Map<string, DigestItem>;
  onJump: (id: string) => void;
}

function splitGreeting(greeting: string): [string, string] {
  const m = greeting.match(/^(Good (?:morning|evening|afternoon)[.!,]?)\s*(.*)$/i);
  return m ? [m[1].replace(/[,]$/, "."), m[2]] : ["Good morning.", greeting];
}

function sourcesOf(ids: string[], itemsById: Map<string, DigestItem>): string {
  const names = [...new Set(ids.map((id) => itemsById.get(id)?.source).filter(Boolean))];
  return names.slice(0, 2).join(" · ");
}

export default function Brief({ brief, itemsById, onJump }: BriefProps) {
  const [hello, lede] = splitGreeting(brief.greeting);
  const number = brief.number && itemsById.has(brief.number.id) ? brief.number : null;

  return (
    <section className="brief" aria-labelledby="brief-hello">
      <h1 id="brief-hello" className="brief-hello">
        {hello}
      </h1>
      {lede && <p className="brief-lede">{lede}</p>}

      <div className="brief-stories">
        {brief.stories.map((story, i) => {
          const target = story.ids.find((id) => itemsById.has(id));
          return (
            <article key={i} className="story">
              <div className="story-rail" aria-hidden="true">
                {String(i + 1).padStart(2, "0")}
              </div>
              <div className="story-main">
                {story.kicker && <div className="story-kicker">{story.kicker}</div>}
                <h2 className="story-headline">{story.headline}</h2>
                <p className="story-body">
                  <Inline text={story.body} />
                </p>
                {story.why && (
                  <p className="story-why">
                    <span className="story-why-label">Why it matters</span>
                    {story.why}
                  </p>
                )}
                {target && (
                  <button type="button" className="story-jump" onClick={() => onJump(target)}>
                    <span>{sourcesOf(story.ids, itemsById)}</span>
                    <span className="story-jump-cta">
                      Full card <span aria-hidden="true">↓</span>
                    </span>
                  </button>
                )}
              </div>
            </article>
          );
        })}
      </div>

      {(number || brief.quick_hits.length > 0) && (
        <div className="brief-extras">
          {number && (
            <button type="button" className="number-card" onClick={() => onJump(number.id)}>
              <span className="number-eyebrow">Number of the day</span>
              <span className={number.value.length > 5 ? "number-value number-value-long" : "number-value"}>{number.value}</span>
              <span className="number-label">{number.label}</span>
            </button>
          )}
          {brief.quick_hits.length > 0 && (
            <div className="quick-hits">
              <h2 className="quick-hits-title">Quick hits</h2>
              <ul>
                {brief.quick_hits
                  .filter((h) => itemsById.has(h.id))
                  .map((h) => (
                    <li key={h.id}>
                      <button type="button" onClick={() => onJump(h.id)}>
                        <Inline text={h.text} />
                      </button>
                    </li>
                  ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {brief.sign_off && <p className="brief-signoff">{brief.sign_off}</p>}
    </section>
  );
}
