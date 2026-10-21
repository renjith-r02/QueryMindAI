import { useState } from "react";
import { ArrowLeft, ArrowRight, Pencil, RefreshCw, Trash2 } from "lucide-react";
import { Card } from "@/components/ui/Card";
import { useAskNavigation } from "@/features/ask/hooks/useAskNavigation";
import { useDashboardStore, type DashboardTile } from "@/features/dashboard/store";
import { ChartCanvas, StatTiles } from "@/features/results/components/ChartCanvas";
import { describeView, labelLookup } from "@/features/results/lib/chartLabels";
import { formatWhen } from "@/lib/format";

const ICON_BUTTON =
  "inline-flex size-9 items-center justify-center rounded-lg text-muted hover:bg-paper hover:text-ink disabled:opacity-40";

export function DashboardTileCard({ tile, first, last }: { tile: DashboardTile; first: boolean; last: boolean }) {
  const rename = useDashboardStore((state) => state.rename);
  const remove = useDashboardStore((state) => state.remove);
  const move = useDashboardStore((state) => state.move);
  const { ask } = useAskNavigation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(tile.title);
  const labelOf = labelLookup(tile.columns);

  function commit() {
    rename(tile.id, draft.trim() || tile.question);
    setEditing(false);
  }

  return (
    <Card as="article" className="flex flex-col gap-3 px-4 py-4" aria-label={tile.title}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          {editing ? (
            <input
              autoFocus
              aria-label="Chart title"
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onBlur={commit}
              onKeyDown={(event) => {
                if (event.key === "Enter") commit();
                if (event.key === "Escape") {
                  setDraft(tile.title);
                  setEditing(false);
                }
              }}
              className="w-full rounded-lg border border-line px-2 py-1 text-sm font-semibold"
            />
          ) : (
            <h2 className="truncate text-sm font-semibold" title={tile.title}>
              {tile.title}
            </h2>
          )}
          <p className="text-xs text-muted">
            {describeView(tile.view, labelOf)} · saved {formatWhen(tile.savedAt)}
          </p>
        </div>
        <div className="flex shrink-0 items-center">
          <button type="button" className={ICON_BUTTON} aria-label="Rename" onClick={() => setEditing(true)}>
            <Pencil className="size-4" />
          </button>
          <button
            type="button"
            className={ICON_BUTTON}
            aria-label="Ask again for fresh data"
            title="Ask again for fresh data"
            onClick={() => ask(tile.question)}
          >
            <RefreshCw className="size-4" />
          </button>
          <button
            type="button"
            className={ICON_BUTTON}
            aria-label="Move earlier"
            disabled={first}
            onClick={() => move(tile.id, -1)}
          >
            <ArrowLeft className="size-4" />
          </button>
          <button
            type="button"
            className={ICON_BUTTON}
            aria-label="Move later"
            disabled={last}
            onClick={() => move(tile.id, 1)}
          >
            <ArrowRight className="size-4" />
          </button>
          <button
            type="button"
            className={ICON_BUTTON}
            aria-label="Remove from dashboard"
            onClick={() => {
              if (window.confirm(`Remove "${tile.title}" from the dashboard?`)) remove(tile.id);
            }}
          >
            <Trash2 className="size-4" />
          </button>
        </div>
      </div>

      {tile.view.kind === "stat" ? (
        <StatTiles view={tile.view} rows={tile.rows} labelOf={labelOf} />
      ) : (
        <div className="h-72">
          <ChartCanvas view={tile.view} rows={tile.rows} labelOf={labelOf} />
        </div>
      )}

      {tile.notes.map((note) => (
        <p key={note} className="text-xs text-muted">
          {note}
        </p>
      ))}
      {tile.title !== tile.question ? <p className="text-xs text-muted">Question: {tile.question}</p> : null}
    </Card>
  );
}
