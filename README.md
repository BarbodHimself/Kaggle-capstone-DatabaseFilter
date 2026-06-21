# Enterprise Database Middleware & Query Optimization Agent

Repository: https://github.com/BarbodHimself/Kaggle-capstone-DatabaseFilter

An intelligent, inline database proxy that intercepts raw SQL traffic, blocks injection attacks at the sanitization boundary, and uses Gemini 2.5 Flash to autonomously rewrite inefficient queries before they reach your production database.

---

## Table of Contents

- [What It Does](#what-it-does)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [What It Accepts and Why It Passes](#what-it-accepts-and-why-it-passes)
- [What It Blocks and Why It Fails](#what-it-blocks-and-why-it-fails)
- [Known Limitations](#known-limitations)
- [MCP Tool Server](#mcp-tool-server)
- [Implementation Options](#implementation-options)
  - [Option 1 — Interactive CLI](#option-1--interactive-cli)
  - [Option 2 — ADK Web Playground](#option-2--adk-web-playground)
  - [Option 3 — FastAPI REST Server](#option-3--fastapi-rest-server)
  - [Option 4 — Direct Python Import](#option-4--direct-python-import)
  - [Option 5 — Inline Network Proxy](#option-5--inline-network-proxy)
  - [Option 6 — Kubernetes Sidecar](#option-6--kubernetes-sidecar)
- [Installation Guide](#installation-guide)
- [Running the CLI — Step by Step](#running-the-cli--step-by-step)
- [Connecting to Other Systems](#connecting-to-other-systems)
- [Running the Tests](#running-the-tests)
- [Tech Stack](#tech-stack)
- [Security Model](#security-model)

---

## What It Does

Modern enterprise applications constantly generate poorly-written database traffic. ORM abstractions produce N+1 loops, junior developers write implicit Cartesian joins, and legacy systems use decade-old syntax. At the same time, public-facing input vectors are continuously targeted by SQL injection attacks.

This system sits inline between your application and your database and solves both problems at the same time:

| Concern | Solution |
|---|---|
| Security | Deterministic regex-based injection blocking — runs before any AI processing |
| Performance | AI-driven query rewriting via Gemini 2.5 Flash |
| Credential Safety | Schema context delivered via isolated MCP boundary — no live DB credentials are ever exposed to the LLM |

---

## How It Works

Every query submitted to the proxy is treated as a state transition inside a LangGraph Directed Acyclic Graph (DAG). Sanitization always fully completes before any AI processing begins. This is enforced structurally by the graph topology — not by a runtime flag or a convention.

```
Client Application
        |
        v
[1] State Initialization
        |
        v
[2] Sanitize Node
        |
        |-- REJECTED (destructive keyword or multi-statement) --> SANITIZATION_FAILED
        |
      CLEAN
        |
        v
[3] Optimize Node  (Gemini 2.5 Flash)
        |
        |-- LLM error or missing key --> OPTIMIZATION_FAILED or passthrough
        |
      OPTIMIZED
        |
        v
[4] Routing Node
        |
        |-- any *_FAILED status --> returns error state to caller
        |
      SUCCESS --> optimized query returned to caller
```

### Step by Step

**Step 1 — State Initialization**

Before any processing, a `DatabaseSessionState` dictionary is constructed with:
- `raw_query`: the original unmodified input
- `sanitized_query`: `None` until the sanitizer sets it
- `optimized_query`: `None` until the optimizer sets it
- `query_history`: an append-only list of every query string seen this run
- `session_logs`: a human-readable execution trace
- `current_errors`: a list of error strings; non-empty means execution was blocked
- `execution_status`: starts as `INITIALIZED`

**Step 2 — Sanitize Node**

The raw query is scanned for destructive DDL keywords using word-boundary regex (`\bKEYWORD\b`). Statement stacking is detected by stripping the trailing semicolon and checking for any remaining semicolons. If any rule fires, all errors are written to `current_errors`, `execution_status` becomes `SANITIZATION_FAILED`, and the function returns. The optimize and routing nodes still execute in sequence but immediately skip their logic when they detect the failed status.

**Step 3 — Optimize Node**

Runs only if `execution_status == "SANITIZED"`. Submits the sanitized query to Gemini 2.5 Flash with an expert rewriting prompt. The model returns an optimized SQL equivalent. If `GEMINI_API_KEY` is not set, the node falls back to returning the query unchanged (passthrough mode) so the system still functions without credentials.

**Step 4 — Routing Node**

Reads the current `execution_status`. If it contains `FAILED`, it appends an error log entry and returns. Otherwise it sets `execution_status` to `SUCCESS` and returns the full state to the caller.

---

## Architecture

```
+----------------------------------------------------------+
|                LangGraph DAG  (app/agent.py)             |
|                                                          |
|  +--------------------+                                  |
|  | sanitize_input_node|                                  |
|  +--------+-----------+                                  |
|           |                                              |
|  +--------v-----------+                                  |
|  | optimize_query_node| -------> Gemini 2.5 Flash API    |
|  +--------+-----------+         (google-genai SDK)       |
|           |                                              |
|  +--------v-----------+                                  |
|  |   routing_node     |                                  |
|  +--------------------+                                  |
+----------------------------------------------------------+
                    (separate process, stdio transport)
+----------------------------------------------------------+
|              MCP Server  (app/mcp_server.py)             |
|                                                          |
|   fetch_database_schema  -- Pydantic-validated input     |
|   explain_query_plan     -- Pydantic-validated input     |
|                                                          |
|   Mock registry: users, orders, metrics                  |
|   (swap for real DB driver to connect to production)     |
+----------------------------------------------------------+
```

The MCP server runs as an isolated subprocess. The boundary between the LLM and the database means the model can only call the two explicitly registered tools with strictly validated arguments. It cannot issue arbitrary queries or read credentials.

---

## Project Structure

```
db-query-opt-agent/
|
+-- app/
|   +-- agent.py              LangGraph DAG: state machine, all three nodes, graph compile
|   +-- mcp_server.py         MCP tool server: fetch_database_schema, explain_query_plan
|   +-- fast_api_app.py       FastAPI wrapper for REST deployment (ADK scaffold)
|   +-- config.py             Application configuration (ADK scaffold)
|   +-- app_utils/            Shared helpers and telemetry (ADK scaffold)
|   +-- __init__.py           Exports app object for external import
|
+-- tests/
|   +-- conftest.py           Loads api.env once for the entire test session
|   +-- unit/
|       +-- test_agent.py     End-to-end pytest tests: clean query and injection payload
|
+-- cli_middleware.py         Interactive terminal interface for manual testing
+-- pyproject.toml            uv dependency manifest and project metadata
+-- api.env                   GEMINI_API_KEY (gitignored, never committed)
+-- .gitignore                Comprehensive ignore rules for Python, ADK, IDEs, OS
+-- README.md                 This file
```

---

## What It Accepts and Why It Passes

The system accepts any single-statement `SELECT` query that contains none of the blocked keywords and no semicolon-based stacking.

### Why a query passes

A query passes sanitization when:
1. None of the words `DROP`, `DELETE`, `TRUNCATE`, `ALTER`, `GRANT`, or `REVOKE` appear as whole words in the uppercased query string.
2. The query string, after stripping any single trailing semicolon, contains no further semicolons.

If both conditions are satisfied, `sanitized_query` is set to the original input, `execution_status` becomes `SANITIZED`, and the query advances to the optimizer.

### Accepted query examples

| Input Query | Why It Passes | Optimizer Action |
|---|---|---|
| `SELECT * FROM users WHERE active = 1` | No banned keywords, single statement | Rewrites wildcard to specific columns |
| `SELECT id, email FROM users WHERE id = 1` | Clean, indexed lookup | Returns as-is or adds index hint |
| `SELECT e.name, d.name FROM employees e, departments d WHERE e.dept_id = d.id` | No banned keywords, ANSI-89 implicit join is allowed through sanitization | Rewritten to explicit ANSI-92 INNER JOIN |
| `SELECT id, (SELECT SUM(amount) FROM invoices WHERE user_id = u.id) FROM users u` | Correlated subquery, no banned keywords | Flattened to JOIN or window function |
| `SELECT * FROM orders WHERE id IN (SELECT order_id FROM items WHERE qty > 10)` | Subquery, no banned keywords | Rewritten as INNER JOIN with indexed predicate |
| `SELECT * FROM metrics;` | Trailing semicolons only — stripped and re-checked, no stacking found | Proceeds to optimizer normally |

---

## What It Blocks and Why It Fails

### Blocked: Destructive DDL Keywords

Detection uses `re.search(r"\bKEYWORD\b", query.upper())`. The word-boundary anchors prevent substring false positives — a column named `dropdown` will not trigger the `DROP` rule.

| Input Query | Keyword Detected | Error Written to current_errors |
|---|---|---|
| `DELETE FROM users WHERE id = 99` | `DELETE` | `Security Alert: Destructive keyword 'DELETE' is not permitted.` |
| `DROP TABLE orders` | `DROP` | `Security Alert: Destructive keyword 'DROP' is not permitted.` |
| `TRUNCATE TABLE metrics` | `TRUNCATE` | `Security Alert: Destructive keyword 'TRUNCATE' is not permitted.` |
| `ALTER TABLE users ADD COLUMN age INT` | `ALTER` | `Security Alert: Destructive keyword 'ALTER' is not permitted.` |
| `GRANT ALL ON users TO public` | `GRANT` | `Security Alert: Destructive keyword 'GRANT' is not permitted.` |
| `REVOKE SELECT ON orders FROM analyst` | `REVOKE` | `Security Alert: Destructive keyword 'REVOKE' is not permitted.` |

Why it fails: the keyword appears as a whole word in the uppercased query. The sanitizer appends the error to `current_errors`, sets `execution_status = "SANITIZATION_FAILED"`, and returns immediately. The optimize node checks the status at its first line and skips all logic. `optimized_query` remains `None`.

### Blocked: Statement Stacking

Detection: `raw_query.rstrip(";")` is checked for any remaining `";"`. A single trailing semicolon is legal; any semicolon after that indicates a second statement.

| Input Query | Why It Fails |
|---|---|
| `SELECT * FROM products WHERE id = 10; DROP TABLE transactions;` | Both stacking and DROP are detected. Two errors are written. |
| `SELECT 1; SELECT 2` | Semicolon between two statements detected. |
| `SELECT * FROM users; --` | Stacking detected regardless of what follows the semicolon. |

Why it fails: the second statement introduces attack surface even if the second statement itself looks harmless. The system blocks on structure, not on content analysis of the second statement.

### Complete failure trace example

```
Input:   SELECT * FROM metrics; DROP TABLE users;

Node 1 — sanitize_input_node:
  Checks "DROP"          --> match at word boundary --> error appended
  Checks ";"             --> stacking detected      --> error appended
  execution_status       = "SANITIZATION_FAILED"
  current_errors         = [
    "Security Alert: Destructive keyword 'DROP' is not permitted.",
    "Security Alert: Multi-statement queries are forbidden."
  ]
  sanitized_query        = None

Node 2 — optimize_query_node:
  execution_status != "SANITIZED" --> skip, return state unchanged

Node 3 — routing_node:
  "FAILED" in execution_status --> log error route, return

Final state:
  execution_status  = "SANITIZATION_FAILED"
  optimized_query   = None
  current_errors    = [two errors above]
```

---

## Known Limitations

The following attack vectors are outside the current sanitizer's detection scope. They should be handled at the application layer, database driver layer, or by a dedicated WAF:

| Attack Type | Example | Why Not Currently Blocked |
|---|---|---|
| Tautological bypass | `WHERE pass='x' OR 1=1` | No boolean shortcut detection |
| Inline comment injection | `SELECT 1 -- rest ignored` | Comments not stripped before keyword scan |
| Block comment injection | `SEL/*bypass*/ECT 1` | No comment normalization |
| UNION-based injection | `SELECT 1 UNION SELECT user,pass FROM auth` | `UNION` is not a blocked keyword |
| Second-order injection | Payload stored now, executed later by another query | Out of scope for a single-pass sanitizer |
| Hex/encoding bypass | `0x44524f50` decoded to `DROP` | No encoding normalization |

---

## MCP Tool Server

The MCP server (`app/mcp_server.py`) exposes two tools over the stdio transport. It runs as a separate subprocess — the LLM never has direct database access.

### Tool: `fetch_database_schema`

Returns column definitions and index layout for a named table.

Input argument:
- `table_name` (string) — must fully match `[a-zA-Z0-9_]+`. Any space, quote, hyphen, semicolon, or SQL operator causes an immediate Pydantic validation error before the registry is queried.

Tables currently in the mock registry: `users`, `orders`, `metrics`.

### Tool: `explain_query_plan`

Returns a simulated `EXPLAIN ANALYZE` output for a single SELECT query.

Input argument:
- `query` (string) — must start with `SELECT` or `EXPLAIN`, and must not contain semicolon stacking. These checks run independently of the graph sanitizer — they are a second validation boundary at the tool layer.

### Registering the MCP server

Add this to `mcp_config.json` in the project root:

```json
{
  "mcpServers": {
    "db_optimizer": {
      "command": "uv",
      "args": ["run", "python", "-m", "app.mcp_server"]
    }
  }
}
```

---

## Implementation Options

There are six ways to use this system, covering local development, production deployment, and direct integration.

---

### Option 1 — Interactive CLI

**Best for:** local testing, demos, manual inspection of the sanitization and optimization output.

```bash
uv run python cli_middleware.py
```

A terminal prompt appears. Type any SQL query and press Enter. The full graph runs and the result is printed — either the optimized query on success, or the blocked errors on failure. Type `exit` or `quit` to stop.

**What you will see on success:**

```
DB_MIDDLEWARE > SELECT * FROM users WHERE active = 1

  Intercepting payload...
  Running graph checkpoints...

--------------------------------------------------------------------
  STATUS : SUCCESS
  Input  : SELECT * FROM users WHERE active = 1
  Output : SELECT id, username, email FROM users WHERE active = 1
--------------------------------------------------------------------
```

**What you will see on a blocked query:**

```
DB_MIDDLEWARE > SELECT * FROM users; DROP TABLE users;

  Intercepting payload...
  Running graph checkpoints...

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  STATUS : SECURITY ALERT — execution blocked
  Input  : SELECT * FROM users; DROP TABLE users;
  Errors : ["Security Alert: Destructive keyword 'DROP' is not permitted.",
             "Security Alert: Multi-statement queries are forbidden."]
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

---

### Option 2 — ADK Web Playground

**Best for:** visual demos, presenting to a Capstone committee, non-technical stakeholders.

Requires `agents-cli` installed (`uv tool install google-agents-cli`).

```bash
agents-cli playground
```

Opens a local web server with a chat interface wired directly to the agent graph. Type queries into the chat box and receive the optimized result as a response.

---

### Option 3 — FastAPI REST Server

**Best for:** integrating the middleware into an existing application over HTTP without modifying the application's source code.

```bash
uv run python app/fast_api_app.py
```

The server starts on port `8000`. Applications send queries as HTTP POST requests and receive the optimized SQL in the response body. Environment variables (`ALLOW_ORIGINS`, `LOGS_BUCKET_NAME`) can be set in `api.env` to configure CORS and Google Cloud logging.

Note: `fast_api_app.py` uses `google.auth.default()` for Cloud credentials. For local use without a GCP project, the Google Cloud SDK must be installed and authenticated, or that code path must be adapted.

---

### Option 4 — Direct Python Import

**Best for:** embedding the middleware inside an existing Python application with no network layer overhead.

```python
from app.agent import app

result = app.invoke({
    "raw_query": "SELECT * FROM orders WHERE status = 'pending'",
    "sanitized_query": None,
    "optimized_query": None,
    "query_history": [],
    "session_logs": [],
    "current_errors": [],
    "execution_status": "INITIALIZED"
})

if result["execution_status"] == "SUCCESS":
    # Pass result["optimized_query"] to your database driver
    cursor.execute(result["optimized_query"])
elif result["execution_status"] == "SANITIZATION_FAILED":
    # Log and reject
    raise PermissionError(result["current_errors"])
```

The `app` object is a compiled LangGraph graph. It is stateless — each `invoke()` call creates an independent execution context. Safe to call from multiple threads.

The convenience wrapper `process_query` in `agent.py` constructs the initial state automatically:

```python
from app.agent import process_query

result = process_query("SELECT id FROM users WHERE active = 1")
print(result["optimized_query"])
```

---

### Option 5 — Inline Network Proxy

**Best for:** legacy environments where changing application source code is restricted. All services point their database connection string at the proxy host and port. No application changes are required — only a connection string update.

```
[ Billing Service  ] --+
[ Catalog Service  ] --+--> [ PROXY HOST:PORT ] --> [ Production DB ]
[ Reporting Service] --+
```

The proxy receives the raw query string over the network, runs the graph, and forwards the optimized output to the database. This topology requires wrapping `cli_middleware.py` or `fast_api_app.py` with a TCP socket listener appropriate to your database wire protocol (e.g. MySQL protocol, PostgreSQL wire protocol). That socket layer is not included in this repository but is straightforward to implement using `asyncpg` or `PyMySQL` as the upstream driver.

---

### Option 6 — Kubernetes Sidecar

**Best for:** containerized cloud environments with strict per-request latency budgets. The proxy runs as a sidecar container in the same Kubernetes Pod, communicating over `localhost` with no network hop.

```
+--------------------------------------------+
| Kubernetes Pod                             |
|  +----------------------+                  |
|  | Application Container|                  |
|  | issues raw SQL       | --> localhost    |
|  +----------------------+         |        |
|  +----------------------+         |        |
|  | Proxy Sidecar        | <-------+        |
|  | (localhost:PORT)     | --> Cloud DB     |
|  +----------------------+                  |
+--------------------------------------------+
```

The sidecar scales horizontally alongside the application container with no separate scaling configuration. The `Dockerfile` in the project root can be used as a base image for the sidecar container.

---

## Installation Guide

### Prerequisites

Before cloning, make sure the following are installed on your machine:

| Tool | Required | Install Link |
|---|---|---|
| Python 3.11+ | Yes | https://www.python.org/downloads/ |
| `uv` package manager | Yes | https://docs.astral.sh/uv/getting-started/installation/ |
| Git | Yes | https://git-scm.com |
| `agents-cli` | Only for Playground option | Installed in step 4 |
| Google Cloud SDK | Only for FastAPI/Cloud deploy | https://cloud.google.com/sdk/docs/install |

### Step 1 — Clone the repository

```bash
git clone https://github.com/BarbodHimself/Kaggle-capstone-DatabaseFilter.git
cd Kaggle-capstone-DatabaseFilter/db-query-opt-agent
```

### Step 2 — Install all dependencies

`uv sync` reads `pyproject.toml`, creates a virtual environment inside `.venv/`, and installs all locked packages. No manual `pip install` is needed.

```bash
uv sync
```

Expected output: a list of installed packages ending with `Installed N packages in Xs`.

### Step 3 — Create your API key file

Create a file called `api.env` in the `db-query-opt-agent/` directory (the same folder as `pyproject.toml`).

```
GEMINI_API_KEY=your_key_here
```

Get a free API key from https://aistudio.google.com. This file is gitignored and will never be committed.

If you skip this step, the system still runs but the optimizer falls back to passthrough mode — it returns the sanitized query unchanged without LLM rewriting.

### Step 4 — (Optional) Install agents-cli for the Playground

Only needed if you want the web UI option:

```bash
uv tool install google-agents-cli
uvx google-agents-cli setup
```

### Step 5 — Verify the installation

Run the test suite to confirm everything is wired correctly:

```bash
uv run pytest tests/unit/test_agent.py -v
```

Both tests should pass. If the API key is present, the clean query test will make a real Gemini API call.

---

## Running the CLI — Step by Step

The CLI is the fastest way to test and demonstrate the system interactively.

### Start the CLI

```bash
uv run python cli_middleware.py
```

You will see a header and the prompt:

```
====================================================================
  ENTERPRISE DATABASE MIDDLEWARE INTERCEPTOR
  Engine: Gemini 2.5 Flash  |  Protocol: MCP Secure
  Type your SQL query and press Enter.
  Type 'exit' or 'quit' to stop.
====================================================================

DB_MIDDLEWARE >
```

### Test a clean query

Type this and press Enter:

```
DB_MIDDLEWARE > SELECT * FROM users WHERE active = 1
```

Expected output:

```
  Intercepting payload...
  Running graph checkpoints...

--------------------------------------------------------------------
  STATUS : SUCCESS
  Input  : SELECT * FROM users WHERE active = 1
  Output : SELECT id, username, email FROM users WHERE active = 1
--------------------------------------------------------------------
```

The optimizer removed the wildcard and selected only the relevant columns.

### Test a blocked injection payload

Type this and press Enter:

```
DB_MIDDLEWARE > SELECT * FROM users; DROP TABLE users;
```

Expected output:

```
  Intercepting payload...
  Running graph checkpoints...

!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
  STATUS : SECURITY ALERT — execution blocked
  Input  : SELECT * FROM users; DROP TABLE users;
  Errors : ["Security Alert: Destructive keyword 'DROP' is not permitted.",
             "Security Alert: Multi-statement queries are forbidden."]
!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
```

The query never reached the LLM or the database.

### Test the optimizer on a complex query

```
DB_MIDDLEWARE > SELECT e.name, d.name FROM employees e, departments d WHERE e.dept_id = d.id
```

Expected output: `SUCCESS` with the query rewritten from ANSI-89 implicit join syntax to an explicit ANSI-92 `INNER JOIN`.

### Stop the CLI

```
DB_MIDDLEWARE > exit
```

---

## Connecting to Other Systems

This section explains how to wire the middleware to your own application, database, or service layer.

### Connecting your Python application directly

Import the compiled graph and call it in place of your existing database driver:

```python
from app.agent import process_query
import psycopg2

# Your existing DB connection
conn = psycopg2.connect("dbname=mydb user=postgres")
cursor = conn.cursor()

# Wrap your query through the middleware
result = process_query("SELECT * FROM orders WHERE status = 'pending'")

if result["execution_status"] == "SUCCESS":
    cursor.execute(result["optimized_query"])
elif result["execution_status"] == "SANITIZATION_FAILED":
    raise PermissionError(f"Query blocked: {result['current_errors']}")
else:
    raise RuntimeError(f"Middleware error: {result['current_errors']}")
```

The `process_query` helper constructs the full initial state automatically. No state dictionary needed on your side.

### Connecting a real database to the MCP server

By default, `mcp_server.py` returns mock data from an in-memory registry. To connect it to a real database, replace the `MOCK_SCHEMA_REGISTRY` lookups:

```python
# In app/mcp_server.py — replace this block:
schema = MOCK_SCHEMA_REGISTRY.get(validated.table_name)

# With a real driver call, for example with psycopg2:
import psycopg2, os

def get_real_schema(table_name: str) -> dict | None:
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = %s
    """, (table_name,))
    rows = cur.fetchall()
    conn.close()
    if not rows:
        return None
    return {"columns": {r[0]: r[1] for r in rows}, "indexes": []}
```

Add `DATABASE_URL=postgresql://user:pass@host/dbname` to your `api.env`. The password never leaves the MCP server subprocess — it is never passed to the LLM.

### Connecting via HTTP (FastAPI)

Start the REST server:

```bash
uv run python app/fast_api_app.py
```

Send queries from any HTTP client:

```bash
curl -X POST http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -d '{"message": "SELECT * FROM orders WHERE status = pending"}'
```

Note: the exact request/response schema depends on the ADK FastAPI wrapper version. Check the auto-generated docs at `http://localhost:8000/docs` after starting the server.

### Connecting to Google Cloud

If you have a GCP project, authenticate and set your project:

```bash
gcloud auth login --update-adc
gcloud config set project YOUR_PROJECT_ID
```

Then deploy:

```bash
agents-cli deploy
```

This builds a container image and deploys it to Cloud Run. Your application can then send queries to the deployed HTTPS endpoint instead of running the middleware locally.

---

## Running the Tests

The unit tests run the full graph end-to-end, including the real Gemini API call. The `api.env` file must be present before running.

```bash
uv run pytest tests/unit/test_agent.py -v
```

Expected output:

```
tests/unit/test_agent.py::test_clean_query_optimization    PASSED
tests/unit/test_agent.py::test_malicious_injection_payload PASSED

2 passed in ~22s
```

### What each test verifies

**`test_clean_query_optimization`**

Invokes the graph with `SELECT * FROM users WHERE active = 1`. Asserts:
- `execution_status` is `SUCCESS`
- `sanitized_query` is not `None` and contains `SELECT`
- `optimized_query` is not `None` (Gemini returned a result)
- `current_errors` is empty

**`test_malicious_injection_payload`**

Invokes the graph with `SELECT * FROM metrics; DROP TABLE users;`. Asserts:
- `execution_status` is `SANITIZATION_FAILED`
- `optimized_query` is `None` (optimizer never ran)
- `current_errors` is non-empty
- The string `DROP` appears in the error list
- The string `Multi-statement` appears in the error list

---

## Tech Stack

| Package | Role |
|---|---|
| `langgraph` | DAG-based state machine — enforces strict node execution order |
| `google-genai` | Gemini 2.5 Flash SDK for LLM query rewriting |
| `mcp` | Model Context Protocol SDK — schema tools in an isolated subprocess |
| `pydantic` | Input validation on all MCP tool arguments |
| `fastapi` | HTTP server wrapper for REST-based deployment |
| `python-dotenv` | Portable api.env loading via directory walk-up |
| `uv` | Fast, deterministic dependency resolution and virtual environment management |
| `google-adk` | ADK framework scaffolding and playground runtime |
| `pytest` | Test runner for unit and integration tests |

---

## Security Model

**API key handling**

`GEMINI_API_KEY` is loaded from `api.env` by walking up the directory tree at import time. It is never hardcoded, never interpolated into session logs, and never committed to the repository. The `.gitignore` excludes `api.env` and all `*.env` patterns.

**Sanitization is structurally prior to LLM access**

The LangGraph edge order is `sanitize -> optimize -> route`. This is a compile-time graph definition, not a runtime condition. There is no code path that reaches the optimize node without the sanitize node having fully executed first.

**MCP tool boundary**

The LLM never has direct database access. The MCP server is the only component that queries the schema registry, and it only exposes the two explicitly registered tools. All tool inputs go through Pydantic field validators before any registry lookup. A table name containing a space, hyphen, quote, semicolon, or any non-alphanumeric character is rejected by the validator before the lookup runs.

**No live database connection**

`mcp_server.py` uses a mock in-memory registry. To connect to a real database, replace the `MOCK_SCHEMA_REGISTRY` dictionary lookups with real driver calls (`psycopg2`, `sqlalchemy`, etc.). Credentials for that connection must be injected via environment variables — they must never be passed through MCP tool arguments, where they would enter the LLM's context window.
