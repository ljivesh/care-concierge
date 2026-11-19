import { SquarePen } from "lucide-react";
import { NavBookings } from "@/components/sidebar/nav-bookings";
import { NavConversations } from "@/components/sidebar/nav-conversations";
import { PatientSwitcher } from "@/components/sidebar/patient-switcher";
import { ThemeToggle } from "@/components/sidebar/theme-toggle";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarRail,
} from "@/components/ui/sidebar";
import { APP_NAME, BrandIcon, ORG_NAME } from "@/config/constants";
import { useConversationStore } from "@/lib/store/conversation-store";
import { useActivePatient } from "@/lib/store/patient-store";

export function AppSidebar() {
  const patient = useActivePatient();
  const startNew = useConversationStore((state) => state.startNew);

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton asChild size="lg">
              <div>
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                  <BrandIcon className="size-4" />
                </div>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold">{APP_NAME}</span>
                  <span className="truncate text-muted-foreground text-xs">{ORG_NAME}</span>
                </div>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton onClick={() => startNew(patient.id)} tooltip="New conversation">
                <SquarePen />
                <span>New conversation</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarGroup>
        <NavBookings patient={patient} />
        <NavConversations patientId={patient.id} />
      </SidebarContent>

      <SidebarFooter>
        <ThemeToggle />
        <PatientSwitcher />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
