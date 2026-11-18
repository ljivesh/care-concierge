// Everything that talks to the backend lives here.

import type { ChatEvent, ChatRequest, Transcript } from "./types";

/**
 * POST /v1/chat and call `onEvent` for each Server-Sent Event as it arrives.
 *
 * The browser's EventSource cannot send a POST body, so the response is read
 * as a stream and split into events by hand: events are separated by a blank
 * line, and each has an `event:` line and a `data:` line.
 */
export async function streamChat(body: ChatRequest, onEvent: (event: ChatEvent) => void): Promise<void> {
  const response = await fetch("/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    const problem = await response.json().catch(() => ({}));
    throw new Error(typeof problem.detail === "string" ? problem.detail : "The request was not accepted.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const type = /^event: (.*)$/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (type && data) onEvent({ type, data: JSON.parse(data) } as ChatEvent);
    }
  }
}

/** The saved conversation, or null if the thread has no messages yet. */
export async function fetchTranscript(threadId: string): Promise<Transcript | null> {
  const response = await fetch(`/v1/threads/${threadId}`);
  return response.ok ? ((await response.json()) as Transcript) : null;
}
