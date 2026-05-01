from typing import Any, AsyncIterator

import pandas as pd

from .tools import TOOL_SCHEMAS, dispatch_tool


def build_system_prompt(cancer_types: list[str]) -> str:
    cancer_list = ", ".join(cancer_types) if cancer_types else "(none loaded)"
    return f"""You are an assistant that helps non-technical stakeholders at Owkin explore an in-memory oncology gene-expression dataset.

You have access to two tools that operate on the dataset:

1. get_targets(cancer_name) → list of genes associated with the given cancer indication.
2. get_expressions(genes, cancer_name) → mapping of {{gene: median_expression_value}} for the given genes, scoped to a single cancer indication.

Available cancer indications in the dataset (use exactly one of these values for cancer_name):
{cancer_list}

Tool-use rules:
- When the user asks which genes are involved in a cancer, call get_targets and report the result.
- When the user asks for expression values for a cancer, you MUST chain the tools: first call get_targets(cancer_name) to retrieve the gene list, then call get_expressions(genes=<that list>, cancer_name=<the SAME cancer_name>). Both calls must use the same cancer_name. Do not skip the first step. Do not omit cancer_name from the second call.
- Match the user's cancer term to the closest available indication above (e.g. "esophageal cancer" → "esophageal" if present). If the user asks about a cancer that is not in the list, say so explicitly and list the available ones — do NOT call any tool in that case.
- Never invent gene names, cancer types, or expression values. Only report what the tools return.
- When reporting expression values, use the median values returned by the tool verbatim and label them as "median expression". Each value is the median over patients/samples for that (gene, cancer) pair, as stored in the dataset.

When the user asks "How can you help me?" (or similar), answer concretely: explain that you can list the genes involved in a given cancer, return their median expression values, and that the dataset currently covers the cancer indications listed above. Keep the answer short.

Keep all answers concise and grounded in the tool results."""


async def run_agent(
    messages: list[dict[str, Any]],
    df: pd.DataFrame,
    client: Any,
    *,
    model_name: str,
    cancer_types: list[str],
    max_tool_iterations: int,
) -> AsyncIterator[dict[str, Any]]:
    """Stream agent events as the model thinks → calls tools → answers.

    Mutates `messages` in place: appends each assistant turn and the
    corresponding tool_result user turn so the caller can persist the
    final history.
    """
    system_prompt = build_system_prompt(cancer_types)

    for _ in range(max_tool_iterations):
        response = await client.messages.create(
            model=model_name,
            max_tokens=1024,
            system=system_prompt,
            tools=TOOL_SCHEMAS,
            messages=messages,
        )

        for block in response.content:
            if getattr(block, "type", None) == "text":
                yield {"type": "text", "content": block.text}

        if response.stop_reason != "tool_use":
            messages.append(
                {"role": "assistant", "content": _serialise_blocks(response.content)}
            )
            yield {"type": "done"}
            return

        assistant_blocks = _serialise_blocks(response.content)
        messages.append({"role": "assistant", "content": assistant_blocks})

        tool_result_blocks: list[dict[str, Any]] = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            tool_name = block.name
            tool_input = block.input or {}
            yield {"type": "tool_call", "name": tool_name, "input": tool_input}

            result_str = dispatch_tool(tool_name, tool_input, df)
            yield {"type": "tool_result", "name": tool_name, "result": result_str}

            tool_result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result_str,
                }
            )

        messages.append({"role": "user", "content": tool_result_blocks})

    yield {
        "type": "error",
        "content": (
            f"Aborted: exceeded MAX_TOOL_ITERATIONS={max_tool_iterations}. "
            "The model kept asking for more tool calls without finishing."
        ),
    }


def _serialise_blocks(blocks: list[Any]) -> list[dict[str, Any]]:
    """Convert SDK block objects to plain dicts so messages stay JSON-friendly."""
    out: list[dict[str, Any]] = []
    for block in blocks:
        if hasattr(block, "model_dump"):
            out.append(block.model_dump())
        elif isinstance(block, dict):
            out.append(block)
        else:
            out.append({"type": "text", "text": str(block)})
    return out
