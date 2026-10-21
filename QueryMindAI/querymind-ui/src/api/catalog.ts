import type { SchemaTable } from "@/types/schema";

// querymind-api does not serve schema or examples yet, so these always
// come from the mock backend, even when VITE_API_URL is set.

export async function getSchema(): Promise<SchemaTable[]> {
  return (await import("@/mocks/handlers")).getSchema();
}

/** Approved example questions, also used as suggestions on Home. */
export async function getExamples(): Promise<string[]> {
  return (await import("@/mocks/handlers")).getExamples();
}
