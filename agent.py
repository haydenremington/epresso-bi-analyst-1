"""Dispatcher and assistant router for E-Presso analytical tools."""

from __future__ import annotations

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
            f"Scope: {res['scope']}. Total revenue across {res['rows_used']:,}"
            f" transactions is ${res['value']:,.2f}."
        )
        interpretation = (
            "Represents gross top-line transaction volume across the active dataset."
        )
        caveats = (
            " ".join(res["caveats"])
            if res["caveats"]
            else "No data anomalies reported."
        )
        next_steps = (
            "Revenue is not profit. To evaluate financial sustainability, audit"
            " COGS and store operating expenses."
        )

        answer = (
            f"### Findings\n{findings}\n\n### Interpretation\n{interpretation}\n\n###"
            f" Caveats & Limitations\n{caveats}\n\n### Next Steps\n{next_steps}"
        )
        return answer, call_log, "rules-based"

    elif (
        "channel" in q
        or "storetype" in q
        or "website" in q
        or "brick-and-mortar" in q
    ):
        channel_col = next(
            (c for c in df.columns if c.lower() in ["channel", "storetype"]),
            "StoreType",
        )
        args = {"value_col": "Revenue", "group_col": channel_col}
        call_log = dispatch_tool("group_total", args, df)
        res = call_log["raw_result"]

        breakdown_text = "\n".join(
            [f"- **{k}**: ${v:,.2f}" for k, v in res["value"].items()]
        )
        findings = f"Scope: All channels. Revenue breakdown:\n{breakdown_text}"
        interpretation = (
            "Contrasts revenue generated through digital vs physical retail"
            " channels."
        )
        caveats = (
            " ".join(res["caveats"])
            if res["caveats"]
            else "Channel definitions rely on transaction store attributes."
        )
        next_steps = (
            "Evaluate customer fulfillment costs and returns before adjusting"
            " marketing spend."
        )

        answer = (
            f"### Findings\n{findings}\n\n### Interpretation\n{interpretation}\n\n###"
            f" Caveats & Limitations\n{caveats}\n\n### Next Steps\n{next_steps}"
        )
        return answer, call_log, "rules-based"

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
        caveats = (
            " ".join(res["caveats"])
            if res["caveats"]
            else "Revenue does not factor in inflation."
        )
        next_steps = (
            "Run capacity planning and time-series forecasting to establish future"
            " inventory targets."
        )

        answer = (
            f"### Findings\n{findings}\n\n### Interpretation\n{interpretation}\n\n###"
            f" Caveats & Limitations\n{caveats}\n\n### Next Steps\n{next_steps}"
        )
        return answer, call_log, "rules-based"

    elif "quality" in q or "missing" in q or "duplicates" in q or "null" in q:
        call_log = dispatch_tool("data_quality_report", {}, df)
        res = call_log["raw_result"]

        findings = (
            f"Analyzed {res['value']['rows']:,} rows. Duplicate rows:"
            f" {res['value']['duplicate_rows']}. Missing columns:"
            f" {res['value']['columns_with_missing']}."
        )
        interpretation = (
            "Data hygiene assessment confirms transaction integrity across tables."
        )
        caveats = (
            " ".join(res["caveats"])
            if res["caveats"]
            else "Report reflects currently loaded memory table."
        )
        next_steps = (
            "Audit survey intake forms to reduce null fields in customer feedback"
            " tables."
        )

        answer = (
            f"### Findings\n{findings}\n\n### Interpretation\n{interpretation}\n\n###"
            f" Caveats & Limitations\n{caveats}\n\n### Next Steps\n{next_steps}"
        )
        return answer, call_log, "rules-based"

    else:
        fallback_call = {
            "tool_name": "none",
            "arguments": {},
            "raw_result": {"error": "Question not mapped to an approved tool."},
            "status": "unsupported",
        }
        answer = (
            "### Findings\nI cannot answer this question with the available data"
            " and approved tools. The system does not contain profit, cost, or"
            " margin metrics.\n\n### Supported Questions\n- Overall total revenue"
            " (`get_total`)\n- Revenue by sales channel (`group_total`)\n- Annual"
            " revenue trends (`group_total`)\n- Data quality and missing records"
            " (`data_quality_report`)\n\n### Caveats & Limitations\nRevenue is not"
            " profit.\n\n### Next Steps\nIntegrate COGS and operational expenditure"
            " records to answer profitability questions."
        )
        return answer, fallback_call, "unsupported"


# ---------------------------------------------------------
# Option A: Gemini LLM Function-Calling Router
# ---------------------------------------------------------
TOOL_SCHEMAS = [
    types.FunctionDeclaration(
        name="get_total",
        description=(
            "Calculates the total sum of a numeric column (such as 'Revenue')"
            " across the entire table or within a filtered scope."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "value_col": types.Schema(
                    type="STRING",
                    description="The numeric column to sum. Defaults to 'Revenue'.",
                ),
            },
            required=["value_col"],
        ),
    ),
    types.FunctionDeclaration(
        name="group_total",
        description=(
            "Calculates the sum of a numeric column grouped by a dimension"
            " column (e.g. 'Year', 'StoreType', 'Product')."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "value_col": types.Schema(
                    type="STRING",
                    description="The numeric column to sum (e.g. 'Revenue').",
                ),
                "group_col": types.Schema(
                    type="STRING",
                    description="The column to group by (e.g. 'Year', 'StoreType', 'Product').",
                ),
            },
            required=["value_col", "group_col"],
        ),
    ),
    types.FunctionDeclaration(
        name="data_quality_report",
        description=(
            "Audits the dataset for row counts, duplicate entries, and missing"
            " null values per column."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={},
        ),
    ),
]

SYSTEM_PROMPT = """
You are an executive business intelligence assistant for the E-Presso retail brand.
You analyze data ONLY by invoking the approved analytical tools provided.

STRICT CONTRACT RULES:
1. You may never fabricate, assume, or guess numerical data. Every figure you mention MUST come directly from the tool's raw result payload.
2. If a query asks for information not calculable with the available tools (e.g., store profit, employee salaries, future projections), do NOT invent figures. Clearly refuse and state that cost/profit data is unavailable and revenue is not profit.
3. Every final response MUST follow this exact Markdown structure:
### Findings
State the specific numeric findings returned by the tool, citing the rows used and parameters.

### Interpretation
Contextualize what these figures mean for the business.

### Caveats & Limitations
State any caveats explicitly returned by the tool (including 'Revenue is not profit' and data completeness limitations).

### Next Steps
Provide concrete operational or strategic follow-ups based on the data.
"""

# Primary and fallback model endpoints
PRIMARY_MODEL = "gemini-3.8-flash"
FALLBACK_MODEL = "gemini-3.6-flash"


def _generate_with_retry(client, model_name: str, **kwargs):
    """Attempts generation with a short retry on 503 high demand before falling back."""
    for attempt in range(2):
        try:
            return client.models.generate_content(
                model=model_name, **kwargs
            ), model_name
        except Exception as e:
            if "503" in str(e) and attempt == 0:
                time.sleep(1.5)  # Brief pause on temporary spike
                continue
            raise e


def llm_router(query: str, df, api_key: str) -> tuple[str, dict, str]:
    """Routes user queries through Gemini using tool declarations,
    executes the chosen tool through dispatch_tool, and feeds the output back for
    narration.
    """
    import json

    client = genai.Client(api_key=api_key)
    tool = types.Tool(function_declarations=TOOL_SCHEMAS)

    try:
        # 1. First model call: determine tool use
        try:
            response, active_model = _generate_with_retry(
                client,
                PRIMARY_MODEL,
                contents=query,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    tools=[tool],
                    temperature=0.1,
                ),
            )
        except Exception as err:
            if "503" in str(err) or "404" in str(err):
                response, active_model = _generate_with_retry(
                    client,
                    FALLBACK_MODEL,
                    contents=query,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        tools=[tool],
                        temperature=0.1,
                    ),
                )
            else:
                raise err

        function_calls = response.function_calls
        if not function_calls:
            fallback_log = {
                "tool_name": "none",
                "arguments": {},
                "raw_result": {"message": "Direct refusal or clarification."},
                "status": "unsupported",
            }
            return response.text, fallback_log, f"LLM Direct ({active_model})"

        # 2. Execute local function via dispatcher
        call = function_calls[0]
        tool_name = call.name
        tool_args = dict(call.args) if call.args else {}

        call_log = dispatch_tool(tool_name, tool_args, df)

        # 3. Feed tool response back to model as clean text payload (avoids SDK role conflicts)
        tool_payload_str = json.dumps(call_log["raw_result"], indent=2)
        narration_prompt = (
            f"User Question: {query}\n\n"
            f"Executed Tool: {tool_name}\n"
            f"Raw Tool Result Payload:\n{tool_payload_str}\n\n"
            "Format the response using the required Markdown sections (Findings, Interpretation, Caveats & Limitations, Next Steps)."
        )

        narration, _ = _generate_with_retry(
            client,
            active_model,
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=narration_prompt)],
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.1,
            ),
        )

        return narration.text, call_log, f"LLM Function Call ({active_model})"

    except Exception as e:
        err_log = {
            "tool_name": "error",
            "arguments": {},
            "raw_result": {"exception": str(e)},
            "status": "exception",
        }
        return f"Error contacting Gemini service: {e}", err_log, "LLM Error"
