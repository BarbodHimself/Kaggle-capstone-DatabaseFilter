"""
Enterprise Database Middleware - Query Optimization Agent
=========================================================
Core LangGraph DAG implementing the three-node state machine:
  sanitize_input_node -> optimize_query_node -> routing_node

Environment:
    GEMINI_API_KEY: Loaded from api.env in the project root directory.
    If the key is missing, the optimize node falls back to a passthrough.
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from google import genai
from langgraph.graph import StateGraph, END

# ---------------------------------------------------------------------------
# Environment loading — portable walk-up search for api.env
# ---------------------------------------------------------------------------
# Search from the project root upward so this works regardless of where
# the repo is cloned. No hardcoded user or system paths.
def _find_and_load_env(filename: str = "api.env") -> None:
    """Walk up the directory tree from this file's location to find api.env."""
    current = Path(__file__).resolve().parent
    for _ in range(5):  # max 5 levels up
        candidate = current / filename
        if candidate.is_file():
            load_dotenv(candidate)
            return
        current = current.parent

_find_and_load_env()

api_key = os.environ.get("GEMINI_API_KEY")
client = None
if api_key:
    client = genai.Client(api_key=api_key)

logger = logging.getLogger(__name__)

# ==============================================================================
# Database Session State
# ==============================================================================
class DatabaseSessionState(dict):
    """
    TypedDict-compatible state container passed through every graph node.
    Fields:
        raw_query        : The original, unmodified query from the caller.
        sanitized_query  : Set by sanitize_input_node if the query passes all checks.
        optimized_query  : Set by optimize_query_node after LLM rewrite.
        query_history    : Append-only log of every query string seen this session.
        session_logs     : Human-readable execution trace for debugging.
        current_errors   : List of error strings. Non-empty means execution was blocked.
        execution_status : One of INITIALIZED | SANITIZED | OPTIMIZED | SUCCESS
                           | SANITIZATION_FAILED | OPTIMIZATION_FAILED
    """


# ==============================================================================
# Node 1 — Sanitize Input
# ==============================================================================
def sanitize_input_node(state: dict) -> dict:
    """
    Security firewall. Runs before any AI processing.

    Blocks:
        - Destructive DDL keywords: DROP, DELETE, TRUNCATE, ALTER, GRANT, REVOKE
        - Multi-statement stacking via semicolons

    On any match: populates current_errors, sets execution_status to
    SANITIZATION_FAILED, and returns. The optimize node will skip itself.
    """
    logger.info("sanitize_input_node: start")
    raw_query = state.get("raw_query", "").strip()
    state["session_logs"].append(f"[sanitize] Received: {raw_query}")

    destructive_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER", "GRANT", "REVOKE"]
    upper_query = raw_query.upper()
    errors = []

    for keyword in destructive_keywords:
        if re.search(r"\b" + keyword + r"\b", upper_query):
            errors.append(f"Security Alert: Destructive keyword '{keyword}' is not permitted.")

    # Detect statement stacking: strip trailing semicolon, then check for any remaining
    if ";" in raw_query.rstrip(";"):
        errors.append("Security Alert: Multi-statement queries are forbidden.")

    if errors:
        state["current_errors"].extend(errors)
        state["execution_status"] = "SANITIZATION_FAILED"
        state["session_logs"].append("[sanitize] FAILED — query blocked.")
    else:
        state["sanitized_query"] = raw_query
        state["execution_status"] = "SANITIZED"
        state["query_history"].append(raw_query)
        state["session_logs"].append("[sanitize] PASSED — query forwarded to optimizer.")

    return state


# ==============================================================================
# Node 2 — Optimize Query
# ==============================================================================
def optimize_query_node(state: dict) -> dict:
    """
    Calls Gemini 2.5 Flash to rewrite the sanitized query.

    Skips itself if execution_status is not SANITIZED (i.e. sanitization failed).
    Falls back to a passthrough if GEMINI_API_KEY is not set.
    """
    logger.info("optimize_query_node: start")
    state["session_logs"].append("[optimize] Starting optimization phase.")

    if state["execution_status"] != "SANITIZED":
        state["session_logs"].append("[optimize] Skipped — prior stage did not pass.")
        return state

    query = state["sanitized_query"]

    try:
        prompt = (
            "You are an expert enterprise database query optimizer. "
            "Analyze the following SQL query. Identify any bottlenecks such as "
            "missing indexes, N+1 subquery loops, implicit joins, or full table scans. "
            "Return a strict JSON object with two fields: 'optimized_query' (containing the raw rewritten SQL) "
            "and 'reasoning' (1-3 sentences on what was changed and why). "
            "Do not include any other text.\n\n"
            f"Query:\n{query}"
        )

        if client:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            raw_text = response.text.strip()
            if raw_text.startswith("```json"):
                raw_text = raw_text[7:]
            elif raw_text.startswith("```"):
                raw_text = raw_text[3:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()
            
            try:
                parsed = json.loads(raw_text)
                optimized = parsed.get("optimized_query", query)
                reasoning = parsed.get("reasoning", "No reasoning provided.")
                state["session_logs"].append(f"Optimizer reasoning: {reasoning}")
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to parse JSON from optimizer, falling back to passthrough: {e}")
                optimized = query
        else:
            # Passthrough — no API key available
            logger.warning("optimize_query_node: GEMINI_API_KEY not set, using passthrough.")
            optimized = query

        state["optimized_query"] = optimized
        state["query_history"].append(optimized)
        state["execution_status"] = "OPTIMIZED"
        state["session_logs"].append("[optimize] SUCCESS.")

    except Exception as exc:
        msg = f"[optimize] FAILED: {exc}"
        state["current_errors"].append(msg)
        state["execution_status"] = "OPTIMIZATION_FAILED"
        state["session_logs"].append(msg)
        logger.error(msg)

    return state


# ==============================================================================
# Node 3 — Routing
# ==============================================================================
def routing_node(state: dict) -> dict:
    """
    Final evaluation node. Maps any *_FAILED status to an error route.
    All other statuses become SUCCESS and the optimized query is returned.
    """
    logger.info("routing_node: start")
    status = state["execution_status"]
    state["session_logs"].append(f"[route] Evaluating status: {status}")

    if "FAILED" in status:
        state["session_logs"].append("[route] ERROR — query will not be forwarded.")
    else:
        state["execution_status"] = "SUCCESS"
        state["session_logs"].append("[route] SUCCESS — optimized query ready.")

    return state


# ==============================================================================
# Graph Assembly
# ==============================================================================
_workflow = StateGraph(dict)
_workflow.add_node("sanitize", sanitize_input_node)
_workflow.add_node("optimize", optimize_query_node)
_workflow.add_node("route", routing_node)

_workflow.set_entry_point("sanitize")
_workflow.add_edge("sanitize", "optimize")
_workflow.add_edge("optimize", "route")
_workflow.add_edge("route", END)

# Public interface — import this object to invoke the graph
app = _workflow.compile()


# ==============================================================================
# Convenience wrapper for scripted or CLI use
# ==============================================================================
def process_query(raw_query: str) -> dict:
    """Construct a fresh state and invoke the compiled graph."""
    result = app.invoke({
        "raw_query": raw_query,
        "sanitized_query": None,
        "optimized_query": None,
        "query_history": [],
        "session_logs": [],
        "current_errors": [],
        "execution_status": "INITIALIZED",
    })
    
    if os.environ.get("SAVE_RUN_HISTORY", "True").lower() in ("true", "1", "yes", "y", "t"):
        try:
            history_path = Path(__file__).resolve().parent / "run_history.jsonl"
            with open(history_path, "a") as f:
                f.write(json.dumps(result) + "\n")
        except Exception as e:
            logger.error(f"Failed to write run history: {e}")
            
    return result


if __name__ == "__main__":
    import sys
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "SELECT id, email FROM users WHERE id = 1"
    result = process_query(query)
    print(f"Status : {result['execution_status']}")
    print(f"Output : {result.get('optimized_query')}")
    if result["current_errors"]:
        print(f"Errors : {result['current_errors']}")
