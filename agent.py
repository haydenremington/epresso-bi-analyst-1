"""Dispatcher and assistant router for E-Presso analytical tools."""

from __future__ import annotations

import analytics


# Master registry of approved tools
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
    # Execute the function using the loaded dataframe
    result: analytics.ToolResult = tool_func(df, **arguments)
    raw_dict = result.to_dict()
    status = "error" if result.error else "success"
  except Exception as e:
    raw_dict = analytics._error(tool_name, f"Execution failure: {str(e)}").to_dict()
    status = "exception"

  return {
      "tool_name": tool_name,
      "arguments": arguments,
      "raw_result": raw_dict,
      "status": status,
  }


def rules_based_router(query: str, df) -> tuple[str, dict, str]:
  """Fallback/baseline router: maps standard business questions to approved tools

  without invoking external language models.
  """
  q = query.lower()

  # 1. Total revenue inquiries
  if "total revenue" in q or "how much revenue" in q or "overall sales" in q:
    args = {"value_col": "Revenue"}
    call_log = dispatch_tool("get_total", args, df)
    res = call_log["raw_result"]

    findings = (
        f"Scope: {res['scope']}. Total revenue calculated from"
        f" {res['rows_used']:,} records is ${res['value']:,.2f}."
    )
    interpretation = (
        "This represents gross top-line transaction volume across the active"
        " scope."
    )
    caveats = (
        " ".join(res["caveats"])
        if res["caveats"]
        else "No data anomalies reported."
    )
    next_steps = (
        "Revenue is not profit. To evaluate financial health, evaluate COGS and"
        " store operating expenses."
    )

    answer = (
        f"### Findings\n{findings}\n\n### Interpretation\n{interpretation}\n\n###"
        f" Caveats & Limitations\n{caveats}\n\n### Next Steps\n{next_steps}"
    )
    return answer, call_log, "rules-based"

  # 2. Sales channel comparison
  elif "channel" in q or "website" in q or "brick-and-mortar" in q or "online" in q:
    channel_col = next(
        (c for c in df.columns if c.lower() in ["channel", "storetype", "location"]),
        None,
    )
    if not channel_col:
      return "Channel column not detected in dataset.", {}, "error"

    args = {"value_col": "Revenue", "group_col": channel_col}
    call_log = dispatch_tool("group_total", args, df)
    res = call_log["raw_result"]

    breakdown_text = "\n".join(
        [f"- **{k}**: ${v:,.2f}" for k, v in res["value"].items()]
    )
    findings = f"Scope: All channels. Revenue breakdown:\n{breakdown_text}"
    interpretation = (
        "Compares revenue generated through direct digital vs physical retail"
        " channels."
    )
    next_steps = (
        "Evaluate fulfillment costs and return rates across channels before"
        " shifting marketing spend."
    )

    answer = (
        f"### Findings\n{findings}\n\n### Interpretation\n{interpretation}\n\n###"
        f" Next Steps\n{next_steps}"
    )
    return answer, call_log, "rules-based"

  # 3. Annual progression / trends
  elif "year" in q or "annual" in q or "growth" in q or "trend" in q:
    args = {"value_col": "Revenue", "group_col": "Year"}
    call_log = dispatch_tool("group_total", args, df)
    res = call_log["raw_result"]

    breakdown_text = "\n".join(
        [f"- **{k}**: ${v:,.2f}" for k, v in res["value"].items()]
    )
    findings = f"Scope: Annual progression (2025–2029):\n{breakdown_text}"
    interpretation = (
        "Reflects historical trajectory over the five-year recorded window."
    )
    next_steps = (
        "Perform regression or run time-series forecasting to establish future"
        " inventory requirements."
    )

    answer = (
        f"### Findings\n{findings}\n\n### Interpretation\n{interpretation}\n\n###"
        f" Next Steps\n{next_steps}"
    )
    return answer, call_log, "rules-based"

  # 4. Data Quality / Missing data
  elif "quality" in q or "missing" in q or "duplicates" in q or "null" in q:
    call_log = dispatch_tool("data_quality_report", {}, df)
    res = call_log["raw_result"]

    findings = (
        f"Analyzed {res['value']['rows']:,} rows. Duplicate rows:"
        f" {res['value']['duplicate_rows']}. Columns with missing values:"
        f" {res['value']['columns_with_missing']}."
    )
    interpretation = (
        "Data hygiene assessment across the primary loaded table."
    )
    next_steps = (
        "Audit survey response collection workflows to address any null fields."
    )

    answer = (
        f"### Findings\n{findings}\n\n### Interpretation\n{interpretation}\n\n###"
        f" Next Steps\n{next_steps}"
    )
    return answer, call_log, "rules-based"

  # 5. Unsupported question boundary handling
  else:
    fallback_call = {
        "tool_name": "none",
        "arguments": {},
        "raw_result": {"error": "Question not mapped to an approved tool."},
        "status": "unsupported",
    }
    answer = (
        "### Findings\nI cannot answer this question with the available data and"
        " approved tools.\n\n### Supported Questions\nI can answer questions"
        " regarding:\n- Overall total revenue (`get_total`)\n- Revenue by sales"
        " channel (`group_total`)\n- Annual revenue trends (`group_total`)\n- Data"
        " quality and missing records (`data_quality_report`)\n\n### Next"
        " Steps\nNo business recommendation is supported by this inquiry."
    )
    return answer, fallback_call, "unsupported"
