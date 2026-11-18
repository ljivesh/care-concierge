import { Check, ChevronsUpDown } from "lucide-react";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { SidebarMenu, SidebarMenuButton, SidebarMenuItem, useSidebar } from "@/components/ui/sidebar";
import { LANGUAGE_LABEL, PATIENTS, SOCIETIES } from "@/config/constants";
import { initials } from "@/lib/helpers/format";
import { useActivePatient, usePatientStore } from "@/lib/store/patient-store";

/** Who the page is acting as. Stands in for a login: the seed data has no accounts. */
export function PatientSwitcher() {
  const { isMobile } = useSidebar();
  const active = useActivePatient();
  const setActivePatientId = usePatientStore((state) => state.setActivePatientId);

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
              size="lg"
            >
              <Avatar className="size-8 rounded-lg">
                <AvatarFallback className="rounded-lg bg-primary/10 font-medium text-primary text-xs">
                  {initials(active.name)}
                </AvatarFallback>
              </Avatar>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-medium">{active.name}</span>
                <span className="truncate text-muted-foreground text-xs">
                  {active.society} · {LANGUAGE_LABEL[active.language]}
                </span>
              </div>
              <ChevronsUpDown className="ml-auto size-4" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="end"
            className="max-h-[70vh] w-(--radix-dropdown-menu-trigger-width) min-w-64 overflow-y-auto rounded-lg"
            side={isMobile ? "bottom" : "right"}
            sideOffset={4}
          >
            {SOCIETIES.map((society, index) => (
              <DropdownMenuGroup key={society}>
                {index > 0 && <DropdownMenuSeparator />}
                <DropdownMenuLabel className="text-muted-foreground text-xs">{society}</DropdownMenuLabel>
                {PATIENTS.filter((patient) => patient.society === society).map((patient) => (
                  <DropdownMenuItem
                    className="gap-2"
                    key={patient.id}
                    onSelect={() => setActivePatientId(patient.id)}
                  >
                    <span className="flex-1 truncate">{patient.name}</span>
                    <span className="text-muted-foreground text-xs">{LANGUAGE_LABEL[patient.language]}</span>
                    <Check className={patient.id === active.id ? "size-4" : "size-4 opacity-0"} />
                  </DropdownMenuItem>
                ))}
              </DropdownMenuGroup>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  );
}
