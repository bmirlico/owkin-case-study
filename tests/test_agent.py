from unittest.mock import MagicMock

import pandas as pd
import pytest

from app.agent import build_system_prompt, run_agent


class FakeTextBlock:
    type = "text"

    def __init__(self, text: str):
        self.text = text

    def model_dump(self) -> dict:
        return {"type": "text", "text": self.text}


class FakeToolUseBlock:
    type = "tool_use"

    def __init__(self, tool_id: str, name: str, tool_input: dict):
        self.id = tool_id
        self.name = name
        self.input = tool_input

    def model_dump(self) -> dict:
        return {
            "type": "tool_use",
            "id": self.id,
            "name": self.name,
            "input": self.input,
        }


class FakeMessage:
    def __init__(self, content: list, stop_reason: str):
        self.content = content
        self.stop_reason = stop_reason


@pytest.fixture
def df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"cancer_indication": "lung", "gene": "EGFR", "median_value": 8.4},
            {"cancer_indication": "lung", "gene": "KRAS", "median_value": 6.7},
        ]
    )


def test_system_prompt_lists_cancer_types():
    prompt = build_system_prompt(["lung", "breast"])
    assert "lung" in prompt
    assert "breast" in prompt
    assert "get_targets" in prompt
    assert "get_expressions" in prompt


@pytest.mark.asyncio
async def test_run_agent_dispatches_tool_and_emits_done(df):
    client = MagicMock()
    client.messages.create.side_effect = [
        FakeMessage(
            content=[FakeToolUseBlock("tool_1", "get_targets", {"cancer_name": "lung"})],
            stop_reason="tool_use",
        ),
        FakeMessage(
            content=[FakeTextBlock("EGFR and KRAS are involved in lung cancer.")],
            stop_reason="end_turn",
        ),
    ]

    messages: list = [{"role": "user", "content": "what genes are in lung cancer?"}]
    events = []
    async for evt in run_agent(
        messages,
        df,
        client,
        model_name="claude-sonnet-4-6",
        cancer_types=["lung"],
        max_tool_iterations=5,
    ):
        events.append(evt)

    types = [e["type"] for e in events]
    assert "tool_call" in types
    assert "tool_result" in types
    assert "text" in types
    assert types[-1] == "done"

    tool_call = next(e for e in events if e["type"] == "tool_call")
    assert tool_call["name"] == "get_targets"
    assert tool_call["input"] == {"cancer_name": "lung"}

    tool_result = next(e for e in events if e["type"] == "tool_result")
    assert "EGFR" in tool_result["result"]

    assert client.messages.create.call_count == 2
    assert messages[-1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_run_agent_chains_targets_then_expressions(df):
    client = MagicMock()
    client.messages.create.side_effect = [
        FakeMessage(
            content=[FakeToolUseBlock("t1", "get_targets", {"cancer_name": "lung"})],
            stop_reason="tool_use",
        ),
        FakeMessage(
            content=[
                FakeToolUseBlock("t2", "get_expressions", {"genes": ["EGFR", "KRAS"]})
            ],
            stop_reason="tool_use",
        ),
        FakeMessage(
            content=[FakeTextBlock("Median expressions: EGFR 8.4, KRAS 6.7.")],
            stop_reason="end_turn",
        ),
    ]

    messages: list = [
        {"role": "user", "content": "median expression of genes in lung cancer?"}
    ]
    events = []
    async for evt in run_agent(
        messages,
        df,
        client,
        model_name="claude-sonnet-4-6",
        cancer_types=["lung"],
        max_tool_iterations=5,
    ):
        events.append(evt)

    tool_calls = [e for e in events if e["type"] == "tool_call"]
    assert [t["name"] for t in tool_calls] == ["get_targets", "get_expressions"]
    assert tool_calls[1]["input"]["genes"] == ["EGFR", "KRAS"]
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_run_agent_caps_iterations(df):
    client = MagicMock()
    client.messages.create.return_value = FakeMessage(
        content=[FakeToolUseBlock("t", "get_targets", {"cancer_name": "lung"})],
        stop_reason="tool_use",
    )

    events = []
    async for evt in run_agent(
        [{"role": "user", "content": "loop forever"}],
        df,
        client,
        model_name="claude-sonnet-4-6",
        cancer_types=["lung"],
        max_tool_iterations=3,
    ):
        events.append(evt)

    assert events[-1]["type"] == "error"
    assert client.messages.create.call_count == 3
