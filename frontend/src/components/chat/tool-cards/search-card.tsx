import { ChevronRight, FileSearch } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { Passage } from "@/lib/types/tools";

/** What the document search found. One line; open it to see the sections. */
export function SearchCard({ passages }: { passages: Passage[] }) {
  if (passages.length === 0) {
    return (
      <p className="flex items-center gap-2 text-muted-foreground text-xs">
        <FileSearch className="size-3.5" />
        Searched the clinic documents: nothing relevant found
      </p>
    );
  }
  return (
    <Collapsible className="text-muted-foreground text-xs">
      <CollapsibleTrigger className="group flex items-center gap-2 hover:text-foreground">
        <FileSearch className="size-3.5" />
        Searched the clinic documents: {passages.length} {passages.length === 1 ? "section" : "sections"}
        <ChevronRight className="size-3 transition-transform group-data-[state=open]:rotate-90" />
      </CollapsibleTrigger>
      <CollapsibleContent>
        <ol className="mt-2 space-y-1 border-l pl-3">
          {passages.map((passage) => (
            <li key={passage.n}>
              <span className="font-medium text-foreground">[{passage.n}]</span> {passage.heading_path}
            </li>
          ))}
        </ol>
      </CollapsibleContent>
    </Collapsible>
  );
}
