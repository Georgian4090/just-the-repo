"""
Stage 3: Feature engineering.

One function, used identically by train.py and infer.py. The original
notebook computed this same feature SQL three separate times (train, valid,
test-batch); here it's a single source of truth so train and infer can never
silently drift apart.

Uses DuckDB's built-in jaro_winkler_similarity and levenshtein functions
directly in SQL rather than a Python string-distance library, so the 630K+
row feature computation stays a single vectorized query instead of a
row-by-row Python loop.
"""
import config

FEATURES_SQL = """
CREATE OR REPLACE TABLE {out_table} AS
SELECT
    c.source1_entity_id,
    c.candidate_entity_id,
    CASE WHEN a.country_norm = b.country_norm THEN 1 ELSE 0 END AS country_exact,
    CASE WHEN a.name_norm = b.name_norm THEN 1 ELSE 0 END AS name_exact,
    CASE WHEN a.name_token_key = b.name_token_key THEN 1 ELSE 0 END AS token_exact,
    jaro_winkler_similarity(a.name_norm, b.name_norm) AS name_jw,
    1.0 - (levenshtein(a.name_norm, b.name_norm) * 1.0 /
           greatest(length(a.name_norm), length(b.name_norm), 1)) AS name_lev,
    abs(length(a.name_norm) - length(b.name_norm)) AS name_length_diff,
    CASE WHEN a.address_norm = b.address_norm THEN 1 ELSE 0 END AS address_exact,
    jaro_winkler_similarity(a.address_norm, b.address_norm) AS address_jw,
    1.0 - (levenshtein(a.address_norm, b.address_norm) * 1.0 /
           greatest(length(a.address_norm), length(b.address_norm), 1)) AS address_lev,
    CASE WHEN a.address_digits = b.address_digits
          AND length(a.address_digits) >= {min_digits}
         THEN 1 ELSE 0 END AS address_digits_exact,
    CASE WHEN substr(a.name_norm, 1, 5) = substr(b.name_norm, 1, 5) THEN 1 ELSE 0 END AS name_prefix5,
    CASE WHEN substr(a.name_norm, 1, 8) = substr(b.name_norm, 1, 8) THEN 1 ELSE 0 END AS name_prefix8,
    jaro_winkler_similarity(a.name_romanized, b.name_romanized) AS name_romanized_jw
FROM {candidates_table} c
JOIN {s1_table} a ON c.source1_entity_id = a.entity_id
JOIN {other_table} b ON c.candidate_entity_id = b.entity_id
"""


def compute_features(con, split, candidates_table, s1_table, s2_table, s3_table, out_table):
    """A candidate_entity_id can come from either S2 or S3, so join against a
    union of both normalized tables rather than branching on the ID prefix
    inside SQL."""
    union_table = f"__s23_union_{split}"
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE {union_table} AS
        SELECT * FROM {s2_table}
        UNION ALL
        SELECT * FROM {s3_table}
    """)
    con.execute(
        FEATURES_SQL.format(
            out_table=out_table,
            candidates_table=candidates_table,
            s1_table=s1_table,
            other_table=union_table,
            min_digits=config.MIN_ADDRESS_DIGITS,
        )
    )
    n = con.execute(f"SELECT COUNT(*) FROM {out_table}").fetchone()[0]
    print(f"  features computed for {split}: {n:,} pairs -> table {out_table}")
