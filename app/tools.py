import json
from typing import Any

import pandas as pd


def get_targets(cancer_name: str, df: pd.DataFrame) -> list[str]:
    """Return a list of genes for a given cancer type."""
    return df[df["cancer_indication"] == cancer_name]["gene"].tolist()


def get_expressions(
    genes: list[str], cancer_name: str, df: pd.DataFrame
) -> dict[str, float]:
    """Return the median values for the given list of genes, scoped to a cancer.

    The cancer_name argument is a deliberate deviation from the brief's
    reference signature (`get_expressions(genes)`). With the real CSV, several
    genes (TP53, KRAS, BRCA1/2, PIK3CA, ...) appear in multiple cancer
    indications, and the reference `dict(zip(...))` would silently collapse
    duplicates and return values from the wrong cancer. Scoping by
    cancer_name removes that ambiguity. See README → "Deviation from the
    brief".
    """
    subset = df[(df["gene"].isin(genes)) & (df["cancer_indication"] == cancer_name)]
    return dict(zip(subset["gene"], subset["median_value"]))


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "get_targets",
        "description": (
            "Returns the list of gene names (targets) associated with a given cancer "
            "indication, based on the in-memory oncology dataset. Use this when the "
            "user asks which genes are involved in a particular cancer, or as the "
            "first step before querying expression values for that cancer. "
            "The cancer_name MUST match one of the available cancer types listed "
            "in the system prompt verbatim (lowercase, no extra whitespace)."
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
            "scoped to a single cancer indication, as a {gene: median_value} "
            "mapping. Use this to answer questions about expression levels. To "
            "answer 'what is the median expression of genes involved in <cancer>?', "
            "first call get_targets(cancer_name) to obtain the gene list, then "
            "call this tool with the SAME cancer_name and the returned gene list. "
            "Both arguments are required: the cancer_name disambiguates genes "
            "that appear in multiple cancer indications."
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
                },
                "cancer_name": {
                    "type": "string",
                    "description": (
                        "Cancer indication to scope the expression lookup to. "
                        "Pass the same value used in the preceding get_targets "
                        "call so values come from the right cancer."
                    ),
                },
            },
            "required": ["genes", "cancer_name"],
        },
    },
]


def dispatch_tool(name: str, tool_input: dict[str, Any], df: pd.DataFrame) -> str:
    """Run the named tool with the given input and return a JSON string.

    On unknown tools or runtime errors, returns a JSON-serialised error
    payload so the model can read it and recover.
    """
    try:
        if name == "get_targets":
            return json.dumps(get_targets(tool_input["cancer_name"], df))
        if name == "get_expressions":
            return json.dumps(
                get_expressions(tool_input["genes"], tool_input["cancer_name"], df)
            )
        return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as exc:  # noqa: BLE001 — surface to the model so it can recover
        return json.dumps({"error": f"Tool {name} raised: {exc!s}"})
