import { useLoaderData } from "react-router-dom";
import { getSchema } from "@/api/catalog";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";

export async function loader() {
  return { tables: await getSchema() };
}

export function SchemaPage() {
  const { tables } = useLoaderData<typeof loader>();

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4">
      <PageHeader title="Schema" description="Tables the sample linker is allowed to use." />
      {tables.map((table) => (
        <Card key={table.name} className="overflow-hidden">
          <div className="border-b border-line px-4 py-3">
            <h2 className="font-semibold">{table.name}</h2>
            <p className="text-sm text-muted">{table.blurb}</p>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[28rem] text-sm">
              <tbody>
                {table.columns.map((column) => (
                  <tr key={column.name} className="border-t border-line">
                    <td className="px-4 py-3 font-mono text-primary">{column.name}</td>
                    <td className="px-4 py-3 text-muted">{column.description}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ))}
    </div>
  );
}
