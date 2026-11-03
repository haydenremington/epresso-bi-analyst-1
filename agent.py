"""Dispatcher and assistant router for E-Presso analytical tools."""

from __future__ import annotations

import json
import os
import time
import analytics
from google import genai
from google.genai import types

# ---------------------------------------------------------
# Master Registry of Approved Tools
# ---------------------------------------------------------
APPROVED_TOOLS = {
    "get_total": analytics.get_total,
    "group_total": analytics.group_total,
    "data_quality_report": analytics.data_quality_report,
}


def dispatch_tool(tool_name: str, arguments: dict, df) -> dict:
    """Executes an approved analytical function and returns the standardized ToolResult
    alongside call audit metadata. Free-form code execution is strictly
    prohibited.
    """
    if tool_name not in APPROVED_TOOLS:
        error_res = analytics._error(
            tool=tool_name,
            message=(
                f"Tool '{tool_name}' is not in the approved analytical tools"
                f" registry. Permitted tools: {list(APPROVED_TOOLS.keys())}"
            ),
        )
        return {
            "tool_name": tool_name,
            "arguments": arguments,
            "raw_result": error_res.to_dict(),
            "status": "rejected",
        }

    tool_func = APPROVED_TOOLS[tool_name]

    try:
        result: analytics.ToolResult = tool_func(df, **arguments)
        raw_dict = result.to_dict()
        status = "error" if result.error else "success"
    except Exception as e:
        raw_dict = analytics._error(
            tool_name, f"Execution failure: {str(e)}"
        ).to_dict()
        status = "exception"

    return {
        "tool_name": tool_name,
        "arguments": arguments,
        "raw_result": raw_dict,
        "status": status,
    }


# ---------------------------------------------------------
# Option B Baseline: Rules-Based Deterministic Router
# ---------------------------------------------------------
def rules_based_router(query: str, df) -> tuple[str, dict, str]:
    """Fallback router: maps standard business questions to approved tools deterministically."""
    q = query.lower()

    if "total revenue" in q or "how much revenue" in q or "overall sales" in q:
        args = {"value_col": "Revenue"}
        call_log = dispatch_tool("get_total", args, df)
        res = call_log["raw_result"]

        findings = (
            f"Scope: {res['scope']}. Total
