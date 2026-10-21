import { useMemo, useState } from "react";
import { useLoaderData } from "react-router-dom";
import { RotateCcw, Save, Undo2 } from "lucide-react";
import {
  getGuardrails,
  resetGuardrails,
  saveGuardrails,
  toPolicy,
  type GuardrailPolicy,
  type GuardrailSettings,
} from "@/api/guardrails";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { PageHeader } from "@/components/ui/PageHeader";
import { GuardrailTester } from "@/features/guardrails/components/GuardrailTester";
import { QuestionRules } from "@/features/guardrails/components/QuestionRules";
import { TokenList } from "@/features/guardrails/components/TokenList";

export async function loader() {
  return { guardrails: await getGuardrails() };
}

/** The policy as the server expects it: trimmed patterns, no blank lines. */
function cleaned(policy: GuardrailPolicy): GuardrailPolicy {
  return {
    ...policy,
    question_rules: policy.question_rules.map((rule) => ({
      ...rule,
      label: rule.label.trim(),
      message: rule.message.trim(),
      patterns: rule.patterns.map((pattern) => pattern.trim()).filter(Boolean),
    })),
  };
}

const keyword = (text: string) => {
  const value = text.trim().toUpperCase().split(/\s+/).join(" ");
  return /^[A-Z_]+( [A-Z_]+)*$/.test(value) ? value : null;
};
const column = (text: string) => {
  const value = text.trim().toLowerCase();
  return /^[a-z_][a-z0-9_]*(\.[a-z_][a-z0-9_]*)?$/.test(value) ? value : null;
};



export function GuardrailsPage() {
  const { guardrails: initial } = useLoaderData<typeof loader>();
  const [saved, setSaved] = useState(initial);
  const [draft, setDraft] = useState<GuardrailPolicy>(() => toPolicy(initial));
  const [busy, setBusy] = useState<"save" | "reset" | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [status, setStatus] = useState<{ tone: "ok" | "danger"; text: string } | null>(null);
  const set = (patch: Partial<GuardrailPolicy>) => {
    setDraft((current) => ({ ...current, ...patch }));
    setStatus(null);
  };
  const policy = useMemo(() => cleaned(draft), [draft]);
  const dirty = JSON.stringify(policy) !== JSON.stringify(toPolicy(saved));
  const rowsValid = Number.isInteger(draft.max_rows) && draft.max_rows >= 1 && draft.max_rows <= 100000;

  async function run(kind: "save" | "reset", action: () => Promise<GuardrailSettings>, done: string) {
    setBusy(kind);
    setStatus(null);
    try {
      const result = await action();
      setSaved(result);
      setDraft(toPolicy(result));
      setStatus({ tone: "ok", text: done });
    } catch (error) {
      setStatus({ tone: "danger", text: error instanceof Error ? error.message : "Could not save." });
    } finally {
      setBusy(null);
      setConfirmReset(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <PageHeader
        title="Guardrails"
        description={
          <>
            Every question and every generated query is checked against this policy.
          </>
        }
      />

      <Card className="overflow-hidden">
        <CardHeader
          title="Question rules"
          aside={<span className="text-xs text-muted">Checked before any SQL is written</span>}
        />
        <QuestionRules
          rules={draft.question_rules}
          politeToken={saved.polite_token}
          onChange={(question_rules) => set({ question_rules })}
        />
      </Card>

      <Card className="overflow-hidden">
        <CardHeader
          title="Blocked SQL keywords"
          aside={<span className="text-xs text-muted">Generated SQL containing these never runs</span>}
        />
        <div className="p-4">
          <TokenList
            label="Blocked SQL keywords"
            values={draft.blocked_sql_keywords}
            locked={saved.required_sql_keywords}
            placeholder="e.g. SLEEP or INTO DUMPFILE"
            normalise={keyword}
            invalidHint="Letters and _ only, words separated by single spaces."
            onChange={(blocked_sql_keywords) => set({ blocked_sql_keywords })}
          />
        </div>
      </Card>

      <Card className="overflow-hidden">
        <CardHeader
          title="Restricted columns"
          aside={<span className="text-xs text-muted">Never queried; removed from results</span>}
        />
        <div className="p-4">
          <TokenList
            label="Restricted columns"
            values={draft.restricted_columns}
            placeholder="column or table.column"
            normalise={column}
            invalidHint="Use column or table.column (letters, digits and _)."
            onChange={(restricted_columns) => set({ restricted_columns })}
          />
        </div>
      </Card>

      <Card className="overflow-hidden">
        <CardHeader title="Limits" />
        <label className="flex flex-col gap-1.5 p-4 text-sm">
          <span className="font-medium">Max rows per query</span>
          <input
            type="number"
            min={1}
            max={100000}
            value={draft.max_rows || ""}
            aria-invalid={!rowsValid}
            onChange={(event) => set({ max_rows: event.target.value === "" ? 0 : Number(event.target.value) })}
            className="min-h-11 w-40 rounded-xl border border-line bg-surface px-3"
          />
          <span className={rowsValid ? "text-xs text-muted" : "text-xs text-danger"}>
            {rowsValid ? "Requests can ask for fewer rows, never more." : "Enter a whole number from 1 to 100,000."}
          </span>
        </label>
      </Card>

      <Card className="overflow-hidden">
        <CardHeader
          title="Try it"
          aside={<span className="text-xs text-muted">Uses the policy above, including unsaved changes</span>}
        />
        <GuardrailTester policy={policy} />
      </Card>

      {status ? (
        <Notice tone={status.tone} className="py-3" role="status">
          {status.text}
        </Notice>
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        <Button
          variant="primary"
          disabled={busy !== null || !dirty || !rowsValid}
          onClick={() => run("save", () => saveGuardrails(policy), "Guardrails saved. New questions use them now.")}
        >
          <Save className="size-4" />
          {busy === "save" ? "Saving…" : "Save"}
        </Button>
        <Button
          disabled={busy !== null || !dirty}
          onClick={() => {
            setDraft(toPolicy(saved));
            setStatus(null);
          }}
        >
          <Undo2 className="size-4" />
          Discard changes
        </Button>
        {confirmReset ? (
          <span className="flex items-center gap-2 text-sm">
            Replace the saved policy with the built-in defaults?
            <Button
              disabled={busy !== null}
              onClick={() => run("reset", resetGuardrails, "Built-in guardrails restored.")}
            >
              {busy === "reset" ? "Restoring…" : "Restore"}
            </Button>
            <Button onClick={() => setConfirmReset(false)}>Cancel</Button>
          </span>
        ) : (
          <Button disabled={busy !== null} onClick={() => setConfirmReset(true)}>
            <RotateCcw className="size-4" />
            Restore defaults
          </Button>
        )}
      </div>
    </div>
  );
}
