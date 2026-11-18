import type { UIMessage } from "ai";
import { BookIcon } from "lucide-react";
import { Message, MessageContent, MessageResponse } from "@/components/ai-elements/message";
import { Tool, ToolContent, ToolHeader, ToolInput, ToolOutput } from "@/components/ai-elements/tool";

/** One message: its tool calls, its text, and the document sections it cites. */
export function ChatMessage({ message }: { message: UIMessage }) {
  const citations = message.parts.filter((part) => part.type === "source-document");

  return (
    <Message from={message.role}>
      <MessageContent>
        {message.parts.map((part, index) => {
          if (part.type === "text") {
            return <MessageResponse key={index}>{part.text}</MessageResponse>;
          }
          if (part.type === "dynamic-tool") {
            return (
              <Tool key={part.toolCallId}>
                <ToolHeader type="dynamic-tool" state={part.state} toolName={part.toolName} />
                <ToolContent>
                  <ToolInput input={part.input} />
                  <ToolOutput output={part.output} errorText={part.errorText} />
                </ToolContent>
              </Tool>
            );
          }
          return null;
        })}

        {/* Always visible: an answer about the clinic shows where it came from. */}
        {citations.length > 0 && (
          <ul className="flex flex-col gap-1 text-muted-foreground text-xs">
            {citations.map((citation) => (
              <li className="flex items-start gap-2" key={citation.sourceId}>
                <BookIcon className="mt-0.5 size-3.5 shrink-0" />
                <span>{citation.title}</span>
              </li>
            ))}
          </ul>
        )}
      </MessageContent>
    </Message>
  );
}
