const apiUrl = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");
const useMocksFlag = import.meta.env.VITE_USE_MOCKS;

export const env = {
  apiUrl,
  /** Mocks are on when explicitly requested, or when no API URL is configured. */
  useMocks: useMocksFlag ? useMocksFlag === "true" : apiUrl === "",
} as const;
