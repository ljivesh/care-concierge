import { useState } from "react";
import { AppHeader } from "@/components/app-header";
import { Chat } from "@/components/chat";
import { PATIENTS } from "@/lib/patients";
import { savePatientId, savedPatientId, threadIdFor } from "@/lib/storage";

export function App() {
  const [patientId, setPatientId] = useState(() => savedPatientId(PATIENTS[0].id));
  const [threadId, setThreadId] = useState(() => threadIdFor(patientId));

  function changePatient(id: string) {
    savePatientId(id);
    setPatientId(id);
    setThreadId(threadIdFor(id));
  }

  return (
    <div className="flex h-dvh flex-col">
      <AppHeader
        patientId={patientId}
        onPatientChange={changePatient}
        onNewChat={() => setThreadId(threadIdFor(patientId, true))}
      />
      {/* key: a different thread is a different conversation, with its own state */}
      <Chat key={threadId} patientId={patientId} threadId={threadId} />
    </div>
  );
}
