import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { useConversationStore } from "@/lib/store/conversation-store";
import { useActivePatient } from "@/lib/store/patient-store";

/** Sidebar toggle and a breadcrumb trail: society, patient, conversation. */
export function AppHeader() {
  const patient = useActivePatient();
  const activeId = useConversationStore((state) => state.activeByPatient[patient.id]);
  const title = useConversationStore(
    (state) => state.byPatient[patient.id]?.find((conversation) => conversation.id === activeId)?.title,
  );

  return (
    <header className="flex h-14 shrink-0 items-center gap-2 border-b px-4">
      <SidebarTrigger className="-ml-1" />
      <Separator className="mr-2 data-[orientation=vertical]:h-4" orientation="vertical" />
      <Breadcrumb className="min-w-0">
        <BreadcrumbList className="flex-nowrap">
          <BreadcrumbItem className="hidden md:block">{patient.society}</BreadcrumbItem>
          <BreadcrumbSeparator className="hidden md:block" />
          <BreadcrumbItem className="hidden sm:block">{patient.name}</BreadcrumbItem>
          <BreadcrumbSeparator className="hidden sm:block" />
          <BreadcrumbItem className="min-w-0">
            <BreadcrumbPage className="truncate">{title ?? "New conversation"}</BreadcrumbPage>
          </BreadcrumbItem>
        </BreadcrumbList>
      </Breadcrumb>
    </header>
  );
}
