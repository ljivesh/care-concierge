import { useEffect } from "react";
import { Chat } from "@/components/chat/chat";
import { AppHeader } from "@/components/navigation/app-header";
import { AppSidebar } from "@/components/sidebar/app-sidebar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { useApplyTheme } from "@/hooks/use-theme";
import { useConversationStore } from "@/lib/store/conversation-store";
import { useActivePatient } from "@/lib/store/patient-store";

export function App() {
  useApplyTheme();
  const patient = useActivePatient();
  const threadId = useConversationStore((state) => state.activeByPatient[patient.id]);
  const startNew = useConversationStore((state) => state.startNew);

  // A patient with no open conversation gets a fresh, empty one.
  useEffect(() => {
    if (!threadId) startNew(patient.id);
  }, [threadId, patient.id, startNew]);

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset className="h-dvh overflow-hidden">
        <AppHeader />
        {/* key: a different thread is a different conversation, with its own state */}
        {threadId && <Chat key={threadId} patient={patient} threadId={threadId} />}
      </SidebarInset>
    </SidebarProvider>
  );
}
