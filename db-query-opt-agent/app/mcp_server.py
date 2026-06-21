"""
Enterprise Database Middleware - MCP Tool Server
================================================
Exposes two schema-inspection tools over the MCP stdio transport:
  - fetch_database_schema : returns column and index info for a named table
  - explain_query_plan    : returns a simulated EXPLAIN ANALYZE output

Both tools validate their inputs with Pydantic before any lookup occurs.
No database credentials are handled here — credentials stay outside the LLM boundary.

Integration (add to mcp_config.json):
    {
      "mcpServers": {
        "db_optimizer": {
          "command": "uv",
          "args": ["run", "python", "-m", "app.mcp_server"]
        }
      }
    }
"""

import asyncio
import os
import re
import sqlite3
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from pydantic import BaseModel, Field, field_validator

server = Server("enterprise-db-mcp-server")

# ---------------------------------------------------------------------------
# Input Schemas
# ---------------------------------------------------------------------------

class FetchDatabaseSchemaArgs(BaseModel):
    table_name: str = Field(..., description="Name of the table to inspect.")

    @field_validator("table_name")
    @classmethod
    def only_safe_identifiers(cls, v: str) -> str:
        """Allow only alphanumeric characters and underscores."""
        if not re.fullmatch(r"[a-zA-Z0-9_]+", v):
            raise ValueError(
                "Invalid table name. Only letters, digits, and underscores are allowed."
            )
        return v


class ExplainQueryPlanArgs(BaseModel):
    query: str = Field(..., description="A single SELECT query to analyze.")

    @field_validator("query")
    @classmethod
    def must_be_single_select(cls, v: str) -> str:
        """Block multi-statement payloads and non-SELECT queries at the tool boundary."""
        stripped = v.strip()
        # Multi-statement detection: remove trailing semicolon, check for remaining
        if ";" in stripped.rstrip(";"):
            raise ValueError("Multi-statement queries are not permitted.")
        if not stripped.upper().startswith(("SELECT", "EXPLAIN")):
            raise ValueError("Only SELECT queries are accepted for plan analysis.")
        return stripped


# ---------------------------------------------------------------------------
# Database connection for schema tool
# ---------------------------------------------------------------------------
DB_PATH = os.path.join(os.path.dirname(__file__), "demo.db")


# ---------------------------------------------------------------------------
# Tool Handlers
# ---------------------------------------------------------------------------

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="fetch_database_schema",
            description="Fetch column definitions and index layout for a specific table.",
            inputSchema=FetchDatabaseSchemaArgs.model_json_schema(),
        ),
        Tool(
            name="explain_query_plan",
            description="Return a simulated EXPLAIN ANALYZE output for a SELECT query.",
            inputSchema=ExplainQueryPlanArgs.model_json_schema(),
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
    args = arguments or {}

    if name == "fetch_database_schema":
        try:
            validated = FetchDatabaseSchemaArgs(**args)
        except Exception as exc:
            return [TextContent(type="text", text=f"Validation error: {exc}")]

        if not os.path.exists(DB_PATH):
            return [TextContent(type="text", text="Database file not found. Run seed_db.py first.")]

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Verify table exists and get columns
        cursor.execute(f"PRAGMA table_info({validated.table_name})")
        columns_info = cursor.fetchall()
        
        if not columns_info:
            conn.close()
            return [TextContent(type="text", text=f"Table '{validated.table_name}' not found.")]
            
        columns = {row[1]: row[2] for row in columns_info}
        
        # Get indexes
        cursor.execute(f"PRAGMA index_list({validated.table_name})")
        indexes_info = cursor.fetchall()
        indexes = []
        for idx in indexes_info:
            indexes.append(idx[1])
            
        conn.close()

        lines = [f"Table: {validated.table_name}"]
        lines.append("Columns:")
        for col, dtype in columns.items():
            lines.append(f"  {col}  {dtype}")
        lines.append("Indexes:")
        for idx in indexes:
            lines.append(f"  {idx}")
        if not indexes:
            lines.append("  (None)")
        return [TextContent(type="text", text="\n".join(lines))]

    elif name == "explain_query_plan":
        try:
            validated = ExplainQueryPlanArgs(**args)
        except Exception as exc:
            return [TextContent(type="text", text=f"Validation error: {exc}")]

        upper = validated.query.upper()
        if "USERS" in upper:
            plan = "Index Scan using idx_email on users  (cost=0.29..8.31 rows=1)"
        elif "ORDERS" in upper:
            plan = "Seq Scan on orders  (cost=0.00..154.00 rows=10000) -- Missing index on 'status'"
        elif "METRICS" in upper:
            plan = "Seq Scan on metrics  (cost=0.00..210.00 rows=50000) -- Consider partitioning"
        else:
            plan = "Seq Scan  (cost=0.00..0.00 rows=0)"

        return [TextContent(type="text", text=f"EXPLAIN ANALYZE\n---------------\n{plan}")]

    else:
        raise ValueError(f"Unknown tool: {name}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())
