import { useId, type ComponentPropsWithoutRef } from "react";
import { cn } from "@/lib/cn";

type TextFieldProps = Omit<ComponentPropsWithoutRef<"input">, "onChange"> & {
  label: string;
  hint?: string;
  onChange: (value: string) => void;
};

export function TextField({ label, hint, onChange, className, ...props }: TextFieldProps) {
  const id = useId();
  return (
    <div className="flex flex-col gap-1.5 text-sm">
      <label htmlFor={id} className="font-medium">
        {label}
      </label>
      <input
        id={id}
        aria-describedby={hint ? `${id}-hint` : undefined}
        onChange={(event) => onChange(event.target.value)}
        className={cn("min-h-11 rounded-xl border border-line bg-surface px-3", className)}
        {...props}
      />
      {hint ? (
        <span id={`${id}-hint`} className="text-xs text-muted">
          {hint}
        </span>
      ) : null}
    </div>
  );
}
