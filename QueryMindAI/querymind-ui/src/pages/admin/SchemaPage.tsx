import { useId, useMemo, useState } from "react";
import { useLoaderData } from "react-router-dom";
import { ArrowRight, KeyRound } from "lucide-react";
import { getSchema } from "@/api/catalog";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { DataSourceLogo } from "@/features/datasources/components/DataSourceLogo";
import type { DataSourceType } from "@/features/datasources/types";
import type { SchemaFile, SchemaRelation } from "@/types/schema";

export async function loader() {
  return { files: await getSchema() };
}

const DIALECTS: Record<string, string> = { mysql: "MySQL", postgresql: "PostgreSQL" };

/** Tables whose name, description or columns mention the filter; matching columns only, unless the table matches. */
function filtered(files: SchemaFile[], text: string): SchemaFile[] {
  const query = text.trim().toLowerCase();
  if (!query) return files;
  const has = (value: string | null) => (value ?? "").toLowerCase().includes(query);
  return files
    .map((file) => ({
      ...file,
      tables: file.tables
        .map((table) =>
          has(table.name) || has(table.description)
            ? table
            : { ...table, columns: table.columns.filter((c) => has(c.name) || has(c.description)) },
        )
        .filter((table) => table.columns.length > 0 || has(table.name)),
    }))
    .filter((file) => file.tables.length > 0);
}

export function SchemaPage() {
  const { files } = useLoaderData<typeof loader>();
  const filterId = useId();
  const [filter, setFilter] = useState("");
  const shown = useMemo(() => filtered(files, filter), [files, filter]);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <PageHeader
        title="Schema"
        description="Tables and views documented in the schema files on the server (querymind-agentic/sqls). The same files are indexed for answering questions."
      />
      <div className="flex flex-col gap-1.5 text-sm">
        <label htmlFor={filterId} className="font-medium">
          Filter
        </label>
        <input
          id={filterId}
          type="search"
          value={filter}
          placeholder="Table, column or description, e.g. refund"
          onChange={(event) => setFilter(event.target.value)}
          className="min-h-11 rounded-xl border border-line bg-surface px-3"
        />
      </div>

      {shown.length === 0 ? (
        <EmptyState>
          {files.length ? `Nothing matches "${filter}".` : "No schema files found on the server."}
        </EmptyState>
      ) : null}

      {shown.map((file) => (
        <section key={file.database} aria-labelledby={`db-${file.database}`} className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <DataSourceLogo type={file.dialect as DataSourceType} className="size-7" />
            <h2 id={`db-${file.database}`} className="text-lg font-semibold">
              {file.database}
            </h2>
            <span className="text-sm text-muted">
              {DIALECTS[file.dialect] ?? file.dialect} · {count(file, "table")} · {count(file, "view")} ·{" "}
              <code className="font-mono text-xs">{file.source}</code>
            </span>
          </div>
          {file.tables.map((table) => (
            <RelationCard key={table.name} table={table} open={filter.trim() !== ""} />
          ))}
        </section>
      ))}
    </div>
  );
}

function count(file: SchemaFile, kind: SchemaRelation["kind"]) {
  const n = file.tables.filter((table) => table.kind === kind).length;
  return `${n} ${kind}${n === 1 ? "" : "s"}`;
}

function RelationCard({ table, open }: { table: SchemaRelation; open: boolean }) {
  return (
    <Card as="article" className="overflow-hidden">
      <details open={open || undefined} className="group">
        <summary className="flex cursor-pointer list-none flex-col gap-1 px-4 py-3 hover:bg-paper">
          <span className="flex flex-wrap items-center gap-2">
            <span className="font-mono font-semibold">{table.name}</span>
            {table.kind === "view" ? (
              <span className="rounded-full bg-primary-soft px-2 py-0.5 text-xs text-primary">View</span>
            ) : null}
            <span className="text-xs text-muted">{table.columns.length} columns</span>
          </span>
          {table.description ? <span className="text-sm text-muted">{table.description}</span> : null}
        </summary>
        <div className="overflow-x-auto border-t border-line">
          <table className="w-full min-w-[40rem] text-sm">
            <thead className="bg-paper text-left text-xs text-muted">
              <tr>
                <th className="px-4 py-2 font-medium">Column</th>
                <th className="px-4 py-2 font-medium">Type</th>
                <th className="px-4 py-2 font-medium">Null</th>
                <th className="px-4 py-2 font-medium">References</th>
                <th className="px-4 py-2 font-medium">Description</th>
              </tr>
            </thead>
            <tbody>
              {table.columns.map((column) => (
                <tr key={column.name} className="border-t border-line align-top">
                  <td className="px-4 py-2 font-mono whitespace-nowrap text-primary">
                    <span className="inline-flex items-center gap-1.5">
                      {column.name}
                      {column.primary_key ? <KeyRound className="size-3.5 text-warn" aria-label="primary key" /> : null}
                    </span>
                  </td>
                  <td className="max-w-48 px-4 py-2 font-mono text-xs break-words">{column.data_type ?? "—"}</td>
                  <td className="px-4 py-2 text-muted">
                    {column.nullable === null ? "—" : column.nullable ? "yes" : "no"}
                  </td>
                  <td className="px-4 py-2 font-mono text-xs whitespace-nowrap">
                    {column.references ? (
                      <span className="inline-flex items-center gap-1">
                        <ArrowRight className="size-3" aria-hidden="true" />
                        {column.references}
                      </span>
                    ) : null}
                  </td>
                  <td className="px-4 py-2 text-muted">{column.description}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </Card>
  );
}
