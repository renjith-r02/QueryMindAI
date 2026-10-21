# querymind-agentic

The QueryMind engine: index database knowledge into Qdrant, generate read-only SQL with
an LLM (Gemini or OpenAI), run it on MySQL / PostgreSQL, fix failed SQL, and answer from
the results. Used by the `querymind` command line and by `querymind-api`.

## Setup

Requires Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync                 # creates .venv and installs the package (editable) with dev tools
cp .env.example .env    # then fill in API keys and database URLs
```

## Command line

```bash
uv run querymind index --dry-run          # parse sqls/ without writing
uv run querymind index                    # embed and store in Qdrant
uv run querymind search "refunds paid per month" --type example_query
uv run querymind ask "net revenue by category last month"     # generate SQL only
uv run querymind run "top 5 products by revenue" --show-sql   # generate, run, answer
uv run querymind run "orders per month" --llm-provider openai # pick the model for one run
```

`python -m querymind ...` works the same way.

## Project layout

```
querymind-agentic/
├── pyproject.toml            # package metadata, dependencies, pytest and ruff config
├── .env.example              # every setting, documented
├── sqls/                     # annotated schema files and question/SQL pairs to index
├── src/querymind/
│   ├── config.py             # Settings (environment + .env)
│   ├── exceptions.py         # QueryMindError and subclasses
│   ├── progress.py           # progress events for streaming
│   ├── service.py            # QueryMindService: index / search / ask / run
│   ├── cli.py, __main__.py   # the `querymind` command
│   ├── ingest/               # sql_parser, qa_loader, Chunk model
│   ├── knowledge/            # embeddings (Gemini, FastEmbed), Qdrant store
│   ├── llm/                  # providers (Gemini, OpenAI), Gemini client and retries
│   ├── intent/               # intent classifier: rules + model, before any SQL is written
│   ├── cache/                # semantic cache: reuse recent answers without LLM calls
│   ├── datasources/          # data source settings in Qdrant (seeded from sqls/ + .env); connection resolution
│   ├── database/             # read-only executor, SQL safety checks, result merging
│   └── agent/                # rag (retrieve + generate) and sql_agent (run / repair / answer)
└── tests/                    # mirrors src/querymind; shared fakes in tests/support
```

Import from the subpackages' public names, e.g. `from querymind.agent import QueryMindAgent`
or `from querymind.service import QueryMindService`.

## Intent classification

Every question is classified before SQL is generated (`querymind.intent`):

| Intent             | Meaning                                              | What happens                         |
| ------------------ | ---------------------------------------------------- | ------------------------------------ |
| `SELECT_SIMPLE`    | rows from one table, filtered or sorted              | SQL generated and run                |
| `SELECT_AGGREGATE` | totals, counts, averages, rankings, GROUP BY         | SQL generated and run                |
| `SELECT_JOIN`      | needs two or more tables or databases                | SQL generated and run                |
| `SELECT_TEMPORAL`  | depends on dates or periods (wins over the others)   | SQL generated and run                |
| `UPDATE`           | change values in existing rows                       | one `UPDATE … WHERE …` drafted, **never executed** |
| `UNSUPPORTED`      | DELETE, INSERT, DDL, permissions                     | refused before any SQL is written    |

DELETE, INSERT, DDL and permission requests are refused by deterministic rules before any
model, database or vector-store call. The language model then classifies everything else
against the indexed schema names (catching paraphrases such as "make the test customers
disappear"); it can refuse a request but never un-refuse one. Drafted UPDATEs are screened:
a single statement with a WHERE clause, no other keywords, or they are withheld. If the model
is unavailable, keyword rules classify instead. Each result reports
`{query_type, tables_mentioned, columns_mentioned, traits, reason, source}`.

## Semantic cache

Repeated or near-identical questions are answered from a cache in Qdrant
(`<collection>_cache`) without any LLM call. The only cost is embedding the question,
which is reused for retrieval on a miss. An answer is reused when:

- the question is identical after normalising case, punctuation and spacing, or its
  embedding similarity is at least `QUERYMIND_CACHE_THRESHOLD` (default 0.95);
- numbers, quoted values and time/direction/negation words are equal ("top 5" never
  reuses "top 10", "this month" never reuses "last month");
- the model, embedding, knowledge collection, row limit and database filter are the same;
- it is younger than `QUERYMIND_CACHE_TTL` seconds (default 3600).

Answered questions and UPDATE drafts are cached; failures and refusals are not. Re-indexing
clears the cache. `run(..., use_cache=False)` (API: `"use_cache": false`) asks the model again
and refreshes the entry. Disable with `QUERYMIND_CACHE_ENABLED=false`.

## Database connections

Queries connect to each database using its saved data source (Settings page, stored in
Qdrant) first, with `QUERYMIND_DB_<NAME>` in `.env` as the fallback:

- no saved data source: the `.env` URL is used as is;
- saved and disabled: the database is not queried;
- saved MySQL/PostgreSQL: its host, port, database and user; any empty field falls back to
  the `.env` URL; the password always comes from `.env` (it is never stored in Qdrant);
- saved but incomplete, or Cassandra/DynamoDB (not queryable yet): the `.env` URL if set;
- data sources can't be read (Qdrant down): `.env` only.

New data sources are seeded from `sqls/` with connection details from `.env`. Changes in
Settings apply to the next question without a restart.

## Development

```bash
uv run pytest             # tests run offline: in-memory Qdrant, SQLite, fake models
uv run ruff check         # lint (pyflakes, pycodestyle, isort, bugbear, pyupgrade)
uv run ruff format        # format
```
