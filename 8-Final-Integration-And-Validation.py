# 8-Final-Integration-And-Validation.py

from datetime import datetime
from pathlib import Path
import re

import pandas as pd


RESULTS_DIR = Path("data/results")
OUT_DIR = RESULTS_DIR / "descriptives"
STEP7_DIR = OUT_DIR / "step7_residual_classification"
FINAL_DIR = RESULTS_DIR / "final"
VALIDATION_DIR = FINAL_DIR / "validation_samples"
FINAL_DIR.mkdir(parents=True, exist_ok=True)
VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

LONG_FILE = OUT_DIR / "merged_mapped_long_no20f.csv"
STEP7_CLASSIFIED_FILE = STEP7_DIR / "step7_llm_residual_classified.csv"
MANUAL_ALIAS_FILE = Path("data/dictionaries/manual_alias_bridge.csv")


def safe_to_csv(df, path, index=False):
    path = Path(path)
    try:
        df.to_csv(path, index=index)
        return path
    except PermissionError:
        fallback = path.with_name(f"{path.stem}_{datetime.now():%Y%m%d_%H%M%S}{path.suffix}")
        df.to_csv(fallback, index=index)
        print(f"Permission denied writing {path}; wrote {fallback} instead.")
        return fallback


def normalize_key(x):
    x = "" if pd.isna(x) else str(x)
    x = re.sub(r"\s+", " ", x.strip().upper())
    return x


def is_valid_id(x):
    return str(x).strip() not in {"", "-1", "nan", "None", "NaN"}


def first_existing(row, columns, default=""):
    for col in columns:
        if col in row and not pd.isna(row[col]) and str(row[col]).strip() != "":
            return row[col]
    return default


def prepare_alias_bridge(path):
    if not path.exists():
        return pd.DataFrame()

    alias = pd.read_csv(path)
    if alias.empty:
        return alias

    alias["alias_key"] = ""
    if "competitor_name_standardized" in alias.columns:
        alias["alias_key"] = alias["competitor_name_standardized"].apply(normalize_key)
    elif "alias_name_standardized" in alias.columns:
        alias["alias_key"] = alias["alias_name_standardized"].apply(normalize_key)
    elif "alias_name" in alias.columns:
        alias["alias_key"] = alias["alias_name"].apply(normalize_key)
    elif "competitor_name" in alias.columns:
        alias["alias_key"] = alias["competitor_name"].apply(normalize_key)

    alias = alias[alias["alias_key"] != ""].copy()
    alias = alias.drop_duplicates(subset=["alias_key"], keep="first")
    return alias


def main():
    if not LONG_FILE.exists():
        raise FileNotFoundError(f"Missing Step 6 long mapped file: {LONG_FILE}")

    long = pd.read_csv(LONG_FILE)

    if STEP7_CLASSIFIED_FILE.exists():
        step7 = pd.read_csv(STEP7_CLASSIFIED_FILE)
    else:
        step7 = pd.DataFrame()

    if not step7.empty:
        step7_cols = [
            "competitor_name",
            "competitor_name_standardized",
            "llm_classification",
            "llm_decision",
            "llm_confidence",
            "llm_reason",
        ]
        step7 = step7[[c for c in step7_cols if c in step7.columns]].drop_duplicates(
            subset=["competitor_name", "competitor_name_standardized"],
            keep="first",
        )
        long = long.merge(
            step7,
            on=["competitor_name", "competitor_name_standardized"],
            how="left",
        )
    else:
        for col in ["llm_classification", "llm_decision", "llm_confidence", "llm_reason"]:
            long[col] = ""

    long["final_competitor_name_standardized"] = long["competitor_name_standardized"]
    long["final_competitor_cik"] = long["competitor_cik"]
    long["final_competitor_gvkey"] = long["competitor_gvkey"]
    long["final_match_source"] = long["competitor_match_source"]
    long["final_match_method"] = long["competitor_match_method"]
    long["final_match_stage"] = "step5_mapping"

    unmatched_mask = (~long["final_competitor_cik"].apply(is_valid_id)) & (~long["final_competitor_gvkey"].apply(is_valid_id))
    long.loc[unmatched_mask, "final_match_stage"] = "unmatched_after_step5"

    alias = prepare_alias_bridge(MANUAL_ALIAS_FILE)
    if not alias.empty:
        long["alias_key"] = long["competitor_name_standardized"].apply(normalize_key)
        alias_lookup = alias.set_index("alias_key")

        for idx in long[unmatched_mask].index:
            key = long.at[idx, "alias_key"]
            if key not in alias_lookup.index:
                continue

            row = alias_lookup.loc[key]
            long.at[idx, "final_competitor_name_standardized"] = first_existing(
                row,
                ["standardized_competitor_name", "competitor_name_standardized", "standard_name", "matched_name"],
                long.at[idx, "competitor_name_standardized"],
            )
            long.at[idx, "final_competitor_cik"] = first_existing(row, ["cik", "CIK", "competitor_cik"], "-1")
            long.at[idx, "final_competitor_gvkey"] = first_existing(row, ["gvkey", "GVKEY", "competitor_gvkey"], "-1")
            long.at[idx, "final_match_source"] = first_existing(row, ["source", "match_source"], "manual_alias_bridge")
            long.at[idx, "final_match_method"] = first_existing(row, ["method", "match_method"], "manual_alias_bridge")
            long.at[idx, "final_match_stage"] = "manual_alias_bridge"

        long = long.drop(columns=["alias_key"])

    long["final_has_cik"] = long["final_competitor_cik"].apply(is_valid_id)
    long["final_has_gvkey"] = long["final_competitor_gvkey"].apply(is_valid_id)
    long["final_has_any_identifier"] = long["final_has_cik"] | long["final_has_gvkey"]

    final_unmatched = long[~long["final_has_any_identifier"]].copy()
    final_alias_candidates = long[
        (~long["final_has_any_identifier"]) &
        (long["llm_decision"] == "accept_for_manual_alias_bridge")
    ].copy()

    summary = pd.DataFrame({
        "metric": [
            "total_mentions",
            "final_mentions_with_cik",
            "final_mentions_with_gvkey",
            "final_mentions_with_any_identifier",
            "final_unmatched_mentions",
            "manual_alias_bridge_applied_mentions",
            "manual_alias_bridge_candidate_mentions",
        ],
        "value": [
            len(long),
            long["final_has_cik"].sum(),
            long["final_has_gvkey"].sum(),
            long["final_has_any_identifier"].sum(),
            len(final_unmatched),
            (long["final_match_stage"] == "manual_alias_bridge").sum(),
            len(final_alias_candidates),
        ],
    })

    safe_to_csv(long, FINAL_DIR / "final_competitor_mentions_long.csv", index=False)
    safe_to_csv(summary, FINAL_DIR / "final_mapping_summary.csv", index=False)
    safe_to_csv(final_unmatched, FINAL_DIR / "final_unmatched_review.csv", index=False)
    safe_to_csv(final_alias_candidates, FINAL_DIR / "final_manual_alias_bridge_candidates.csv", index=False)

    matched = long[long["final_has_any_identifier"]].copy()
    if not matched.empty:
        safe_to_csv(matched.sample(n=min(100, len(matched)), random_state=42), VALIDATION_DIR / "final_matched_sample.csv", index=False)
    if not final_unmatched.empty:
        safe_to_csv(final_unmatched.sample(n=min(100, len(final_unmatched)), random_state=42), VALIDATION_DIR / "final_unmatched_sample.csv", index=False)
    if not final_alias_candidates.empty:
        safe_to_csv(
            final_alias_candidates.sample(n=min(100, len(final_alias_candidates)), random_state=42),
            VALIDATION_DIR / "final_manual_alias_candidate_sample.csv",
            index=False,
        )

    print("Step 8 completed. Outputs saved in:", FINAL_DIR)


if __name__ == "__main__":
    main()
