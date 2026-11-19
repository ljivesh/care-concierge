import { create } from "zustand";
import { fetchBookings } from "@/lib/api/concierge-api";
import type { Booking } from "@/lib/types/tools";

interface BookingsState {
  byPatient: Record<string, Booking[]>;
  /** Load the patient's bookings from the server. Called on open and after every turn. */
  refresh: (patientId: string) => Promise<void>;
}

export const useBookingsStore = create<BookingsState>()((set) => ({
  byPatient: {},
  refresh: async (patientId) => {
    try {
      const bookings = await fetchBookings(patientId);
      set((state) => ({ byPatient: { ...state.byPatient, [patientId]: bookings } }));
    } catch {
      // server unreachable: keep what is already shown
    }
  },
}));
