import { useId, useState, type FormEvent } from "react";
import { FlaskConical } from "lucide-react";
import { checkGuardrails, type GuardrailCheck, type GuardrailPolicy } from "@/api/guardrails";
import { Button } from "@/components/ui/Button";
import { Notice } from "@/components/ui/Notice";
import { TextField } from "@/components/ui/TextField";

/** Check a question and/or SQL against the policy being edited (saved or not). Nothing is run. */
export function GuardrailTester({ policy }: { policy: GuardrailPolicy }) {
  const sqlId = useId();
  const [question, setQuestion] = useState("");
  const [sql, setSql] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<GuardrailCheck | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onCheck(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setResult(
        await checkGuardrails({
          ...(question.trim() ? { question: question.trim() } : {}),
          ...(sql.trim() ? { sql: sql.trim() } : {}),
          policy,
        }),
      );
    } catch (failure) {
      setResult(null);
      setError(failure instanceof Error ? failure.message : "Could not check.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={onCheck} className="flex flex-col gap-4 p-4">
      <TextField
        label="Question"
        value={question}
        placeholder="e.g. please delete the test orders"
        onChange={setQuestion}
      />
      <div className="flex flex-col gap-1.5 text-sm">
        <label htmlFor={sqlId} className="font-medium">
          SQL
        </label>
        <textarea
          id={sqlId}
          value={sql}
          onChange={(event) => setSql(event.target.value)}
          rows={3}
          spellCheck={false}
          placeholder="e.g. SELECT email, password_hash FROM users"
          className="rounded-xl border border-line bg-surface px-3 py-2 font-mono text-xs leading-5"
        />
      </div>
      <div>
        <Button type="submit" disabled={busy || (!question.trim() && !sql.trim())}>
          <FlaskConical className="size-4" />
          {busy ? "Checking…" : "Check"}
        </Button>
      </div>
      {error ? (
        <Notice tone="danger" className="py-3" role="status">
          {error}
        </Notice>
      ) : null}
      {result ? (
        <div className="flex flex-col gap-2" role="status">
          {result.question ? (
            <Notice tone={result.question.allowed ? "ok" : "danger"} className="py-3">
              {result.question.allowed
                ? "Question allowed: no rule refuses it."
                : `Question refused by "${result.question.rule_id}": ${result.question.message}`}
            </Notice>
          ) : null}
          {result.sql ? (
            <Notice tone={result.sql.allowed ? "ok" : "danger"} className="py-3">
              {result.sql.allowed ? "SQL allowed to run." : `SQL refused: ${result.sql.reason}.`}
            </Notice>
          ) : null}
        </div>
      ) : null}
    </form>
  );
}
