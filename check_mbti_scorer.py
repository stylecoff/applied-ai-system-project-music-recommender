"""Temporary check: run all 16 MBTI profiles through the REAL recommender.

Run from the repo root:  python check_mbti_scorer.py
"""

import inspect

from src import recommender
from src.mbti import profile_from_mbti, validate_mbti, PAIRS

print("recommend_songs signature:", inspect.signature(recommender.recommend_songs))
print("score_song signature:     ", inspect.signature(recommender.score_song))

songs = recommender.load_songs("data/songs.csv")
print(f"Loaded songs: {len(songs)}\n")

codes = [a + b + c + d for a in "EI" for b in "SN" for c in "TF" for d in "JP"]
problems = []
no_full_match = []

for code in codes:
    profile = profile_from_mbti(code)
    try:
        results = recommender.recommend_songs(profile, songs, k=5)
    except Exception as exc:  # show the real error instead of hiding it
        problems.append(f"{code}: recommend_songs crashed -> {type(exc).__name__}: {exc}")
        continue

    if len(results) != 5:
        problems.append(f"{code}: expected 5 results, got {len(results)}")
        continue

    top, score, reasons = results[0]
    genre_ok = top["genre"] == profile["favorite_genre"]
    mood_ok = top["mood"] == profile["favorite_mood"]
    if not (genre_ok and mood_ok):
        no_full_match.append(code)

    scores = [r[1] for r in results]
    if scores != sorted(scores, reverse=True):
        problems.append(f"{code}: scores not sorted high to low")

    print(f"{code}  wants {profile['favorite_genre']:<10} / {profile['favorite_mood']:<10}"
          f" -> {top['title']} ({top['genre']}, {top['mood']}) score {score:.2f}"
          f"  genre {'Y' if genre_ok else 'n'} mood {'Y' if mood_ok else 'n'}")

print()
print("Types whose top song misses genre or mood:", ", ".join(no_full_match) or "none")
print("Problems:", "none" if not problems else "")
for p in problems:
    print(" -", p)