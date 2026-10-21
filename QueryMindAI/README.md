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
| `QUERYMIND_MAX_ROWS`, `QUERYMIND_QUERY_TIMEOUT` | `1000`, `30` s              | Per query                                                    |
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

`index --dry-run` should list about 122 chunks for `ecommerce` and 68 for `returns_db`.
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
- **Guardrails**, **Logs**, **Schema**, **Overview**.

> The API has no authentication yet. Run it on your machine or a trusted network only.

## 9. Running the tests

Every project's tests run offline (fake models, in-memory Qdrant, SQLite):

```bash
cd querymind-agentic && uv run pytest && uv run ruff check
cd querymind-api     && uv run pytest
cd querymind-ui      && npm test && npm run lint && npm run typecheck
```

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
