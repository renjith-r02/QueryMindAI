import { useId, useState, type FormEvent } from "react";
import { Lock, Plus, X } from "lucide-react";
import { Button } from "@/components/ui/Button";

type TokenListProps = {
  label: string;
  values: string[];
  /** Values that can't be removed (shown with a lock). */
  locked?: string[];
  placeholder: string;
  /** Normalise a typed value; return null to reject it. */
  normalise: (value: string) => string | null;
  invalidHint: string;
  onChange: (values: string[]) => void;
};

/** An editable list of short values (SQL keywords, column names) shown as removable chips. */
export function TokenList({
  label,
  values,
  locked = [],
  placeholder,
  normalise,
  invalidHint,
  onChange,
}: TokenListProps) {
  const id = useId();
  const [text, setText] = useState("");
  const [invalid, setInvalid] = useState(false);

  function add(event: FormEvent) {
    event.preventDefault();
    const value = normalise(text);
    if (!value) {
      setInvalid(true);
      return;
    }
    if (!values.includes(value)) onChange([...values, value]);
    setText("");
    setInvalid(false);
  }

  return (
    <div className="flex flex-col gap-3">
      <ul className="flex flex-wrap gap-2" aria-label={label}>
        {values.map((value) => (
          <li
            key={value}
            className="inline-flex items-center gap-1.5 rounded-full border border-line bg-paper py-1 pr-1 pl-3 font-mono text-xs"
          >
            {value}
            {locked.includes(value) ? (
              <span className="inline-flex size-6 items-center justify-center text-muted" title="Always blocked">
                <Lock className="size-3.5" aria-label="always on" />
              </span>
            ) : (
              <button
                type="button"
                onClick={() => onChange(values.filter((item) => item !== value))}
                aria-label={`Remove ${value}`}
                className="inline-flex size-6 items-center justify-center rounded-full hover:bg-line"
              >
                <X className="size-3.5" />
              </button>
            )}
          </li>
        ))}
      </ul>
      <form onSubmit={add} className="flex flex-wrap items-start gap-2">
        <div className="flex flex-col gap-1">
          <label htmlFor={id} className="sr-only">
            {`Add to ${label.toLowerCase()}`}
          </label>
          <input
            id={id}
            value={text}
            placeholder={placeholder}
            aria-invalid={invalid}
            aria-describedby={invalid ? `${id}-hint` : undefined}
            onChange={(event) => {
              setText(event.target.value);
              setInvalid(false);
            }}
            className="min-h-11 w-64 rounded-xl border border-line bg-surface px-3 font-mono text-sm"
          />
          {invalid ? (
            <span id={`${id}-hint`} className="text-xs text-danger">
              {invalidHint}
            </span>
          ) : null}
        </div>
        <Button type="submit" disabled={!text.trim()}>
          <Plus className="size-4" />
          Add
        </Button>
      </form>
    </div>
  );
}
