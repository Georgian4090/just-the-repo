"""
Stage 1: Normalization.

Produces one normalized Parquet file per (split, source) with every field the
later blocking/feature stages need, computed in a single pass. (The original
notebook rewrote this three times as v1 -> v2 -> v3; this collapses it into
one query that lands on the final schema directly.)
"""
import config

NORMALIZE_SQL = """
CREATE OR REPLACE TABLE {table} AS
SELECT
    entity_id,
    business_name                                          AS name_raw,
    business_address                                       AS address_raw,
    country                                                AS country_raw,
    lower(trim(coalesce(country, '')))                     AS country_norm,

    -- Unicode-safe normalization: keeps non-Latin scripts intact instead of
    -- collapsing them to an empty string.
    normalize_unicode_py(business_name)                    AS name_norm,
    normalize_unicode_py(business_address)                 AS address_norm,

    -- Cross-script bridge: romanized name, used as its own blocking key and
    -- feature so e.g. a Devanagari name and its Latin spelling can match.
    romanize_py(business_name)                             AS name_romanized,

    -- Digit-only address key. Script-invariant: a PIN/street number is
    -- written in Arabic numerals regardless of what script the rest of the
    -- address uses, so this block works even when name matching can't.
    regexp_replace(coalesce(business_address, ''), '[^0-9]', '', 'g')
                                                            AS address_digits,

    -- Token key for token/prefix blocking, built from the Unicode-safe name
    -- so it doesn't inherit the ASCII-only bug either.
    normalize_unicode_py(business_name)                    AS name_token_key
FROM read_csv(
    '{input_path}',
    delim = '\t',
    header = true,
    auto_detect = true,
    all_varchar = true
)
"""


def normalize_source(con, input_path, output_path, table_name):
    con.execute(NORMALIZE_SQL.format(table=table_name, input_path=input_path))
    con.execute(f"COPY {table_name} TO '{output_path}' (FORMAT PARQUET, COMPRESSION ZSTD)")
    n = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    print(f"  normalized {table_name}: {n:,} rows -> {output_path}")


def run(con, split):
    """split: 'train' or 'test'."""
    sources = {
        "s1": getattr(config, f"{split.upper()}_S1"),
        "s2": getattr(config, f"{split.upper()}_S2"),
        "s3": getattr(config, f"{split.upper()}_S3"),
    }
    for source, path in sources.items():
        out = config.norm_path(split, source)
        normalize_source(con, path, out, f"{split}_{source}_norm")
    print(f"Normalization complete for split='{split}'.")
