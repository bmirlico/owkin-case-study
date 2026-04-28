import json
from typing import Any

import pandas as pd


def get_targets(cancer_name: str, df: pd.DataFrame) -> list[str]:
    """Return the list of genes associated with a given cancer indication.

    Matching is case-insensitive on cancer_indication so the LLM does not have
    to guess the exact casing used in the CSV.
    """
    if not isinstance(cancer_name, str):
        return []
    needle = cancer_name.strip().lower()
    if not needle:
        return []
    matches = df[df["cancer_indication"].astype(str).str.lower() == needle]
    return matches["gene"].astype(str).tolist()


def get_expressions(genes: list[str], df: pd.DataFrame) -> dict[str, float]:
    """Return median expression values for the given list of genes.

    Returns {gene: median_value}. If a gene appears in multiple rows (e.g.
    associated with several cancers), the last row in the CSV wins — this
    mirrors the reference dict(zip(...)) semantics from the brief.
    """
    if not isinstance(genes, list) or not genes:
        return {}
    subset = df[df["gene"].isin(genes)]
    return {str(g): float(v) for g, v in zip(subset["gene"], subset["median_value"])}


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_targets",
        "description": (
            "Returns the list of gene names (targets) associated with a given cancer "
            "indication, based on the in-memory oncology dataset. Use this when the "
            "user asks which genes are involved in a particular cancer, or as the "
            "first step before querying expression values for that cancer. "
            "The cancer_name should match one of the available cancer types listed "
            "in the system prompt; matching is case-insensitive."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "cancer_name": {
                    "type": "string",
                    "description": (
                        "Name of the cancer indication (e.g. 'lung', 'breast', "
                        "'esophageal'). Must be one of the values listed in the "
                        "system prompt."
                    ),
                }
            },
            "required": ["cancer_name"],
        },
    },
    {
        "name": "get_expressions",
        "description": (
            "Returns the median expression value for each of the provided genes, "
            "as a {gene: median_value} mapping. Use this to answer questions about "
            "expression levels. To answer 'what is the median expression of genes "
            "involved in <cancer>?', first call get_targets(cancer_name) to obtain "
            "the gene list, then pass that list to this tool."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "genes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of gene symbols, typically the output of get_targets."
                    ),
                }
            },
            "required": ["genes"],
        },
    },
]


def dispatch_tool(name: str, tool_input: dict[str, Any], df: pd.DataFrame) -> str:
    """Run the named tool with the given input and return a JSON string.

    On bad input or unknown tools, returns a JSON-serialised error payload so
    the model can read it and recover (e.g. retry with a corrected argument).
    """
    try:
        if name == "get_targets":
            cancer_name = tool_input.get("cancer_name")
            if not isinstance(cancer_name, str):
                return json.dumps(
                    {"error": "get_targets requires 'cancer_name' as a string."}
                )
            return json.dumps(get_targets(cancer_name, df))

        if name == "get_expressions":
            genes = tool_input.get("genes")
            if not isinstance(genes, list) or not all(isinstance(g, str) for g in genes):
                return json.dumps(
                    {"error": "get_expressions requires 'genes' as a list of strings."}
                )
            return json.dumps(get_expressions(genes, df))

        return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as exc:  # noqa: BLE001 — surface to the model so it can recover
        return json.dumps({"error": f"Tool {name} raised: {exc!s}"})
