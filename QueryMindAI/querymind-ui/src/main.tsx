import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource/figtree/400.css";
import "@fontsource/figtree/500.css";
import "@fontsource/figtree/600.css";
import "@fontsource/figtree/700.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@/styles/globals.css";
import { App } from "@/app/App";
import { env } from "@/config/env";
import { useHistoryStore } from "@/features/history/store";
import { DEFAULT_SETTINGS } from "@/features/settings/store";

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root");

async function start(container: HTMLElement) {
  if (env.useMocks) {
    // Example history for the demo; loaded on demand so it is not in the API build.
    const { seedHistory } = await import("@/mocks/seed");
    useHistoryStore.getState().seedIfEmpty(seedHistory(DEFAULT_SETTINGS));
  }

  createRoot(container).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

void start(root);
