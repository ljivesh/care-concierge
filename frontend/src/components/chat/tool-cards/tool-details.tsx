import { ChevronRight } from "lucide-react";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

interface Props {
  toolName: string;
  input: unknown;
  output: unknown;
}

/** The raw tool call behind a card: its name, arguments and result. Closed by default. */
export function ToolDetails({ toolName, input, output }: Props) {
  return (
    <Collapsible className="text-muted-foreground text-xs">
      <CollapsibleTrigger className="group flex items-center gap-1 hover:text-foreground">
        <ChevronRight className="size-3 transition-transform group-data-[state=open]:rotate-90" />
        <code>{toolName}</code>
      </CollapsibleTrigger>
      <CollapsibleContent className="mt-2 space-y-2">
        <Json label="Arguments" value={input} />
        {output !== undefined && <Json label="Result" value={output} />}
      </CollapsibleContent>
    </Collapsible>
  );
}

function Json({ label, value }: { label: string; value: unknown }) {
  return (
    <div>
      <p className="mb-1 font-medium uppercase tracking-wide">{label}</p>
      <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words rounded-md bg-muted p-2 font-mono">
        {JSON.stringify(value, null, 2)}
      </pre>
    </div>
  );
}
