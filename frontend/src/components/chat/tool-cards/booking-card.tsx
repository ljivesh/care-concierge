import { CalendarCheck, CalendarSync, CalendarX, Clock, FlaskConical, Stethoscope } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { formatSlot, subtypeLabel } from "@/lib/helpers/format";
import type { Booking } from "@/lib/types/tools";

/** One booking as a row: who, what, when, and its status. */
export function BookingRow({ booking }: { booking: Booking }) {
  const { date, time } = formatSlot(booking.scheduled_for);
  const Icon = booking.service === "LAB" ? FlaskConical : Stethoscope;
  return (
    <div className="flex items-center gap-3">
      <div className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
        <Icon className="size-4" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-sm">{booking.clinician_name}</p>
        <p className="truncate text-muted-foreground text-xs">{subtypeLabel(booking.subtype)}</p>
      </div>
      <div className="text-right text-xs">
        <p className="font-medium">{date}</p>
        <p className="flex items-center justify-end gap-1 text-muted-foreground">
          <Clock className="size-3" />
          {time}
        </p>
      </div>
      <Badge variant={booking.status === "BOOKED" ? "default" : "secondary"}>
        {booking.status.toLowerCase().replace("_", "-")}
      </Badge>
    </div>
  );
}

/** What happened to the booking, as the card's title. */
function headline(booking: Booking) {
  if (booking.cancelled || booking.already_cancelled) {
    return {
      icon: CalendarX,
      text: booking.late_cancellation ? "Cancelled late: counts as a no-show" : "Appointment cancelled",
      tone: "text-muted-foreground",
    };
  }
  if (booking.rescheduled) {
    const was = booking.previous_scheduled_for ? formatSlot(booking.previous_scheduled_for) : null;
    return {
      icon: CalendarSync,
      text: was ? `Appointment moved from ${was.date}, ${was.time}` : "Appointment moved",
      tone: "text-primary",
    };
  }
  if (booking.already_booked || booking.unchanged) {
    return { icon: CalendarCheck, text: "You already have this appointment", tone: "text-primary" };
  }
  return { icon: CalendarCheck, text: "Appointment booked", tone: "text-primary" };
}

export function BookingCard({ booking }: { booking: Booking }) {
  const { icon: Icon, text, tone } = headline(booking);
  return (
    <div className="space-y-3 rounded-xl border bg-card p-4">
      <p className={`flex items-center gap-2 font-medium text-sm ${tone}`}>
        <Icon className="size-4" />
        {text}
      </p>
      <BookingRow booking={booking} />
    </div>
  );
}

export function BookingsListCard({ bookings }: { bookings: Booking[] }) {
  if (bookings.length === 0) {
    return <p className="rounded-xl border border-dashed p-4 text-muted-foreground text-sm">No bookings yet.</p>;
  }
  return (
    <div className="divide-y rounded-xl border bg-card px-4">
      {bookings.map((booking) => (
        <div className="py-3" key={booking.id}>
          <BookingRow booking={booking} />
        </div>
      ))}
    </div>
  );
}
