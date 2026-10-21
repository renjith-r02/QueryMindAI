"""Command line entry point.

    # index every .sql / .json file in sqls/ (default)
    uv run python -m querymind index
    # index specific files; JSON files are question -> SQL pairs (see qa_loader)
    uv run python -m querymind index sqls/ecommerce_mysql_schema.sql my_pairs.json
    # inspect what would be indexed without touching Qdrant
    uv run python -m querymind index --dry-run
    # query the collection
    uv run python -m querymind search "refunds paid per month" --type example_query
    # RAG: retrieve context and let the LLM generate the SQL answer
    uv run python -m querymind ask "net revenue by category last month"
    # full loop: generate SQL, run it on the databases, answer from the results
    uv run python -m querymind run "top 5 products by revenue this year" --show-sql

    # use OpenAI GPT-6 Luna instead of the default Gemini for this run
    uv run python -m querymind run "orders per month this year" --llm-provider openai

    # evaluate on the test set (evaluation/test_set.json); writes evaluation/reports/<timestamp>/
    uv run python -m querymind evaluate
    uv run python -m querymind evaluate --validate-only     # check ground-truth SQL, no model calls

Settings come from flags, the environment, or querymind-agentic/.env
(see .env.example): GEMINI_API_KEY, OPENAI_API_KEY, EMBEDDING_PROVIDER, EMBEDDING_MODEL,
EMBEDDING_DIM, LLM_PROVIDER, LLM_MODEL, LLM_REASONING_EFFORT, QDRANT_URL, QDRANT_API_KEY, QDRANT_COLLECTION,
QUERYMIND_DB_<DATABASE> connection URLs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from querymind.agent.rag import RagAnswer
from querymind.agent.sql_agent import AgentResult
from querymind.config import Settings
from querymind.evaluation.dataset import DEFAULT_FEW_SHOT, DEFAULT_REPORTS, DEFAULT_TEST_SET
from querymind.exceptions import CollectionMismatchError, MissingApiKeyError, NoSourceFilesError
from querymind.intent import Intent
from querymind.knowledge.embeddings import DEFAULT_MODELS, PROVIDERS
from querymind.llm.providers import DEFAULT_LLM_MODELS, LLM_PROVIDERS, REASONING_EFFORTS
from querymind.progress import ProgressEvent
from querymind.service import QueryMindService


def _service(args: argparse.Namespace) -> QueryMindService:
    settings = args.settings.with_overrides(
        qdrant_url=args.url,
        collection=args.collection,
        embedding_provider=args.provider,
        embedding_model=args.model,
        embedding_dimensions=args.dimensions,
        gemini_api_key=args.api_key,
        llm_provider=getattr(args, "llm_provider", None),
        llm_model=getattr(args, "llm_model", None),
        llm_reasoning_effort=getattr(args, "reasoning_effort", None),
        max_rows=getattr(args, "max_rows", None),
        query_timeout=getattr(args, "timeout", None),
    )
    return QueryMindService(settings)


def cmd_index(args: argparse.Namespace) -> int:
    service = _service(args)
    paths = [Path(p) for p in args.paths] or None
    report = service.index(
        paths, database=args.database, dialect=args.dialect, recreate=args.recreate, dry_run=args.dry_run
    )
    for source in report.sources:
        summary = ", ".join(f"{kind}={n}" for kind, n in source.counts.items())
        print(f"{source.name} [{source.database}]: {len(source.chunks)} chunks ({summary})")
        if args.dry_run and args.verbose:
            for chunk in source.chunks:
                print(f"    {chunk.doc_type:<14} {chunk.title}")
    if not args.dry_run:
        print(
            f"Indexed {report.indexed} chunks into '{report.collection}' at {report.qdrant_url} "
            f"using {report.embedding}"
        )
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    for hit in _service(args).search(args.query, limit=args.limit, doc_type=args.type, database=args.database):
        print(f"[{hit.score:.3f}] {hit.doc_type} | {hit.database} | {hit.title}")
        if args.show_content:
            print("    " + hit.content.replace("\n", "\n    "))
    return 0


def _progress_printer(args: argparse.Namespace):
    """Live progress on stderr when it is a terminal, so piped and --json output stay clean."""
    if args.json or not sys.stderr.isatty():
        return None

    def show(event: ProgressEvent) -> None:
        mark = {"running": "…", "done": "✓", "failed": "✗"}[event.status]
        print(f"  {mark} {event.message}", file=sys.stderr, flush=True)

    return show


def cmd_ask(args: argparse.Namespace) -> int:
    result = _service(args).ask(args.question, database=args.database, on_progress=_progress_printer(args))
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        _print_answer(result, show_context=args.show_context)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    result = _service(args).run(
        args.question,
        database=args.database,
        max_repairs=args.max_repairs,
        max_rows=args.max_rows,
        on_progress=_progress_printer(args),
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, default=str))
    else:
        _print_agent_result(result, show_sql=args.show_sql, preview_rows=args.preview_rows)
    return 0 if result.status in {"answered", "generated"} else 1


def cmd_evaluate(args: argparse.Namespace) -> int:
    import datetime as dt

    from querymind.evaluation import Evaluator, summary, validate, write_report  # imports sqlglot

    service = _service(args)
    checked, issues = validate(service, args.test_set, args.few_shot)
    print(f"Validated {checked} ground-truth and few-shot statements on the live databases: {len(issues)} problem(s)")
    for issue in issues:
        print(f"  {issue.source} {issue.id}: {issue.problem}")
    if args.validate_only:
        return 1 if issues else 0

    def progress(case) -> None:
        verdict = "PASS" if case.execution_match else "FAIL"
        exact = "exact" if case.exact_match else "semantic" if case.semantic_match else "different SQL"
        print(f"{case.id} {case.query_type:<17} {verdict} ({exact}, {case.latency_ms / 1000:.1f} s) {case.reason}")

    evaluator = Evaluator(service, max_repairs=args.max_repairs, on_case=progress)
    ids = set(args.ids) if args.ids else None
    run = evaluator.run(args.test_set, args.few_shot, ids=ids, probes=not args.no_probes)
    output = args.output or DEFAULT_REPORTS / dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    markdown, data = write_report(run, Path(output))
    overall = summary(run)["overall"]
    print(
        f"\nExecution accuracy {overall['execution_accuracy']:.1%} | exact match {overall['exact_match_rate']:.1%} | "
        f"semantic match {overall['semantic_match_rate']:.1%} over {overall['cases']} cases"
    )
    print(f"Report: {markdown}\nResults: {data}")
    return 0


def _print_intent(intent: Intent | None) -> None:
    if intent is None:
        return
    tables = f" | tables: {', '.join(intent.tables_mentioned)}" if intent.tables_mentioned else ""
    print(f"Intent: {intent.query_type} ({intent.source}){tables}")


def _print_agent_result(result: AgentResult, show_sql: bool, preview_rows: int) -> None:
    plan = result.plan
    _print_intent(result.intent)
    if result.status == "blocked":
        print(f"Refused: {result.intent.blocked_message if result.intent else plan.explanation}")
        return
    if result.status == "generated":  # a drafted UPDATE: always shown, never run
        print(result.final.answer.strip())
        for caveat in result.final.caveats:
            print(f"  - note: {caveat}")
        for query in plan.queries:
            print(f"\n-- {query.database} ({query.dialect}), NOT EXECUTED: {query.purpose}\n{query.sql.strip()}")
        for warning in result.warnings:
            print(f"WARNING: {warning}", file=sys.stderr)
        return
    if result.status == "not_answerable":
        print(f"Not answerable: {plan.explanation if plan else ''}")
        return
    if result.status == "failed":
        print(f"Failed after {len(result.attempts)} attempt(s):", file=sys.stderr)
        for error in result.attempts[-1].errors if result.attempts else []:
            print(f"  [{error.database}] {error.error}", file=sys.stderr)
        show_sql = True
    else:
        print(result.final.answer.strip())
        for caveat in result.final.caveats:
            print(f"  - note: {caveat}")

    if show_sql and plan:
        print(f"\n--- SQL (attempt {len(result.attempts)}, model {result.model}) ---")
        for query, outcome in zip(plan.queries, result.attempts[-1].results, strict=True):
            status = f"{len(outcome.rows)} rows, {outcome.elapsed_ms} ms" if outcome.ok else "ERROR"
            print(f"-- {query.database} ({query.dialect}) [{status}]: {query.purpose}\n{query.sql.strip()}\n")
        if plan.merge_sql:
            print(f"-- merge (SQLite)\n{plan.merge_sql.strip()}\n")

    table = result.result
    if table is not None and table.ok and preview_rows:
        print(f"\n--- Result ({len(table.rows)} rows{', truncated' if table.truncated else ''}) ---")
        _print_table(table.columns, table.rows[:preview_rows])
    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)


def _print_table(columns: list[str], rows: list[list]) -> None:
    cells = [[str(c) for c in columns]] + [["" if v is None else str(v) for v in row] for row in rows]
    widths = [min(max(len(row[i]) for row in cells), 40) for i in range(len(columns))]
    for index, row in enumerate(cells):
        print("  ".join(value[:40].ljust(width) for value, width in zip(row, widths, strict=True)))
        if index == 0:
            print("  ".join("-" * width for width in widths))


def _print_answer(result: RagAnswer, show_context: bool) -> None:
    answer = result.answer
    print(f"Question: {result.question}")
    print(f"Model:    {result.model} ({len(result.context)} context chunks)")
    _print_intent(result.intent)
    print()
    if result.status == "blocked":
        print(f"Refused: {answer.explanation}")
        return
    if result.intent is not None and result.intent.is_update:
        print("Drafted UPDATE (not executed; review before running it yourself):")
    if not answer.answerable:
        print("Not answerable from the indexed knowledge.")
    for number, query in enumerate(answer.queries, start=1):
        print(f"-- Query {number}: {query.database} ({query.dialect}) - {query.purpose}")
        print(query.sql.strip() + "\n")
    if answer.merge_steps:
        print(f"Merge: {answer.merge_steps}\n")
    print(f"Explanation: {answer.explanation}")
    for assumption in answer.assumptions:
        print(f"  - assumption: {assumption}")
    for warning in result.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)

    used = set(answer.sources)
    print("\nSources:")
    for item in result.context:
        if show_context or item.id in used:
            marker = "*" if item.id in used else " "
            print(f" {marker} [{item.id}] {item.score:.3f} {item.doc_type:<14} {item.database:<11} {item.title}")


def build_parser(settings: Settings) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="querymind", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", help=f"Qdrant URL (default: {settings.qdrant_url})")
    parser.add_argument("--collection", help=f"Qdrant collection (default: {settings.collection})")
    parser.add_argument(
        "--provider", choices=PROVIDERS, help=f"embedding provider (default: {settings.embedding_provider})"
    )
    parser.add_argument(
        "--model", help="embedding model; defaults: " + ", ".join(f"{p}={m}" for p, m in DEFAULT_MODELS.items())
    )
    parser.add_argument("--dimensions", type=int, help="Gemini output dimensionality: 768 (default), 1536 or 3072")
    parser.add_argument(
        "--api-key",
        default=None,
        help="Gemini API key; prefer GEMINI_API_KEY in .env so the key stays out of shell history",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    index = commands.add_parser("index", help="parse files and upsert them into Qdrant")
    index.add_argument("paths", nargs="*", help=f".sql or .json files (default: all in {settings.source_dir})")
    index.add_argument("--database", help="override the detected database name (SQL files)")
    index.add_argument("--dialect", choices=["mysql", "postgresql"], help="override the detected dialect")
    index.add_argument("--recreate", action="store_true", help="drop and recreate the collection first")
    index.add_argument("--dry-run", action="store_true", help="parse only; do not embed or write")
    index.add_argument("-v", "--verbose", action="store_true", help="list chunks in --dry-run")
    index.set_defaults(func=cmd_index)

    search = commands.add_parser("search", help="semantic search over the collection")
    search.add_argument("query")
    search.add_argument("-k", "--limit", type=int, default=5)
    search.add_argument("--type", help="filter by doc_type, e.g. table, example_query, business_rule")
    search.add_argument("--database", help="filter by database, e.g. ecommerce, returns_db")
    search.add_argument("--show-content", action="store_true")
    search.set_defaults(func=cmd_search)

    ask = commands.add_parser("ask", help="RAG: retrieve context and generate SQL with the LLM")
    ask.add_argument("question")
    ask.add_argument("--database", help="restrict retrieval to one database, e.g. ecommerce")
    _add_llm_arguments(ask, settings)
    ask.add_argument("--json", action="store_true", help="print the full result, including context, as JSON")
    ask.add_argument("--show-context", action="store_true", help="list every retrieved chunk, not only cited ones")
    ask.set_defaults(func=cmd_ask)

    run = commands.add_parser("run", help="RAG + execute the SQL on the databases + final answer from the LLM")
    run.add_argument("question")
    run.add_argument("--database", help="restrict retrieval to one database, e.g. ecommerce")
    _add_llm_arguments(run, settings)
    run.add_argument(
        "--max-rows", type=int, help="maximum rows fetched per query (default and upper bound: the guardrail row limit)"
    )
    run.add_argument("--timeout", type=int, help=f"statement timeout in seconds (default {settings.query_timeout})")
    run.add_argument("--max-repairs", type=int, default=2, help="times to regenerate SQL after an error")
    run.add_argument("--preview-rows", type=int, default=20, help="result rows to print (0 = none)")
    run.add_argument("--show-sql", action="store_true", help="print the executed SQL")
    run.add_argument("--json", action="store_true", help="print everything as JSON")
    run.set_defaults(func=cmd_run)

    evaluate = commands.add_parser(
        "evaluate",
        help="score text-to-SQL on the test set: execution accuracy, exact/semantic match, by query type",
    )
    evaluate.add_argument("--test-set", type=Path, default=DEFAULT_TEST_SET, help="test set JSON")
    evaluate.add_argument("--few-shot", type=Path, default=DEFAULT_FEW_SHOT, help="few-shot library JSON")
    evaluate.add_argument("--output", type=Path, help=f"report directory (default: {DEFAULT_REPORTS}/<timestamp>)")
    evaluate.add_argument("--ids", nargs="+", help="only these case/probe ids, e.g. T01 T05 G01")
    evaluate.add_argument("--max-repairs", type=int, default=2, help="self-repair attempts per question")
    evaluate.add_argument("--no-probes", action="store_true", help="skip the guardrail probes")
    evaluate.add_argument(
        "--validate-only",
        action="store_true",
        help="only run the ground-truth and few-shot SQL on the databases (no model calls)",
    )
    _add_llm_arguments(evaluate, settings)
    evaluate.set_defaults(func=cmd_evaluate)
    parser.set_defaults(settings=settings)
    return parser


def _add_llm_arguments(command: argparse.ArgumentParser, settings: Settings) -> None:
    command.add_argument(
        "--llm-provider", choices=LLM_PROVIDERS, help=f"model provider (default: {settings.llm_provider})"
    )
    command.add_argument(
        "--llm-model",
        help=f"generation model (default: {settings.resolved_llm_model}); provider defaults: "
        + ", ".join(f"{p}={m}" for p, m in DEFAULT_LLM_MODELS.items()),
    )
    command.add_argument(
        "--reasoning-effort", choices=REASONING_EFFORTS, help="OpenAI reasoning effort (default: the model's own)"
    )


def main(argv: list[str] | None = None) -> int:
    # Real environment variables win over values in .env.
    args = build_parser(Settings.from_env()).parse_args(argv)
    try:
        return args.func(args)
    except (MissingApiKeyError, CollectionMismatchError, NoSourceFilesError) as error:
        print(error, file=sys.stderr)
        return 2
