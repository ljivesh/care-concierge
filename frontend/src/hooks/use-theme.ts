import { useEffect } from "react";
import { useThemeStore } from "@/lib/store/theme-store";

/** Applies the chosen theme by toggling shadcn's `dark` class on <html>. */
export function useApplyTheme(): void {
  const theme = useThemeStore((state) => state.theme);

  useEffect(() => {
    const system = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () => {
      const dark = theme === "dark" || (theme === "system" && system.matches);
      document.documentElement.classList.toggle("dark", dark);
    };
    apply();
    system.addEventListener("change", apply);
    return () => system.removeEventListener("change", apply);
  }, [theme]);
}
