import { Card } from "@/components/ui/Card";
import { Notice } from "@/components/ui/Notice";
import { useSettingsStore } from "@/features/settings/store";
import { FeedbackButtons } from "@/features/results/components/FeedbackButtons";
import { ResultGraph } from "@/features/results/components/ResultGraph";
import { ResultTable } from "@/features/results/components/ResultTable";
import { SqlPanel } from "@/features/results/components/SqlPanel";
import { transpile } from "@/features/results/lib/dialect";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { useAskStore } from "@/features/ask/store";
import type { CacheInfo, QueryIntent } from "@/types/query";
import type { Run } from "@/types/run";

export function QueryView({ run }: { run: Run }) {
  const settings = useSettingsStore((state) => state.settings);
  const healed = run.status === "healed";
  const showSecondary = settings.multiDialect && settings.secondaryDialect !== settings.primaryDialect;
  const caveats = run.caveats ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="text-xs font-medium tracking-wide text-muted uppercase">Question</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">{run.question}</h1>
        <p className="mt-2 text-sm text-muted">
          {run.notExecuted ? "Drafted" : healed ? "Self-healed" : "Executed"} in {run.ms} ms ·{" "}
          {run.notExecuted ? "not executed" : run.queries ? "live databases" : "sample e-commerce data"}
        </p>
        {run.intent ? <IntentBadge intent={run.intent} /> : null}
      </div>

      {run.cached ? <CachedNotice question={run.question} cached={run.cached} /> : null}

      {run.notExecuted ? (
        <Notice tone="danger" className="py-3" role="note">
          <p className="font-medium text-danger">This UPDATE was not run.</p>
          <p className="mt-1 text-ink">
            QueryMind only drafts changes. Review the statement and its WHERE clause, then run it yourself inside a
            transaction if it is correct.
          </p>
        </Notice>
      ) : null}

      {healed && run.brokenSql ? (
        <Notice tone="danger" className="py-3">
          <p className="font-medium text-danger">The first SQL attempt failed and was retried with the error.</p>
          <pre className="mt-2 overflow-x-auto font-mono text-xs text-ink">{run.brokenSql}</pre>
        </Notice>
      ) : null}

      {healed && run.healingNote ? (
        <Notice tone="ok" className="py-3">
          Self-healed successfully. {run.healingNote}
        </Notice>
      ) : null}

      {run.answer ? (
        <Card className="px-4 py-4">
          <h2 className="text-sm font-semibold">Answer</h2>
          <p className="mt-2 text-sm leading-6 whitespace-pre-wrap text-ink">{run.answer}</p>
          {caveats.length > 0 ? (
            <ul className="mt-3 list-disc pl-5 text-sm text-muted">
              {caveats.map((caveat) => (
                <li key={caveat}>{caveat}</li>
              ))}
            </ul>
          ) : null}
        </Card>
      ) : null}

      {settings.explanation && run.explanation ? (
        <Card className="px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold">Plain English breakdown</h2>
            <span className="rounded-full bg-ok-soft px-2 py-1 text-xs font-medium text-ok">Explanation on</span>
          </div>
          <p className="mt-2 text-sm leading-6 whitespace-pre-line text-ink">{run.explanation}</p>
        </Card>
      ) : null}

      {run.queries ? (
        <>
          {run.queries.map((query, index) => (
            <SqlPanel
              key={index}
              title={`${query.database} (${query.dialect}) SQL`}
              sql={query.sql.trim()}
              note={query.purpose}
            />
          ))}
          {run.mergeSql ? (
            <SqlPanel
              title="Merge (SQLite)"
              sql={run.mergeSql.trim()}
              note="Combines the results of the queries above."
            />
          ) : null}
        </>
      ) : null}
      {run.sql && !run.queries ? (
        <SqlPanel title={`${settings.primaryDialect} SQL`} sql={transpile(run.sql, settings.primaryDialect)} />
      ) : null}
      {run.sql && !run.queries && showSecondary ? (
        <SqlPanel
          title={`${settings.secondaryDialect} rewrite`}
          sql={transpile(run.sql, settings.secondaryDialect)}
          note="Transpiled for the secondary dialect."
        />
      ) : null}

      {run.rows.length > 0 ? <ResultTable columns={run.columns} rows={run.rows} /> : null}
      {run.rows.length > 0 ? (
        <ResultGraph
          key={run.id}
          columns={run.columns}
          rows={run.rows}
          source={{ runId: run.id, question: run.question, sql: run.sql }}
        />
      ) : null}

      <FeedbackButtons run={run} />
    </div>
  );
}

const INTENT_LABELS: Record<QueryIntent["query_type"], string> = {
  SELECT_SIMPLE: "Simple lookup",
  SELECT_AGGREGATE: "Aggregate",
  SELECT_JOIN: "Across tables",
  SELECT_TEMPORAL: "Time-based",
  UPDATE: "Change request (draft only)",
  UNSUPPORTED: "Not allowed",
};

/** How the intent classifier read the question. */
function IntentBadge({ intent }: { intent: QueryIntent }) {
  return (
    <p className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted" title={intent.reason}>
      <span className="rounded-full bg-primary-soft px-2 py-0.5 font-medium text-primary">
        {INTENT_LABELS[intent.query_type]}
      </span>
      <span className="font-mono">{intent.query_type}</span>
      {intent.tables_mentioned.length ? <span>· {intent.tables_mentioned.join(", ")}</span> : null}
    </p>
  );
}

const timeAgo = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

function age(cachedAt: number): string {
  const minutes = Math.round((cachedAt - Date.now()) / 60_000);
  return Math.abs(minutes) < 60 ? timeAgo.format(minutes, "minute") : timeAgo.format(Math.round(minutes / 60), "hour");
}

/** The answer was reused from the semantic cache; offer to ask the model again. */
function CachedNotice({ question, cached }: { question: string; cached: CacheInfo }) {
  const ask = useAskStore((state) => state.ask);
  const same = cached.question.trim().toLowerCase() === question.trim().toLowerCase();
  return (
    <Notice className="flex flex-wrap items-center justify-between gap-3 py-3" role="note">
      <span>
        <span className="font-medium">Answered from cache</span>
        <span className="text-muted">
          {" "}
          · {same ? "the same question" : `a matching question (“${cached.question}”)`} was answered{" "}
          {age(cached.cachedAt)}, {Math.round(cached.similarity * 100)}% similar. No model calls were made.
        </span>
      </span>
      <Button onClick={() => void ask(question, { fresh: true })}>
        <RefreshCw className="size-4" />
        Get a fresh answer
      </Button>
    </Notice>
  );
}
