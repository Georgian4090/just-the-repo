"""
Central configuration for the Entity Resolution pipeline.

Every path, hyperparameter and threshold lives here so nothing is hardcoded
inside src/*.py. Override paths with environment variables when you move
machines instead of editing this file, e.g.:

    export ER_DATA_ROOT=/mnt/d/amazon-ml-challenge/dataset
"""
import os

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

DATA_ROOT = os.environ.get("ER_DATA_ROOT", os.path.join(PROJECT_ROOT, "dataset"))
TRAIN_DIR = os.path.join(DATA_ROOT, "train")
TEST_DIR = os.path.join(DATA_ROOT, "test")
PROCESSED_DIR = os.environ.get("ER_PROCESSED_DIR", os.path.join(DATA_ROOT, "processed"))
MODEL_DIR = os.path.join(PROJECT_ROOT, "models")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

for _d in (PROCESSED_DIR, MODEL_DIR, OUTPUT_DIR):
    os.makedirs(_d, exist_ok=True)

TRAIN_S1 = os.path.join(TRAIN_DIR, "train_source1.tsv")
TRAIN_S2 = os.path.join(TRAIN_DIR, "train_source2.tsv")
TRAIN_S3 = os.path.join(TRAIN_DIR, "train_source3.tsv")
TRAIN_GT = os.path.join(TRAIN_DIR, "train_ground_truth.tsv")

TEST_S1 = os.path.join(TEST_DIR, "test_source1.tsv")
TEST_S2 = os.path.join(TEST_DIR, "test_source2.tsv")
TEST_S3 = os.path.join(TEST_DIR, "test_source3.tsv")


def norm_path(split, source):
    """Normalized parquet path for a given split ('train'/'test') and source
    ('s1'/'s2'/'s3')."""
    return os.path.join(PROCESSED_DIR, f"{split}_{source}_norm.parquet")


def candidates_path(split):
    """Candidate-pairs parquet path for a given split."""
    return os.path.join(PROCESSED_DIR, f"{split}_candidates.parquet")


FEATURES_PATH_TRAIN = os.path.join(PROCESSED_DIR, "train_features.parquet")
FEATURES_PATH_TEST = os.path.join(PROCESSED_DIR, "test_features.parquet")
VALID_SCORED_PATH = os.path.join(PROCESSED_DIR, "valid_scored.parquet")

MODEL_PATH = os.path.join(MODEL_DIR, "xgb_matcher.json")
THRESHOLD_PATH = os.path.join(MODEL_DIR, "threshold.json")

MATCHING_OUTPUT = os.path.join(OUTPUT_DIR, "matching_results.tsv")
CANDIDATE_OUTPUT = os.path.join(OUTPUT_DIR, "candidate_pairs.tsv")

# ---------------------------------------------------------------------------
# Blocking
# ---------------------------------------------------------------------------
# Minimum digits required before the address-digits block is trusted (a
# 1-2 digit match is coincidence, not signal).
MIN_ADDRESS_DIGITS = 4

# A name token used as a blocking key must appear in at most this many
# records within its (source, country) bucket, or it's a generic category
# word (e.g. "pediatric", "limited", "private") rather than an identifying
# one, and gets excluded from the rare-token block. Computed from the data
# itself (document frequency), not a fixed stopword list.
TOKEN_MAX_DF = 50
TOKEN_MIN_LEN = 3  # ignore very short tokens; they're rarely discriminative

# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------
FEATURE_COLUMNS = [
    "country_exact",
    "name_exact",
    "token_exact",
    "name_jw",
    "name_lev",
    "name_length_diff",
    "address_exact",
    "address_jw",
    "address_lev",
    "address_digits_exact",
    "name_prefix5",
    "name_prefix8",
    "name_romanized_jw",
]

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
XGB_PARAMS = dict(
    n_estimators=600,
    max_depth=8,
    learning_rate=0.04,
    tree_method="hist",
    eval_metric="aucpr",
    n_jobs=max(1, os.cpu_count() or 4),
)

# Split by S1 *entity*, not by pair — a pair-level random split would let
# correlated candidates of the same entity land on both sides of the split
# and make validation numbers look better than they really are.
VALID_FRACTION = 0.15
RANDOM_SEED = 42

THRESHOLD_SWEEP = [round(0.05 + 0.01 * i, 2) for i in range(91)]  # 0.05 .. 0.95

# ---------------------------------------------------------------------------
# Runtime (tuned for a 12GB RAM local machine — override via env vars on a
# different machine rather than editing this file)
# ---------------------------------------------------------------------------
DUCKDB_MEMORY_LIMIT = os.environ.get("ER_DUCKDB_MEMORY", "8GB")
DUCKDB_THREADS = int(os.environ.get("ER_DUCKDB_THREADS", os.cpu_count() or 4))
