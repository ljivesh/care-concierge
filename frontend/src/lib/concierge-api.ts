// The backend's wire format: the events POST /v1/chat streams, and the
// transcript GET /v1/threads/{id} returns. Nothing here knows about the AI SDK.

export interface Citation {
  n: number;
  doc_id: string;
  title: string;
  heading_path: string;
}

export type ConciergeEvent =
  | { type: "token"; data: { text: string; replace?: boolean } }
  | { type: "tool_call"; data: { id: string; name: string; args: unknown } }
  | { type: "tool_result"; data: { id: string; name: string; status: "success" | "error"; result: unknown } }
  | { type: "citation"; data: Citation }
  | { type: "final"; data: { reply: string; citations: Citation[] } }
  | { type: "error"; data: { message: string } };

export type TranscriptMessage =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string }
  | { role: "tool_call"; id: string; name: string; args: unknown }
  | { role: "tool_result"; id: string; name: string; status: "success" | "error"; result: unknown };

export interface Transcript {
  thread_id: string;
  patient_id: string;
  messages: TranscriptMessage[];
  citations: Citation[];
}

export interface ChatRequest {
  thread_id: string;
  patient_id: string;
  message: string;
  request_id: string;
}

/**
 * POST /v1/chat and yield each Server-Sent Event as it arrives.
 *
 * The browser's EventSource cannot send a POST body, so the response is read
 * as a stream and split by hand: events are separated by a blank line, and
 * each has an `event:` line and a `data:` line.
 */
export async function* streamChat(body: ChatRequest, signal?: AbortSignal): AsyncGenerator<ConciergeEvent> {
  const response = await fetch("/v1/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
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
    if (done) return;
    buffer += decoder.decode(value, { stream: true });

    let end: number;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const block = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const type = /^event: (.*)$/m.exec(block)?.[1];
      const data = /^data: (.*)$/m.exec(block)?.[1];
      if (type && data) yield { type, data: JSON.parse(data) } as ConciergeEvent;
    }
  }
}

/** The saved conversation, or null if the thread has no messages yet. */
export async function fetchTranscript(threadId: string): Promise<Transcript | null> {
  const response = await fetch(`/v1/threads/${threadId}`);
  return response.ok ? ((await response.json()) as Transcript) : null;
}

/** How a citation is shown under an answer. */
export function citationLabel(citation: Citation): string {
  return `[${citation.n}] ${citation.heading_path}`;
}

/** The patient-readable sentence inside a failed tool result. */
export function toolErrorText(result: unknown): string {
  const message = (result as { error?: { message?: unknown } } | null)?.error?.message;
  return typeof message === "string" ? message : "The tool call failed.";
}
