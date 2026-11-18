import type { DynamicToolUIPart } from "ai";
import { BookingCard, BookingsListCard } from "@/components/chat/tool-cards/booking-card";
import { EscalationCard } from "@/components/chat/tool-cards/escalation-card";
import { SearchCard } from "@/components/chat/tool-cards/search-card";
import { SymptomCard } from "@/components/chat/tool-cards/symptom-card";
import { ToolDetails } from "@/components/chat/tool-cards/tool-details";
import { ToolErrorCard } from "@/components/chat/tool-cards/tool-error-card";
import { Spinner } from "@/components/ui/spinner";
import {
  isBooking,
  isBookingList,
  isEscalation,
  isPassageList,
  isSymptomLog,
  isToolError,
} from "@/lib/types/tools";

const RUNNING_LABEL: Record<string, string> = {
  book_service: "Booking your appointment",
  list_service_requests: "Looking up your bookings",
  log_symptom: "Noting your symptom",
  search_clinic_docs: "Searching the clinic documents",
  escalate_emergency: "Alerting the care team",
};

interface Props {
  part: DynamicToolUIPart;
  /** Lets a card send a follow-up message. Off for old messages. */
  onSuggest?: (message: string) => void;
}

/** Picks the right card for a tool call, by what the tool returned. */
function ToolResult({ part, onSuggest }: Props) {
  const { output } = part;
  if (isToolError(output)) return <ToolErrorCard error={output.error} onSuggest={onSuggest} />;
  if (part.toolName === "search_clinic_docs" && isPassageList(output)) return <SearchCard passages={output} />;
  if (isEscalation(output)) return <EscalationCard escalation={output} />;
  if (isBookingList(output)) return <BookingsListCard bookings={output} />;
  if (isBooking(output)) return <BookingCard booking={output} />;
  if (isSymptomLog(output)) return <SymptomCard log={output} />;
  return null; // an unknown shape: the details below still show it
}

/**
 * One tool call in the conversation: a spinner while it runs, then a card
 * built from its result, with the raw call available underneath.
 */
export function ToolCard({ part, onSuggest }: Props) {
  if (part.state !== "output-available") {
    return (
      <p className="flex items-center gap-2 text-muted-foreground text-sm">
        <Spinner className="size-3.5" />
        {RUNNING_LABEL[part.toolName] ?? "Working"}…
      </p>
    );
  }
  return (
    <div className="space-y-2">
      <ToolResult onSuggest={onSuggest} part={part} />
      <ToolDetails input={part.input} output={part.output} toolName={part.toolName} />
    </div>
  );
}
