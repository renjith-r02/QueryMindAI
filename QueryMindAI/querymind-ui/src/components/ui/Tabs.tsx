import { useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export type TabItem<T extends string> = { id: T; label: string; count?: number };

/** Accessible tabs (WAI-ARIA tablist): arrow keys, Home and End move between tabs. */
export function Tabs<T extends string>({
  label,
  items,
  value,
  onChange,
  children,
}: {
  label: string;
  items: TabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  children: ReactNode;
}) {
  const baseId = useId();
  const refs = useRef(new Map<T, HTMLButtonElement>());

  function onKeyDown(event: KeyboardEvent) {
    const index = items.findIndex((item) => item.id === value);
    const last = items.length - 1;
    const next = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: last }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    const target = items[(next + items.length) % items.length]!;
    onChange(target.id);
    refs.current.get(target.id)?.focus();
  }

  return (
    <div>
      <div role="tablist" aria-label={label} className="flex gap-1 border-b border-line" onKeyDown={onKeyDown}>
        {items.map((item) => {
          const selected = item.id === value;
          return (
            <button
              key={item.id}
              ref={(node) => {
                if (node) refs.current.set(item.id, node);
                else refs.current.delete(item.id);
              }}
              type="button"
              role="tab"
              id={`${baseId}-tab-${item.id}`}
              aria-label={item.count !== undefined ? `${item.label} (${item.count})` : undefined}
              aria-selected={selected}
              aria-controls={`${baseId}-panel`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(item.id)}
              className={cn(
                "-mb-px flex min-h-11 items-center gap-2 border-b-2 border-transparent px-3 text-sm font-medium text-muted hover:text-ink",
                selected && "border-primary text-primary",
              )}
            >
              {item.label}
              {item.count !== undefined ? (
                <span className="rounded-full bg-paper px-2 py-0.5 text-xs text-muted">{item.count}</span>
              ) : null}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`${baseId}-panel`} aria-labelledby={`${baseId}-tab-${value}`} className="pt-3">
        {children}
      </div>
    </div>
  );
}
