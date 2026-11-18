import { useChat } from "@ai-sdk/react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { fetchTranscript } from "@/lib/api/concierge-api";
import { ConciergeTransport } from "@/lib/api/concierge-transport";
import { titleFrom } from "@/lib/helpers/format";
import { messagesFromTranscript } from "@/lib/helpers/transcript";
import { useConversationStore } from "@/lib/store/conversation-store";

/**
 * One conversation with the concierge: the AI SDK's `useChat`, wired to our
 * backend, plus restoring the saved transcript when the conversation opens.
 */
export function useConciergeChat(patientId: string, threadId: string) {
  const transport = useMemo(() => new ConciergeTransport(patientId), [patientId]);
  const { messages, setMessages, sendMessage, regenerate, status, error, clearError } = useChat({
    id: threadId,
    transport,
    // Message ids double as request ids, and the server requires a UUID there.
    generateId: () => crypto.randomUUID(),
  });

  const [restoring, setRestoring] = useState(true);
  useEffect(() => {
    let current = true;
    fetchTranscript(threadId)
      .then((transcript) => {
        if (current && transcript) setMessages(messagesFromTranscript(transcript));
      })
      .catch(() => {
        // offline or server down: start with an empty conversation
      })
      .finally(() => {
        if (current) setRestoring(false);
      });
    return () => {
      current = false;
    };
  }, [threadId, setMessages]);

  const touch = useConversationStore((state) => state.touch);
  const busy = status === "submitted" || status === "streaming";

  const send = useCallback(
    (text: string) => {
      const message = text.trim();
      if (!message || busy) return;
      touch(patientId, threadId, titleFrom(message));
      void sendMessage({ text: message });
    },
    [busy, patientId, threadId, touch, sendMessage],
  );

  /** Resend the last message with the same id, so the server does not act twice. */
  const retry = useCallback(() => {
    clearError();
    void regenerate();
  }, [clearError, regenerate]);

  return { messages, status, error, busy, restoring, send, retry };
}
