import { apiFetch } from "@/api/client";
import { env } from "@/config/env";
import type { SchemaFile } from "@/types/schema";

const mocks = () => import("@/mocks/handlers");

/** Tables and views per database, read by the server from the annotated schema files. */
export async function getSchema(database?: string): Promise<SchemaFile[]> {
  if (env.useMocks) return (await mocks()).getSchema(database);
  const query = database ? `?database=${encodeURIComponent(database)}` : "";
  return apiFetch<SchemaFile[]>(`/admin/schema${query}`);
}

// querymind-api does not serve approved examples yet, so these always come from the mock
// backend, even when VITE_API_URL is set.

/** Approved example questions, also used as suggestions on Home. */
export async function getExamples(): Promise<string[]> {
  return (await mocks()).getExamples();
}
