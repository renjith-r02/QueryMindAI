import { useEffect, useState } from "react";
import { useLoaderData } from "react-router-dom";
import { Plus, RotateCcw, Save, Trash2, Upload } from "lucide-react";
import { createDataSource, deleteDataSource, listDataSources, updateDataSource } from "@/api/datasources";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { EmptyState, Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { DataSourceEditor } from "@/features/datasources/components/DataSourceEditor";
import { clearLegacySources, readLegacySources } from "@/features/datasources/legacy";
import {
  DATA_SOURCE_TYPES,
  defaultConnection,
  toInput,
  TYPE_INFO,
  type DataSource,
  type DataSourceInput,
  type DataSourceType,
} from "@/features/datasources/types";
import { cn } from "@/lib/cn";

export async function loader() {
  return { sources: await listDataSources() };
}

type Status = { tone: "ok" | "danger"; text: string } | null;

const same = (a: DataSourceInput, b: DataSourceInput) => JSON.stringify(toInput(a)) === JSON.stringify(toInput(b));
const message = (error: unknown) => (error instanceof Error ? error.message : "Something went wrong.");

export function SettingsPage() {
  const { sources: initial } = useLoaderData<typeof loader>();
  const [sources, setSources] = useState<DataSource[]>(initial);
  const [selectedId, setSelectedId] = useState<string | undefined>(initial[0]?.id);
  const [draft, setDraft] = useState<DataSourceInput | null>(initial[0] ? toInput(initial[0]) : null);
  const [newType, setNewType] = useState<DataSourceType>("mysql");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status>(null);
  const [legacy, setLegacy] = useState(readLegacySources);

  const selected = sources.find((source) => source.id === selectedId);
  const fromEnv = selected?.origin === "env";
  const dirty = Boolean(selected && draft && !same(selected, draft));

  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  function select(source: DataSource | undefined) {
    if (dirty && !window.confirm(`Discard unsaved changes to "${selected?.name}"?`)) return false;
    setSelectedId(source?.id);
    setDraft(source ? toInput(source) : null);
    setStatus(null);
    return true;
  }

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setStatus(null);
    try {
      await action();
    } catch (error) {
      setStatus({ tone: "danger", text: message(error) });
    } finally {
      setBusy(false);
    }
  }

  const add = () =>
    run(async () => {
      if (dirty && !window.confirm(`Discard unsaved changes to "${selected?.name}"?`)) return;
      const label = TYPE_INFO[newType].label;
      const taken = new Set(sources.map((s) => s.name.toLowerCase()));
      let n = sources.filter((s) => s.type === newType).length + 1;
      while (taken.has(`${label} source ${n}`.toLowerCase())) n += 1;
      const created = await createDataSource({
        name: `${label} source ${n}`,
        type: newType,
        enabled: true,
        connection: defaultConnection(newType),
        sections: {},
      });
      setSources((current) => [...current, created]);
      setSelectedId(created.id);
      setDraft(toInput(created));
      setStatus({ tone: "ok", text: `Added "${created.name}".` });
    });

  const save = () =>
    run(async () => {
      if (!selected || !draft) return;
      // A database known only from .env becomes a saved data source (with a new id).
      const saved = fromEnv ? await createDataSource(draft) : await updateDataSource(selected.id, draft);
      setSources((current) => current.map((s) => (s.id === selected.id ? saved : s)));
      setSelectedId(saved.id);
      setDraft(toInput(saved));
      setStatus({ tone: "ok", text: fromEnv ? "Saved to settings." : "Saved." });
    });

  const remove = () =>
    run(async () => {
      if (!selected || !window.confirm(`Delete the data source "${selected.name}"?`)) return;
      await deleteDataSource(selected.id);
      const remaining = sources.filter((s) => s.id !== selected.id);
      setSources(remaining);
      setSelectedId(remaining[0]?.id);
      setDraft(remaining[0] ? toInput(remaining[0]) : null);
      setStatus({ tone: "ok", text: `Deleted "${selected.name}".` });
    });

  const importLegacy = () =>
    run(async () => {
      const taken = new Set(sources.map((s) => s.name.toLowerCase()));
      const created: DataSource[] = [];
      const skipped: string[] = [];
      for (const source of legacy) {
        if (taken.has(source.name.toLowerCase())) {
          skipped.push(source.name);
          continue;
        }
        created.push(await createDataSource(source));
        taken.add(source.name.toLowerCase());
      }
      clearLegacySources();
      setLegacy([]);
      setSources((current) => [...current, ...created]);
      const parts = [`Imported ${created.length} data source${created.length === 1 ? "" : "s"}.`];
      if (skipped.length) parts.push(`Skipped existing: ${skipped.join(", ")}.`);
      setStatus({ tone: "ok", text: parts.join(" ") });
    });

  const discardLegacy = () => {
    if (!window.confirm("Discard the data sources saved in this browser? They will not be imported.")) return;
    clearLegacySources();
    setLegacy([]);
  };

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageHeader
        title="Settings"
        description="Data sources QueryMind can query, with the documentation the model uses to write queries. Saved on the server."
      />

      {legacy.length > 0 ? (
        <Notice className="flex flex-wrap items-center justify-between gap-3 py-3">
          <span>
            {legacy.length} data source{legacy.length === 1 ? " was" : "s were"} saved in this browser before settings
            moved to the server ({legacy.map((s) => s.name).join(", ")}).
          </span>
          <span className="flex gap-2">
            <Button onClick={importLegacy} disabled={busy}>
              <Upload className="size-4" />
              Import
            </Button>
            <Button onClick={discardLegacy} disabled={busy}>
              Discard
            </Button>
          </span>
        </Notice>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[18rem_1fr]">
        <Card className="h-fit overflow-hidden">
          <CardHeader title="Data sources" aside={<span className="text-xs text-muted">{sources.length}</span>} />
          <ul className="divide-y divide-line">
            {sources.map((source) => (
              <li key={source.id}>
                <button
                  type="button"
                  aria-current={source.id === selectedId}
                  onClick={() => source.id !== selectedId && select(source)}
                  className={cn(
                    "flex w-full items-center justify-between gap-2 px-4 py-3 text-left text-sm hover:bg-paper",
                    source.id === selectedId && "bg-primary-soft",
                  )}
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{source.name}</span>
                    <span className="text-xs text-muted">
                      {TYPE_INFO[source.type].label}
                      {source.enabled ? "" : " · disabled"}
                    </span>
                  </span>
                  {source.origin === "env" ? (
                    <span className="rounded-full bg-paper px-2 py-0.5 text-xs font-medium text-muted">from .env</span>
                  ) : null}
                  {source.id === selectedId && dirty ? (
                    <span className="rounded-full bg-warn-soft px-2 py-0.5 text-xs font-medium text-warn">Unsaved</span>
                  ) : null}
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
            <Button onClick={add} disabled={busy}>
              <Plus className="size-4" />
              Add data source
            </Button>
          </div>
        </Card>

        {selected && draft ? (
          <div className="flex flex-col gap-4">
            {fromEnv ? (
              <Notice className="py-3">
                This database is configured in the server&apos;s .env file and isn&apos;t saved in settings yet. Queries
                use the .env connection. Save to keep these settings and documentation in QueryMind; the password stays
                in .env.
              </Notice>
            ) : null}
            <DataSourceEditor key={selected.id} value={draft} onChange={setDraft} />
            {status ? (
              <Notice tone={status.tone} className="py-3" role="status">
                {status.text}
              </Notice>
            ) : null}
            <div className="sticky bottom-0 flex flex-wrap items-center gap-2 border-t border-line bg-paper py-3">
              <Button variant="primary" onClick={save} disabled={busy || (!dirty && !fromEnv)}>
                <Save className="size-4" />
                {busy ? "Saving…" : fromEnv ? "Save to settings" : "Save changes"}
              </Button>
              <Button onClick={() => setDraft(toInput(selected))} disabled={busy || !dirty}>
                <RotateCcw className="size-4" />
                Revert
              </Button>
              <span className="flex-1" />
              <Button
                className="border-danger/40 text-danger"
                onClick={remove}
                disabled={busy || fromEnv}
                title={fromEnv ? "Configured in the server's .env; remove it there" : undefined}
              >
                <Trash2 className="size-4" />
                Delete data source
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {status ? (
              <Notice tone={status.tone} className="py-3" role="status">
                {status.text}
              </Notice>
            ) : null}
            <EmptyState>No data sources yet. Add one to describe where your data lives.</EmptyState>
          </div>
        )}
      </div>
    </div>
  );
}
