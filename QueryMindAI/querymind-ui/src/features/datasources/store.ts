import { create } from "zustand";
import { persist } from "zustand/middleware";
import { ECOMMERCE_MYSQL } from "@/features/datasources/defaults";
import { TYPE_INFO, type DataSource, type DataSourceType } from "@/features/datasources/types";

type DataSourceStore = {
  sources: DataSource[];
  /** Adds a source of the given type and returns its id. */
  add: (type: DataSourceType) => string;
  update: (id: string, patch: Partial<Omit<DataSource, "id">>) => void;
  /** Switches type, keeping connection values whose field exists in the new type. */
  changeType: (id: string, type: DataSourceType) => void;
  remove: (id: string) => void;
};

export function defaultConnection(type: DataSourceType, current: Record<string, string> = {}) {
  return Object.fromEntries(
    TYPE_INFO[type].connection.map((field) => [field.key, current[field.key] ?? field.defaultValue ?? ""]),
  );
}

export const useDataSourceStore = create<DataSourceStore>()(
  persist(
    (set, get) => ({
      sources: [ECOMMERCE_MYSQL],
      add: (type) => {
        const id = crypto.randomUUID();
        const count = get().sources.filter((source) => source.type === type).length + 1;
        const source: DataSource = {
          id,
          name: `${TYPE_INFO[type].label} source ${count}`,
          type,
          enabled: true,
          connection: defaultConnection(type),
          sections: {},
        };
        set((state) => ({ sources: [...state.sources, source] }));
        return id;
      },
      update: (id, patch) =>
        set((state) => ({ sources: state.sources.map((s) => (s.id === id ? { ...s, ...patch } : s)) })),
      changeType: (id, type) =>
        set((state) => ({
          sources: state.sources.map((s) =>
            s.id === id ? { ...s, type, connection: defaultConnection(type, s.connection) } : s,
          ),
        })),
      remove: (id) => set((state) => ({ sources: state.sources.filter((s) => s.id !== id) })),
    }),
    { name: "querymind-datasources", version: 1 },
  ),
);
