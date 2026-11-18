import { useState, type FormEvent, type KeyboardEvent } from "react";

interface Props {
  busy: boolean;
  onSend: (message: string) => void;
}

/** The message box. Enter sends; Shift+Enter adds a line. */
export function Composer({ busy, onSend }: Props) {
  const [draft, setDraft] = useState("");
  const message = draft.trim();

  function submit(event: FormEvent | KeyboardEvent) {
    event.preventDefault();
    if (!message || busy) return;
    setDraft("");
    onSend(message);
  }

  return (
    <form onSubmit={submit}>
      <textarea
        rows={1}
        placeholder="Type a message"
        aria-label="Message"
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) submit(event);
        }}
      />
      <button className="send" disabled={busy || !message}>
        {busy ? "…" : "Send"}
      </button>
    </form>
  );
}
