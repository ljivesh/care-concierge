import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PATIENTS } from "@/lib/patients";

interface Props {
  patientId: string;
  onPatientChange: (patientId: string) => void;
  onNewChat: () => void;
}

export function AppHeader({ patientId, onPatientChange, onNewChat }: Props) {
  return (
    <header className="border-b">
      <div className="mx-auto flex w-full max-w-3xl flex-wrap items-center gap-2 px-4 py-3">
        <h1 className="mr-auto font-semibold">Care Concierge</h1>
        <Select value={patientId} onValueChange={onPatientChange}>
          <SelectTrigger aria-label="Patient" className="w-64">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PATIENTS.map((patient) => (
              <SelectItem key={patient.id} value={patient.id}>
                {patient.name} · {patient.society}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button variant="outline" onClick={onNewChat}>
          New chat
        </Button>
      </div>
    </header>
  );
}
