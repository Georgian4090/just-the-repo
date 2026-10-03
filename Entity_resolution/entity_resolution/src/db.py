"""
DuckDB connection helper.

One place that wires up memory/thread limits and registers the two Python
UDFs the rest of the pipeline depends on:

  * normalize_unicode_py — Unicode-safe lowercase/trim/collapse. Fixes the
    real bug found while iterating on this project: a plain
    regexp_replace(lower(x), '[^a-z0-9]+', ' ') silently blanks out any
    non-Latin-script text. On this dataset that means every Devanagari /
    Gujarati / native-script business name in the India rows collapses to an
    empty string, which is why exact_name recall on those rows was 0%, not
    just low.

  * romanize_py — transliterates any script to ASCII (via `unidecode`, a
    pure offline codepoint table, MIT licensed, no external lookups) so a
    Devanagari name and its Latin-script equivalent for the same business
    become fuzzy-comparable at all, instead of permanently unmatchable.
"""
import re
import unicodedata

import duckdb

import config


def _normalize_unicode_py(text):
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    out = []
    for ch in text.lower():
        cat = unicodedata.category(ch)
        # Keep letters (L*), numbers (N*) and combining marks (Mn); collapse
        # everything else (punctuation, symbols, most whitespace) to a space.
        if cat[0] in ("L", "N") or cat == "Mn":
            out.append(ch)
        else:
            out.append(" ")
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _romanize_py(text):
    if not text:
        return ""
    try:
        from unidecode import unidecode
    except ImportError:  # pragma: no cover - surfaced clearly at runtime instead
        raise ImportError(
            "The 'unidecode' package is required for cross-script name "
            "matching. Install it with: pip install Unidecode"
        )
    return _normalize_unicode_py(unidecode(text))


def get_connection():
    con = duckdb.connect(database=":memory:")
    con.execute(f"PRAGMA memory_limit='{config.DUCKDB_MEMORY_LIMIT}'")
    con.execute(f"PRAGMA threads={config.DUCKDB_THREADS}")
    con.create_function("normalize_unicode_py", _normalize_unicode_py, ["VARCHAR"], "VARCHAR")
    con.create_function("romanize_py", _romanize_py, ["VARCHAR"], "VARCHAR")
    return con
