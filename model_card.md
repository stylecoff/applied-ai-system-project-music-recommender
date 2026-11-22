## 🎧 Final project update: VibeFinder (MBTI starting profile, assistant, and trust checks)

*Paste this section at the end of `model_card.md`.*

### Intended use
A classroom music recommender for **new listeners with no history**. It turns four MBTI letters into a starting taste profile and recommends five songs from a 75-song catalog. It is a learning project, not a production recommender, and it should not be used to make decisions about people.

### How it works (short)
- **Scoring:** the Module 3 content-based scorer (genre +2.0, mood +1.0, then closeness on energy, valence, acousticness, danceability, tempo; maximum 7.1).
- **MBTI to profile:** each letter nudges the numeric targets, and letter pairs pick a genre and a mood. Type names and families are display labels only.
- **History blend:** optional picked songs are mixed into the profile (20%, 40%, or 60% for 1, 2, or 3 or more songs).
- **Trust checks:** a confidence score (30% to 75%, a rule of thumb) and a bias check that warns about one-genre lists.
- **Assistant:** Gemini answers from retrieved data only (top 10 songs, the profile, MBTI text). Every song it names is verified, and a catalog-only fallback is used if anything fails.

### Data
- 75 songs in `data/songs.csv`: 20 starter songs (some fictional), 45 songs from my own Receiptify top tracks, and 10 added to cover missing genre and mood combinations.
- Genre and mood labels are my judgment. Numeric features are hand-estimated, not measured from audio.
- The listening history is a one-month snapshot of one person, not a live Spotify connection.

### Evaluation (`python -m src.evaluate`)
- All 16 types receive a top song matching both genre and mood (16/16), five songs each, sorted by score, identical on a repeat run.
- **Every type's default top 5 comes from one genre** (average 1.0 distinct genres), and the bias check warns for 16/16.
- Only 9 different top songs appear across the 16 types, and 15 pairs of types receive the same five songs in a different order.
- "Mix it up" keeps every genre at 2 or fewer songs (16/16), lowering the average match from 84.2% to 74.7%.
- The assistant's verification and fallback were tested with a fake model (no network). Live Gemini availability varies, which is why the fallback exists.

### Limitations and biases
- **Genre bias:** the genre bonus is double the mood bonus, so genre decides most of the list.
- **Stereotyping:** the MBTI mapping gives every "I" calmer music and every "E" louder music. It is a design choice, not evidence, and MBTI itself is debated.
- **Catalog bias:** the catalog reflects one person's taste and a small set of genres, so some listeners will find nothing that fits.
- **Popularity and recency:** the system has no notion of either, and it never learns from a user's reactions.
- **Verification limit:** the assistant check confirms which songs are named, not that every sentence of the explanation is accurate.

### Misuse and mitigation
- Someone could treat the MBTI result as a fact about a person. The app labels it a rough guess, shows a confidence score, and explains where the link comes from.
- The assistant could be asked off-topic questions or told to ignore its rules. Questions are cleaned and cut to 300 characters, kept in a marked block, and any answer naming a song outside the retrieved list is replaced by the fallback.
- No keys, logs, or screenshots with account names are committed.

### AI collaboration
I built this extension with an AI assistant (Claude) and used Gemini inside the app. I ran the tests, the evaluation, and the app myself. The AI was wrong at least once: it picked a backup Gemini model that Google had already closed to new users, which I found by running the live check. It also first printed my API key in an error message, so I replaced the key and the code now hides keys in errors.