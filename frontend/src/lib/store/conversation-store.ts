import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface ConversationSummary {
  id: string; // the thread_id sent to the server
  title: string;
  updatedAt: number;
}

interface ConversationState {
  /** Each patient's conversations, newest first. */
  byPatient: Record<string, ConversationSummary[]>;
  /** The conversation each patient currently has open. */
  activeByPatient: Record<string, string>;
  /** Open a new, empty conversation. It joins the list once a message is sent. */
  startNew: (patientId: string) => void;
  select: (patientId: string, threadId: string) => void;
  /** Record activity: adds the conversation on its first message, then moves it to the top. */
  touch: (patientId: string, threadId: string, title: string) => void;
  remove: (patientId: string, threadId: string) => void;
}

/**
 * The list of conversations in the sidebar. The messages themselves live on
 * the server (the LangGraph checkpointer); the server has no "list my threads"
 * endpoint, so the page remembers the thread ids and titles it has used.
 */
export const useConversationStore = create<ConversationState>()(
  persist(
    (set) => ({
      byPatient: {},
      activeByPatient: {},

      startNew: (patientId) =>
        set((state) => ({ activeByPatient: { ...state.activeByPatient, [patientId]: crypto.randomUUID() } })),

      select: (patientId, threadId) =>
        set((state) => ({ activeByPatient: { ...state.activeByPatient, [patientId]: threadId } })),

      touch: (patientId, threadId, title) =>
        set((state) => {
          const list = state.byPatient[patientId] ?? [];
          const existing = list.find((conversation) => conversation.id === threadId);
          const updated = { id: threadId, title: existing?.title ?? title, updatedAt: Date.now() };
          const others = list.filter((conversation) => conversation.id !== threadId);
          return { byPatient: { ...state.byPatient, [patientId]: [updated, ...others] } };
        }),

      remove: (patientId, threadId) =>
        set((state) => {
          const list = (state.byPatient[patientId] ?? []).filter((conversation) => conversation.id !== threadId);
          const wasOpen = state.activeByPatient[patientId] === threadId;
          return {
            byPatient: { ...state.byPatient, [patientId]: list },
            activeByPatient: wasOpen
              ? { ...state.activeByPatient, [patientId]: crypto.randomUUID() }
              : state.activeByPatient,
          };
        }),
    }),
    { name: "care-conversations" },
  ),
);
