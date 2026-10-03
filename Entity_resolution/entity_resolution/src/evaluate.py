"""
Stage 5: Threshold selection.

Sweeps a probability threshold and picks the one that maximizes the metric
actually used for scoring: macro-averaged F0.5 over Source-1 *entities*,
including entities with zero predicted matches (correctly predicting a
singleton scores 1.0; this is why the sweep must operate at the entity
level, not the pair level — a pair-level metric like AUC doesn't capture
that empty-list singleton credit or the double per-entity averaging).
"""
import json

import config


def _f_beta(precision, recall, beta=0.5):
    if precision == 0 and recall == 0:
        return 0.0
    b2 = beta ** 2
    denom = b2 * precision + recall
    if denom == 0:
        return 0.0
    return (1 + b2) * precision * recall / denom


def _macro_f05(pred_by_entity, true_by_entity, all_entities):
    scores = []
    for ent in all_entities:
        pred = pred_by_entity.get(ent, set())
        true = true_by_entity.get(ent, set())
        if not pred and not true:
            scores.append(1.0)  # correctly predicted singleton
            continue
        if not pred:
            scores.append(0.0)  # missed every true match
            continue
        tp = len(pred & true)
        precision = tp / len(pred)
        recall = tp / len(true) if true else 0.0
        scores.append(_f_beta(precision, recall))
    return sum(scores) / len(scores) if scores else 0.0


def run(con, valid_df):
    """valid_df: the scored validation dataframe produced by train.run()
    (one row per candidate *pair*, with a 'score' column)."""
    valid_entities = valid_df["source1_entity_id"].unique().tolist()
    id_list = ",".join(f"'{e}'" for e in valid_entities)

    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE gt_valid AS
        SELECT source1_entity_id, TRIM(m) AS candidate_entity_id
        FROM (
            SELECT source1_entity_id,
                   UNNEST(string_split(coalesce(matched_entity_ids, ''), ',')) AS m
            FROM read_csv(
                '{config.TRAIN_GT}', delim='\t', header=true,
                auto_detect=true, all_varchar=true
            )
        )
        WHERE TRIM(m) <> '' AND source1_entity_id IN ({id_list})
    """)
    gt_df = con.execute("SELECT * FROM gt_valid").fetchdf()
    true_by_entity = (
        gt_df.groupby("source1_entity_id")["candidate_entity_id"].apply(set).to_dict()
        if not gt_df.empty else {}
    )

    best_t, best_f05 = None, -1.0
    for t in config.THRESHOLD_SWEEP:
        above = valid_df[valid_df["score"] >= t]
        pred_by_entity = (
            above.groupby("source1_entity_id")["candidate_entity_id"].apply(set).to_dict()
            if not above.empty else {}
        )
        f05 = _macro_f05(pred_by_entity, true_by_entity, valid_entities)
        if f05 > best_f05:
            best_f05, best_t = f05, t

    print(f"  best threshold = {best_t}  (macro-F0.5 = {best_f05:.4f} on validation)")
    with open(config.THRESHOLD_PATH, "w") as f:
        json.dump({"threshold": best_t, "macro_f05": best_f05}, f, indent=2)
    return best_t, best_f05
