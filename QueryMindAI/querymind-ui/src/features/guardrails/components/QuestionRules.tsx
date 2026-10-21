import { useId, useState } from "react";
import { ChevronDown, ChevronRight, Lock, Plus, Trash2 } from "lucide-react";
import type { QuestionRule } from "@/api/guardrails";
import { Button } from "@/components/ui/Button";
import { Switch } from "@/components/ui/Switch";
import { TextField } from "@/components/ui/TextField";

type QuestionRulesProps = {
  rules: QuestionRule[];
  politeToken: string;
  onChange: (rules: QuestionRule[]) => void;
};

const slug = (text: string) =>
  text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 48) || "rule";

function uniqueId(label: string, rules: QuestionRule[]) {
  const base = slug(label);
  let id = base;
  for (let n = 2; rules.some((rule) => rule.id === id); n++) id = `${base}-${n}`;
  return id;
}

/** The question rules: each refuses matching questions before any SQL is written. */
export function QuestionRules({ rules, politeToken, onChange }: QuestionRulesProps) {
  const [open, setOpen] = useState<string | null>(null);
  const update = (id: string, patch: Partial<QuestionRule>) =>
    onChange(rules.map((rule) => (rule.id === id ? { ...rule, ...patch } : rule)));

  function addRule() {
    const id = uniqueId("custom rule", rules);
    onChange([
      ...rules,
      {
        id,
        label: "Custom rule",
        message: "This question is not allowed.",
        patterns: [""],
        enabled: true,
        locked: false,
      },
    ]);
    setOpen(id);
  }

  return (
    <div className="flex flex-col">
      <ul className="divide-y divide-line">
        {rules.map((rule) => (
          <li key={rule.id} className="flex flex-col gap-3 px-4 py-3">
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={() => setOpen(open === rule.id ? null : rule.id)}
                aria-expanded={open === rule.id}
                aria-label={`Edit ${rule.label}`}
                className="inline-flex size-8 shrink-0 items-center justify-center rounded-lg hover:bg-paper"
              >
                {open === rule.id ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
              </button>
              <div className="min-w-0 flex-1">
                <p className="flex items-center gap-2 font-medium">
                  {rule.label}
                  {rule.locked ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-paper px-2 py-0.5 text-xs font-normal text-muted">
                      <Lock className="size-3" />
                      Always on
                    </span>
                  ) : null}
                </p>
                <p className="truncate text-sm text-muted">{rule.message}</p>
              </div>
              {rule.locked ? null : (
                <Switch
                  label={rule.label}
                  checked={rule.enabled}
                  onChange={(enabled) => update(rule.id, { enabled })}
                />
              )}
            </div>
            {open === rule.id ? (
              <RuleEditor
                rule={rule}
                politeToken={politeToken}
                onChange={(patch) => update(rule.id, patch)}
                onRemove={() => onChange(rules.filter((item) => item.id !== rule.id))}
              />
            ) : null}
          </li>
        ))}
      </ul>
      <div className="border-t border-line px-4 py-3">
        <Button onClick={addRule}>
          <Plus className="size-4" />
          Add rule
        </Button>
      </div>
    </div>
  );
}

function RuleEditor({
  rule,
  politeToken,
  onChange,
  onRemove,
}: {
  rule: QuestionRule;
  politeToken: string;
  onChange: (patch: Partial<QuestionRule>) => void;
  onRemove: () => void;
}) {
  const id = useId();
  return (
    <div className="ml-11 flex flex-col gap-3" role="group" aria-label={`${rule.label} settings`}>
      <div className="grid gap-3 sm:grid-cols-2">
        <TextField label="Name" value={rule.label} onChange={(label) => onChange({ label })} />
        <TextField
          label="Message shown to the user"
          value={rule.message}
          onChange={(message) => onChange({ message })}
        />
      </div>
      <div className="flex flex-col gap-1.5 text-sm">
        <label htmlFor={id} className="font-medium">
          Patterns
        </label>
        <textarea
          id={id}
          value={rule.patterns.join("\n")}
          onChange={(event) => onChange({ patterns: event.target.value.split("\n") })}
          rows={Math.min(8, Math.max(2, rule.patterns.length + 1))}
          spellCheck={false}
          aria-describedby={`${id}-hint`}
          className="rounded-xl border border-line bg-surface px-3 py-2 font-mono text-xs leading-5"
        />
        <span id={`${id}-hint`} className="text-xs text-muted">
          One case-insensitive regular expression per line; a question matching any of them is refused.{" "}
          <code className="font-mono">{politeToken}</code> matches an optional lead-in such as "please" or "can you".
          {rule.locked ? " The built-in patterns of this rule can't be removed; you can add more." : ""}
        </span>
      </div>
      <p className="text-xs text-muted">
        ID <code className="font-mono">{rule.id}</code>
      </p>
      {rule.locked ? null : (
        <div>
          <Button onClick={onRemove}>
            <Trash2 className="size-4" />
            Remove rule
          </Button>
        </div>
      )}
    </div>
  );
}
