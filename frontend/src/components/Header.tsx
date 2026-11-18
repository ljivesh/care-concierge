import { PATIENTS } from "../patients";

interface Props {
  patientId: string;
  disabled: boolean;
  onPatientChange: (patientId: string) => void;
  onNewChat: () => void;
}

export function Header({ patientId, disabled, onPatientChange, onNewChat }: Props) {
  return (
    <header>
      <h1>Care Concierge</h1>
      <select
        aria-label="Patient"
        value={patientId}
        disabled={disabled}
        onChange={(event) => onPatientChange(event.target.value)}
      >
        {PATIENTS.map((patient) => (
          <option key={patient.id} value={patient.id}>
            {patient.name} · {patient.society}
          </option>
        ))}
      </select>
      <button className="ghost" type="button" disabled={disabled} onClick={onNewChat}>
        New chat
      </button>
    </header>
  );
}
