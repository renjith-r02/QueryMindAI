import { useState, type FormEvent } from "react";
import { ArrowRight, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { useAskNavigation } from "@/features/ask/hooks/useAskNavigation";

export function Composer({
  placeholder = "Ask about products, orders, revenue, or inventory",
  variant = "default",
}: {
  placeholder?: string;
  /** "hero" is the large question box on Home. */
  variant?: "default" | "hero";
}) {
  const { ask } = useAskNavigation();
  const [value, setValue] = useState("");

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!value.trim()) return;
    ask(value);
    setValue("");
  }

  if (variant === "hero") {
    return (
      <form
        onSubmit={onSubmit}
        className="flex flex-col gap-3 rounded-2xl border border-line bg-surface p-3 shadow-sm focus-within:border-primary sm:flex-row sm:items-center"
      >
        <span className="hidden size-11 shrink-0 place-items-center rounded-xl bg-primary-soft text-primary sm:grid">
          <Sparkles className="size-5" aria-hidden="true" />
        </span>
        <div className="flex min-w-0 flex-1 flex-col">
          <label className="sr-only" htmlFor="question">
            Question
          </label>
          <input
            id="question"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            placeholder="Ask anything about your data…"
            aria-describedby="question-example"
            className="min-h-10 bg-transparent text-base outline-none"
          />
          <span id="question-example" className="truncate text-sm text-muted">
            e.g. “Top 10 products by revenue last quarter”
          </span>
        </div>
        <Button type="submit" variant="primary" className="min-h-12">
          <ArrowRight className="size-4" />
          Generate SQL
        </Button>
      </form>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={onSubmit} className="flex flex-col gap-2 sm:flex-row">
        <label className="sr-only" htmlFor="question">
          Question
        </label>
        <input
          id="question"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder={placeholder}
          className="min-h-12 flex-1 rounded-xl border border-line bg-surface px-4 text-base outline-none focus:border-primary"
        />
        <Button type="submit" variant="primary" className="min-h-12">
          Ask
          <ArrowRight className="size-4" />
        </Button>
      </form>
    </div>
  );
}
