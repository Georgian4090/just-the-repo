"""
Stage 6: Inference and output.

Produces matching_results.tsv and candidate_pairs.tsv in the exact shape
utils/validate_submission.py checks:

    source1_entity_id \t comma,joined,ids

one row per S1 entity, every required S1 test entity present, empty string
when there are no candidates/matches.

Two real bugs found earlier in this project are fixed here on purpose:

  1. The original notebook's final scoring loop pointed S1_FILE/S2_FILE/
     S3_FILE at *_train_v3.parquet for every source, so it silently re-scored
     training data instead of the test set. This module only ever reads
     config.TEST_* / the test-split feature and candidate tables.

  2. Output rows were previously built by iterating over `candidates`, so any
     S1 entity blocking found zero candidates for was never written to
     either file — a hard validator failure ("required S1 entity(ies)
     missing"), not just a warning. Here, rows are built starting from the
     *required* S1 ID list (test_source1.tsv) and left-joined to
     candidates/matches, so every required entity gets a row even when its
     list is empty.
"""
import json

import xgboost as xgb

import config


def _write_id_list_tsv(path, header_cols, required_ids, id_lists_by_entity):
    """Write a matching/candidate-style TSV: one row per required id, a
    deduped/sorted comma-joined list (sorted for run-to-run determinism),
    empty string when the entity has no candidates/matches."""
    with open(path, "w", encoding="utf-8") as f:
        f.write("\t".join(header_cols) + "\n")
        for ent in required_ids:
            ids = sorted(set(id_lists_by_entity.get(ent, [])))
            f.write(f"{ent}\t{','.join(ids)}\n")


def run(con):
    required_s1 = [
        r[0]
        for r in con.execute(
            f"SELECT DISTINCT entity_id FROM read_csv("
            f"'{config.TEST_S1}', delim='\t', header=true, "
            f"auto_detect=true, all_varchar=true)"
        ).fetchall()
    ]
    print(f"  required S1 test entities: {len(required_s1):,}")

    # ---- candidate_pairs.tsv: the blocking union, as-is -------------------
    cand_df = con.execute(
        f"SELECT source1_entity_id, candidate_entity_id "
        f"FROM read_parquet('{config.candidates_path('test')}')"
    ).fetchdf()
    cand_by_entity = (
        cand_df.groupby("source1_entity_id")["candidate_entity_id"].apply(list).to_dict()
        if not cand_df.empty else {}
    )
    _write_id_list_tsv(
        config.CANDIDATE_OUTPUT,
        ["source1_entity_id", "candidate_entity_ids"],
        required_s1,
        cand_by_entity,
    )
    print(f"  wrote {config.CANDIDATE_OUTPUT}")

    # ---- matching_results.tsv: score every candidate, threshold, group ----
    model = xgb.XGBClassifier()
    model.load_model(config.MODEL_PATH)

    with open(config.THRESHOLD_PATH) as f:
        threshold = json.load(f)["threshold"]

    feat_df = con.execute("SELECT * FROM test_features").fetchdf()
    if feat_df.empty:
        print("  WARNING: test_features is empty; matching_results.tsv will have no matches.")
        matches_by_entity = {}
    else:
        feat_df["score"] = model.predict_proba(feat_df[config.FEATURE_COLUMNS])[:, 1]
        accepted = feat_df[feat_df["score"] >= threshold]
        matches_by_entity = (
            accepted.groupby("source1_entity_id")["candidate_entity_id"].apply(list).to_dict()
            if not accepted.empty else {}
        )

    # Assert (don't just assume) that every match is one of that entity's own
    # candidates, mirroring the validator's soft cross-check but as a hard
    # stop here — if this ever fires it's a pipeline bug, not a data issue.
    for ent, ids in matches_by_entity.items():
        bad = set(ids) - set(cand_by_entity.get(ent, []))
        if bad:
            raise RuntimeError(
                f"Pipeline bug: {ent} has matched id(s) {bad} absent from its "
                "own candidate set. Aborting before writing an invalid submission."
            )

    _write_id_list_tsv(
        config.MATCHING_OUTPUT,
        ["source1_entity_id", "matched_entity_ids"],
        required_s1,
        matches_by_entity,
    )
    print(f"  wrote {config.MATCHING_OUTPUT}  (threshold={threshold})")
