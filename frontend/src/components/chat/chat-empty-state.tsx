import { STARTER_PROMPTS } from "@/config/constants";
import type { Patient } from "@/lib/types/concierge";

interface Props {
  patient: Patient;
  onPick: (message: string) => void;
}

/** A greeting and four starter prompts, written in the patient's own language. */
export function ChatEmptyState({ patient, onPick }: Props) {
  const firstName = patient.name.split(" ")[0];
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-8 py-10">
      <div className="space-y-2 text-center">
        <h2 className="font-semibold text-2xl tracking-tight">Namaste, {firstName}</h2>
        <p className="mx-auto max-w-md text-muted-foreground text-sm">
          Your care concierge at {patient.society}. Write in English, हिंदी or Hinglish.
        </p>
      </div>
      <div className="grid w-full max-w-xl gap-3 sm:grid-cols-2">
        {STARTER_PROMPTS.map(({ icon: Icon, title, prompt }) => (
          <button
            className="group flex flex-col gap-2 rounded-xl border bg-card p-4 text-left transition-colors hover:border-primary/40 hover:bg-accent/50 focus-visible:outline-2 focus-visible:outline-ring"
            key={title}
            onClick={() => onPick(prompt[patient.language])}
            type="button"
          >
            <span className="flex items-center gap-2 font-medium text-sm">
              <Icon className="size-4 text-primary" />
              {title}
            </span>
            <span className="line-clamp-2 text-muted-foreground text-xs">{prompt[patient.language]}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
