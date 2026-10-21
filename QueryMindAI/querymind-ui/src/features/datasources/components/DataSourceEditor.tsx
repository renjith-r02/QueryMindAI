import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { SelectField } from "@/components/ui/SelectField";
import { SwitchField } from "@/components/ui/Switch";
import { buildSchemaHeader } from "@/features/datasources/schemaHeader";
import { useDataSourceStore } from "@/features/datasources/store";
import {
  DATA_SOURCE_TYPES,
  SECTION_KEYS,
  SECTIONS,
  sectionHeading,
  TYPE_INFO,
  type DataSource,
  type DataSourceType,
} from "@/features/datasources/types";
import { SqlPanel } from "@/features/results/components/SqlPanel";

const INPUT = "min-h-11 rounded-xl border border-line bg-surface px-3 text-sm";
const TYPE_LABELS = DATA_SOURCE_TYPES.map((type) => TYPE_INFO[type].label);

export function DataSourceEditor({ source, onRemoved }: { source: DataSource; onRemoved: () => void }) {
  const update = useDataSourceStore((state) => state.update);
  const changeType = useDataSourceStore((state) => state.changeType);
  const remove = useDataSourceStore((state) => state.remove);
  const info = TYPE_INFO[source.type];

  return (
    <div className="flex flex-col gap-4">
      <Card className="flex flex-col gap-4 p-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="flex flex-col gap-2 text-sm">
            <span className="font-medium">Name</span>
            <input
              value={source.name}
              onChange={(event) => update(source.id, { name: event.target.value })}
              className={INPUT}
            />
          </label>
          <SelectField
            label="Type"
            value={info.label}
            options={TYPE_LABELS}
            onChange={(label) =>
              changeType(source.id, DATA_SOURCE_TYPES.find((type) => TYPE_INFO[type].label === label) as DataSourceType)
            }
          />
        </div>
        <SwitchField
          label="Use this data source"
          detail="Disabled sources keep their settings but are not offered for questions."
          checked={source.enabled}
          onChange={(enabled) => update(source.id, { enabled })}
        />
      </Card>

      <Card className="overflow-hidden">
        <CardHeader title="Connection" />
        <div className="grid gap-4 p-4 sm:grid-cols-2">
          {info.connection.map((field) => (
            <label key={field.key} className="flex flex-col gap-2 text-sm">
              <span className="font-medium">{field.label}</span>
              <input
                value={source.connection[field.key] ?? ""}
                placeholder={field.placeholder}
                onChange={(event) =>
                  update(source.id, { connection: { ...source.connection, [field.key]: event.target.value } })
                }
                className={INPUT}
              />
            </label>
          ))}
        </div>
        <p className="border-t border-line px-4 py-3 text-xs text-muted">
          Passwords and keys are not stored here. Keep credentials in the server configuration.
        </p>
      </Card>

      <Card className="overflow-hidden">
        <CardHeader
          title="Documentation"
          aside={<span className="text-xs text-muted">Helps the model write correct queries</span>}
        />
        <div className="flex flex-col gap-5 p-4">
          {SECTION_KEYS.map((key) => (
            <label key={key} className="flex flex-col gap-1 text-sm">
              <span className="font-mono text-xs font-medium tracking-wide">{sectionHeading(key, source.type)}</span>
              <span className="text-xs text-muted">{SECTIONS[key].hint}</span>
              <textarea
                value={source.sections[key] ?? ""}
                onChange={(event) => update(source.id, { sections: { ...source.sections, [key]: event.target.value } })}
                rows={Math.min(14, Math.max(4, (source.sections[key] ?? "").split("\n").length + 1))}
                spellCheck={false}
                className="mt-1 rounded-xl border border-line bg-surface px-3 py-2 font-mono text-xs leading-5"
              />
            </label>
          ))}
        </div>
      </Card>

      <details className="group">
        <summary className="cursor-pointer text-sm font-medium text-primary">Preview as schema file header</summary>
        <div className="mt-3">
          <SqlPanel
            title="Schema header"
            note="Same format as the annotated files in querymind-agentic/sqls/."
            sql={buildSchemaHeader(source)}
          />
        </div>
      </details>

      <div>
        <Button
          className="border-danger/40 text-danger"
          onClick={() => {
            if (window.confirm(`Delete the data source "${source.name}"?`)) {
              remove(source.id);
              onRemoved();
            }
          }}
        >
          <Trash2 className="size-4" />
          Delete data source
        </Button>
      </div>
    </div>
  );
}
