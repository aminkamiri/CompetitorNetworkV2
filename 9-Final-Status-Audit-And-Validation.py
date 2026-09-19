from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


PROJECT = Path(r"C:\Users\mnasiri\Documents\GitHub\CompetitorNetworkV2")
FINAL_DIR = PROJECT / "data" / "results" / "final"
DESCRIPTIVES_DIR = PROJECT / "data" / "results" / "descriptives"
MISSING_DIR = DESCRIPTIVES_DIR / "missing_review"
STEP7_DIR = DESCRIPTIVES_DIR / "step7_residual_classification"

FINAL_LONG = FINAL_DIR / "final_competitor_mentions_long_ultra_cautious_rev2.csv"
STEP7_FILE = STEP7_DIR / "step7_llm_residual_classified.csv"
UNIFIED_MISSING = MISSING_DIR / "unified_missing_name_review.csv"

OUT_LONG_STATUS = FINAL_DIR / "final_competitor_mentions_long_with_status_rev1.csv"
OUT_MENTION_SUMMARY = FINAL_DIR / "final_status_mention_summary_rev1.csv"
OUT_UNIQUE_SUMMARY = FINAL_DIR / "final_status_unique_name_summary_rev1.csv"
OUT_STAGE_SUMMARY = FINAL_DIR / "final_status_by_stage_summary_rev1.csv"
OUT_STEP7_SUMMARY = FINAL_DIR / "final_status_by_step7_decision_summary_rev1.csv"
OUT_UNIQUE_REVIEW = FINAL_DIR / "final_status_unique_name_review_frame_rev1.csv"
SAMPLE_DIR = FINAL_DIR / "validation_samples" / "final_status_samples_rev1"

CHUNKSIZE = 100_000

STEP7_COLUMNS = [
    "llm_classification",
    "llm_decision",
    "llm_confidence",
    "needs_manual_check",
    "llm_reason",
    "suggested_alias_name",
    "suggested_alias_scope",
    "suggested_alias_reason",
]

CORE_REVIEW_COLUMNS = [
    "final_status",
    "competitor_name",
    "competitor_name_standardized",
    "final_competitor_name_standardized",
    "final_competitor_gvkey",
    "final_competitor_cik",
    "final_identifier_status",
    "final_match_source",
    "final_match_method",
    "final_match_stage",
    "final_resolution",
    "competitor_match_source",
    "competitor_match_method",
    "step85_review_step",
    "step85_human_decision",
    "step85_conservative_disposition",
    "llm_classification",
    "llm_decision",
    "llm_confidence",
    "suggested_alias_name",
    "suggested_alias_scope",
    "sic_file",
    "fyear",
    "filename",
]


def clean_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "<na>"}:
        return ""
    return text


def normalize_key(value) -> str:
    text = clean_text(value).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def make_key(row: pd.Series, standardized_col: str, raw_col: str) -> str:
    return normalize_key(row.get(standardized_col)) or normalize_key(row.get(raw_col))


def load_step7_lookup() -> dict[str, dict]:
    step7 = pd.read_csv(STEP7_FILE, low_memory=False)
    for col in STEP7_COLUMNS:
        if col not in step7.columns:
            step7[col] = ""
    if "frequency" in step7.columns:
        step7["_frequency_sort"] = pd.to_numeric(step7["frequency"], errors="coerce").fillna(0)
    else:
        step7["_frequency_sort"] = 0
    records = []
    for _, row in step7.sort_values("_frequency_sort", ascending=False).iterrows():
        for col in ["competitor_name_standardized", "competitor_name", "suggested_alias_name"]:
            key = normalize_key(row.get(col))
            if key:
                rec = row[STEP7_COLUMNS].to_dict()
                rec["merge_key"] = key
                records.append(rec)
    expanded = pd.DataFrame(records)
    expanded = expanded.drop_duplicates("merge_key", keep="first")
    return expanded.set_index("merge_key")[STEP7_COLUMNS].to_dict("index")


def load_pre_step7_generic_keys() -> set[str]:
    unified = pd.read_csv(UNIFIED_MISSING, low_memory=False)
    if "suggested_action" in unified.columns:
        action = unified["suggested_action"].fillna("").astype(str)
    elif "recommended_action" in unified.columns:
        action = unified["recommended_action"].fillna("").astype(str)
    else:
        action = pd.Series([""] * len(unified))

    generic = unified[
        action.eq("review_remove_generic")
        | unified.get("is_likely_generic_category", False).astype(str).str.lower().eq("true")
    ].copy()
    generic["merge_key"] = generic.apply(
        lambda r: make_key(r, "competitor_name_standardized", "competitor_name"), axis=1
    )
    return set(generic["merge_key"][generic["merge_key"] != ""])


def final_status(row: pd.Series, pre_step7_generic_keys: set[str]) -> str:
    identifier_status = clean_text(row.get("final_identifier_status"))
    if identifier_status == "public_identifier_matched":
        return "identified_public_firm"
    if identifier_status == "verified_company_no_public_identifier":
        return "identified_verified_company_no_public_id"

    resolution = clean_text(row.get("final_resolution"))
    if resolution == "unmatched_rejected":
        return "dropped_human_rejected"
    if resolution == "unmatched_unclear":
        return "unresolved_unclear"

    llm_decision = clean_text(row.get("llm_decision"))
    if llm_decision == "drop":
        return "dropped_llm_nonfirm_or_generic"

    merge_key = clean_text(row.get("merge_key"))
    if merge_key in pre_step7_generic_keys:
        return "dropped_generic_or_nonfirm_pre_step7"

    return "unresolved_no_safe_candidate"


def add_step7_fields(chunk: pd.DataFrame, step7_lookup: dict[str, dict]) -> pd.DataFrame:
    chunk = chunk.copy()
    chunk["merge_key"] = chunk.apply(
        lambda r: make_key(r, "competitor_name_standardized", "competitor_name"), axis=1
    )
    records = []
    for key in chunk["merge_key"]:
        records.append(step7_lookup.get(key, {}))
    step7_fields = pd.DataFrame(records, index=chunk.index)
    for col in STEP7_COLUMNS:
        if col not in step7_fields.columns:
            step7_fields[col] = ""
    return pd.concat([chunk, step7_fields[STEP7_COLUMNS]], axis=1)


def write_samples(unique_review: pd.DataFrame) -> None:
    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    for status, group in unique_review.groupby("final_status", dropna=False):
        sample = group.sample(n=min(100, len(group)), random_state=42).copy()
        sample["manual_validation"] = ""
        sample["notes"] = ""
        safe_status = re.sub(r"[^A-Za-z0-9_]+", "_", str(status)).strip("_").lower()
        sample.to_csv(SAMPLE_DIR / f"{safe_status}_sample100.csv", index=False)


def compact_years(series: pd.Series, limit: int = 40) -> str:
    values = sorted(set(pd.to_numeric(series, errors="coerce").dropna().astype(int)))
    return "|".join(map(str, values[:limit]))


def compact_strings(series: pd.Series, limit: int = 30) -> str:
    values = sorted(set(series.dropna().astype(str)))
    return "|".join(values[:limit])


def main() -> None:
    step7_lookup = load_step7_lookup()
    pre_step7_generic_keys = load_pre_step7_generic_keys()

    first_write = True
    mention_parts = []
    stage_parts = []
    step7_parts = []
    unique_parts = []

    for chunk_no, chunk in enumerate(pd.read_csv(FINAL_LONG, chunksize=CHUNKSIZE, low_memory=False), start=1):
        chunk = add_step7_fields(chunk, step7_lookup)
        chunk["final_status"] = chunk.apply(
            lambda r: final_status(r, pre_step7_generic_keys), axis=1
        )
        chunk["final_status_stage"] = chunk["final_status"] + " | " + chunk["final_match_stage"].fillna("").astype(str)

        chunk.to_csv(OUT_LONG_STATUS, index=False, mode="w" if first_write else "a", header=first_write)
        first_write = False

        mention_parts.append(
            chunk.groupby(["final_status", "final_identifier_status"], dropna=False)
            .agg(mention_rows=("competitor_name", "size"))
            .reset_index()
        )
        stage_parts.append(
            chunk.groupby(["final_status", "final_match_stage", "final_resolution"], dropna=False)
            .agg(mention_rows=("competitor_name", "size"))
            .reset_index()
        )
        step7_parts.append(
            chunk.groupby(["final_status", "llm_decision", "llm_classification"], dropna=False)
            .agg(mention_rows=("competitor_name", "size"))
            .reset_index()
        )

        review_cols = [c for c in CORE_REVIEW_COLUMNS if c in chunk.columns]
        unique_part = (
            chunk[review_cols + ["merge_key"]]
            .sort_values(["final_status", "competitor_name"])
            .drop_duplicates(["final_status", "merge_key"], keep="first")
        )
        freq = (
            chunk.groupby(["final_status", "merge_key"], dropna=False)
            .agg(
                mention_rows=("competitor_name", "size"),
                years=("fyear", compact_years),
                sic_files=("sic_file", compact_strings),
            )
            .reset_index()
        )
        unique_part = unique_part.merge(freq, on=["final_status", "merge_key"], how="left")
        unique_parts.append(unique_part)
        print(f"Processed chunk {chunk_no}: {len(chunk):,} rows")

    mention_summary = (
        pd.concat(mention_parts, ignore_index=True)
        .groupby(["final_status", "final_identifier_status"], dropna=False)["mention_rows"]
        .sum()
        .reset_index()
        .sort_values("mention_rows", ascending=False)
    )
    stage_summary = (
        pd.concat(stage_parts, ignore_index=True)
        .groupby(["final_status", "final_match_stage", "final_resolution"], dropna=False)["mention_rows"]
        .sum()
        .reset_index()
        .sort_values("mention_rows", ascending=False)
    )
    step7_summary = (
        pd.concat(step7_parts, ignore_index=True)
        .groupby(["final_status", "llm_decision", "llm_classification"], dropna=False)["mention_rows"]
        .sum()
        .reset_index()
        .sort_values("mention_rows", ascending=False)
    )
    unique_all = pd.concat(unique_parts, ignore_index=True)
    unique_totals = (
        unique_all.groupby(["final_status", "merge_key"], dropna=False)
        .agg(
            mention_rows=("mention_rows", "sum"),
            years=("years", lambda s: "|".join(sorted(set("|".join(s.dropna().astype(str)).split("|")) - {""})[:40])),
            sic_files=("sic_files", lambda s: "|".join(sorted(set("|".join(s.dropna().astype(str)).split("|")) - {""})[:30])),
        )
        .reset_index()
    )
    metadata_cols = [c for c in unique_all.columns if c not in {"mention_rows", "years", "sic_files"}]
    unique_meta = (
        unique_all.sort_values(["final_status", "mention_rows"], ascending=[True, False])
        .drop_duplicates(["final_status", "merge_key"], keep="first")[metadata_cols]
    )
    unique_review = unique_meta.merge(unique_totals, on=["final_status", "merge_key"], how="left")
    unique_review = unique_review.sort_values(["final_status", "mention_rows"], ascending=[True, False])
    unique_summary = (
        unique_review.groupby("final_status", dropna=False)
        .agg(unique_names=("merge_key", "nunique"), mention_rows=("mention_rows", "sum"))
        .reset_index()
        .sort_values("mention_rows", ascending=False)
    )

    mention_summary.to_csv(OUT_MENTION_SUMMARY, index=False)
    unique_summary.to_csv(OUT_UNIQUE_SUMMARY, index=False)
    stage_summary.to_csv(OUT_STAGE_SUMMARY, index=False)
    step7_summary.to_csv(OUT_STEP7_SUMMARY, index=False)
    unique_review.to_csv(OUT_UNIQUE_REVIEW, index=False)
    write_samples(unique_review)

    print("Final status audit layer complete")
    print(f"Step 7 keys: {len(step7_lookup):,}")
    print(f"Pre-Step 7 generic keys: {len(pre_step7_generic_keys):,}")
    print(f"Wrote: {OUT_LONG_STATUS}")
    print(f"Wrote: {OUT_MENTION_SUMMARY}")
    print(f"Wrote: {OUT_UNIQUE_SUMMARY}")
    print(f"Wrote: {OUT_STAGE_SUMMARY}")
    print(f"Wrote: {OUT_STEP7_SUMMARY}")
    print(f"Wrote: {OUT_UNIQUE_REVIEW}")
    print(f"Wrote samples under: {SAMPLE_DIR}")
    print(mention_summary.to_string(index=False))
    print(unique_summary.to_string(index=False))


if __name__ == "__main__":
    main()
