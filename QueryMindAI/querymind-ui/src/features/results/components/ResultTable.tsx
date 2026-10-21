import { Card, CardHeader } from "@/components/ui/Card";
import { formatCell } from "@/lib/format";
import type { Column, Row } from "@/types/query";

export function ResultTable({ columns, rows }: { columns: Column[]; rows: Row[] }) {
  return (
    <Card className="overflow-hidden">
      <CardHeader title="Results" aside={<span className="text-xs text-muted">{rows.length} rows</span>} />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[32rem] text-left text-sm">
          <thead className="bg-paper text-xs tracking-wide text-muted uppercase">
            <tr>
              {columns.map((column) => (
                <th key={column.key} className="px-4 py-3 font-medium">
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="border-t border-line">
                {columns.map((column) => (
                  <td key={column.key} className="px-4 py-3">
                    {formatCell(column.key, row[column.key] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
