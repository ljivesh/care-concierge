import { CalendarClock } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { SlotSuggestion } from "@/lib/types/tools";

interface Props {
  slots: SlotSuggestion[];
  /** Sends a message; tapping a slot asks to book it. */
  onSuggest?: (message: string) => void;
}

/** Free slots, grouped by day. A label looks like "Thu 19 Nov 2026, 07:15". */
export function SlotsCard({ slots, onSuggest }: Props) {
  if (slots.length === 0) {
    return (
      <p className="rounded-xl border border-dashed p-4 text-muted-foreground text-sm">
        No free slots in the next two weeks.
      </p>
    );
  }

  const days = new Map<string, SlotSuggestion[]>();
  for (const slot of slots) {
    const day = slot.label.split(", ")[0];
    days.set(day, [...(days.get(day) ?? []), slot]);
  }

  return (
    <div className="space-y-3 rounded-xl border bg-card p-4">
      <p className="flex items-center gap-2 font-medium text-sm">
        <CalendarClock className="size-4 text-primary" />
        Free slots with {slots[0].clinician_name}
      </p>
      {[...days].map(([day, daySlots]) => (
        <div className="flex flex-wrap items-center gap-2" key={day}>
          <span className="w-28 shrink-0 text-muted-foreground text-xs">{day}</span>
          {daySlots.map((slot) => (
            <Button
              disabled={!onSuggest}
              key={slot.scheduled_for}
              onClick={() => onSuggest?.(`Book ${slot.label}`)}
              size="sm"
              variant="outline"
            >
              {slot.label.split(", ")[1]}
            </Button>
          ))}
        </div>
      ))}
    </div>
  );
}
