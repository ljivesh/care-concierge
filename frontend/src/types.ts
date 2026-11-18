// Shapes shared by the API client and the components.

export interface Citation {
  n: number;
  doc_id: string;
  title: string;
  heading_path: string;
}

/** One tool call in a turn, filled in when its result arrives. */
export interface ToolStep {
  id: string;
  name: string;
  args: Record<string, unknown>;
  status?: "success" | "error";
  result?: unknown;
}

export interface UserRow {
  role: "user";
  text: string;
}

export interface AssistantRow {
  role: "assistant";
  text: string;
  steps: ToolStep[];
  citations: Citation[];
  streaming?: boolean;
  error?: boolean;
}

export type ChatRow = UserRow | AssistantRow;

/** The Server-Sent Events that POST /v1/chat emits. */
export type ChatEvent =
  | { type: "token"; data: { text: string; replace?: boolean } }
  | { type: "tool_call"; data: { id: string; name: string; args: Record<string, unknown> } }
  | { type: "tool_result"; data: { id: string; name: string; status: "success" | "error"; result: unknown } }
  | { type: "citation"; data: Citation }
  | { type: "final"; data: { reply: string; citations: Citation[] } }
  | { type: "error"; data: { message: string } };

export interface ChatRequest {
  thread_id: string;
  patient_id: string;
  message: string;
  request_id: string;
}

/** One entry of GET /v1/threads/{thread_id}. */
export type TranscriptMessage =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string }
  | { role: "tool_call"; id: string; name: string; args: Record<string, unknown> }
  | { role: "tool_result"; id: string; name: string; status: "success" | "error"; result: unknown };

export interface Transcript {
  thread_id: string;
  patient_id: string;
  messages: TranscriptMessage[];
  citations: Citation[];
}
