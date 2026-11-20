import os

import pytest

from src.evaluate import ALL_CODES, evaluate_all, format_markdown, format_text, main
from src.pipeline import load_catalog

SONGS_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "songs.csv")
needs_catalog = pytest.mark.skipif(not os.path.exists(SONGS_CSV), reason="data/songs.csv not found")


def test_there_are_16_unique_codes():
    assert len(ALL_CODES) == 16 and len(set(ALL_CODES)) == 16


@pytest.fixture(scope="module")
def report():
    return evaluate_all(load_catalog())


@needs_catalog
def test_report_has_a_row_per_type_and_a_summary(report):
    assert [r["code"] for r in report["rows"]] == ALL_CODES
    assert report["summary"]["types"] == 16


@needs_catalog
def test_reliability_checks_pass_on_the_real_catalog(report):
    s = report["summary"]
    assert s["all_have_five"] and s["all_sorted"]
    assert s["deterministic"]
    assert s["both_match"] == 16        # no type is left without a genre and mood match
    assert s["mix_capped"] == 16        # "Mix it up" always keeps genres at 2 or fewer
    assert s["history_confidence"] == [75]


@needs_catalog
def test_text_and_markdown_formats(report):
    text = format_text(report)
    assert "INFP" in text and "Summary" in text
    markdown = format_markdown(report)
    assert "| Type | Wants | Top song |" in markdown
    assert markdown.count("\n| ") >= 16


@needs_catalog
def test_main_prints_and_exits_zero(capsys):
    assert main([]) == 0
    assert "VibeFinder evaluation" in capsys.readouterr().out
    assert main(["--markdown"]) == 0
    assert "| Type |" in capsys.readouterr().out