// What each tool returns, and guards to recognise it. Tool results reach the
// page as `unknown`, so a card checks the shape before it renders.

export interface Booking {
  id: string;
  clinician_name: string;
  service: "DOCTOR" | "LAB";
  subtype: string;
  scheduled_for: string; // ISO time in the society's timezone
  status: string;
  /** True when the patient asked again for an appointment they already hold. */
  already_booked?: boolean;
}

export interface SymptomLog {
  id: string;
  symptom: string;
  severity: number;
}

export interface Escalation {
  id: string;
  level: number;
  status: string;
  nurse_callback_minutes: number;
  call_first: string;
  hospital_name: string;
  hospital_emergency_phone: string;
}

export interface Passage {
  n: number;
  doc_id: string;
  title: string;
  heading_path: string;
  similarity: number;
}

export interface SlotSuggestion {
  clinician_name: string;
  scheduled_for: string;
  label: string;
}

export interface ToolError {
  error: { code: string; message: string; suggestions?: SlotSuggestion[] };
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

export const isToolError = (value: unknown): value is ToolError => isRecord(value) && isRecord(value.error);

export const isBooking = (value: unknown): value is Booking =>
  isRecord(value) && typeof value.clinician_name === "string" && typeof value.scheduled_for === "string";

export const isBookingList = (value: unknown): value is Booking[] => Array.isArray(value) && value.every(isBooking);

export const isSymptomLog = (value: unknown): value is SymptomLog =>
  isRecord(value) && typeof value.symptom === "string" && typeof value.severity === "number";

export const isEscalation = (value: unknown): value is Escalation =>
  isRecord(value) && typeof value.hospital_emergency_phone === "string";

export const isPassageList = (value: unknown): value is Passage[] =>
  Array.isArray(value) && value.every((item) => isRecord(item) && typeof item.heading_path === "string");

export const isSlotList = (value: unknown): value is SlotSuggestion[] =>
  Array.isArray(value) && value.every((item) => isRecord(item) && typeof item.label === "string");
