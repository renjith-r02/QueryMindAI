import { Card } from "@/components/ui/Card";

export function StatCard({ label, value }: { label: string; value: string | number }) {
  return (
    <Card as="div" className="px-4 py-4">
      <p className="text-sm text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold">{value}</p>
    </Card>
  );
}
