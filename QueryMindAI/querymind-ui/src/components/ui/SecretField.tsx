import { useId, useState } from "react";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/Button";

/**
 * A write-only secret. `saved` is the server's hint ("…abcd") or null; `value` is the pending
 * change: undefined keeps the saved secret, "" removes it, any other string replaces it.
 */
export function SecretField({
  label,
  hint,
  saved,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  saved: string | null;
  value: string | undefined;
  onChange: (value: string | undefined) => void;
}) {
  const id = useId();
  const [editing, setEditing] = useState(false);
  const removing = value === "" && saved !== null;
  const showInput = editing || saved === null;

  return (
    <div className="flex flex-col gap-1.5 text-sm">
      <label htmlFor={id} className="font-medium">
        {label}
      </label>
      {showInput && !removing ? (
        <div className="flex gap-2">
          <input
            id={id}
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={value ?? ""}
            placeholder={saved ? "Enter a new value" : "Not set"}
            aria-describedby={hint ? `${id}-hint` : undefined}
            onChange={(event) => onChange(event.target.value === "" && saved === null ? undefined : event.target.value)}
            className="min-h-11 flex-1 rounded-xl border border-line bg-surface px-3 font-mono"
          />
          {saved ? (
            <Button
              onClick={() => {
                setEditing(false);
                onChange(undefined);
              }}
            >
              Cancel
            </Button>
          ) : null}
        </div>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <span id={id} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-paper px-3 text-muted">
            {removing ? (
              "Will be removed when you save"
            ) : (
              <>
                <Check className="size-4 text-ok" aria-hidden="true" />
                Saved <span className="font-mono">{saved}</span>
              </>
            )}
          </span>
          {removing ? (
            <Button onClick={() => onChange(undefined)}>Undo</Button>
          ) : (
            <>
              <Button onClick={() => setEditing(true)}>Replace</Button>
              <Button className="text-danger" onClick={() => onChange("")}>
                Remove
              </Button>
            </>
          )}
        </div>
      )}
      {hint ? (
        <span id={`${id}-hint`} className="text-xs text-muted">
          {hint}
        </span>
      ) : null}
    </div>
  );
}
