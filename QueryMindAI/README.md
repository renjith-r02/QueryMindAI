# QueryMind

Ask questions about your databases in plain English. QueryMind classifies the question,
retrieves the relevant schema documentation from a vector store, writes read-only SQL with an
LLM (Google Gemini by default, OpenAI optional), runs it on MySQL and PostgreSQL, fixes failed
SQL automatically, and answers from the results, with a table and charts.

```
question ─► intent classifier ─► semantic cache ─► retrieve schema docs (Qdrant)
         ─► generate SQL (LLM) ─► run read-only (MySQL / PostgreSQL) ─► repair on error
         ─► merge results across databases ─► written answer + table + chart
```

DELETE, INSERT and schema changes are always refused. UPDATE requests get SQL that is shown
for review and **never executed**.

## Repository layout

| Folder              | What it is                                                     | Tech                        |
| ------------------- | -------------------------------------------------------------- | --------------------------- |
| `querymind-agentic` | The engine: indexing, intent, RAG, SQL agent, cache, CLI       | Python 3.13, uv, Qdrant     |
| `querymind-api`     | HTTP API over the engine (REST + Server-Sent Events)            | FastAPI, uvicorn            |
| `querymind-ui`      | Web app: ask questions, results, charts, dashboard, settings    | React 19, Vite, TypeScript  |

Each folder has its own README with more detail. `querymind-api` installs `querymind-agentic`
as an editable dependency, so engine changes apply without reinstalling.

---

## 1. Prerequisites

| Tool                            | Version | Used for                                          |
| ------------------------------- | ------- | ------------------------------------------------- |
| [uv](https://docs.astral.sh/uv/) | recent  | Python environments and dependencies (installs Python 3.13 if needed) |
| Node.js                         | 20+     | The UI                                            |
| Qdrant                          | 1.10+   | Vector store, answer cache, data source settings  |
| MySQL                           | 8.0+    | The `ecommerce` database                          |
| PostgreSQL                      | 13+     | The `returns_db` database                         |
| A Google Gemini API key         |         | LLM and embeddings ([get one](https://aistudio.google.com/apikey)) |

Optional: an OpenAI API key, to use OpenAI models instead of Gemini.

Docker is the quickest way to get the three servers running locally, but any installation works:

```bash
docker run -d --name qdrant   -p 6333:6333 -v qdrant_storage:/qdrant/storage qdrant/qdrant
docker run -d --name mysql    -p 3306:3306 -e MYSQL_ROOT_PASSWORD=changeme mysql:8
docker run -d --name postgres -p 5432:5432 -e POSTGRES_PASSWORD=changeme postgres:16
```

Check Qdrant is up: `curl http://localhost:6333/collections`.

## 2. Create the databases

The annotated schema scripts are in `querymind-agentic/sqls/`. Besides creating the tables,
their comment headers document the data, and QueryMind indexes those headers so the LLM writes
correct SQL.

**MySQL** (the script creates the `ecommerce` database itself):

```bash
mysql -h 127.0.0.1 -u root -p < querymind-agentic/sqls/ecommerce_mysql_schema.sql
```

**PostgreSQL** (create the database first, then run the script inside it; it creates schema `rma`):

```bash
createdb -h localhost -U postgres returns_db
psql -h localhost -U postgres -d returns_db -f querymind-agentic/sqls/returns_postgres_schema.sql
```

**Sample data:** the scripts create empty tables. This repository does not include data or a
seed script yet, so load your own data, or ask the team for a data dump, before expecting answers
with rows in them.

**Recommended: read-only users.** QueryMind runs every query in a read-only transaction and
rejects write statements, but a read-only account is the real safety net:

```sql
-- MySQL
CREATE USER 'readonly'@'%' IDENTIFIED BY 'choose-a-password';
GRANT SELECT ON ecommerce.* TO 'readonly'@'%';

-- PostgreSQL (connected to returns_db)
CREATE ROLE readonly LOGIN PASSWORD 'choose-a-password';
GRANT CONNECT ON DATABASE returns_db TO readonly;
GRANT USAGE ON SCHEMA rma TO readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA rma TO readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA rma GRANT SELECT ON TABLES TO readonly;
```

## 3. Configure the engine (`querymind-agentic/.env`)

```bash
cd querymind-agentic
cp .env.example .env
```

Edit `.env`. The minimum is:

```bash
# Gemini: used for the LLM and for embeddings
GEMINI_API_KEY=your-gemini-api-key

# One line per database: QUERYMIND_DB_<NAME>, where NAME matches the schema file's database
QUERYMIND_DB_ECOMMERCE=mysql+pymysql://readonly:choose-a-password@localhost:3306/ecommerce
QUERYMIND_DB_RETURNS_DB=postgresql+psycopg://readonly:choose-a-password@localhost:5432/returns_db

QDRANT_URL=http://localhost:6333
```

Everything else has sensible defaults and is documented in `.env.example`:

| Setting                                    | Default                          | Notes                                                        |
| ------------------------------------------ | -------------------------------- | ------------------------------------------------------------ |
| `LLM_PROVIDER`                             | `gemini`                         | `openai` to use OpenAI (needs `OPENAI_API_KEY`)              |
| `LLM_MODEL` / `GEMINI_MODEL` / `OPENAI_MODEL` | `gemini-3.8-flash` / `gpt-6-luna` | Model per provider                                        |
| `EMBEDDING_PROVIDER`                       | `gemini`                         | `fastembed` runs locally without a key                       |
| `EMBEDDING_DIM`                            | `768`                            | Changing it requires re-indexing with `--recreate`           |
| `QUERYMIND_MAX_ROWS`, `QUERYMIND_QUERY_TIMEOUT` | `1000`, `30` s              | Per query; the row limit only seeds the guardrail policy (§8) |
| `QUERYMIND_CACHE_*`                        | on, 0.95, 3600 s                 | Semantic answer cache                                        |

`.env` holds secrets: it is git-ignored, so never commit it. Real environment variables
override values in `.env`.

> **Using OpenAI instead of Gemini:** set `LLM_PROVIDER=openai` and `OPENAI_API_KEY=...`.
> Embeddings still use Gemini unless you also set `EMBEDDING_PROVIDER=fastembed`.

## 4. Install the engine and index the knowledge base

```bash
cd querymind-agentic
uv sync                                  # creates .venv with the engine and dev tools
uv run querymind index --dry-run         # parse sqls/ without calling any service
uv run querymind index                   # embed the docs and store them in Qdrant
```

`index --dry-run` should list about 122 chunks for `ecommerce`, 68 for `returns_db` and 32
few-shot examples (`few_shot_examples.json`).
Re-run `uv run querymind index` whenever the files in `sqls/` change (this also clears the
answer cache).

Try a question from the command line (this calls the LLM and your databases):

```bash
uv run querymind run "How many orders are there per status?" --show-sql
```

## 5. Start the API (`querymind-api`)

```bash
cd querymind-api
cp .env.example .env                      # optional: CORS origins, Okta test hosts
uv sync --extra dev
uv run uvicorn app.main:app --reload      # http://localhost:8000
```

The API reads the engine settings from `querymind-agentic/.env`; `querymind-api/.env` holds
only API-specific settings. Check it:

```bash
curl http://localhost:8000/health         # {"status":"ok","service":"querymind-api"}
```

Interactive API docs: http://localhost:8000/docs (the spec is also saved in `querymind-api/docs/`).

## 6. Start the UI (`querymind-ui`)

```bash
cd querymind-ui
npm install
echo "VITE_API_URL=http://localhost:8000" > .env.local
npm run dev                               # http://localhost:8080
```

Without `VITE_API_URL`, the UI runs on a built-in mock backend with sample data, which is
useful for UI work without any server.

Open http://localhost:8080 and ask a question, e.g. *"Top 5 products by revenue this year"*.

## 7. Data sources

Open **Settings** in the UI to see the data sources. On first use they are created from the
schema files in `querymind-agentic/sqls/`, with connection details from your `.env`, and saved
in Qdrant (collection `querymind_datasources`).

For each database, queries use:

1. its **saved data source** (host, port, database, user from Settings), with any empty field
   and **always the password** taken from `QUERYMIND_DB_<NAME>` in `.env`. Passwords are never
   stored in Qdrant;
2. otherwise the **`.env` URL** as is. Databases that exist only in `.env` show up in Settings
   as "from .env" and can be saved from there;
3. disabled data sources are not queried.

Settings also hold each source's documentation (purpose, tables, relationships, join paths,
business rules). Cassandra and DynamoDB sources can be documented but not queried yet.

## 8. Admin console

**Admin console** (bottom of the sidebar):

- **Model Config**: switch between Gemini and OpenAI, set models and API keys (saved to
  `querymind-agentic/.env`, applied without a restart; keys are write-only), and test the connection.
- **Okta SSO**: configure Okta OIDC settings and test the connection. Sign-in is **not enforced yet**.
- **Guardrails**: the policy every question and generated query is checked against, stored in
  Qdrant (collection `querymind_guardrails`) and applied to new questions as soon as it is saved:
  - *Question rules* (regular expressions) refuse a question before any SQL is written.
  - *Blocked SQL keywords* stop generated SQL from running.
  - *Restricted columns* (default `users.password_hash`) can't be used in SQL and are removed from results.
  - The *row limit* per query.

  The rules for deleting data, DDL, inserts and permissions, and the core write keywords (INSERT,
  UPDATE, DELETE, DROP, ...), are locked: they can be reworded but not removed or disabled. If
  Qdrant can't be read, the built-in policy applies. *Try it* checks a question or SQL against
  unsaved changes. API: `GET/PUT /guardrails`, `POST /guardrails/reset`, `POST /guardrails/check`.
- **Logs**, **Schema**, **Overview**.

> The API has no authentication yet. Run it on your machine or a trusted network only.

## 9. Running the tests

Every project's tests run offline (fake models, in-memory Qdrant, SQLite):

```bash
cd querymind-agentic && uv run pytest && uv run ruff check
cd querymind-api     && uv run pytest
cd querymind-ui      && npm test && npm run lint && npm run typecheck
```

## 10. Evaluate text-to-SQL accuracy

The evaluation harness asks every test question through the real pipeline: intent, retrieval with
few-shot examples, SQL generation, guardrails, read-only execution and self-repair. It then scores
the answers against ground-truth SQL. Everything lives in `querymind-agentic`:

| File | What it is |
| --- | --- |
| `sqls/few_shot_examples.json` | **Few-shot library**: 32 verified question → SQL pairs, labelled by query type, for both databases. Indexed into Qdrant; the SQL generator sees the most similar ones as examples. |
| `evaluation/test_set.json` | **Test set**: 25 questions with ground-truth SQL (6 simple, 7 aggregate, 6 join, 6 temporal; 14 MySQL, 11 PostgreSQL) and 9 destructive **guardrail probes**. |
| `evaluation/reports/<timestamp>/` | One folder per run: `report.md` (for people) and `results.json` (every case, for comparing runs). |
| `src/querymind/evaluation/` | The harness: `dataset.py` (file formats), `compare.py` (metrics), `harness.py` (runner), `report.py` (report). |

### 10.1 Run it

Prerequisites: steps 1-4 done, so the databases are loaded, `.env` is set and the knowledge base
is indexed.

```bash
cd querymind-agentic

# 1. Index the few-shot library (first time, and after every change to it)
uv run querymind index sqls/few_shot_examples.json

# 2. Check the ground-truth and few-shot SQL on the live databases (no model calls, a few seconds)
uv run querymind evaluate --validate-only

# 3. Full evaluation (about 50 model calls, roughly 8-10 minutes with Gemini)
uv run querymind evaluate
```

The run prints one line per case (`T05 SELECT_AGGREGATE PASS (semantic, 13.1 s)`), then the totals
and the path of the report: `evaluation/reports/<timestamp>/report.md`.

Options:

| Option | Use |
| --- | --- |
| `--validate-only` | Run only the ground-truth and few-shot SQL. Exits with 1 if any statement fails, or if any ground truth returns no rows. |
| `--ids T05 T13 G01` | Only these cases or probes, e.g. to re-check failures quickly. |
| `--no-probes` | Skip the guardrail probes. |
| `--max-repairs N` | Self-repair attempts per question (default 2, as in the app). |
| `--output DIR` | Write the report somewhere else. |
| `--test-set FILE`, `--few-shot FILE` | Use other files, e.g. a draft test set. |
| `--llm-provider openai --llm-model ...` | Evaluate another model with the same test set. |

### 10.2 Read the report

- **Execution accuracy** (the main metric; the assignment's pass mark is 50%). The generated SQL
  and the ground truth both run on the live databases, and the result sets are compared row by row.
  Column names are ignored and columns may come in any order. Rows are compared as a set unless a
  case sets `order_matters`. Numbers compare as numbers (5 = 5.00). Non-integral values match
  within 0.5%, or when one is the other rounded (8.6477 = 8.6). *Relaxed* execution accuracy also
  accepts extra columns.
- **Exact match rate**: both statements are normalised by sqlglot (whitespace, keyword and
  identifier case, quoting, trailing `;`) and compared as text.
- **Semantic match**: an exact match, or `sqlglot.diff()` finds no edits after table and column
  aliases are normalised. A final `ORDER BY` is ignored when the question asks for no order.
- The report also has **per-query-type** and **per-database** breakdowns, intent-classification
  accuracy, and **guardrails compliance**: the share of destructive probes that never ran.
- **Execution misses** lists each failed case with the reason and both SQL statements.

Model temperature is 0, but hosted models are not fully deterministic, so expect small differences
between runs, mostly in exact match. Each report records its test-set and few-shot file hashes, the
model, the embeddings and the guardrail policy version, so you can tell whether two runs are
comparable.

### 10.3 Add or change few-shot examples

Edit `sqls/few_shot_examples.json`. Each pair:

```json
{
  "id": "FS33",
  "query_type": "SELECT_AGGREGATE",
  "database": "ecommerce",
  "dialect": "mysql",
  "question": "How many orders did each customer place?",
  "sql": "SELECT user_id, COUNT(*) AS orders FROM orders GROUP BY user_id;",
  "notes": "Optional: the business rule this example teaches."
}
```

Rules for a good example:

- **IDs:** use a unique `id`.
- **Query type:** `query_type` is one of `SELECT_SIMPLE`, `SELECT_AGGREGATE`, `SELECT_JOIN`,
  `SELECT_TEMPORAL` or `UPDATE`.
- **Base tables:** use tables, not the documented views; the views may not be installed.
- **Business rules:** follow the rules in the schema files, e.g. sales exclude `pending` and
  `cancelled` orders, and refunds count only when `status IN ('refunded','closed')`.
- **Write statements:** only `UPDATE` examples may write, and they need a `WHERE` clause. They're
  checked by the guardrails, never executed.
- **No test questions:** never copy a test-set question into the library, or the evaluation
  measures memory instead of skill. The unit tests check this.

Then validate and re-index:

```bash
uv run querymind evaluate --validate-only            # every SELECT must run
uv run querymind index sqls/few_shot_examples.json   # replaces this file's examples in Qdrant
uv run pytest tests/evaluation                       # coverage and no-overlap checks
```

### 10.4 Add or change test cases

Edit `evaluation/test_set.json`. Each case:

```json
{
  "id": "T26",
  "query_type": "SELECT_TEMPORAL",
  "database": "returns_db",
  "dialect": "postgresql",
  "question": "How many returns were requested in August 2026?",
  "ground_truth_sql": "SELECT count(*) FROM rma.returns WHERE requested_at >= '2026-08-01' AND requested_at < '2026-09-01';",
  "order_matters": false,
  "notes": "Optional"
}
```

- **Fixed dates:** use them ("in August 2026", not "last month") so results don't change over
  time.
- **Unambiguous wording:** say which rows and columns you want, e.g. "excluding rejected returns",
  "show the SKU and units", or "month as YYYY-MM". Otherwise a correct answer can fail on
  presentation.
- **Query type:** label `query_type` with the classifier's precedence. TEMPORAL beats AGGREGATE,
  which beats JOIN, which beats SIMPLE.
- **Row order:** set `order_matters: true` only when the question asks for an order and the ground
  truth has no ties.
- **Single database:** each case uses one database. Cross-database questions aren't scored yet.
- **Guardrail probes:** add them under `guardrail_probes` as `{"id": "G10", "question": "..."}`.
  Use `"expect": "drafted"` for change requests, which must be drafted and never executed.

Then run `uv run querymind evaluate --validate-only`. Every ground truth must run and return rows.
After that, run `uv run querymind evaluate` for a new report.

### 10.5 Keep and compare results

Reports are plain files, so you can commit the run you want to keep, e.g. the one for the
assignment hand-in. Compare runs with `results.json`: `summary.overall`, `summary.by_query_type`,
and the per-case `execution_match` / `exact_match` / `reason` fields. If you change the model, the
few-shot library or the guardrails, rerun the full evaluation. The report header shows which inputs
changed.

## Troubleshooting

| Symptom                                                         | Fix                                                                                   |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| "The model provider's API key is not configured" (503)           | Set `GEMINI_API_KEY` (or `OPENAI_API_KEY` with `LLM_PROVIDER=openai`) in `querymind-agentic/.env`, then restart the API |
| "The vector store is unavailable" (503)                          | Start Qdrant and check `QDRANT_URL`                                                    |
| Collection stores N-dim vectors but the model produces M-dim (409) | You changed the embedding model or `EMBEDDING_DIM`: run `uv run querymind index --recreate` |
| "No connection configured for database 'x'"                      | Add `QUERYMIND_DB_X=...` to `.env`, or add the data source in Settings                 |
| Answers say the question can't be answered                       | Run `uv run querymind index`; check the database has data                             |
| UI shows "Could not reach the QueryMind API"                     | Start the API; check `VITE_API_URL` in `querymind-ui/.env.local` and restart `npm run dev` |
| Browser CORS error                                               | Add your UI origin to `QUERYMIND_CORS_ORIGINS` in `querymind-api/.env`                 |
| Changed `.env` but nothing happened                              | Restart the API (`--reload` only watches code, not `.env`)                             |
| An answer looks stale                                            | It may come from the semantic cache: click **Get a fresh answer**                     |
