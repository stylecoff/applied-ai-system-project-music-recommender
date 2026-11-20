import os

import pytest

from src.assistant import (
    MAX_QUESTION_CHARS,
    AssistantError,
    ask_assistant,
    bold_titles,
    build_prompt,
    call_gemini,
    clean_question,
    fallback_answer,
    retrieve_context,
    verify_answer,
)
from src.pipeline import load_catalog, run_pipeline

SONGS_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "songs.csv")
needs_catalog = pytest.mark.skipif(not os.path.exists(SONGS_CSV), reason="data/songs.csv not found")


def make_catalog():
    genres = ["indie pop", "pop", "rock", "lofi", "jazz"]
    songs = []
    for i in range(1, 21):
        songs.append({
            "id": i, "title": f"Song {i}", "artist": f"Artist {i}",
            "genre": genres[i % 5], "mood": ["nostalgic", "happy", "intense"][i % 3],
            "energy": 0.1 + (i % 10) / 12, "valence": 0.5, "acousticness": 0.4,
            "danceability": 0.5, "tempo_bpm": 70 + i * 3,
        })
    return songs


class FakeLLM:
    """Records prompts and returns a fixed answer."""

    def __init__(self, answer):
        self.answer = answer
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def setup():
    songs = make_catalog()
    result = run_pipeline("INFP", songs)
    context = retrieve_context(result, songs)
    return songs, result, context


# --- guardrail ---------------------------------------------------------------

@pytest.mark.parametrize("bad", ["", "   ", "\n\t", None, 42])
def test_empty_or_non_text_questions_are_rejected(bad):
    with pytest.raises(AssistantError):
        clean_question(bad)


def test_long_question_is_cut_to_300_characters():
    cleaned, truncated = clean_question("a" * 1000)
    assert len(cleaned) == MAX_QUESTION_CHARS and truncated is True


def test_short_question_is_not_truncated_and_spaces_are_collapsed():
    cleaned, truncated = clean_question("  what   should\nI play?  ")
    assert cleaned == "what should I play?" and truncated is False


def test_square_brackets_are_removed_from_the_question():
    cleaned, _ = clean_question("play [Fake Song] please")
    assert "[" not in cleaned and "]" not in cleaned


# --- retrieve ----------------------------------------------------------------

def test_retrieve_gets_ten_songs_the_type_and_the_explainer(setup):
    _, _, context = setup
    assert len(context["songs"]) == 10
    assert context["code"] == "INFP"
    assert context["type"]["name"] == "Mediator"
    assert "What is MBTI?" in context["mbti_explainer"]
    assert context["songs"][0]["match_percent"] >= context["songs"][-1]["match_percent"]


def test_retrieved_songs_change_with_the_user(setup):
    songs, _, context = setup
    other = retrieve_context(run_pipeline("ESTJ", songs), songs)
    assert [s["title"] for s in context["songs"]] != [s["title"] for s in other["songs"]]


# --- prompt ------------------------------------------------------------------

def test_prompt_contains_rules_context_and_question_but_not_unretrieved_songs(setup):
    songs, _, context = setup
    prompt = build_prompt(context, "What should I play first?")
    for s in context["songs"]:
        assert s["title"] in prompt
    retrieved = {s["title"] for s in context["songs"]}
    outside = [s["title"] for s in songs if s["title"] not in retrieved]
    assert outside and all(f"- {title} by" not in prompt for title in outside)
    assert "square brackets" in prompt
    assert "<<<QUESTION\nWhat should I play first?\nQUESTION>>>" in prompt
    assert "Mediator" in prompt


# --- verify ------------------------------------------------------------------

def test_verify_accepts_retrieved_titles(setup):
    songs, _, context = setup
    title = context["songs"][0]["title"]
    check = verify_answer(f"Try [{title}] first.", context, songs)
    assert check["ok"] and check["cited"] == [title]


def test_verify_is_case_insensitive(setup):
    songs, _, context = setup
    title = context["songs"][0]["title"].upper()
    assert verify_answer(f"[{title}]", context, songs)["ok"]


def test_verify_rejects_a_song_that_does_not_exist(setup):
    songs, _, context = setup
    check = verify_answer("Try [Totally Made Up Song].", context, songs)
    assert not check["ok"] and check["not_in_catalog"] == ["Totally Made Up Song"]


def test_verify_rejects_a_real_song_that_was_not_retrieved(setup):
    songs, _, context = setup
    retrieved = {s["title"] for s in context["songs"]}
    outside = next(s["title"] for s in songs if s["title"] not in retrieved)
    check = verify_answer(f"Try [{outside}].", context, songs)
    assert not check["ok"] and check["outside_context"] == [outside]


def test_verify_allows_answers_with_no_songs(setup):
    songs, _, context = setup
    assert verify_answer("MBTI sorts people into 16 types.", context, songs)["ok"]


# --- ask_assistant -----------------------------------------------------------

def test_good_answer_is_verified_and_marked_gemini(setup):
    songs, result, context = setup
    title = context["songs"][0]["title"]
    llm = FakeLLM(f"Start with [{title}], it fits your calm side.")
    reply = ask_assistant("Where do I start?", result, songs, llm=llm)
    assert reply["source"] == "gemini" and reply["verified"] is True
    assert reply["cited"] == [title] and reply["reason"] is None


def test_made_up_song_triggers_the_fallback(setup):
    songs, result, _ = setup
    reply = ask_assistant("Where do I start?", result, songs, llm=FakeLLM("Try [Imaginary Hit]."))
    assert reply["source"] == "fallback" and reply["verified"] is False
    assert "Imaginary Hit" in reply["reason"]
    assert "best matches in the catalog" in reply["answer"]
    assert "Imaginary Hit" not in reply["answer"]


def test_song_outside_the_retrieved_list_triggers_the_fallback(setup):
    songs, result, context = setup
    retrieved = {s["title"] for s in context["songs"]}
    outside = next(s["title"] for s in songs if s["title"] not in retrieved)
    reply = ask_assistant("Hi", result, songs, llm=FakeLLM(f"Try [{outside}]."))
    assert reply["source"] == "fallback"


@pytest.mark.parametrize("failure", [AssistantError("no key"), RuntimeError("boom"), TimeoutError()])
def test_llm_errors_trigger_the_fallback(setup, failure):
    songs, result, _ = setup
    reply = ask_assistant("Hi", result, songs, llm=FakeLLM(failure))
    assert reply["source"] == "fallback" and reply["answer"]


@pytest.mark.parametrize("empty", ["", "   ", None])
def test_empty_llm_answer_triggers_the_fallback(setup, empty):
    songs, result, _ = setup
    assert ask_assistant("Hi", result, songs, llm=FakeLLM(empty))["source"] == "fallback"


def test_empty_question_is_rejected_without_calling_the_llm(setup):
    songs, result, _ = setup
    llm = FakeLLM("anything")
    reply = ask_assistant("   ", result, songs, llm=llm)
    assert reply["source"] == "rejected"
    assert llm.prompts == []


def test_long_question_is_truncated_before_it_reaches_the_llm(setup):
    songs, result, _ = setup
    llm = FakeLLM("MBTI is a rough guide.")
    reply = ask_assistant("x" * 5000, result, songs, llm=llm)
    assert reply["truncated"] is True
    assert "x" * 301 not in llm.prompts[0]


def test_the_prompt_sent_to_the_llm_uses_retrieved_data(setup):
    """RAG check: change the user and the context the model receives changes."""
    songs, result, _ = setup
    llm_a, llm_b = FakeLLM("ok"), FakeLLM("ok")
    ask_assistant("Hi", result, songs, llm=llm_a)
    ask_assistant("Hi", run_pipeline("ESTJ", songs), songs, llm=llm_b)
    assert llm_a.prompts[0] != llm_b.prompts[0]
    assert "INFP" in llm_a.prompts[0] and "ESTJ" in llm_b.prompts[0]


def test_history_shows_up_in_the_prompt(setup):
    songs, _, _ = setup
    result = run_pipeline("INFP", songs, history_titles=["Song 3"])
    llm = FakeLLM("ok")
    ask_assistant("Hi", result, songs, llm=llm)
    assert "Songs they said they like: Song 3" in llm.prompts[0]


# --- display helpers ---------------------------------------------------------

def test_bold_titles():
    assert bold_titles("Try [Ribs] and [ Space Song ].") == "Try **Ribs** and **Space Song**."


def test_fallback_answer_lists_five_songs(setup):
    _, _, context = setup
    text = fallback_answer(context)
    assert text.count("% match") == 5 and "rough guess" in text


# --- Gemini call -------------------------------------------------------------

def test_call_gemini_without_a_key_raises_a_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(AssistantError, match="GEMINI_API_KEY"):
        call_gemini("hello")


def test_key_with_line_breaks_is_rejected_and_never_printed():
    messy = "API Key\nSECRET-VALUE-123\n\nName\nGemini API Key"
    with pytest.raises(AssistantError) as err:
        call_gemini("hello", api_key=messy)
    assert "SECRET-VALUE-123" not in str(err.value)
    assert "line breaks" in str(err.value)


def test_errors_from_the_library_never_contain_the_key(monkeypatch):
    import sys
    import types

    secret = "SECRET-VALUE-123"

    class BrokenClient:
        def __init__(self, api_key):
            raise RuntimeError(f"Illegal header value {api_key}")

    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = BrokenClient
    fake_google = types.ModuleType("google")
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)

    with pytest.raises(AssistantError) as err:
        call_gemini("hello", api_key=secret)
    assert secret not in str(err.value)
    assert "[hidden]" in str(err.value)


def test_ask_assistant_fallback_reason_never_contains_the_key(setup):
    songs, result, _ = setup
    messy = "API Key\nSECRET-VALUE-123"
    reply = ask_assistant("Hi", result, songs, llm=lambda prompt: call_gemini(prompt, api_key=messy))
    assert reply["source"] == "fallback"
    assert "SECRET-VALUE-123" not in reply["reason"]


# --- real catalog ------------------------------------------------------------

@needs_catalog
def test_real_catalog_end_to_end_with_a_fake_llm():
    songs = load_catalog()
    result = run_pipeline("ENFP", songs)
    context = retrieve_context(result, songs)
    title = context["songs"][0]["title"]
    reply = ask_assistant("Why these songs?", result, songs, llm=FakeLLM(f"Because [{title}] is upbeat."))
    assert reply["source"] == "gemini" and reply["verified"]


# --- retries and backup model ------------------------------------------------

class FakeAPIError(Exception):
    def __init__(self, code, message):
        super().__init__(f"{code} {message}")
        self.code = code


def install_fake_genai(monkeypatch, script):
    """script: {model name: [outcome, ...]}; an outcome is a text or an Exception.
    Returns the list of models that were called, in order."""
    import sys
    import types

    calls = []

    class FakeModels:
        def generate_content(self, model, contents):
            calls.append(model)
            outcome = script[model].pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return types.SimpleNamespace(text=outcome)

    class FakeClient:
        def __init__(self, api_key):
            self.models = FakeModels()

    fake_genai = types.ModuleType("google.genai")
    fake_genai.Client = FakeClient
    fake_google = types.ModuleType("google")
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    return calls


@pytest.fixture
def no_waiting(monkeypatch):
    import src.assistant as assistant

    waits = []
    monkeypatch.setattr(assistant, "_sleep", lambda seconds: waits.append(seconds))
    return waits


def test_busy_model_is_retried_and_then_succeeds(monkeypatch, no_waiting):
    calls = install_fake_genai(monkeypatch, {"main": [FakeAPIError(503, "UNAVAILABLE"), "Hello"]})
    assert call_gemini("hi", model="main", api_key="k") == "Hello"
    assert calls == ["main", "main"] and len(no_waiting) == 1


def test_persistently_busy_model_switches_to_the_backup(monkeypatch, no_waiting):
    import src.assistant as assistant

    backup = "backup"
    monkeypatch.setattr(assistant, "FALLBACK_MODELS", (backup,))
    busy = FakeAPIError(503, "UNAVAILABLE")
    calls = install_fake_genai(monkeypatch, {"main": [busy, busy, busy], backup: ["From backup"]})
    assert call_gemini("hi", model="main", api_key="k") == "From backup"
    assert calls == ["main", "main", "main", backup]


def test_missing_model_goes_straight_to_the_backup(monkeypatch, no_waiting):
    import src.assistant as assistant

    backup = "backup"
    monkeypatch.setattr(assistant, "FALLBACK_MODELS", (backup,))
    calls = install_fake_genai(monkeypatch, {"main": [FakeAPIError(404, "NOT_FOUND")], backup: ["ok"]})
    assert call_gemini("hi", model="main", api_key="k") == "ok"
    assert calls == ["main", backup] and no_waiting == []


def test_bad_key_stops_immediately_without_trying_other_models(monkeypatch, no_waiting):
    calls = install_fake_genai(monkeypatch, {"main": [FakeAPIError(403, "PERMISSION_DENIED")]})
    with pytest.raises(AssistantError, match="PERMISSION_DENIED"):
        call_gemini("hi", model="main", api_key="k")
    assert calls == ["main"]


def test_everything_busy_ends_in_a_clear_error(monkeypatch, no_waiting):
    import src.assistant as assistant

    backup = "backup"
    monkeypatch.setattr(assistant, "FALLBACK_MODELS", (backup,))
    busy = FakeAPIError(503, "UNAVAILABLE")
    install_fake_genai(monkeypatch, {"main": [busy, busy, busy], backup: [busy, busy, busy]})
    with pytest.raises(AssistantError, match="Gemini request failed"):
        call_gemini("hi", model="main", api_key="k")


def test_empty_text_from_gemini_is_an_error(monkeypatch, no_waiting):
    install_fake_genai(monkeypatch, {"main": ["   "]})
    with pytest.raises(AssistantError, match="empty answer"):
        call_gemini("hi", model="main", api_key="k")


def test_backup_models_can_come_from_the_environment(monkeypatch, no_waiting):
    monkeypatch.setenv("GEMINI_FALLBACK_MODELS", "alpha, beta")
    busy = FakeAPIError(503, "UNAVAILABLE")
    calls = install_fake_genai(monkeypatch, {
        "main": [busy, busy, busy], "alpha": [busy, busy, busy], "beta": ["from beta"]})
    assert call_gemini("hi", model="main", api_key="k") == "from beta"
    assert calls[-1] == "beta"


def test_error_message_lists_every_model_that_failed(monkeypatch, no_waiting):
    import src.assistant as assistant

    monkeypatch.setattr(assistant, "FALLBACK_MODELS", ("backup",))
    busy = FakeAPIError(503, "UNAVAILABLE")
    gone = FakeAPIError(404, "NOT_FOUND")
    install_fake_genai(monkeypatch, {"main": [busy, busy, busy], "backup": [gone]})
    with pytest.raises(AssistantError) as err:
        call_gemini("hi", model="main", api_key="k")
    assert "model main" in str(err.value) and "model backup" in str(err.value)