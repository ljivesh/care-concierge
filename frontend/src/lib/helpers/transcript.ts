// Turns the saved transcript (GET /v1/threads/{id}) into AI SDK messages,
// so a reloaded conversation renders exactly like a live one.

import type { UIMessage } from "ai";
import type { Citation, Transcript } from "@/lib/types/concierge";

type Part = UIMessage["parts"][number];

/** A citation as an AI SDK part. The heading path travels in `title`. */
export function citationPart(citation: Citation) {
  return {
    type: "source-document" as const,
    sourceId: String(citation.n),
    mediaType: "text/markdown",
    title: citation.heading_path,
    filename: citation.doc_id,
  };
}

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
      reply = reply.map((part): Part =>
        part.type === "dynamic-tool" && part.toolCallId === entry.id
          ? {
              type: "dynamic-tool",
              toolCallId: part.toolCallId,
              toolName: part.toolName,
              input: part.input,
              state: "output-available",
              output: entry.result,
            }
          : part,
      );
    }
  }

  // The server keeps citations for the most recent reply only.
  reply.push(...transcript.citations.map(citationPart));
  closeReply();
  return messages;
}
