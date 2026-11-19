import { create } from "zustand";

interface ComposerState {
  /** A message waiting to be sent by the open conversation. */
  pending: string | null;
  /** Ask the open conversation to send this message (used by buttons outside the chat). */
  ask: (message: string) => void;
  clear: () => void;
}

export const useComposerStore = create<ComposerState>()((set) => ({
  pending: null,
  ask: (message) => set({ pending: message }),
  clear: () => set({ pending: null }),
}));
