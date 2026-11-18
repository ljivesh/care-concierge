// Remembers the chosen patient and each patient's thread id across reloads.
// localStorage can be unavailable (private windows), so every access is guarded
// and the page still works without it.

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // nothing to do: the value simply will not survive a reload
  }
}

export function savedPatientId(fallback: string): string {
  return read("care-patient") ?? fallback;
}

export function savePatientId(patientId: string): void {
  write("care-patient", patientId);
}

/** The thread for a patient. `fresh` starts a new conversation. */
export function threadIdFor(patientId: string, fresh = false): string {
  const key = `care-thread-${patientId}`;
  const existing = fresh ? null : read(key);
  if (existing) return existing;
  const created = crypto.randomUUID();
  write(key, created);
  return created;
}
