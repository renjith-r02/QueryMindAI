import { apiFetch } from "@/api/client";
import { env } from "@/config/env";
import { toInput, type DataSource, type DataSourceInput } from "@/features/datasources/types";

/** Data source settings, stored by querymind-api in Qdrant. */

const mocks = () => import("@/mocks/datasources");

export async function listDataSources(): Promise<DataSource[]> {
  if (env.useMocks) return (await mocks()).listDataSources();
  return apiFetch<DataSource[]>("/datasources");
}

export async function createDataSource(input: DataSourceInput): Promise<DataSource> {
  if (env.useMocks) return (await mocks()).createDataSource(toInput(input));
  return apiFetch<DataSource>("/datasources", { method: "POST", body: JSON.stringify(toInput(input)) });
}

export async function updateDataSource(id: string, input: DataSourceInput): Promise<DataSource> {
  if (env.useMocks) return (await mocks()).updateDataSource(id, toInput(input));
  return apiFetch<DataSource>(`/datasources/${encodeURIComponent(id)}`, {
    method: "PUT",
    body: JSON.stringify(toInput(input)),
  });
}

export async function deleteDataSource(id: string): Promise<void> {
  if (env.useMocks) return (await mocks()).deleteDataSource(id);
  await apiFetch<null>(`/datasources/${encodeURIComponent(id)}`, { method: "DELETE" });
}
