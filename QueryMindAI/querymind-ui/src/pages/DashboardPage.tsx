import { EmptyState } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { DashboardTileCard } from "@/features/dashboard/components/DashboardTileCard";
import { useDashboardStore } from "@/features/dashboard/store";

export function DashboardPage() {
  const tiles = useDashboardStore((state) => state.tiles);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <PageHeader
        title="Dashboard"
        description="Charts you saved from query results. Each shows the data as it was when saved; ask again for fresh numbers."
      />
      {tiles.length === 0 ? (
        <EmptyState>No saved charts yet. Ask a question, then choose “Save to dashboard” on its graph view.</EmptyState>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {tiles.map((tile, index) => (
            <DashboardTileCard key={tile.id} tile={tile} first={index === 0} last={index === tiles.length - 1} />
          ))}
        </div>
      )}
    </div>
  );
}
