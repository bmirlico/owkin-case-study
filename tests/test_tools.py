import json

import pandas as pd
import pytest

from app.tools import dispatch_tool, get_expressions, get_targets


@pytest.fixture
def df() -> pd.DataFrame:
    # Note: TP53 and KRAS appear in two cancers each, so the tests can verify
    # that get_expressions scopes by cancer_name and doesn't leak values across
    # cancers (the bug the cancer_name argument was added to fix).
    return pd.DataFrame(
        [
            {"cancer_indication": "lung", "gene": "EGFR", "median_value": 8.4},
            {"cancer_indication": "lung", "gene": "KRAS", "median_value": 6.7},
            {"cancer_indication": "lung", "gene": "TP53", "median_value": 9.1},
            {"cancer_indication": "breast", "gene": "BRCA1", "median_value": 7.3},
            {"cancer_indication": "breast", "gene": "BRCA2", "median_value": 6.9},
            {"cancer_indication": "breast", "gene": "TP53", "median_value": 2.5},
            {"cancer_indication": "colorectal", "gene": "KRAS", "median_value": 5.0},
        ]
    )


def test_get_targets_known_cancer(df):
    assert get_targets("lung", df) == ["EGFR", "KRAS", "TP53"]


def test_get_targets_case_insensitive(df):
    assert get_targets("LUNG", df) == ["EGFR", "KRAS", "TP53"]
    assert get_targets("  Breast  ", df) == ["BRCA1", "BRCA2", "TP53"]


def test_get_targets_unknown_cancer(df):
    assert get_targets("nonexistent", df) == []


def test_get_targets_empty_string(df):
    assert get_targets("", df) == []


def test_get_expressions_scoped_to_cancer(df):
    result = get_expressions(["EGFR", "KRAS", "TP53"], "lung", df)
    assert result == {"EGFR": 8.4, "KRAS": 6.7, "TP53": 9.1}


def test_get_expressions_does_not_leak_across_cancers(df):
    # TP53 is in both lung (9.1) and breast (2.5). Asking for breast must
    # return only breast's value — this is the regression test for the
    # dict(zip) bug in the brief's reference function.
    result = get_expressions(["TP53", "BRCA1"], "breast", df)
    assert result == {"TP53": 2.5, "BRCA1": 7.3}


def test_get_expressions_partial_match(df):
    result = get_expressions(["EGFR", "GHOST"], "lung", df)
    assert result == {"EGFR": 8.4}


def test_get_expressions_unknown_cancer(df):
    assert get_expressions(["EGFR"], "nonexistent", df) == {}


def test_get_expressions_empty_list(df):
    assert get_expressions([], "lung", df) == {}


def test_get_expressions_case_insensitive(df):
    assert get_expressions(["EGFR"], "LUNG", df) == {"EGFR": 8.4}


def test_dispatch_get_targets(df):
    out = dispatch_tool("get_targets", {"cancer_name": "lung"}, df)
    assert json.loads(out) == ["EGFR", "KRAS", "TP53"]


def test_dispatch_get_expressions(df):
    out = dispatch_tool(
        "get_expressions",
        {"genes": ["EGFR", "KRAS"], "cancer_name": "lung"},
        df,
    )
    assert json.loads(out) == {"EGFR": 8.4, "KRAS": 6.7}


def test_dispatch_get_expressions_missing_cancer_name(df):
    out = dispatch_tool("get_expressions", {"genes": ["EGFR"]}, df)
    assert "error" in json.loads(out)


def test_dispatch_unknown_tool(df):
    out = dispatch_tool("frobnicate", {}, df)
    assert "error" in json.loads(out)


def test_dispatch_bad_input_targets(df):
    out = dispatch_tool("get_targets", {"cancer_name": 42}, df)
    assert "error" in json.loads(out)


def test_dispatch_bad_input_expressions(df):
    out = dispatch_tool("get_expressions", {"genes": "EGFR", "cancer_name": "lung"}, df)
    assert "error" in json.loads(out)
