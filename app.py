"""VibeFinder: a music recommender that starts from your MBTI type.

"""

import streamlit as st

from src.applogging import setup_logging
from src.assistant import ask_assistant, bold_titles
from src.insights import history_tracks
from src.mbti import MBTI_EXPLAINER, MBTIError
from src.pipeline import load_catalog, run_pipeline
from src.playback import get_playback
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

st.set_page_config(page_title="VibeFinder", page_icon="🎧", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&display=swap');
    h1, h2, h3 { font-family: 'Space Grotesk', system-ui, sans-serif; letter-spacing: -0.01em; }
    .vf-eyebrow { font-size: 12px; font-weight: 600; letter-spacing: 0.12em;
                  text-transform: uppercase; color: #17695F; margin-bottom: 0; }
    </style>
    """,
    unsafe_allow_html=True,
)


# --- cached loaders ---------------------------------------------------------

@st.cache_resource
def init_logging():
    return str(setup_logging())


@st.cache_data
def get_catalog():
    return load_catalog()


@st.cache_data(ttl=600, show_spinner=False)
def cached_playback(title, artist):
    return get_playback({"title": title, "artist": artist})


init_logging()
catalog = get_catalog()
history_options = [s["title"] for s in history_tracks(catalog)]
artist_by_title = {s["title"]: s["artist"] for s in catalog}


# --- header -----------------------------------------------------------------

st.markdown('<p class="vf-eyebrow">Music recommender for new listeners</p>', unsafe_allow_html=True)
st.title("VibeFinder")
st.write(
    "Tell us your four MBTI letters and get a starting taste profile and five songs to try, "
    "even if we know nothing else about you."
)


# --- controls (left) --------------------------------------------------------

def on_pick():
    option = st.session_state.get("picker")
    if option:
        st.session_state["code_text"] = code_from_option(option)


st.session_state.setdefault("code_text", "INFP")

left, right = st.columns([1, 2.2], gap="large")

with left:
    with st.container(border=True):
        st.subheader("Your MBTI type")
        st.text_input(
            "4-letter code",
            key="code_text",
            max_chars=4,
            help="One letter from each pair: E or I, S or N, T or F, J or P. Example: INFP.",
        )
        st.selectbox(
            "Or pick one of the 16 types",
            options=type_options(),
            index=None,
            placeholder="Choose a type",
            key="picker",
            on_change=on_pick,
        )

        st.divider()
        st.subheader("Listening history")
        use_history = st.toggle(
            "Blend in songs I listen to",
            value=False,
            help="Optional. Songs you pick here sharpen the profile that the letters start.",
        )
        history_titles = []
        if use_history:
            history_titles = st.multiselect(
                "Pick songs you like",
                options=history_options,
                format_func=lambda t: f"{t} - {artist_by_title.get(t, '')}",
                placeholder="Choose up to a few songs",
            )
        st.caption(
            "These come from a Receiptify snapshot of the author's top tracks last month. "
            "It is not a live Spotify connection."
        )

        st.divider()
        mix_it_up = st.toggle(
            "Mix it up",
            value=False,
            help="No more than 2 songs from the same genre in the top 5.",
        )


# --- run the pipeline -------------------------------------------------------

try:
    result = run_pipeline(
        st.session_state["code_text"], catalog, history_titles, k=5, mix_it_up=mix_it_up
    )
except MBTIError as exc:
    with right:
        st.error(str(exc))
        st.caption("Your code needs exactly one letter from each pair, in this order: E/I, S/N, T/F, J/P.")
    st.stop()

current_signature = signature(result.code, history_titles, mix_it_up)


# --- results (right) --------------------------------------------------------

with right:
    # Profile card
    st.subheader("Starting taste profile")
    with st.container(border=True):
        label = result.type_label
        st.markdown(f"### {result.code} · {label['name']}")
        st.caption(f"{label['family']} · {label['description']}")

        g_col, m_col = st.columns(2)
        g_col.metric("Favorite genre", result.profile["favorite_genre"])
        m_col.metric("Favorite mood", result.profile["favorite_mood"])

        for bar_label, fraction, shown in profile_bars(result.profile):
            st.progress(fraction, text=f"{bar_label}: {shown}")
        st.caption(history_summary(result))

        with st.expander("Why these numbers? One line per letter"):
            for line in result.letter_notes:
                st.markdown(f"- {line}")
        with st.expander("What is MBTI, and how does it connect to music?"):
            st.markdown(MBTI_EXPLAINER.replace("\n", "  \n"))
        st.caption(
            "The type name and family are display labels only. "
            "Songs are matched from your four letters."
        )

    # Songs
    st.subheader("Top 5 for this listener")
    if result.mix_it_up:
        st.caption("Mix it up is on: no more than 2 songs from the same genre.")

    with st.spinner("Finding song previews..."):
        playback = {
            rec["song"]["title"]: cached_playback(rec["song"]["title"], rec["song"]["artist"])
            for rec in result.recommendations
        }

    for rec in result.recommendations:
        song = rec["song"]
        play = playback[song["title"]]
        with st.container(border=True):
            art_col, info_col = st.columns([1, 5])
            with art_col:
                if play["artwork_url"]:
                    st.image(play["artwork_url"])
                else:
                    st.markdown("### 🎵")
            with info_col:
                st.markdown(
                    f"**{rec['rank']}. {song['title']}**  \n"
                    f"{song['artist']} · {song['genre']} · {song['mood']}"
                )
                if rec["variety"]:
                    st.caption("Added for variety")
                st.progress(min(1.0, rec["match_percent"] / 100), text=f"{rec['match_percent']}% match")

                if play["preview_url"]:
                    st.audio(play["preview_url"])
                else:
                    st.caption("No preview found for this song. Use the links to listen.")

                b1, b2, b3 = st.columns(3)
                b1.link_button("YouTube", play["links"]["youtube"])
                b2.link_button("Spotify", play["links"]["spotify"])
                if play["track_url"]:
                    b3.link_button("Apple Music", play["track_url"])

                with st.expander("Why this song"):
                    for reason in rec["reasons"]:
                        st.markdown(f"- {reason}")
    st.caption("Song previews courtesy of Apple (iTunes Search). Song features are hand-estimated.")

    # Trust checks
    st.subheader("Trust checks")
    conf_col, bias_col = st.columns(2)
    with conf_col:
        with st.container(border=True):
            conf = result.confidence
            st.metric("Confidence score", f"{conf['percent']}%")
            st.markdown(f"**{conf['label']}**")
            st.caption(conf["note"])
            st.caption(confidence_tip(len(result.history)))
    with bias_col:
        with st.container(border=True):
            st.markdown("**Bias check**")
            if result.warnings:
                for warning in result.warnings:
                    st.warning(warning)
            else:
                st.success("No bias warnings for this list.")
            st.info(result.guess_note)

    # Assistant
    st.subheader("Ask the assistant")
    st.caption(
        "Gemini answers using only the 10 best songs for you, and every song it names is checked. "
        "If it fails, you get a catalog-only answer instead. Questions are limited to 300 characters."
    )

    clicked_example = None
    example_cols = st.columns(len(EXAMPLE_QUESTIONS))
    for index, (col, example) in enumerate(zip(example_cols, EXAMPLE_QUESTIONS)):
        if col.button(example, key=f"example_{index}"):
            clicked_example = example

    with st.form("ask_form"):
        typed_question = st.text_input("Your question", key="assistant_question")
        submitted = st.form_submit_button("Ask")

    question = clicked_example if clicked_example is not None else (typed_question if submitted else None)

    if question is not None:
        with st.spinner("Asking Gemini... this can take a few seconds"):
            reply = ask_assistant(question, result, catalog)
        st.session_state["last_reply"] = {
            "signature": current_signature,
            "question": question,
            "reply": reply,
        }

    saved = st.session_state.get("last_reply")
    if saved and saved["signature"] == current_signature:
        reply = saved["reply"]
        kind, banner_text = answer_banner(reply)
        getattr(st, kind)(banner_text)
        if reply["source"] != "rejected":
            st.caption(f"You asked: {saved['question']}")
            if reply["truncated"]:
                st.caption("Your question was longer than 300 characters, so it was shortened.")
            st.markdown(bold_titles(reply["answer"]) if reply["source"] == "gemini" else reply["answer"])
            if reply["source"] == "fallback" and reply["reason"]:
                with st.expander("Why the fallback was used"):
                    st.write(reply["reason"])

st.divider()
st.caption(
    "VibeFinder is a class project. MBTI is a rough guess about taste, not a rule. "
    "Song features are hand-estimated, and the listening history is a snapshot."
)