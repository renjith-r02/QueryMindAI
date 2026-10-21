import { Card } from "@/components/ui/Card";
import type { ClarifyOption } from "@/types/query";

export function ClarifyOptions({
  question,
  options,
  onChoose,
}: {
  question: string;
  options: ClarifyOption[];
  onChoose: (optionId: string) => void;
}) {
  return (
    <Card className="p-4">
      <h2 className="text-lg font-semibold">Did you mean one of these?</h2>
      <p className="mt-1 text-sm text-muted">
        “{question}” matches more than one amount column. Pick one before SQL is generated.
      </p>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {options.map((option) => (
          <button
            key={option.id}
            type="button"
            onClick={() => onChoose(option.id)}
            className="rounded-2xl border border-line p-4 text-left hover:border-primary"
          >
            <span className="block font-semibold text-primary">{option.title}</span>
            <span className="mt-2 block text-sm leading-6 text-muted">{option.detail}</span>
          </button>
        ))}
      </div>
    </Card>
  );
}
