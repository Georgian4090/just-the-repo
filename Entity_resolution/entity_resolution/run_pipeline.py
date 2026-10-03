#!/usr/bin/env python3
"""
CLI entry point for the pipeline.

    python run_pipeline.py normalize  [train|test|all]
    python run_pipeline.py block      [train|test|all]
    python run_pipeline.py recall                        # train-only, needs block already run
    python run_pipeline.py features   [train|test|all]
    python run_pipeline.py train                          # trains + saves validation scores
    python run_pipeline.py evaluate                        # threshold sweep on saved val scores
    python run_pipeline.py infer                            # writes output/*.tsv
    python run_pipeline.py all                                # normalize -> infer, end to end

Run `all` for a first end-to-end pass on your machine; after that, re-run
individual stages as you iterate (e.g. just `block` after changing
config.TOKEN_MAX_DF, or `train` + `evaluate` after changing model params).
Each stage reads from Parquet/JSON the previous stage wrote, so stages don't
need to be re-run from scratch unless their own inputs changed.
"""
import argparse
import sys

import pandas as pd

import config
from src import db, normalize, blocking, features, train, evaluate, infer


def _load_norm_tables(con, split):
    for tbl, path in (
        (f"{split}_s1_norm", config.norm_path(split, "s1")),
        (f"{split}_s2_norm", config.norm_path(split, "s2")),
        (f"{split}_s3_norm", config.norm_path(split, "s3")),
    ):
        con.execute(f"CREATE OR REPLACE TABLE {tbl} AS SELECT * FROM read_parquet('{path}')")


def cmd_normalize(con, split):
    for s in (["train", "test"] if split == "all" else [split]):
        normalize.run(con, s)


def cmd_block(con, split):
    for s in (["train", "test"] if split == "all" else [split]):
        _load_norm_tables(con, s)
        blocking.build_candidates(con, s)


def cmd_recall(con):
    con.execute(
        f"CREATE OR REPLACE TABLE train_candidates AS "
        f"SELECT * FROM read_parquet('{config.candidates_path('train')}')"
    )
    blocking.measure_recall(con, "train", config.TRAIN_GT)


def cmd_features(con, split):
    for s in (["train", "test"] if split == "all" else [split]):
        _load_norm_tables(con, s)
        con.execute(
            f"CREATE OR REPLACE TABLE {s}_candidates AS "
            f"SELECT * FROM read_parquet('{config.candidates_path(s)}')"
        )
        out_table = "train_features" if s == "train" else "test_features"
        out_path = config.FEATURES_PATH_TRAIN if s == "train" else config.FEATURES_PATH_TEST
        features.compute_features(
            con, s, f"{s}_candidates", f"{s}_s1_norm", f"{s}_s2_norm", f"{s}_s3_norm", out_table
        )
        con.execute(f"COPY {out_table} TO '{out_path}' (FORMAT PARQUET, COMPRESSION ZSTD)")


def cmd_train(con):
    con.execute(
        f"CREATE OR REPLACE TABLE train_features AS "
        f"SELECT * FROM read_parquet('{config.FEATURES_PATH_TRAIN}')"
    )
    return train.run(con)


def cmd_evaluate(con, valid_df):
    return evaluate.run(con, valid_df)


def cmd_infer(con):
    con.execute(
        f"CREATE OR REPLACE TABLE test_features AS "
        f"SELECT * FROM read_parquet('{config.FEATURES_PATH_TEST}')"
    )
    infer.run(con)


def main():
    parser = argparse.ArgumentParser(description="Entity Resolution pipeline")
    parser.add_argument(
        "stage",
        choices=["normalize", "block", "recall", "features", "train", "evaluate", "infer", "all"],
    )
    parser.add_argument("split", nargs="?", default="all", choices=["train", "test", "all"])
    args = parser.parse_args()

    con = db.get_connection()
    try:
        if args.stage == "normalize":
            cmd_normalize(con, args.split)
        elif args.stage == "block":
            cmd_block(con, args.split)
        elif args.stage == "recall":
            cmd_recall(con)
        elif args.stage == "features":
            cmd_features(con, args.split)
        elif args.stage == "train":
            cmd_train(con)
        elif args.stage == "evaluate":
            valid_df = pd.read_parquet(config.VALID_SCORED_PATH)
            cmd_evaluate(con, valid_df)
        elif args.stage == "infer":
            cmd_infer(con)
        elif args.stage == "all":
            print("[1/6] normalize"); cmd_normalize(con, "all")
            print("[2/6] block"); cmd_block(con, "all")
            print("[3/6] recall check (train)"); cmd_recall(con)
            print("[4/6] features"); cmd_features(con, "all")
            print("[5/6] train + evaluate")
            valid_df = cmd_train(con)
            cmd_evaluate(con, valid_df)
            print("[6/6] infer"); cmd_infer(con)
            print("\nDone. See output/matching_results.tsv and output/candidate_pairs.tsv")
            print("Validate before submitting:")
            print(
                "  python utils/validate_submission.py --matching output/matching_results.tsv "
                "--candidate output/candidate_pairs.tsv --test-dir dataset/test"
            )
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
