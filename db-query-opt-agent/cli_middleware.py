"""
Enterprise Database Middleware - Interactive CLI
================================================
Interactive terminal loop for manual query testing.
Submits raw SQL to the compiled LangGraph agent and prints a formatted result.

Usage:
    uv run python cli_middleware.py

Commands at the prompt:
    Any SQL string   — run through the sanitize/optimize/route graph
    exit / quit      — shut down cleanly
    Ctrl-C           — force stop
"""

import os
import sys
import time
from pathlib import Path
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Portable env loading — walk up from this file's location to find api.env
# ---------------------------------------------------------------------------
def _find_and_load_env(filename: str = "api.env") -> None:
    current = Path(__file__).resolve().parent
    for _ in range(5):
        candidate = current / filename
        if candidate.is_file():
            load_dotenv(candidate)
            return
        current = current.parent

_find_and_load_env()

from app.agent import app  # noqa: E402  (import after env is loaded)


def print_banner() -> None:
    separator = "=" * 68
    print(f"\n{separator}")
    print("  ENTERPRISE DATABASE MIDDLEWARE INTERCEPTOR")
    print(f"  Engine: Gemini 2.5 Flash  |  Protocol: MCP Secure")
    print(f"  Type your SQL query and press Enter.")
    print(f"  Type 'exit' or 'quit' to stop.")
    print(f"{separator}\n")


def build_initial_state(raw_query: str) -> dict:
    return {
        "raw_query": raw_query,
        "sanitized_query": None,
        "optimized_query": None,
        "query_history": [],
        "session_logs": [],
        "current_errors": [],
        "execution_status": "INITIALIZED",
    }


def run() -> None:
    if not os.getenv("GEMINI_API_KEY"):
        print(
            "WARNING: GEMINI_API_KEY not found in api.env.\n"
            "The optimizer will run in passthrough mode — queries will be returned as-is.\n"
        )

    print_banner()

    while True:
        try:
            raw = input("DB_MIDDLEWARE > ").strip()
        except KeyboardInterrupt:
            print("\nShutting down. Bye.")
            break

        if not raw:
            continue

        if raw.lower() in ("exit", "quit"):
            print("Safe exit.")
            break

        print("  Intercepting payload...")
        time.sleep(0.2)
        print("  Running graph checkpoints...\n")

        state = app.invoke(build_initial_state(raw))
        status = state.get("execution_status")

        if status == "SUCCESS":
            print("-" * 68)
            print("  STATUS : SUCCESS")
            print(f"  Input  : {state['raw_query']}")
            print(f"  Output : {state['optimized_query']}")
            
            reasoning = None
            for log in reversed(state.get("session_logs", [])):
                if log.startswith("Optimizer reasoning: "):
                    reasoning = log[len("Optimizer reasoning: "):]
                    break
            if reasoning:
                print(f"  Why    : {reasoning}")
                
            print("-" * 68 + "\n")

        elif status == "SANITIZATION_FAILED":
            print("!" * 68)
            print("  STATUS : SECURITY ALERT — execution blocked")
            print(f"  Input  : {state['raw_query']}")
            print(f"  Errors : {state['current_errors']}")
            print("!" * 68 + "\n")

        else:
            print(f"  STATUS : {status}")
            if state["current_errors"]:
                print(f"  Errors : {state['current_errors']}")
            print()


if __name__ == "__main__":
    run()