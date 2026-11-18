// Small display helpers.

/** "Ananya Sharma" -> "AS" */
export function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((word) => word[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

/**
 * "2027-01-12T10:30:00+05:30" -> { date: "Tue, 12 Jan 2027", time: "10:30" }.
 * The wall-clock digits are taken from the string as written, so the page shows
 * the society's local time whatever timezone the browser is in.
 */
export function formatSlot(iso: string): { date: string; time: string } {
  const [day, clock = ""] = iso.split("T");
  const [year, month, dayOfMonth] = day.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, dayOfMonth)).toLocaleDateString("en-IN", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  });
  return { date, time: clock.slice(0, 5) };
}

/** "CARDIOLOGY" -> "Cardiology", "FASTING_BLOOD_SUGAR" -> "Fasting blood sugar" */
export function subtypeLabel(code: string): string {
  if (code.length <= 4) return code; // CBC, LFT, KFT, ENT
  const words = code.toLowerCase().replaceAll("_", " ");
  return words[0].toUpperCase() + words.slice(1);
}

/** A conversation title from its first message. */
export function titleFrom(message: string, max = 42): string {
  const oneLine = message.replace(/\s+/g, " ").trim();
  return oneLine.length > max ? `${oneLine.slice(0, max - 1)}…` : oneLine;
}
