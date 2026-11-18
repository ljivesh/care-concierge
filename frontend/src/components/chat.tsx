import { useChat } from "@ai-sdk/react";
import { useEffect, useMemo } from "react";
import {
  Conversation,
  ConversationContent,
  ConversationEmptyState,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
} from "@/components/ai-elements/prompt-input";
import { ChatMessage } from "@/components/chat-message";
import { Button } from "@/components/ui/button";
import { fetchTranscript } from "@/lib/concierge-api";
import { ConciergeTransport } from "@/lib/concierge-transport";
import { messagesFromTranscript } from "@/lib/transcript";

interface Props {
  patientId: string;
  threadId: string;
}

/**
 * One conversation. The parent gives this component a `key` of the thread id,
 * so switching patient or starting a new chat mounts a fresh one.
 */
export function Chat({ patientId, threadId }: Props) {
  const transport = useMemo(() => new ConciergeTransport(patientId), [patientId]);
  const { messages, setMessages, sendMessage, regenerate, status, error, clearError } = useChat({
    id: threadId,
    transport,
    // Message ids double as request ids, and the server requires a UUID there.
    generateId: () => crypto.randomUUID(),
  });

  // On load: restore the conversation from the server.
  useEffect(() => {
    let current = true;
    fetchTranscript(threadId)
      .then((transcript) => {
        if (current && transcript) setMessages(messagesFromTranscript(transcript));
      })
      .catch(() => {
        // offline or server down: start with an empty conversation
      });
    return () => {
      current = false;
    };
  }, [threadId, setMessages]);

  const busy = status === "submitted" || status === "streaming";

  return (
    <>
      <Conversation>
        <ConversationContent className="mx-auto w-full max-w-3xl">
          {messages.length === 0 ? (
            <ConversationEmptyState
              title="How can we help?"
              description="Book a consultation or lab test, see your bookings, note a symptom, or ask about the clinic. English, हिंदी or Hinglish."
            />
          ) : (
            messages.map((message) => <ChatMessage key={message.id} message={message} />)
          )}
          {error && (
            <div className="flex items-center gap-3 text-destructive text-sm">
              <span>{error.message || "Could not reach the server."}</span>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  clearError();
                  // Resends the same message with the same id, so the server will not act twice.
                  void regenerate();
                }}
              >
                Retry
              </Button>
            </div>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      <div className="mx-auto w-full max-w-3xl px-4 pb-4">
        <PromptInput
          onSubmit={({ text }) => {
            if (text.trim() && !busy) void sendMessage({ text: text.trim() });
          }}
        >
          <PromptInputBody>
            <PromptInputTextarea placeholder="Type a message" />
          </PromptInputBody>
          <PromptInputFooter>
            <PromptInputTools />
            <PromptInputSubmit status={status} />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </>
  );
}
