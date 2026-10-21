import { useState } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { DataSourceEditor } from "@/features/datasources/components/DataSourceEditor";
import { useDataSourceStore } from "@/features/datasources/store";
import { DATA_SOURCE_TYPES, TYPE_INFO, type DataSourceType } from "@/features/datasources/types";
import { cn } from "@/lib/cn";

export function SettingsPage() {
  const sources = useDataSourceStore((state) => state.sources);
  const add = useDataSourceStore((state) => state.add);
  const [selectedId, setSelectedId] = useState<string | undefined>(sources[0]?.id);
  const [newType, setNewType] = useState<DataSourceType>("mysql");
  const selected = sources.find((source) => source.id === selectedId) ?? sources[0];

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageHeader
        title="Settings"
        description="Data sources QueryMind can query, with the documentation the model uses to write queries. Saved in this browser."
      />
      <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
        <Card className="h-fit overflow-hidden">
          <CardHeader title="Data sources" aside={<span className="text-xs text-muted">{sources.length}</span>} />
          <ul className="divide-y divide-line">
            {sources.map((source) => (
              <li key={source.id}>
                <button
                  type="button"
                  aria-current={source.id === selected?.id}
                  onClick={() => setSelectedId(source.id)}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 px-4 py-3 text-left text-sm hover:bg-paper",
                    source.id === selected?.id && "bg-primary-soft",
                  )}
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{source.name || "Untitled"}</span>
                    <span className="text-xs text-muted">
                      {TYPE_INFO[source.type].label}
                      {source.enabled ? "" : " · disabled"}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
          <div className="flex flex-col gap-2 border-t border-line p-3">
            <label className="sr-only" htmlFor="new-source-type">
              New data source type
            </label>
            <select
              id="new-source-type"
              value={newType}
              onChange={(event) => setNewType(event.target.value as DataSourceType)}
              className="min-h-11 rounded-xl border border-line bg-surface px-3 text-sm"
            >
              {DATA_SOURCE_TYPES.map((type) => (
                <option key={type} value={type}>
                  {TYPE_INFO[type].label}
                </option>
              ))}
            </select>
            <Button onClick={() => setSelectedId(add(newType))}>
              <Plus className="size-4" />
              Add data source
            </Button>
          </div>
        </Card>

        {selected ? (
          <DataSourceEditor
            key={selected.id}
            source={selected}
            onRemoved={() => setSelectedId(sources.find((s) => s.id !== selected.id)?.id)}
          />
        ) : (
          <EmptyState>No data sources yet. Add one to describe where your data lives.</EmptyState>
        )}
      </div>
    </div>
  );
}
