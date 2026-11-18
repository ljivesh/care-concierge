import { Conversation, ConversationContent, ConversationScrollButton } from "@/components/ai-elements/conversation";
import {
  PromptInput,
  PromptInputBody,
  PromptInputFooter,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
} from "@/components/ai-elements/prompt-input";
import { ChatEmptyState } from "@/components/chat/chat-empty-state";
import { ChatMessage } from "@/components/chat/chat-message";
import { ChatSkeleton } from "@/components/chat/chat-skeleton";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { useConciergeChat } from "@/hooks/use-concierge-chat";
import type { Patient } from "@/lib/types/concierge";

interface Props {
  patient: Patient;
  threadId: string;
}

/**
 * One conversation. The parent gives this component a `key` of the thread id,
 * so switching patient or conversation mounts a fresh one.
 */
export function Chat({ patient, threadId }: Props) {
  const { messages, status, error, busy, restoring, send, retry } = useConciergeChat(patient.id, threadId);
  const lastId = messages.at(-1)?.id;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <Conversation>
        <ConversationContent className="mx-auto min-h-full w-full max-w-3xl">
          {restoring ? (
            <ChatSkeleton />
          ) : messages.length === 0 ? (
            <ChatEmptyState onPick={send} patient={patient} />
          ) : (
            messages.map((message) => (
              <ChatMessage
                key={message.id}
                message={message}
                onSuggest={message.id === lastId && !busy ? send : undefined}
              />
            ))
          )}

          {status === "submitted" && (
            <p className="flex items-center gap-2 text-muted-foreground text-sm">
              <Spinner className="size-3.5" />
              Thinking…
            </p>
          )}

          {error && (
            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm">
              <span className="text-destructive">{error.message || "Could not reach the server."}</span>
              <Button onClick={retry} size="sm" variant="outline">
                Try again
              </Button>
            </div>
          )}
        </ConversationContent>
        <ConversationScrollButton />
      </Conversation>

      <div className="mx-auto w-full max-w-3xl px-4 pb-4">
        <PromptInput onSubmit={({ text }) => send(text)}>
          <PromptInputBody>
            <PromptInputTextarea placeholder="Ask about the clinic, book a visit, or note a symptom" />
          </PromptInputBody>
          <PromptInputFooter>
            <PromptInputTools>
              <span className="px-2 text-muted-foreground text-xs">
                Not for emergencies. In an emergency call 112.
              </span>
            </PromptInputTools>
            <PromptInputSubmit status={status} />
          </PromptInputFooter>
        </PromptInput>
      </div>
    </div>
  );
}
