// The chat's state and behaviour, as one hook. Components only render what it returns.

import { useCallback, useEffect, useState } from "react";
import { fetchTranscript, streamChat } from "./api";
import { applyEvent, emptyReply, rowsFromTranscript } from "./transcript";
import type { AssistantRow, ChatRow } from "./types";

export function useChat(patientId: string, threadId: string) {
  const [rows, setRows] = useState<ChatRow[]>([]);
  const [busy, setBusy] = useState(false);

  // On load, and whenever the thread changes, restore the conversation from the server.
  useEffect(() => {
    let current = true;
    setRows([]);
    fetchTranscript(threadId)
      .then((transcript) => {
        if (current && transcript) setRows(rowsFromTranscript(transcript));
      })
      .catch(() => {
        // offline or server down: start with an empty conversation
      });
    return () => {
      current = false;
    };
  }, [threadId]);

  /** Change the reply currently being written (always the last row). */
  const updateReply = useCallback((change: (reply: AssistantRow) => AssistantRow) => {
    setRows((all) =>
      all.map((row, index) => (index === all.length - 1 && row.role === "assistant" ? change(row) : row)),
    );
  }, []);

  const send = useCallback(
    async (message: string) => {
      setBusy(true);
      setRows((all) => [...all, { role: "user", text: message }, emptyReply()]);
      try {
        await streamChat(
          // One request_id per message. The server uses it to make sure a repeated request writes once.
          { thread_id: threadId, patient_id: patientId, message, request_id: crypto.randomUUID() },
          (event) => updateReply((reply) => applyEvent(reply, event)),
        );
      } catch (problem) {
        const text = problem instanceof Error ? problem.message : "Could not reach the server.";
        updateReply((reply) => ({ ...reply, text, error: true }));
      } finally {
        updateReply((reply) => ({ ...reply, streaming: false }));
        setBusy(false);
      }
    },
    [patientId, threadId, updateReply],
  );

  return { rows, busy, send };
}
