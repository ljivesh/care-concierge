// The backend's wire format: what POST /v1/chat streams and GET /v1/threads/{id} returns.

export type Language = "en" | "hi" | "hinglish";

export interface Patient {
  id: string;
  name: string;
  society: string;
  language: Language;
}

export interface Citation {
  n: number;
  doc_id: string;
  title: string;
  heading_path: string;
}

export type ToolStatus = "success" | "error";

/** The Server-Sent Events of one chat turn. */
export type ConciergeEvent =
  | { type: "token"; data: { text: string; replace?: boolean } }
  | { type: "tool_call"; data: { id: string; name: string; args: unknown } }
  | { type: "tool_result"; data: { id: string; name: string; status: ToolStatus; result: unknown } }
  | { type: "citation"; data: Citation }
  | { type: "final"; data: { reply: string; citations: Citation[] } }
  | { type: "error"; data: { message: string } };

export interface ChatRequest {
  thread_id: string;
  patient_id: string;
  message: string;
  request_id: string;
}

export type TranscriptMessage =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string }
  | { role: "tool_call"; id: string; name: string; args: unknown }
  | { role: "tool_result"; id: string; name: string; status: ToolStatus; result: unknown };

export interface Transcript {
  thread_id: string;
  patient_id: string;
  messages: TranscriptMessage[];
  citations: Citation[];
}
