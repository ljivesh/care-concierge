import type { SourceDocumentUIPart } from "ai";
import { BookOpenText, ChevronRight } from "lucide-react";
import { Fragment } from "react";

/**
 * The document sections an answer cites. Always visible: an answer about the
 * clinic shows where it came from. A heading path such as
 * "Society Annex — Lotus Tower > Wellness room > Hours" is drawn as a trail.
 */
export function Citations({ citations }: { citations: SourceDocumentUIPart[] }) {
  if (citations.length === 0) return null;
  return (
    <div className="space-y-1.5 border-t pt-3">
      <p className="flex items-center gap-1.5 font-medium text-muted-foreground text-xs">
        <BookOpenText className="size-3.5" />
        Sources
      </p>
      <ol className="space-y-1 text-xs">
        {citations.map((citation) => {
          const trail = citation.title.split(" > ");
          return (
            <li className="flex items-start gap-2" key={citation.sourceId}>
              <span className="mt-px flex h-4 min-w-4 items-center justify-center rounded bg-primary/10 px-1 font-medium text-[10px] text-primary tabular-nums">
                {citation.sourceId}
              </span>
              <span className="flex flex-wrap items-center gap-x-1 text-muted-foreground">
                {trail.map((heading, index) => (
                  <Fragment key={index}>
                    {index > 0 && <ChevronRight className="size-3 opacity-60" />}
                    <span className={index === trail.length - 1 ? "font-medium text-foreground" : undefined}>
                      {heading}
                    </span>
                  </Fragment>
                ))}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
