import { create } from "zustand";
import { persist } from "zustand/middleware";
import { DEFAULT_PATIENT_ID, PATIENTS } from "@/config/constants";
import type { Patient } from "@/lib/types/concierge";

interface PatientState {
  activePatientId: string;
  setActivePatientId: (patientId: string) => void;
}

/** Which seed patient the page is acting as. Remembered across reloads. */
export const usePatientStore = create<PatientState>()(
  persist(
    (set) => ({
      activePatientId: DEFAULT_PATIENT_ID,
      setActivePatientId: (patientId) => set({ activePatientId: patientId }),
    }),
    { name: "care-patient" },
  ),
);

export function useActivePatient(): Patient {
  const id = usePatientStore((state) => state.activePatientId);
  return PATIENTS.find((patient) => patient.id === id) ?? PATIENTS[0];
}
