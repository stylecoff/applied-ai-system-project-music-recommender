from types import SimpleNamespace

from src.mbti import profile_from_mbti
from src.uihelpers import (
    EXAMPLE_QUESTIONS,
    answer_banner,
    code_from_option,
    confidence_tip,
    history_summary,
    profile_bars,
    signature,
    type_options,
)


def test_type_options_cover_all_16_and_round_trip():
    options = type_options()
    assert len(options) == 16
    codes = [code_from_option(o) for o in options]
    assert len(set(codes)) == 16 and "INFP" in codes
    assert any(o == "INFP - Mediator (Diplomats)" for o in options)


def test_profile_bars_are_fractions_with_labels():
    bars = profile_bars(profile_from_mbti("ESTJ"))
    assert [b[0] for b in bars] == ["Energy", "Happiness (valence)", "Acoustic sound", "Danceability", "Tempo"]
    assert all(0.0 <= b[1] <= 1.0 for b in bars)
    assert bars[-1][2].endswith("BPM")


def test_tempo_bar_covers_the_full_range():
    low = profile_bars({**profile_from_mbti("INFP"), "preferred_tempo": 60})[-1][1]
    high = profile_bars({**profile_from_mbti("INFP"), "preferred_tempo": 164})[-1][1]
    assert low == 0.0 and high == 1.0


def test_history_summary_wording():
    assert "letters only" in history_summary(SimpleNamespace(history=[]))
    assert "1 track you" in history_summary(SimpleNamespace(history=[1]))
    assert "20%" in history_summary(SimpleNamespace(history=[1]))
    assert "60%" in history_summary(SimpleNamespace(history=[1, 2, 3, 4]))


def test_confidence_tip():
    assert "3 more tracks" in confidence_tip(0)
    assert "1 more track " in confidence_tip(2)
    assert "highest level" in confidence_tip(5)


def test_answer_banner_kinds():
    assert answer_banner({"source": "gemini", "answer": "x"})[0] == "success"
    assert answer_banner({"source": "fallback", "answer": "x"})[0] == "warning"
    kind, text = answer_banner({"source": "rejected", "answer": "Please type a question."})
    assert kind == "error" and text == "Please type a question."


def test_signature_changes_with_settings_and_ignores_case():
    base = signature("infp", ["A"], False)
    assert base == signature(" INFP ", ["A"], False)
    assert base != signature("INFP", ["A", "B"], False)
    assert base != signature("INFP", ["A"], True)


def test_there_are_three_example_questions():
    assert len(EXAMPLE_QUESTIONS) == 3