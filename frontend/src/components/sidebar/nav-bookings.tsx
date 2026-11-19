import { CalendarSync, CalendarX, FlaskConical, MoreHorizontal, Stethoscope } from "lucide-react";
import { useEffect } from "react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import { BOOKING_ACTION_PROMPT } from "@/config/constants";
import { formatSlot, subtypeLabel } from "@/lib/helpers/format";
import { useBookingsStore } from "@/lib/store/bookings-store";
import { useComposerStore } from "@/lib/store/composer-store";
import type { Patient } from "@/lib/types/concierge";
import type { Booking } from "@/lib/types/tools";

const NO_BOOKINGS: Booking[] = [];

/** "Cardiology appointment with Dr. Arvind Khanna on Tue, 12 Jan 2027 at 10:30" */
function describe(booking: Booking): string {
  const { date, time } = formatSlot(booking.scheduled_for);
  const what = (booking.subtypes ?? [booking.subtype]).map(subtypeLabel).join(", ");
  const kind = booking.service === "LAB" ? "lab collection" : "appointment";
  return `${what} ${kind} with ${booking.clinician_name} on ${date} at ${time}`;
}

/** The patient's upcoming bookings, each with Reschedule and Cancel. */
export function NavBookings({ patient }: { patient: Patient }) {
  const bookings = useBookingsStore((state) => state.byPatient[patient.id]) ?? NO_BOOKINGS;
  const refresh = useBookingsStore((state) => state.refresh);
  const ask = useComposerStore((state) => state.ask);

  useEffect(() => {
    void refresh(patient.id);
  }, [patient.id, refresh]);

  const upcoming = bookings
    .filter((booking) => booking.status === "BOOKED" && new Date(booking.scheduled_for) > new Date())
    .sort((a, b) => a.scheduled_for.localeCompare(b.scheduled_for));

  return (
    <SidebarGroup className="group-data-[collapsible=icon]:hidden">
      <SidebarGroupLabel>My bookings</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {upcoming.length === 0 && <p className="px-2 py-1.5 text-muted-foreground text-xs">No upcoming bookings.</p>}
          {upcoming.map((booking) => {
            const { date, time } = formatSlot(booking.scheduled_for);
            const Icon = booking.service === "LAB" ? FlaskConical : Stethoscope;
            const tests = (booking.subtypes ?? [booking.subtype]).map(subtypeLabel).join(", ");
            return (
              <SidebarMenuItem key={booking.id}>
                <SidebarMenuButton asChild className="h-auto py-1.5">
                  <div>
                    <Icon />
                    <div className="grid min-w-0 flex-1 leading-tight">
                      <span className="truncate text-sm">{tests}</span>
                      <span className="truncate text-muted-foreground text-xs">
                        {date} · {time} · {booking.clinician_name}
                      </span>
                    </div>
                  </div>
                </SidebarMenuButton>
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <SidebarMenuAction title="Change this booking">
                      <MoreHorizontal />
                      <span className="sr-only">Change this booking</span>
                    </SidebarMenuAction>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="start" side="right">
                    <DropdownMenuItem
                      onSelect={() => ask(BOOKING_ACTION_PROMPT.reschedule[patient.language](describe(booking)))}
                    >
                      <CalendarSync />
                      Reschedule
                    </DropdownMenuItem>
                    <DropdownMenuItem
                      onSelect={() => ask(BOOKING_ACTION_PROMPT.cancel[patient.language](describe(booking)))}
                      variant="destructive"
                    >
                      <CalendarX />
                      Cancel
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </SidebarMenuItem>
            );
          })}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}
