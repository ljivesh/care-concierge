import { NotebookPen } from "lucide-react";
import type { SymptomLog } from "@/lib/types/tools";
import { cn } from "@/lib/utils";

/** A logged symptom, with its 1-5 severity drawn as five dots. */
export function SymptomCard({ log }: { log: SymptomLog }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-card p-4">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <NotebookPen className="size-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="text-muted-foreground text-xs">Symptom noted for the care team</p>
        <p className="truncate font-medium text-sm">{log.symptom}</p>
      </div>
      <div aria-label={`Severity ${log.severity} of 5`} className="flex items-center gap-1" role="img">
        {[1, 2, 3, 4, 5].map((level) => (
          <span className={cn("size-2 rounded-full", level <= log.severity ? "bg-primary" : "bg-muted")} key={level} />
        ))}
        <span className="ml-1 text-muted-foreground text-xs tabular-nums">{log.severity}/5</span>
      </div>
    </div>
  );
}
