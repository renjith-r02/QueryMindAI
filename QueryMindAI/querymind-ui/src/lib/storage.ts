import type { Run } from "@/types/run";
import type { Settings } from "@/types/settings";

/** Key used before history and settings were split into separate persisted stores. */
const LEGACY_KEY = "querymind-sample-v1";

type LegacyState = { history?: Run[]; settings?: Partial<Settings> };

/** Read data saved by the previous version so upgrading users keep their history. */
export function readLegacyState(): LegacyState {
  try {
    const raw = localStorage.getItem(LEGACY_KEY);
    return raw ? (JSON.parse(raw) as LegacyState) : {};
  } catch {
    return {};
  }
}
