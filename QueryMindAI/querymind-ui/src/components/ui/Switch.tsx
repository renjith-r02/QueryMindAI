import { cn } from "@/lib/cn";

type SwitchProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
};

export function Switch({ checked, onChange, label }: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cn("relative h-7 w-12 shrink-0 rounded-full", checked ? "bg-primary" : "bg-line")}
    >
      <span className={cn("absolute top-0.5 size-6 rounded-full bg-surface", checked ? "left-5" : "left-0.5")} />
    </button>
  );
}

/** A labelled settings row with a switch on the right. */
export function SwitchField({ detail, ...props }: SwitchProps & { detail: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div>
        <p className="font-medium">{props.label}</p>
        <p className="text-sm text-muted">{detail}</p>
      </div>
      <Switch {...props} />
    </div>
  );
}
