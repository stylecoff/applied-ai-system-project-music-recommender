"""Evaluation script: runs all 16 MBTI types through the real pipeline.
"""

from __future__ import annotations

import sys
from collections import Counter
from itertools import combinations

from src.mbti import PAIRS
from src.pipeline import load_catalog, run_pipeline

ALL_CODES = [a + b + c + d for a in PAIRS[0] for b in PAIRS[1] for c in PAIRS[2] for d in PAIRS[3]]
ALL_CODES = sorted(ALL_CODES)
HISTORY_TRACK_COUNT = 3
MAX_PER_GENRE_WHEN_MIXED = 2


def _top_genres(result) -> list[str]:
    return [r["song"]["genre"] for r in result.recommendations]


def evaluate_all(songs: list[dict]) -> dict:
    """Run every check and return {"rows": [...], "summary": {...}}."""
    rows = []
    top5_sets = {}
    for code in ALL_CODES:
        result = run_pipeline(code, songs, k=5)
        top = result.recommendations[0]
        genres = _top_genres(result)
        counts = Counter(genres)
        rows.append({
            "code": code,
            "wants": f"{result.profile['favorite_genre']} / {result.profile['favorite_mood']}",
            "top_title": top["song"]["title"],
            "top_artist": top["song"]["artist"],
            "top_genre": top["song"]["genre"],
            "top_mood": top["song"]["mood"],
            "match_percent": top["match_percent"],
            "genre_match": top["song"]["genre"] == result.profile["favorite_genre"],
            "mood_match": top["song"]["mood"] == result.profile["favorite_mood"],
            "distinct_genres": len(counts),
            "max_same_genre": max(counts.values()),
            "bias_warnings": len(result.warnings),
            "recommendations": len(result.recommendations),
            "scores_sorted": [r["score"] for r in result.recommendations]
                             == sorted((r["score"] for r in result.recommendations), reverse=True),
        })
        top5_sets[code] = frozenset(r["song"]["title"] for r in result.recommendations)

    # Does "Mix it up" really cap each genre, and what does it cost in match quality?
    mix_ok, plain_avg, mixed_avg = 0, [], []
    for code in ALL_CODES:
        plain = run_pipeline(code, songs, k=5)
        mixed = run_pipeline(code, songs, k=5, mix_it_up=True)
        if max(Counter(_top_genres(mixed)).values()) <= MAX_PER_GENRE_WHEN_MIXED:
            mix_ok += 1
        plain_avg.append(sum(r["match_percent"] for r in plain.recommendations) / 5)
        mixed_avg.append(sum(r["match_percent"] for r in mixed.recommendations) / 5)

    # Does listening history change the profile and the confidence?
    from src.insights import history_tracks

    history_titles = [s["title"] for s in history_tracks(songs)[:HISTORY_TRACK_COUNT]]
    top_changed, confidence_values = 0, set()
    for code in ALL_CODES:
        plain = run_pipeline(code, songs, k=5)
        with_history = run_pipeline(code, songs, history_titles=history_titles, k=5)
        confidence_values.add(with_history.confidence["percent"])
        if with_history.recommendations[0]["song"]["title"] != plain.recommendations[0]["song"]["title"]:
            top_changed += 1

    # Same input twice gives the same output?
    first = [run_pipeline(c, songs, k=5).recommendations[0]["song"]["title"] for c in ALL_CODES]
    second = [run_pipeline(c, songs, k=5).recommendations[0]["song"]["title"] for c in ALL_CODES]

    identical_pairs = [(a, b) for a, b in combinations(ALL_CODES, 2) if top5_sets[a] == top5_sets[b]]
    n = len(rows)
    summary = {
        "songs": len(songs),
        "types": n,
        "both_match": sum(r["genre_match"] and r["mood_match"] for r in rows),
        "genre_match": sum(r["genre_match"] for r in rows),
        "mood_match": sum(r["mood_match"] for r in rows),
        "all_have_five": all(r["recommendations"] == 5 for r in rows),
        "all_sorted": all(r["scores_sorted"] for r in rows),
        "avg_distinct_genres": round(sum(r["distinct_genres"] for r in rows) / n, 2),
        "types_with_bias_warning": sum(r["bias_warnings"] > 0 for r in rows),
        "distinct_top_songs": len({r["top_title"] for r in rows}),
        "identical_top5_pairs": len(identical_pairs),
        "identical_pair_examples": identical_pairs[:4],
        "mix_capped": mix_ok,
        "avg_match_plain": round(sum(plain_avg) / n, 1),
        "avg_match_mixed": round(sum(mixed_avg) / n, 1),
        "history_titles": history_titles,
        "history_top_changed": top_changed,
        "history_confidence": sorted(confidence_values),
        "deterministic": first == second,
    }
    return {"rows": rows, "summary": summary}


def _yn(flag: bool) -> str:
    return "yes" if flag else "no"


def format_text(report: dict) -> str:
    s = report["summary"]
    lines = [f"VibeFinder evaluation: {s['songs']} songs, {s['types']} MBTI types, top 5, no history", ""]
    lines.append(f"{'type':<5} {'wants':<24} {'top song':<34} {'match':>5}  genre mood  genres  max-same  warn")
    for r in report["rows"]:
        song = f"{r['top_title']} ({r['top_genre']}, {r['top_mood']})"
        lines.append(
            f"{r['code']:<5} {r['wants']:<24} {song[:34]:<34} {r['match_percent']:>4}%  "
            f"{_yn(r['genre_match']):<5} {_yn(r['mood_match']):<5} {r['distinct_genres']:>5}  "
            f"{r['max_same_genre']:>8}  {r['bias_warnings']:>4}"
        )
    lines += ["", "Summary"]
    lines += summary_lines(s)
    return "\n".join(lines)


def summary_lines(s: dict) -> list[str]:
    examples = ", ".join(f"{a}/{b}" for a, b in s["identical_pair_examples"]) or "none"
    return [
        f"- Top song matches both genre and mood: {s['both_match']}/{s['types']}",
        f"- Top song matches genre: {s['genre_match']}/{s['types']}; matches mood: {s['mood_match']}/{s['types']}",
        f"- Every type returns 5 songs, sorted by score: {_yn(s['all_have_five'] and s['all_sorted'])}",
        f"- Average distinct genres in the top 5: {s['avg_distinct_genres']}",
        f"- Types where the bias check warns (3+ of top 5 in one genre): {s['types_with_bias_warning']}/{s['types']}",
        f"- Different top songs across the 16 types: {s['distinct_top_songs']}/{s['types']}",
        f"- Pairs of types with the same top 5 songs (order may differ): {s['identical_top5_pairs']} (for example {examples})",
        f"- 'Mix it up' keeps every genre at 2 or fewer: {s['mix_capped']}/{s['types']}; "
        f"average match {s['avg_match_plain']}% plain vs {s['avg_match_mixed']}% mixed",
        f"- With {HISTORY_TRACK_COUNT} history tracks: confidence {s['history_confidence']}, "
        f"top song changed for {s['history_top_changed']}/{s['types']} types",
        f"- Same input gives the same output twice: {_yn(s['deterministic'])}",
    ]


def format_markdown(report: dict) -> str:
    s = report["summary"]
    lines = [
        f"Evaluation on {s['songs']} songs, all {s['types']} MBTI types, top 5, no history "
        "(`python -m src.evaluate`):",
        "",
        "| Type | Wants | Top song | Match | Genre | Mood | Genres in top 5 |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in report["rows"]:
        lines.append(
            f"| {r['code']} | {r['wants']} | {r['top_title']} ({r['top_genre']}, {r['top_mood']}) | "
            f"{r['match_percent']}% | {_yn(r['genre_match'])} | {_yn(r['mood_match'])} | {r['distinct_genres']} |"
        )
    lines += [""] + summary_lines(s)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    report = evaluate_all(load_catalog())
    print(format_markdown(report) if "--markdown" in argv else format_text(report))
    s = report["summary"]
    ok = s["all_have_five"] and s["all_sorted"] and s["deterministic"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())