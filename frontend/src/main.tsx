import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "@/App";
import { TooltipProvider } from "@/components/ui/tooltip";
import "./index.css";

// shadcn's dark theme is switched by a `dark` class. Follow the system setting.
const prefersDark = window.matchMedia("(prefers-color-scheme: dark)");
const applyTheme = () => document.documentElement.classList.toggle("dark", prefersDark.matches);
applyTheme();
prefersDark.addEventListener("change", applyTheme);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <TooltipProvider>
      <App />
    </TooltipProvider>
  </StrictMode>,
);
