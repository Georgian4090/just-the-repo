"""
Stage 2: Blocking / candidate generation.

Unions five independent strategies so each catches a different noise type,
then applies document-frequency filtering to the token strategy so generic
category words ("pediatric", "limited private") don't blow up the candidate
count while adding zero discriminative value (a block with 30k+ members
reduces nothing — it's not really "blocking").

Strategies (each run against S2 and against S3 separately, then unioned):
  1. exact_name      — exact match on normalized name, same country
  2. exact_address   — exact match on normalized address, same country
  3. exact_digits    — exact match on address digit-string
                        (>= MIN_ADDRESS_DIGITS), script-invariant
  4. romanized_name  — exact match on romanized name; catches cross-script
                        variants exact_name can't
  5. rare_token      — shared name token whose document frequency is below
                        TOKEN_MAX_DF within its (source, country) bucket

candidate_pairs.tsv (built later, in infer.py) is exactly this union, per
the challenge spec: "the final candidate list just before the ML model
scores them."
"""
import config


def _exact_block(s1_table, other_table, key_col, block_name):
    return f"""
    SELECT DISTINCT
        a.entity_id AS source1_entity_id,
        b.entity_id AS candidate_entity_id,
        '{block_name}' AS block_source
    FROM {s1_table} a
    JOIN {other_table} b
      ON a.{key_col} = b.{key_col}
     AND a.country_norm = b.country_norm
    WHERE a.{key_col} IS NOT NULL AND a.{key_col} <> ''
    """


def _digits_block(s1_table, other_table, block_name):
    return f"""
    SELECT DISTINCT
        a.entity_id AS source1_entity_id,
        b.entity_id AS candidate_entity_id,
        '{block_name}' AS block_source
    FROM {s1_table} a
    JOIN {other_table} b
      ON a.address_digits = b.address_digits
     AND a.country_norm = b.country_norm
    WHERE length(a.address_digits) >= {config.MIN_ADDRESS_DIGITS}
    """


def _build_token_df(con, tables, out_table):
    """Document frequency of each name token per country bucket, computed
    across the given (non-S1) tables — this identifies category words versus
    identifying ones from the data itself, not a fixed stopword list."""
    union_sql = " UNION ALL ".join(
        f"SELECT entity_id, country_norm, name_token_key FROM {t}" for t in tables
    )
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE {out_table} AS
        SELECT country_norm, token, COUNT(*) AS df
        FROM (
            SELECT country_norm, entity_id,
                   UNNEST(string_split(name_token_key, ' ')) AS token
            FROM ({union_sql})
        )
        WHERE length(token) >= {config.TOKEN_MIN_LEN}
        GROUP BY country_norm, token
    """)


def _rare_token_block(s1_table, other_table, token_df_table, block_name):
    return f"""
    WITH s1_tokens AS (
        SELECT entity_id, country_norm,
               UNNEST(string_split(name_token_key, ' ')) AS token
        FROM {s1_table}
    ),
    other_tokens AS (
        SELECT entity_id, country_norm,
               UNNEST(string_split(name_token_key, ' ')) AS token
        FROM {other_table}
    ),
    rare AS (
        SELECT country_norm, token FROM {token_df_table}
        WHERE df <= {config.TOKEN_MAX_DF}
    )
    SELECT DISTINCT
        s.entity_id AS source1_entity_id,
        o.entity_id AS candidate_entity_id,
        '{block_name}' AS block_source
    FROM s1_tokens s
    JOIN rare r ON s.country_norm = r.country_norm AND s.token = r.token
    JOIN other_tokens o ON o.country_norm = r.country_norm AND o.token = r.token
    WHERE length(s.token) >= {config.TOKEN_MIN_LEN}
    """


def build_candidates(con, split):
    """Requires {split}_s1_norm / _s2_norm / _s3_norm tables to already be
    registered on `con` (run_pipeline.py loads them from the normalized
    parquet files before calling this)."""
    s1 = f"{split}_s1_norm"
    s2 = f"{split}_s2_norm"
    s3 = f"{split}_s3_norm"

    _build_token_df(con, [s2, s3], "token_df")

    parts = []
    for other, suffix in ((s2, "s2"), (s3, "s3")):
        parts.append(_exact_block(s1, other, "name_norm", f"exact_name_{suffix}"))
        parts.append(_exact_block(s1, other, "address_norm", f"exact_address_{suffix}"))
        parts.append(_digits_block(s1, other, f"exact_digits_{suffix}"))
        parts.append(_exact_block(s1, other, "name_romanized", f"romanized_name_{suffix}"))
        parts.append(_rare_token_block(s1, other, "token_df", f"rare_token_{suffix}"))

    union_sql = "\nUNION ALL\n".join(parts)
    con.execute(f"CREATE OR REPLACE TABLE {split}_candidates_raw AS {union_sql}")

    # Collapse to one row per (s1, candidate) pair. block_sources is kept for
    # diagnostics (which strategy found what) but the pair itself is what
    # gets scored downstream.
    con.execute(f"""
        CREATE OR REPLACE TABLE {split}_candidates AS
        SELECT
            source1_entity_id,
            candidate_entity_id,
            string_agg(DISTINCT block_source, ',') AS block_sources
        FROM {split}_candidates_raw
        GROUP BY source1_entity_id, candidate_entity_id
    """)

    out = config.candidates_path(split)
    con.execute(f"COPY {split}_candidates TO '{out}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    n_pairs = con.execute(f"SELECT COUNT(*) FROM {split}_candidates").fetchone()[0]
    n_s1 = con.execute(
        f"SELECT COUNT(DISTINCT source1_entity_id) FROM {split}_candidates"
    ).fetchone()[0]
    print(f"  {split} candidates: {n_pairs:,} pairs across {n_s1:,} S1 entities -> {out}")


def measure_recall(con, split, ground_truth_path):
    """Recall of the union candidate set against ground truth. Only
    meaningful on the train split, where ground truth exists. Run this
    before touching features/training — it's your true recall ceiling."""
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE gt_pairs AS
        SELECT source1_entity_id, TRIM(m) AS candidate_entity_id
        FROM (
            SELECT source1_entity_id,
                   UNNEST(string_split(coalesce(matched_entity_ids, ''), ',')) AS m
            FROM read_csv(
                '{ground_truth_path}', delim='\t', header=true,
                auto_detect=true, all_varchar=true
            )
        )
        WHERE TRIM(m) <> ''
    """)
    total = con.execute("SELECT COUNT(*) FROM gt_pairs").fetchone()[0]
    recovered = con.execute(f"""
        SELECT COUNT(*)
        FROM gt_pairs g
        JOIN {split}_candidates c
          ON g.source1_entity_id = c.source1_entity_id
         AND g.candidate_entity_id = c.candidate_entity_id
    """).fetchone()[0]
    recall = recovered / total if total else float("nan")
    print(f"  blocking recall on {split}: {recovered:,}/{total:,} = {recall:.4%}")
    return recall
