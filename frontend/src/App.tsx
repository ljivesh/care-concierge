import { useEffect, useRef, useState } from "react";
import { Composer } from "./components/Composer";
import { Header } from "./components/Header";
import { MessageRow } from "./components/MessageRow";
import { PATIENTS } from "./patients";
import { savePatientId, savedPatientId, threadIdFor } from "./storage";
import { useChat } from "./useChat";

export function App() {
  const [patientId, setPatientId] = useState(() => savedPatientId(PATIENTS[0].id));
  const [threadId, setThreadId] = useState(() => threadIdFor(patientId));
  const { rows, busy, send } = useChat(patientId, threadId);

  // Keep the newest message in view.
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => {
    bottom.current?.scrollIntoView({ block: "end" });
  }, [rows]);

  function changePatient(id: string) {
    savePatientId(id);
    setPatientId(id);
    setThreadId(threadIdFor(id));
  }

  return (
    <div className="app">
      <Header
        patientId={patientId}
        disabled={busy}
        onPatientChange={changePatient}
        onNewChat={() => setThreadId(threadIdFor(patientId, true))}
      />
      <main className="messages">
        {rows.length === 0 && (
          <p className="empty">
            Book a consultation or lab test, see your bookings, note a symptom, or ask about the clinic. English,
            हिंदी or Hinglish.
          </p>
        )}
        {rows.map((row, index) => (
          <MessageRow key={index} row={row} />
        ))}
        <div ref={bottom} />
      </main>
      <Composer busy={busy} onSend={send} />
    </div>
  );
}
