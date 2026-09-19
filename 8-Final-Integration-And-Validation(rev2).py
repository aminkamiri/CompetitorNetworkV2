# 8-Final-Integration-And-Validation(rev2).py

from datetime import datetime
from pathlib import Path
import re

import pandas as pd


RESULTS_DIR = Path("data/results")
OUT_DIR = RESULTS_DIR / "descriptives"
STEP7_DIR = OUT_DIR / "step7_residual_classification"
FINAL_DIR = RESULTS_DIR / "final"
VALIDATION_DIR = FINAL_DIR / "validation_samples"

LONG_FILE = OUT_DIR / "merged_mapped_long_no20f.csv"
STEP7_CLASSIFIED_FILE = STEP7_DIR / "step7_llm_residual_classified.csv"
MANUAL_ALIAS_FILE = Path("data/dictionaries/manual_alias_bridge.csv")

STEP7_COLUMNS = [
    "llm_classification",
    "llm_decision",
    "llm_confidence",
    "llm_reason",
    "needs_manual_check",
    "suggested_alias_name",
    "suggested_alias_scope",
    "suggested_alias_reason",
]

STEP7_REVIEW_COLUMNS = [
    "frequency",
    "sic_files",
    "years",
    "example_filename",
]

FINAL_STAGE_ORDER = [
    "step5_mapped",
    "manual_alias_bridge_applied",
    "llm_dropped_residual",
    "llm_alias_candidate_unresolved",
    "llm_manual_review_unresolved",
    "unmatched_no_step7_classification",
]


def safe_to_csv(df, path, index=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_csv(path, index=index)
        return path
    except PermissionError:
        fallback = path.with_name(f"{path.stem}_{datetime.now():%Y%m%d_%H%M%S}{path.suffix}")
        df.to_csv(fallback, index=index)
        print(f"Permission denied writing {path}; wrote {fallback} instead.")
        return fallback


def normalize_key(value):
    value = "" if pd.isna(value) else str(value)
    value = re.sub(r"[^A-Z0-9]+", " ", value.upper())
    return re.sub(r"\s+", " ", value).strip()


def make_merge_key(row):
    standardized = normalize_key(row.get("competitor_name_standardized", ""))
    if standardized:
        return standardized
    return normalize_key(row.get("competitor_name", ""))


def is_valid_id(value):
    text = "" if pd.isna(value) else str(value).strip()
    return text.lower() not in {"", "-1", "nan", "none", "null"}


def first_existing(row, columns, default=""):
    for col in columns:
        if col in row.index:
            value = row[col]
            if not pd.isna(value) and str(value).strip() != "":
                return value
    return default


def ensure_columns(df, columns, default=""):
    for col in columns:
        if col not in df.columns:
            df[col] = default
    return df


def add_manual_columns(df):
    df = df.copy()
    df["manual_validation"] = ""
    df["notes"] = ""
    return df


def sample_with_notes(df, path, n=100):
    sample = df.copy()
    if sample.empty:
        sample = add_manual_columns(sample)
    else:
        sample = sample.sample(n=min(n, len(sample)), random_state=42)
        sample = add_manual_columns(sample)
    safe_to_csv(sample, path, index=False)


def build_step7_lookup(step7):
    if step7.empty:
        return pd.DataFrame()

    step7 = ensure_columns(step7.copy(), STEP7_COLUMNS + STEP7_REVIEW_COLUMNS, "")
    missing = [col for col in ["competitor_name"] if col not in step7.columns]
    if missing:
        raise ValueError(f"Step 7 file is missing required merge columns: {missing}")

    step7["merge_key"] = step7.apply(make_merge_key, axis=1)
    step7 = step7[step7["merge_key"] != ""].copy()

    if "frequency" in step7.columns:
        step7["_frequency_sort"] = pd.to_numeric(step7["frequency"], errors="coerce").fillna(0)
    else:
        step7["_frequency_sort"] = 0
    step7 = step7.sort_values("_frequency_sort", ascending=False)

    keep_cols = (
        ["merge_key"]
        + STEP7_COLUMNS
        + STEP7_REVIEW_COLUMNS
    )
    step7 = step7[keep_cols].drop_duplicates(subset=["merge_key"], keep="first")
    return step7


def load_step7():
    if not STEP7_CLASSIFIED_FILE.exists():
        return pd.DataFrame()
    return pd.read_csv(STEP7_CLASSIFIED_FILE)


def alias_bridge_value(row, candidates, default=""):
    return first_existing(row, candidates, default=default)


def prepare_alias_bridge(path):
    if not path.exists():
        return pd.DataFrame()

    alias = pd.read_csv(path)
    if alias.empty:
        return alias

    alias = alias.copy()
    key_source_cols = [
        "competitor_name",
        "competitor_name_standardized",
        "alias_name",
        "alias_name_standardized",
        "suggested_alias_name",
        "approved_alias_name",
    ]

    records = []
    for _, row in alias.iterrows():
        for key_col in key_source_cols:
            if key_col not in alias.columns:
                continue
            key = normalize_key(row[key_col])
            if key == "":
                continue
            record = row.to_dict()
            record["alias_lookup_key"] = key
            record["alias_lookup_key_source"] = key_col
            records.append(record)

    if not records:
        return pd.DataFrame()

    expanded = pd.DataFrame(records)
    expanded = expanded.drop_duplicates(subset=["alias_lookup_key"], keep="first")
    return expanded


def candidate_keys_for_row(row):
    keys = []
    for col in ["competitor_name", "competitor_name_standardized", "suggested_alias_name"]:
        if col in row.index:
            key = normalize_key(row[col])
            if key and key not in keys:
                keys.append(key)
    return keys


def apply_manual_alias_bridge(long, alias):
    long = long.copy()
    long["manual_alias_bridge_source"] = ""
    long["manual_alias_lookup_key"] = ""
    long["manual_alias_lookup_key_source"] = ""
    long["manual_alias_bridge_applied"] = False

    if alias.empty:
        return long, 0

    alias_lookup = alias.set_index("alias_lookup_key", drop=False)
    applied = 0

    unmatched_mask = ~long["step5_has_any_identifier"]
    for idx, row in long.loc[unmatched_mask].iterrows():
        selected = None
        selected_key = ""
        for key in candidate_keys_for_row(row):
            if key in alias_lookup.index:
                selected = alias_lookup.loc[key]
                selected_key = key
                break
        if selected is None:
            continue

        long.at[idx, "final_competitor_name_standardized"] = alias_bridge_value(
            selected,
            [
                "approved_alias_name",
                "standardized_competitor_name",
                "competitor_name_standardized",
                "standard_name",
                "matched_name",
            ],
            row.get("competitor_name_standardized", ""),
        )
        long.at[idx, "final_competitor_cik"] = alias_bridge_value(
            selected,
            ["approved_cik", "cik", "CIK", "competitor_cik"],
            "-1",
        )
        long.at[idx, "final_competitor_gvkey"] = alias_bridge_value(
            selected,
            ["approved_gvkey", "gvkey", "GVKEY", "competitor_gvkey"],
            "-1",
        )
        long.at[idx, "final_match_source"] = alias_bridge_value(
            selected,
            ["approved_source", "source", "match_source"],
            "manual_alias_bridge",
        )
        long.at[idx, "final_match_method"] = alias_bridge_value(
            selected,
            ["approved_method", "method", "match_method"],
            "manual_alias_bridge",
        )
        long.at[idx, "manual_alias_bridge_source"] = alias_bridge_value(
            selected,
            ["approved_source", "source", "match_source"],
            "manual_alias_bridge",
        )
        long.at[idx, "manual_alias_lookup_key"] = selected_key
        long.at[idx, "manual_alias_lookup_key_source"] = alias_bridge_value(
            selected,
            ["alias_lookup_key_source"],
            "",
        )
        long.at[idx, "manual_alias_bridge_applied"] = True
        applied += 1

    return long, applied


def collapse_values(values):
    clean = []
    for value in values:
        if pd.isna(value):
            continue
        text = str(value).strip()
        if text and text not in clean:
            clean.append(text)
    return "; ".join(clean)


def build_alias_candidates(long):
    candidates = long[
        (~long["step5_has_any_identifier"])
        & (long["llm_decision"] == "accept_for_manual_alias_bridge")
    ].copy()
    requested_cols = [
        "competitor_name",
        "competitor_name_standardized",
        "suggested_alias_name",
        "suggested_alias_scope",
        "frequency",
        "sic_files",
        "years",
        "example_filename",
        "llm_classification",
        "llm_confidence",
        "llm_reason",
        "suggested_alias_reason",
    ]
    out = ensure_columns(candidates, requested_cols, "")[requested_cols].copy()

    for col in [
        "manual_alias_decision",
        "approved_alias_name",
        "approved_cik",
        "approved_gvkey",
        "approved_source",
        "reviewer_notes",
    ]:
        out[col] = ""
    return out


def mode_values(values):
    clean = [str(v).strip() for v in values if not pd.isna(v) and str(v).strip() != ""]
    if not clean:
        return ""
    counts = pd.Series(clean).value_counts()
    modes = counts[counts == counts.max()].index.tolist()
    return "; ".join(modes)


def build_aggregated_alias_candidates(long):
    candidates = long[
        (~long["step5_has_any_identifier"])
        & (long["llm_decision"] == "accept_for_manual_alias_bridge")
    ].copy()
    candidates = ensure_columns(
        candidates,
        [
            "merge_key",
            "competitor_name",
            "suggested_alias_name",
            "suggested_alias_scope",
            "frequency",
            "sic_files",
            "years",
            "llm_classification",
            "llm_confidence",
        ],
        "",
    )
    out_cols = [
        "suggested_alias_name",
        "suggested_alias_scope",
        "frequency_sum",
        "n_unique_raw_names",
        "raw_name_examples",
        "sic_files",
        "years",
        "llm_classification_modes",
        "llm_confidence_mean",
        "manual_alias_decision",
        "approved_alias_name",
        "approved_cik",
        "approved_gvkey",
        "approved_source",
        "reviewer_notes",
    ]
    if candidates.empty:
        return pd.DataFrame(columns=out_cols)

    unique_candidates = candidates.drop_duplicates(subset=["merge_key"], keep="first").copy()
    unique_candidates["_frequency_numeric"] = pd.to_numeric(
        unique_candidates["frequency"], errors="coerce"
    ).fillna(0)
    unique_candidates["_llm_confidence_numeric"] = pd.to_numeric(
        unique_candidates["llm_confidence"], errors="coerce"
    )

    grouped = (
        unique_candidates.groupby(["suggested_alias_name", "suggested_alias_scope"], dropna=False)
        .agg(
            frequency_sum=("_frequency_numeric", "sum"),
            n_unique_raw_names=("competitor_name", "nunique"),
            raw_name_examples=("competitor_name", lambda x: "; ".join(list(dict.fromkeys([str(v) for v in x if not pd.isna(v)]))[:10])),
            sic_files=("sic_files", collapse_values),
            years=("years", collapse_values),
            llm_classification_modes=("llm_classification", mode_values),
            llm_confidence_mean=("_llm_confidence_numeric", "mean"),
        )
        .reset_index()
        .sort_values("frequency_sum", ascending=False)
    )
    grouped["llm_confidence_mean"] = grouped["llm_confidence_mean"].round(2)
    for col in [
        "manual_alias_decision",
        "approved_alias_name",
        "approved_cik",
        "approved_gvkey",
        "approved_source",
        "reviewer_notes",
    ]:
        grouped[col] = ""
    return grouped[out_cols]


def first_nonblank(values):
    for value in values:
        if not pd.isna(value) and str(value).strip() != "":
            return value
    return ""


def first_nonblank_or_count(values, fallback_count):
    value = first_nonblank(values)
    return value if value != "" else fallback_count


def build_summary(long, alias_applied_count, step7_rows):
    rows = [
        ("total_mentions", len(long)),
        ("step7_classified_rows_available", step7_rows),
        ("final_mentions_with_cik", int(long["final_has_cik"].sum())),
        ("final_mentions_with_gvkey", int(long["final_has_gvkey"].sum())),
        ("final_mentions_with_any_identifier", int(long["final_has_any_identifier"].sum())),
        ("final_unmatched_mentions", int((~long["final_has_any_identifier"]).sum())),
        ("manual_alias_bridge_applied_mentions", alias_applied_count),
    ]
    for stage in FINAL_STAGE_ORDER:
        rows.append((f"final_stage_{stage}", int((long["final_match_stage"] == stage).sum())))
    return pd.DataFrame(rows, columns=["metric", "value"])


def print_step7_merge_diagnostics(long, step7_lookup):
    step5_unmatched = ~long["step5_has_any_identifier"]
    unmatched = long[step5_unmatched].copy()
    with_classification = unmatched["llm_decision"].fillna("").astype(str).str.strip() != ""
    print("Step 7 merge diagnostics")
    print(f"Total Step 6 long rows: {len(long)}")
    print(f"Unmatched Step 6 rows before Step 7: {int(step5_unmatched.sum())}")
    print(f"Step 7 unique merge keys: {len(step7_lookup)}")
    print(f"Unmatched rows with Step 7 classification: {int(with_classification.sum())}")
    print(f"Unmatched rows without Step 7 classification: {int((~with_classification).sum())}")
    print("Value counts of llm_decision among unmatched rows:")
    print(unmatched["llm_decision"].fillna("").replace("", "(missing)").value_counts(dropna=False).to_string())


def main():
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

    if not LONG_FILE.exists():
        raise FileNotFoundError(f"Missing Step 6 long mapped file: {LONG_FILE}")

    long = pd.read_csv(LONG_FILE)
    required_long_cols = [
        "competitor_name",
        "competitor_name_standardized",
        "competitor_cik",
        "competitor_gvkey",
        "competitor_match_source",
        "competitor_match_method",
    ]
    missing = [col for col in required_long_cols if col not in long.columns]
    if missing:
        raise ValueError(f"Step 6 long file is missing required columns: {missing}")

    step7_raw = load_step7()
    step7_lookup = build_step7_lookup(step7_raw) if not step7_raw.empty else pd.DataFrame()

    long["merge_key"] = long.apply(make_merge_key, axis=1)

    if not step7_lookup.empty:
        long = long.merge(step7_lookup, on="merge_key", how="left")
    long = ensure_columns(long, STEP7_COLUMNS + STEP7_REVIEW_COLUMNS, "")

    long["step5_has_cik"] = long["competitor_cik"].apply(is_valid_id)
    long["step5_has_gvkey"] = long["competitor_gvkey"].apply(is_valid_id)
    long["step5_has_any_identifier"] = long["step5_has_cik"] | long["step5_has_gvkey"]
    print_step7_merge_diagnostics(long, step7_lookup)

    long["final_competitor_name_standardized"] = long["competitor_name_standardized"]
    long["final_competitor_cik"] = long["competitor_cik"]
    long["final_competitor_gvkey"] = long["competitor_gvkey"]
    long["final_match_source"] = long["competitor_match_source"]
    long["final_match_method"] = long["competitor_match_method"]
    long["manual_alias_bridge_source"] = ""
    long["final_match_stage"] = ""

    long.loc[long["step5_has_any_identifier"], "final_match_stage"] = "step5_mapped"

    alias = prepare_alias_bridge(MANUAL_ALIAS_FILE)
    long, alias_applied_count = apply_manual_alias_bridge(long, alias)

    long["final_has_cik"] = long["final_competitor_cik"].apply(is_valid_id)
    long["final_has_gvkey"] = long["final_competitor_gvkey"].apply(is_valid_id)
    long["final_has_any_identifier"] = long["final_has_cik"] | long["final_has_gvkey"]

    alias_applied_mask = (~long["step5_has_any_identifier"]) & long["manual_alias_bridge_applied"]
    long.loc[alias_applied_mask, "final_match_stage"] = "manual_alias_bridge_applied"

    step5_unmatched_mask = ~long["step5_has_any_identifier"]
    unresolved_mask = step5_unmatched_mask & (~long["final_has_any_identifier"])
    long.loc[unresolved_mask & (long["llm_decision"] == "drop"), "final_match_stage"] = "llm_dropped_residual"
    long.loc[
        unresolved_mask & (long["llm_decision"] == "accept_for_manual_alias_bridge"),
        "final_match_stage",
    ] = "llm_alias_candidate_unresolved"
    long.loc[
        unresolved_mask & (long["llm_decision"] == "manual_review"),
        "final_match_stage",
    ] = "llm_manual_review_unresolved"
    long.loc[unresolved_mask & (long["final_match_stage"] == ""), "final_match_stage"] = "unmatched_no_step7_classification"

    final_unmatched = long[~long["final_has_any_identifier"]].copy()
    final_alias_candidates = build_alias_candidates(long)
    final_alias_candidates_aggregated = build_aggregated_alias_candidates(long)
    final_dropped = long[step5_unmatched_mask & (long["llm_decision"] == "drop")].copy()
    final_manual_review = long[step5_unmatched_mask & (long["llm_decision"] == "manual_review")].copy()
    summary = build_summary(long, alias_applied_count, len(step7_raw))

    safe_to_csv(long, FINAL_DIR / "final_competitor_mentions_long.csv", index=False)
    safe_to_csv(summary, FINAL_DIR / "final_mapping_summary.csv", index=False)
    safe_to_csv(final_unmatched, FINAL_DIR / "final_unmatched_review.csv", index=False)
    safe_to_csv(final_alias_candidates, FINAL_DIR / "final_manual_alias_bridge_candidates.csv", index=False)
    safe_to_csv(
        final_alias_candidates_aggregated,
        FINAL_DIR / "final_manual_alias_bridge_candidates_aggregated.csv",
        index=False,
    )
    safe_to_csv(final_dropped, FINAL_DIR / "final_llm_dropped_residuals.csv", index=False)
    safe_to_csv(final_manual_review, FINAL_DIR / "final_manual_review_residuals.csv", index=False)

    sample_with_notes(long[long["final_has_any_identifier"]], VALIDATION_DIR / "final_matched_sample.csv")
    sample_with_notes(
        long[
            (~long["step5_has_any_identifier"])
            & (long["llm_decision"] == "accept_for_manual_alias_bridge")
        ],
        VALIDATION_DIR / "final_alias_candidate_sample.csv",
    )
    sample_with_notes(final_dropped, VALIDATION_DIR / "final_llm_dropped_sample.csv")
    sample_with_notes(final_manual_review, VALIDATION_DIR / "final_manual_review_sample.csv")
    sample_with_notes(final_unmatched, VALIDATION_DIR / "final_unmatched_sample.csv")

    print("Step 8 final integration completed")
    print(f"Input long rows: {len(long)}")
    print(f"Step 7 classified rows available: {len(step7_raw)}")
    print(f"Manual alias bridge applied rows: {alias_applied_count}")
    print(f"Final rows with any identifier: {int(long['final_has_any_identifier'].sum())}")
    print(f"Final unmatched rows: {int((~long['final_has_any_identifier']).sum())}")
    print(f"Outputs saved in: {FINAL_DIR}")


if __name__ == "__main__":
    main()
