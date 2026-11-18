import { MessageSquare, Plus, Trash2 } from "lucide-react";
import {
  SidebarGroup,
  SidebarGroupAction,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { useConversationStore } from "@/lib/store/conversation-store";

/** The active patient's conversations, newest first. */
export function NavConversations({ patientId }: { patientId: string }) {
  const conversations = useConversationStore((state) => state.byPatient[patientId]) ?? [];
  const activeId = useConversationStore((state) => state.activeByPatient[patientId]);
  const { startNew, select, remove } = useConversationStore();

  return (
    <SidebarGroup>
      <SidebarGroupLabel>Conversations</SidebarGroupLabel>
      <SidebarGroupAction onClick={() => startNew(patientId)} title="New conversation">
        <Plus />
        <span className="sr-only">New conversation</span>
      </SidebarGroupAction>
      <SidebarGroupContent>
        <SidebarMenu>
          {conversations.length === 0 && (
            <p className="px-2 py-1.5 text-muted-foreground text-xs group-data-[collapsible=icon]:hidden">
              Nothing yet. Send a message to start.
            </p>
          )}
          {conversations.map((conversation) => (
            <SidebarMenuItem key={conversation.id}>
              <SidebarMenuButton
                isActive={conversation.id === activeId}
                onClick={() => select(patientId, conversation.id)}
                tooltip={conversation.title}
              >
                <MessageSquare />
                <span>{conversation.title}</span>
              </SidebarMenuButton>
              <SidebarMenuAction
                onClick={() => remove(patientId, conversation.id)}
                showOnHover
                title="Remove from this list"
              >
                <Trash2 />
                <span className="sr-only">Remove from this list</span>
              </SidebarMenuAction>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}
