import type { UIMessage } from "ai";
import { Message, MessageContent, MessageResponse } from "@/components/ai-elements/message";
import { Citations } from "@/components/chat/citations";
import { ToolCard } from "@/components/chat/tool-cards/tool-card";

interface Props {
  message: UIMessage;
  /** Set only on the latest reply, so buttons in old messages do nothing. */
  onSuggest?: (message: string) => void;
}

/** One message: its tool cards, its text, and the sections it cites. */
export function ChatMessage({ message, onSuggest }: Props) {
  const citations = message.parts.filter((part) => part.type === "source-document");

  return (
    <Message from={message.role}>
      <MessageContent className="gap-3">
        {message.parts.map((part, index) => {
          if (part.type === "text") return <MessageResponse key={index}>{part.text}</MessageResponse>;
          if (part.type === "dynamic-tool") return <ToolCard key={part.toolCallId} onSuggest={onSuggest} part={part} />;
          return null;
        })}
        <Citations citations={citations} />
      </MessageContent>
    </Message>
  );
}
