"""
Stage 4: Train the matcher.

Splits by Source-1 *entity*, not by pair, so correlated candidates of the
same entity never leak across train/validation. A pair-level random split
would let near-duplicate candidates land on both sides and make the
validation number lie to you (this was flagged as a real risk earlier —
"tune ... against the actual macro-F0.5 formula on a source1-entity-level
stratified holdout, not a random pair-level split").
"""
import json

import xgboost as xgb
from sklearn.model_selection import train_test_split

import config


def _label_pairs(con, features_table, ground_truth_path):
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
    con.execute(f"""
        CREATE OR REPLACE TABLE labeled_pairs AS
        SELECT f.*, CASE WHEN g.candidate_entity_id IS NOT NULL THEN 1 ELSE 0 END AS label
        FROM {features_table} f
        LEFT JOIN gt_pairs g
          ON f.source1_entity_id = g.source1_entity_id
         AND f.candidate_entity_id = g.candidate_entity_id
    """)
    return con.execute("SELECT * FROM labeled_pairs").fetchdf()


def run(con):
    df = _label_pairs(con, "train_features", config.TRAIN_GT)
    if df.empty:
        raise RuntimeError(
            "No training pairs found. Did you run `normalize`, `block` and "
            "`features` for the train split first?"
        )

    entities = df["source1_entity_id"].unique()
    train_ents, valid_ents = train_test_split(
        entities, test_size=config.VALID_FRACTION, random_state=config.RANDOM_SEED
    )
    train_df = df[df["source1_entity_id"].isin(train_ents)]
    valid_df = df[df["source1_entity_id"].isin(valid_ents)].copy()

    X_train, y_train = train_df[config.FEATURE_COLUMNS], train_df["label"]
    X_valid, y_valid = valid_df[config.FEATURE_COLUMNS], valid_df["label"]

    pos = max(int(y_train.sum()), 1)
    neg = max(int((y_train == 0).sum()), 1)
    scale_pos_weight = neg / pos
    print(
        f"  train pairs: {len(train_df):,} ({pos:,} positive, {neg:,} negative, "
        f"scale_pos_weight={scale_pos_weight:.2f})"
    )

    model = xgb.XGBClassifier(
        **config.XGB_PARAMS,
        scale_pos_weight=scale_pos_weight,
        random_state=config.RANDOM_SEED,
    )
    model.fit(X_train, y_train, eval_set=[(X_valid, y_valid)], verbose=False)
    model.save_model(config.MODEL_PATH)
    print(f"  model saved -> {config.MODEL_PATH}")

    valid_df["score"] = model.predict_proba(X_valid)[:, 1]
    valid_df.to_parquet(config.VALID_SCORED_PATH)
    print(
        f"  validation scores saved -> {config.VALID_SCORED_PATH} "
        f"({valid_df['source1_entity_id'].nunique():,} S1 entities)"
    )
    return valid_df
