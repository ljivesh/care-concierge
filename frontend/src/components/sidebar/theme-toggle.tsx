import { Monitor, Moon, Sun } from "lucide-react";
import { Button } from "@/components/ui/button";
import { type Theme, useThemeStore } from "@/lib/store/theme-store";
import { cn } from "@/lib/utils";

const OPTIONS: { value: Theme; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light theme", icon: Sun },
  { value: "system", label: "Match system theme", icon: Monitor },
  { value: "dark", label: "Dark theme", icon: Moon },
];

export function ThemeToggle() {
  const { theme, setTheme } = useThemeStore();
  return (
    <div className="flex w-fit items-center gap-0.5 rounded-full border bg-background p-0.5 group-data-[collapsible=icon]:hidden">
      {OPTIONS.map(({ value, label, icon: Icon }) => (
        <Button
          key={value}
          aria-label={label}
          aria-pressed={theme === value}
          className={cn("size-6 rounded-full", theme === value && "bg-accent text-accent-foreground")}
          onClick={() => setTheme(value)}
          size="icon"
          variant="ghost"
        >
          <Icon className="size-3.5" />
        </Button>
      ))}
    </div>
  );
}
