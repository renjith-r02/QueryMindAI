import { create } from "zustand";
import { persist } from "zustand/middleware";
import { readLegacyState } from "@/lib/storage";
import type { GuardSettings, Settings } from "@/types/settings";

export const DEFAULT_SETTINGS: Settings = {
  explanation: true,
  primaryDialect: "PostgreSQL",
  secondaryDialect: "MySQL",
  multiDialect: true,
  maxRows: 1000,
  selectOnly: true,
  blockDestructive: true,
  domainRules: true,
  rateLimit: true,
};

type SettingsStore = {
  settings: Settings;
  setSettings: (patch: Partial<Settings>) => void;
};

export const useSettingsStore = create<SettingsStore>()(
  persist(
    (set) => ({
      settings: { ...DEFAULT_SETTINGS, ...readLegacyState().settings },
      setSettings: (patch) => set((state) => ({ settings: { ...state.settings, ...patch } })),
    }),
    {
      name: "querymind-settings",
      version: 1,
      // Fill in settings added after the user last saved.
      merge: (persisted, current) => ({
        ...current,
        settings: { ...DEFAULT_SETTINGS, ...(persisted as Partial<SettingsStore> | undefined)?.settings },
      }),
    },
  ),
);

export function selectGuardSettings({ settings }: SettingsStore): GuardSettings {
  return {
    selectOnly: settings.selectOnly,
    blockDestructive: settings.blockDestructive,
    domainRules: settings.domainRules,
    maxRows: settings.maxRows,
  };
}
