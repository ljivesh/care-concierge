// Pure functions that build and update the list of chat rows.
// Kept out of the components so the logic can be read (and tested) on its own.

import type { AssistantRow, ChatEvent, ChatRow, ToolStep, Transcript } from "./types";

export function emptyReply(): AssistantRow {
  return { role: "assistant", text: "", steps: [], citations: [], streaming: true };
}

/** Apply one streamed event to the reply that is being written. */
export function applyEvent(reply: AssistantRow, event: ChatEvent): AssistantRow {
  switch (event.type) {
    case "token":
      return { ...reply, text: event.data.replace ? event.data.text : reply.text + event.data.text };
    case "tool_call":
      // Any text streamed before a tool call was not the final reply.
      return { ...reply, text: "", steps: [...reply.steps, { ...event.data }] };
    case "tool_result":
      return {
        ...reply,
        steps: reply.steps.map((step) =>
          step.id === event.data.id ? { ...step, status: event.data.status, result: event.data.result } : step,
        ),
      };
    case "citation":
      return { ...reply, citations: [...reply.citations, event.data] };
    case "final":
      return { ...reply, text: event.data.reply, citations: event.data.citations, streaming: false };
    case "error":
      return { ...reply, text: event.data.message, error: true, streaming: false };
  }
}

/** Turn the saved transcript (GET /v1/threads/{id}) back into chat rows. */
export function rowsFromTranscript(transcript: Transcript): ChatRow[] {
  const rows: ChatRow[] = [];
  let steps: ToolStep[] = [];
  for (const message of transcript.messages) {
    if (message.role === "user") {
      rows.push({ role: "user", text: message.content });
      steps = [];
    } else if (message.role === "tool_call") {
      steps.push({ id: message.id, name: message.name, args: message.args });
    } else if (message.role === "tool_result") {
      const step = steps.find((candidate) => candidate.id === message.id);
      if (step) {
        step.status = message.status;
        step.result = message.result;
      }
    } else {
      rows.push({ role: "assistant", text: message.content, steps, citations: [] });
      steps = [];
    }
  }
  // The server keeps citations for the most recent reply only.
  const last = rows[rows.length - 1];
  if (last?.role === "assistant") last.citations = transcript.citations;
  return rows;
}
