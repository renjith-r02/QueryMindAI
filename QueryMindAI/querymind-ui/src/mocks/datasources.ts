import { ApiError } from "@/api/client";
import { ECOMMERCE_MYSQL } from "@/features/datasources/defaults";
import type { DataSource, DataSourceInput } from "@/features/datasources/types";

/** Stand-in for querymind-api's /datasources; keeps data sources in this browser. */
const KEY = "querymind-mock-datasources";

function load(): DataSource[] {
  const saved = localStorage.getItem(KEY);
  if (saved) return JSON.parse(saved) as DataSource[];
  const now = Date.now() / 1000;
  const seeded = [{ ...ECOMMERCE_MYSQL, id: crypto.randomUUID(), created_at: now, updated_at: now }];
  save(seeded);
  return seeded;
}

function save(sources: DataSource[]) {
  localStorage.setItem(KEY, JSON.stringify(sources));
}

function checkName(sources: DataSource[], name: string, exceptId?: string) {
  const clash = sources.find((s) => s.name.toLowerCase() === name.trim().toLowerCase() && s.id !== exceptId);
  if (clash) throw new ApiError(409, `A data source named '${clash.name}' already exists.`);
}

function find(sources: DataSource[], id: string): number {
  const index = sources.findIndex((s) => s.id === id);
  if (index < 0) throw new ApiError(404, "Data source not found.");
  return index;
}

export async function listDataSources(): Promise<DataSource[]> {
  return load();
}

export async function createDataSource(input: DataSourceInput): Promise<DataSource> {
  const sources = load();
  checkName(sources, input.name);
  const now = Date.now() / 1000;
  const created = { ...input, name: input.name.trim(), id: crypto.randomUUID(), created_at: now, updated_at: now };
  save([...sources, created]);
  return created;
}

export async function updateDataSource(id: string, input: DataSourceInput): Promise<DataSource> {
  const sources = load();
  const index = find(sources, id);
  checkName(sources, input.name, id);
  const updated = { ...sources[index]!, ...input, name: input.name.trim(), updated_at: Date.now() / 1000 };
  sources[index] = updated;
  save(sources);
  return updated;
}

export async function deleteDataSource(id: string): Promise<void> {
  const sources = load();
  sources.splice(find(sources, id), 1);
  save(sources);
}
