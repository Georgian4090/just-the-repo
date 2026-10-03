# Business Entity Resolution — Pipeline

Local (non-Colab) pipeline for the ML Challenge entity-resolution task:
given business records from three noisy sources, find every Source-2/3
record that matches each Source-1 entity.

This reconstructs and fixes the pipeline developed iteratively in Colab —
carrying forward what worked (DuckDB for everything at this scale, the
Unicode-safe normalization fix, rare-token blocking, the V3 blocking union),
dropping what didn't earn its keep (canonicalization added only ~2pp recall
on top of everything else and isn't worth further tuning time), and fixing
three real bugs found along the way (see "Bugs fixed" below).

## Pipeline

```
Raw TSVs (3 sources × train/test)
        │
        ▼
[1] NORMALIZE   (src/normalize.py)   — Unicode-safe text, romanized name,
        │                              digit-only address, token key
        ▼
[2] BLOCK       (src/blocking.py)    — 5 strategies unioned:
        │                              exact name / exact address / address
        │                              digits / romanized name / rare token
        ▼
[3] FEATURES    (src/features.py)    — 13 pairwise features, one query,
        │                              shared by train + infer
        ▼
[4] TRAIN       (src/train.py)       — XGBoost, entity-level train/valid split
        │
        ▼
[5] EVALUATE    (src/evaluate.py)    — threshold sweep on macro-F0.5,
        │                              the actual leaderboard metric
        ▼
[6] INFER       (src/infer.py)       — score test candidates, write
                                        output/matching_results.tsv and
                                        output/candidate_pairs.tsv
```

## Setup

```bash
pip install -r requirements.txt
```

Put the challenge data under `dataset/`:

```
dataset/
├── train/
│   ├── train_source1.tsv
│   ├── train_source2.tsv
│   ├── train_source3.tsv
│   └── train_ground_truth.tsv
└── test/
    ├── test_source1.tsv
    ├── test_source2.tsv
    └── test_source3.tsv
```

(Or point `ER_DATA_ROOT` at wherever the data actually lives, e.g.
`export ER_DATA_ROOT=/mnt/d/amazon-ml-challenge/dataset`.)

## Run it

First pass, end to end:

```bash
python run_pipeline.py all
```

Then validate before submitting anything:

```bash
python utils/validate_submission.py \
    --matching output/matching_results.tsv \
    --candidate output/candidate_pairs.tsv \
    --test-dir dataset/test
```

After the first pass, iterate on individual stages instead of re-running
everything — each stage reads the Parquet/JSON the previous one wrote:

```bash
python run_pipeline.py block train      # e.g. after changing config.TOKEN_MAX_DF
python run_pipeline.py recall           # re-check the recall ceiling
python run_pipeline.py features train
python run_pipeline.py train
python run_pipeline.py evaluate
python run_pipeline.py block test
python run_pipeline.py features test
python run_pipeline.py infer
```

All paths, blocking thresholds, feature list, model hyperparameters, and the
threshold sweep range live in **`config.py`** — nothing is hardcoded inside
`src/`.

## Bugs fixed (relative to the original Colab notebook)

1. **Unicode stripping.** The original `normalize_text` macro was
   `regexp_replace(lower(x), '[^a-z0-9]+', ' ')`, which silently blanks out
   any non-Latin-script name (Devanagari, Gujarati, etc.) to an empty
   string. `src/db.py::_normalize_unicode_py` keeps any Unicode letter,
   number, or combining-mark character instead, so native-script names
   survive normalization.
2. **Cross-script matching.** Unicode-safe normalization alone doesn't make
   `प्रभाव बिजनेस सेंटर` equal `Prabhav Business Center` — they're different
   scripts for the same sounds, not different formatting of the same
   string. `romanize_py` (via `unidecode`, MIT-licensed, pure offline
   transliteration table — no external lookups, compliant with the
   challenge's no-external-data rule) bridges this and is used both as a
   blocking key and a feature (`name_romanized_jw`).
3. **Token-block explosion.** Blocking on raw name tokens let generic
   category words ("pediatric", "limited private") create blocks with
   30,000+ members that add compute cost without adding recall.
   `src/blocking.py::_build_token_df` computes document frequency per
   (country, token) from the data itself and only uses tokens at or below
   `config.TOKEN_MAX_DF` as blocking keys.
4. **Train/test path bug.** An earlier version of the final scoring loop
   pointed at `*_train_v3.parquet` for all three sources, so it silently
   re-scored training data instead of producing a real test submission.
   `src/infer.py` only ever reads `config.TEST_*` / the test-split tables.
5. **Missing entities.** Building output rows by iterating over
   `candidates` meant any S1 entity blocking found zero candidates for was
   never written to either output file — a **hard** validator failure
   (`required S1 entity(ies) missing`), not a warning. `src/infer.py` now
   builds rows starting from the required S1 ID list
   (`test_source1.tsv`) and left-joins candidates/matches onto it, so every
   required entity gets a row, empty when it has no matches.

## Known gaps / honest limitations

- **Phonetic blocking** (Soundex/Metaphone) and **sorted-neighborhood
  address blocking** were part of the original plan but aren't implemented
  here — the rare-token + romanized-name blocks cover much of the same
  ground more cheaply. Worth adding if measured recall still has room after
  the current five strategies.
- **No collective/graph-based resolution.** Matches are grouped directly by
  `source1_entity_id`; if two Source-1 entities should transitively share a
  match, that's not handled. This is the single highest-leverage extension
  if you have time left — build a graph over all scored pairs and run
  connected-components or correlation clustering before thresholding,
  instead of thresholding each pair independently. Given F0.5's precision
  weighting, this is a strong lever specifically for cutting false
  positives.
- **Canonicalization** (legal-suffix stripping etc.) was measured at ~+2pp
  recall beyond the current blocking union on a 10k-entity sample —
  real, but small enough not to be worth further tuning time right now.
- Always re-run `recall` after changing blocking logic, and treat that
  number as your ceiling: no amount of matcher tuning recovers a true match
  that never entered `candidate_pairs.tsv`.

## Country handling

`country_norm` is used to scope every blocking join, but as a plain
lowercase/trim — not a fixed `{US, India}` vocabulary — precisely because
the test set adds France, which never appears in training. Nothing in
`config.py` or `src/` hardcodes a country list.

## Compliance notes

- The XGBoost matcher trains from scratch on the provided labeled pairs —
  no external model weights, APIs, or business-registry lookups are used
  anywhere in the pipeline, per the challenge's fair-play rules.
- `unidecode` is a static, offline transliteration table (codepoint →
  ASCII), not a lookup service — it doesn't look up or resolve business
  identities, it only re-renders text.
