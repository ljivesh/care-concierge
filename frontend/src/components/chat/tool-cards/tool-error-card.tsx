import { CircleAlert } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { ToolError } from "@/lib/types/tools";

interface Props {
  error: ToolError["error"];
  /** Sends a message; used by the suggested-slot buttons. */
  onSuggest?: (message: string) => void;
}

const TITLES: Record<string, string> = {
  SLOT_TAKEN: "That slot was just taken",
  NOT_A_SLOT: "No slot at that time",
  NOT_OFFERED_AT_SOCIETY: "Not offered at your society",
};

/** A tool call the server refused. Free slots, when offered, are one tap away. */
export function ToolErrorCard({ error, onSuggest }: Props) {
  const suggestions = error.suggestions ?? [];
  return (
    <Alert>
      <CircleAlert />
      <AlertTitle>{TITLES[error.code] ?? "That did not go through"}</AlertTitle>
      <AlertDescription className="space-y-3">
        {suggestions.length === 0 && <p>{error.message}</p>}
        {suggestions.length > 0 && (
          <>
            <p>Free slots with {suggestions[0].clinician_name}:</p>
            <div className="flex flex-wrap gap-2">
              {suggestions.map((slot) => (
                <Button
                  disabled={!onSuggest}
                  key={slot.scheduled_for}
                  onClick={() => onSuggest?.(`Book ${slot.label}`)}
                  size="sm"
                  variant="outline"
                >
                  {slot.label}
                </Button>
              ))}
            </div>
          </>
        )}
      </AlertDescription>
    </Alert>
  );
}
