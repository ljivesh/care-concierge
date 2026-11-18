// Turns the saved transcript (GET /v1/threads/{id}) into AI SDK messages,
// so a reloaded conversation renders exactly like a live one.

import type { UIMessage } from "ai";
import { citationLabel, toolErrorText, type Transcript } from "./concierge-api";

type Part = UIMessage["parts"][number];

export function messagesFromTranscript(transcript: Transcript): UIMessage[] {
  const messages: UIMessage[] = [];
  let reply: Part[] = []; // everything the assistant did since the last user message

  const closeReply = () => {
    if (reply.length > 0) messages.push({ id: crypto.randomUUID(), role: "assistant", parts: reply });
    reply = [];
  };

  for (const entry of transcript.messages) {
    if (entry.role === "user") {
      closeReply();
      messages.push({ id: crypto.randomUUID(), role: "user", parts: [{ type: "text", text: entry.content }] });
    } else if (entry.role === "assistant") {
      reply.push({ type: "text", text: entry.content });
    } else if (entry.role === "tool_call") {
      reply.push({
        type: "dynamic-tool",
        toolCallId: entry.id,
        toolName: entry.name,
        state: "input-available",
        input: entry.args,
      });
    } else {
      // Fill in the result on the call it belongs to.
      reply = reply.map((part): Part => {
        if (part.type !== "dynamic-tool" || part.toolCallId !== entry.id) return part;
        const call = { type: part.type, toolCallId: part.toolCallId, toolName: part.toolName, input: part.input };
        return entry.status === "success"
          ? { ...call, state: "output-available", output: entry.result }
          : { ...call, state: "output-error", errorText: toolErrorText(entry.result) };
      });
    }
  }

  // The server keeps citations for the most recent reply only.
  for (const citation of transcript.citations) {
    reply.push({
      type: "source-document",
      sourceId: String(citation.n),
      mediaType: "text/markdown",
      title: citationLabel(citation),
      filename: citation.doc_id,
    });
  }
  closeReply();
  return messages;
}
