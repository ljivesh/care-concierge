// The bridge between our backend and the AI SDK.
//
// `useChat` does not talk to a server itself; it asks a "transport" to send the
// messages and hand back a stream of chunks in the AI SDK's own format. This
// transport calls POST /v1/chat and translates each of our SSE events into the
// matching chunk:
//
//   token        -> text-start / text-delta
//   tool_call    -> tool-input-available
//   tool_result  -> tool-output-available | tool-output-error
//   citation     -> source-document
//   final        -> text-end, finish
//   error        -> error

import type { ChatTransport, UIMessage, UIMessageChunk } from "ai";
import { citationLabel, streamChat, toolErrorText, type ChatRequest } from "./concierge-api";

function textOf(message: UIMessage): string {
  return message.parts.map((part) => (part.type === "text" ? part.text : "")).join("");
}

function toChunks(request: ChatRequest, signal?: AbortSignal): ReadableStream<UIMessageChunk> {
  return new ReadableStream<UIMessageChunk>({
    async start(controller) {
      let textId = 0; // each run of text between tool calls is its own text part
      let textOpen = false;
      const closeText = () => {
        if (textOpen) controller.enqueue({ type: "text-end", id: `text-${textId}` });
        textOpen = false;
      };

      controller.enqueue({ type: "start" });
      try {
        for await (const event of streamChat(request, signal)) {
          switch (event.type) {
            case "token":
              if (event.data.replace) closeText(); // the server is sending the whole reply in one piece
              if (!textOpen) {
                textId += 1;
                textOpen = true;
                controller.enqueue({ type: "text-start", id: `text-${textId}` });
              }
              controller.enqueue({ type: "text-delta", id: `text-${textId}`, delta: event.data.text });
              break;
            case "tool_call":
              closeText();
              controller.enqueue({
                type: "tool-input-available",
                toolCallId: event.data.id,
                toolName: event.data.name,
                input: event.data.args,
                dynamic: true, // the tools live on the server; the page has no schema for them
              });
              break;
            case "tool_result":
              if (event.data.status === "success") {
                controller.enqueue({
                  type: "tool-output-available",
                  toolCallId: event.data.id,
                  output: event.data.result,
                  dynamic: true,
                });
              } else {
                controller.enqueue({
                  type: "tool-output-error",
                  toolCallId: event.data.id,
                  errorText: toolErrorText(event.data.result),
                  dynamic: true,
                });
              }
              break;
            case "citation":
              controller.enqueue({
                type: "source-document",
                sourceId: String(event.data.n),
                mediaType: "text/markdown",
                title: citationLabel(event.data),
                filename: event.data.doc_id,
              });
              break;
            case "final":
              closeText();
              break;
            case "error":
              closeText();
              controller.enqueue({ type: "error", errorText: event.data.message });
              break;
          }
        }
        closeText();
        controller.enqueue({ type: "finish" });
        controller.close();
      } catch (problem) {
        controller.error(problem);
      }
    },
  });
}

export class ConciergeTransport implements ChatTransport<UIMessage> {
  constructor(private readonly patientId: string) {}

  async sendMessages({
    chatId,
    messages,
    abortSignal,
  }: Parameters<ChatTransport<UIMessage>["sendMessages"]>[0]): Promise<ReadableStream<UIMessageChunk>> {
    const lastUserMessage = [...messages].reverse().find((message) => message.role === "user");
    if (!lastUserMessage) throw new Error("There is no message to send.");
    return toChunks(
      {
        thread_id: chatId,
        patient_id: this.patientId,
        message: textOf(lastUserMessage),
        // The message's own id is the request_id. Sending the same message again
        // (a retry) reuses it, and the server then writes nothing twice.
        request_id: lastUserMessage.id,
      },
      abortSignal,
    );
  }

  // The server keeps no open stream to rejoin; a reload restores from the transcript instead.
  async reconnectToStream(): Promise<null> {
    return null;
  }
}
