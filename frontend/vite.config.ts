import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    // "@/..." means "src/...", the import style shadcn components use.
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    // `npm run dev` serves the page on :5173 and forwards API calls to the FastAPI app.
    proxy: {
      "/v1": "http://localhost:8000",
      "/healthz": "http://localhost:8000",
    },
  },
});
