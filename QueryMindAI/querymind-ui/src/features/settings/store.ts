import { create } from "zustand";
import { persist } from "zustand/middleware";
import { readLegacyState } from "@/lib/storage";
import type { Settings } from "@/types/settings";

export const DEFAULT_SETTINGS: Settings = {
  explanation: true,
  primaryDialect: "PostgreSQL",
  secondaryDialect: "MySQL",
  multiDialect: true,
};

type SettingsStore = {
  settings: Settings;
  setSettings: (patch: Partial<Settings>) => void;
};

export const useSettingsStore = create<SettingsStore>()(
  persist(
    (set) => ({
      settings: known(readLegacyState().settings),
      setSettings: (patch) => set((state) => ({ settings: { ...state.settings, ...patch } })),
    }),
    {
      name: "querymind-settings",
      version: 1,
      // Fill in settings added after the user last saved, and drop ones that moved to the server
      // (the guardrail switches and row limit are now in the guardrail policy).
      merge: (persisted, current) => ({
        ...current,
        settings: known((persisted as Partial<SettingsStore> | undefined)?.settings),
      }),
    },
  ),
);

function known(saved: Partial<Settings> | undefined): Settings {
  const settings = { ...DEFAULT_SETTINGS };
  for (const key of Object.keys(DEFAULT_SETTINGS) as (keyof Settings)[]) {
    if (saved?.[key] !== undefined) Object.assign(settings, { [key]: saved[key] });
  }
  return settings;
}
