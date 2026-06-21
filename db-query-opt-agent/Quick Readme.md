# db-query-opt-agent

Simple ReAct agent
Agent generated with `agents-cli` version `0.5.0`

## Project Structure

```
db-query-opt-agent/
├── app/         # Core agent code
│   ├── agent.py               # Main agent logic
│   └── app_utils/             # App utilities and helpers
├── tests/                     # Unit, integration, and load tests
├── GEMINI.md                  # AI-assisted development guide
└── pyproject.toml             # Project dependencies
```

> 💡 **Tip:** Use [Gemini CLI](https://github.com/google-gemini/gemini-cli) for AI-assisted development - project context is pre-configured in `GEMINI.md`.

## Requirements

Before you begin, ensure you have:
- **uv**: Python package manager (used for all dependency management in this project) - [Install](https://docs.astral.sh/uv/getting-started/installation/)
- **agents-cli**: Agents CLI - Install with `uv tool install google-agents-cli`
- **Google Cloud SDK**: For GCP services - [Install](https://cloud.google.com/sdk/docs/install)
- **Environment Variables**: The project reads `GEMINI_API_KEY` directly from the `api.env` file located in the Capstone root directory.

### Installed Dependencies
All dependencies are locked in `pyproject.toml` and installable via `uv sync`. Key additions for this project:
- `mcp`: Model Context Protocol SDK
- `google-genai`: Google's Gemini SDK
- `langgraph`: DAG execution orchestrator
- `pydantic`: Input validation for MCP tools
- `python-dotenv`: Local environment loading


## Quick Start

Install `agents-cli` and its skills if not already installed:

```bash
uvx google-agents-cli setup
```

Install required packages:

```bash
agents-cli install
```

Test the agent with a local web server:

```bash
## How To Use This Agent

There are several ways to interact with the Enterprise Query Optimization Agent locally:

### 1. Interactive Playground (Recommended for Demos)
The project includes a built-in interactive web UI for testing the ADK graph. Simply start the playground:
```bash
agents-cli playground
```
Once it opens in your browser, type a raw SQL query into the chat. The agent will run the sanitization and optimization graph, responding with the optimized output.

### 2. Programmatic Execution in Code
You can import the compiled ADK graph directly into any Python script and invoke it with a state payload:

```python
from app.agent import app

response = app.invoke({
    "raw_query": "SELECT * FROM users",
    "sanitized_query": None,
    "optimized_query": None,
    "query_history": [],
    "session_logs": [],
    "current_errors": [],
    "execution_status": "INITIALIZED"
})
print(response["optimized_query"])
```

## Running the Unit Tests

We have implemented rigorous, production-grade unit tests using `pytest`. These test the end-to-end execution of the ADK graph across both valid and malicious injection payloads.

Execute the test suite locally:
```bash
uv run pytest tests/unit/test_agent.py -v
```

## Commands

| Command              | Description                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------------- |
| `agents-cli install` | Install dependencies using uv                                                         |
| `agents-cli playground` | Launch local development environment                                                  |
| `agents-cli lint`    | Run code quality checks                                                               |
| `agents-cli eval`    | Evaluate agent behavior (generate, grade, analyze, and more — see `agents-cli eval --help`) |
| `uv run pytest tests/unit tests/integration` | Run unit and integration tests                                                        |

##  Project Management

| Command | What It Does |
|---------|--------------|
| `agents-cli scaffold enhance` | Add CI/CD pipelines and Terraform infrastructure |
| `agents-cli infra cicd` | One-command setup of entire CI/CD pipeline + infrastructure |
| `agents-cli scaffold upgrade` | Auto-upgrade to latest version while preserving customizations |

---

## Development

Edit your agent logic in `app/agent.py` and test with `agents-cli playground` - it auto-reloads on save.

## Deployment

```bash
gcloud config set project <your-project-id>
agents-cli deploy
```

To add CI/CD and Terraform, run `agents-cli scaffold enhance`.
To set up your production infrastructure, run `agents-cli infra cicd`.

## Observability

Built-in telemetry exports to Cloud Trace, BigQuery, and Cloud Logging.
