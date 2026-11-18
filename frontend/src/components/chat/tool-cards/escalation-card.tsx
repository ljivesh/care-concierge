import { Phone, Siren } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import type { Escalation } from "@/lib/types/tools";

const dial = (phone: string) => `tel:${phone.replace(/[^\d+]/g, "")}`;

/** An emergency: the numbers to call come first, as buttons that dial on a phone. */
export function EscalationCard({ escalation }: { escalation: Escalation }) {
  return (
    <Alert variant="destructive">
      <Siren />
      <AlertTitle>Emergency: call now</AlertTitle>
      <AlertDescription className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <Button asChild size="sm" variant="destructive">
            <a href={dial(escalation.call_first)}>
              <Phone />
              Call {escalation.call_first}
            </a>
          </Button>
          <Button asChild size="sm" variant="outline">
            <a href={dial(escalation.hospital_emergency_phone)}>
              <Phone />
              {escalation.hospital_name} · {escalation.hospital_emergency_phone}
            </a>
          </Button>
        </div>
        <p>
          The care team has been alerted (level {escalation.level}). A nurse will call within{" "}
          {escalation.nurse_callback_minutes} minutes. Do not wait for the call.
        </p>
      </AlertDescription>
    </Alert>
  );
}
