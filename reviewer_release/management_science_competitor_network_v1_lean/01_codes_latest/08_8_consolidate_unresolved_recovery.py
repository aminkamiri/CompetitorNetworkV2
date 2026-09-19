from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


PROJECT = Path(r"C:\Users\mnasiri\Documents\GitHub\CompetitorNetworkV2")
STEP87_DIR = PROJECT / "data" / "results" / "final" / "step87_unresolved_recovery"

STEP87_REFINED = STEP87_DIR / "step87_unresolved_recovery_best_candidate_refined.csv"
STEP87_ORIGINAL = STEP87_DIR / "step87_unresolved_recovery_best_candidate.csv"
STEP87_CIQ = STEP87_DIR / "step87c_ciq_common_unresolved_best_candidate.csv"
NO_EVIDENCE_PATTERNS = STEP87_DIR / "step87_no_external_evidence_top500_pattern_audit.csv"

OUT_MASTER = STEP87_DIR / "step88_unresolved_recovery_consolidated_master.csv"
OUT_REVIEW = STEP87_DIR / "step88_unresolved_recovery_manual_review_queue.csv"
OUT_SUMMARY = STEP87_DIR / "step88_unresolved_recovery_consolidated_summary.csv"
OUT_SOURCE_SUMMARY = STEP87_DIR / "step88_unresolved_recovery_source_summary.csv"
OUT_TOP_UNRESOLVED = STEP87_DIR / "step88_remaining_no_evidence_top500.csv"


def clean_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "<na>"}:
        return ""
    return text


def valid_id(value) -> bool:
    text = clean_text(value)
    if text == "" or text.lower() in {"-1", "-1.0", "-99999", "nan", "none", "null"}:
        return False
    num = pd.to_numeric(text, errors="coerce")
    if not pd.isna(num) and num in {-1, -99999}:
        return False
    return True


def normalize_key(value) -> str:
    text = clean_text(value).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_refined() -> pd.DataFrame:
    df = pd.read_csv(STEP87_REFINED, low_memory=False)
    original = pd.read_csv(STEP87_ORIGINAL, low_memory=False)
    no_external = original[
        original["step87_resolution_suggestion"].fillna("").astype(str).eq("no_external_evidence")
    ].copy()
    no_external["step87_refined_resolution_suggestion"] = "no_external_evidence"
    no_external["step87_refined_reason"] = "No deterministic candidate in Step 8.7 main sources."
    no_external = no_external[~no_external["record_id"].isin(set(df["record_id"]))].copy()
    df = pd.concat([df, no_external], ignore_index=True, sort=False)
    for col in [
        "record_id", "frequency", "competitor_name", "suggested_alias_name",
        "candidate_input_name", "candidate_name", "candidate_conm", "candidate_source",
        "candidate_match_rule", "candidate_gvkey", "candidate_cik",
        "candidate_sic_support", "step87_refined_resolution_suggestion",
        "step87_refined_reason", "step87_refined_n_distinct_public_ids",
        "step87_refined_score_gap", "step85_overlap", "step85_conservative_disposition",
        "years", "sic_files", "llm_classification", "llm_decision", "llm_confidence",
    ]:
        if col not in df.columns:
            df[col] = ""
    df["base_has_public_id"] = df["candidate_gvkey"].map(valid_id) | df["candidate_cik"].map(valid_id)
    return df


def load_ciq() -> pd.DataFrame:
    if not STEP87_CIQ.exists():
        return pd.DataFrame(columns=["record_id"])
    ciq = pd.read_csv(STEP87_CIQ, low_memory=False)
    for col in [
        "record_id", "candidate_name", "candidate_companyid", "candidate_isin",
        "candidate_date_overlap", "ciq_crosswalk_gvkey",
        "ciq_identifier_upgrade_candidate", "candidate_match_rule",
    ]:
        if col not in ciq.columns:
            ciq[col] = ""
    ciq = ciq.rename(
        columns={
            "candidate_name": "ciq_candidate_name",
            "candidate_companyid": "ciq_companyid",
            "candidate_isin": "ciq_isin",
            "candidate_match_rule": "ciq_match_rule",
        }
    )
    ciq["ciq_identifier_upgrade_candidate"] = ciq["ciq_identifier_upgrade_candidate"].astype(str).str.lower().eq("true")
    ciq["ciq_has_gvkey_crosswalk"] = ciq["ciq_crosswalk_gvkey"].map(valid_id)
    return ciq[
        [
            "record_id", "ciq_candidate_name", "ciq_companyid", "ciq_isin",
            "candidate_date_overlap", "ciq_crosswalk_gvkey",
            "ciq_has_gvkey_crosswalk", "ciq_identifier_upgrade_candidate",
            "ciq_match_rule",
        ]
    ].drop_duplicates("record_id", keep="first")


def load_no_evidence_patterns() -> pd.DataFrame:
    if not NO_EVIDENCE_PATTERNS.exists():
        return pd.DataFrame(columns=["pattern_key", "pattern_category"])
    pat = pd.read_csv(NO_EVIDENCE_PATTERNS, low_memory=False)
    name_col = "suggested_alias_name" if "suggested_alias_name" in pat.columns else "competitor_name"
    pat["pattern_key"] = pat[name_col].map(normalize_key)
    return pat[["pattern_key", "pattern_category"]].drop_duplicates("pattern_key", keep="first")


def proposed_action(row: pd.Series) -> tuple[str, str, str, str, str]:
    refined = clean_text(row.get("step87_refined_resolution_suggestion"))
    ciq_upgrade = clean_text(row.get("ciq_identifier_upgrade_candidate")).lower() == "true"
    ciq_gvkey = clean_text(row.get("ciq_crosswalk_gvkey"))
    base_has_public = clean_text(row.get("base_has_public_id")).lower() == "true"
    n_public = pd.to_numeric(row.get("step87_refined_n_distinct_public_ids"), errors="coerce")
    n_public = int(n_public) if not pd.isna(n_public) else 0
    score_gap = pd.to_numeric(row.get("step87_refined_score_gap"), errors="coerce")
    score_gap = float(score_gap) if not pd.isna(score_gap) else 0.0
    sic_support = clean_text(row.get("candidate_sic_support"))
    pattern = clean_text(row.get("pattern_category"))

    if refined == "already_resolved_in_step85":
        return (
            "already_resolved_in_step85",
            "do_not_reprocess",
            "Step 8.5 already supplied the governing decision.",
            clean_text(row.get("candidate_gvkey")),
            clean_text(row.get("candidate_cik")),
        )

    if refined == "recovered_public_identifier_refined" and base_has_public and n_public <= 1:
        return (
            "auto_recover_public_identifier",
            "auto_accept_candidate",
            "Identifier-backed refined candidate with unique public identity.",
            clean_text(row.get("candidate_gvkey")),
            clean_text(row.get("candidate_cik")),
        )

    if ciq_upgrade and refined in {"recovered_public_identifier_refined", "company_evidence_public_identifier_missing"}:
        return (
            "auto_recover_public_identifier_ciq_crosswalk",
            "auto_accept_candidate",
            "CIQ companyid has GVKEY crosswalk and CIQ date overlaps residual years.",
            ciq_gvkey,
            "",
        )

    if ciq_upgrade and refined == "no_external_evidence":
        return (
            "manual_review_public_candidate_ciq_new",
            "manual_review",
            "Previously no-evidence alias now has CIQ companyid-to-GVKEY evidence; review before accepting.",
            ciq_gvkey,
            "",
        )

    if refined == "needs_manual_review_broad_alias":
        return (
            "manual_review_public_candidate",
            "manual_review",
            "Identifier-backed or company-backed evidence exists, but alias is broad or ambiguous.",
            clean_text(row.get("candidate_gvkey")) if base_has_public else ciq_gvkey,
            clean_text(row.get("candidate_cik")),
        )

    if refined == "company_evidence_public_identifier_missing":
        if sic_support in {"sic4_match", "sic3_match", "sic2_match"} or score_gap >= 30:
            return (
                "verified_company_no_public_identifier",
                "auto_accept_verified_company_no_id",
                "External company evidence with supporting SIC or strong candidate ranking, but no GVKEY/CIK.",
                "-99999",
                "-99999",
            )
        return (
            "manual_review_company_no_identifier",
            "manual_review",
            "Company evidence exists but public identifier is missing and support is not strong enough for automatic no-ID classification.",
            "-99999",
            "-99999",
        )

    if refined == "no_external_evidence":
        if pattern in {"product_or_business_unit_like", "multiple_or_compound_name"}:
            return (
                "remain_unresolved_reason_coded",
                "leave_unresolved",
                f"No external evidence; pattern suggests {pattern}.",
                "-1",
                "-1",
            )
        return (
            "remain_unresolved_no_evidence",
            "leave_unresolved",
            "No deterministic external evidence after Step 8.7 and CIQ_COMMON.",
            "-1",
            "-1",
        )

    return (
        "manual_review_residual",
        "manual_review",
        "Residual evidence pattern did not meet an automatic rule.",
        clean_text(row.get("candidate_gvkey")),
        clean_text(row.get("candidate_cik")),
    )


def main() -> None:
    refined = load_refined()
    ciq = load_ciq()
    patterns = load_no_evidence_patterns()

    master = refined.merge(ciq, on="record_id", how="left")
    master["pattern_key"] = master["suggested_alias_name"].map(normalize_key)
    master = master.merge(patterns, on="pattern_key", how="left")

    decisions = master.apply(proposed_action, axis=1, result_type="expand")
    decisions.columns = [
        "step88_proposed_action",
        "step88_review_bucket",
        "step88_reason",
        "step88_proposed_gvkey",
        "step88_proposed_cik",
    ]
    master = pd.concat([master, decisions], axis=1)

    master["step88_public_identifier_recovered"] = master["step88_proposed_action"].isin(
        {"auto_recover_public_identifier", "auto_recover_public_identifier_ciq_crosswalk"}
    )
    master["step88_verified_company_no_public_id"] = master["step88_proposed_action"].eq(
        "verified_company_no_public_identifier"
    )
    master["step88_manual_review_needed"] = master["step88_review_bucket"].eq("manual_review")

    master.to_csv(OUT_MASTER, index=False)

    review_cols = [
        "step88_proposed_action", "step88_review_bucket", "step88_reason",
        "frequency", "competitor_name", "suggested_alias_name", "candidate_name",
        "candidate_conm", "ciq_candidate_name", "candidate_source", "candidate_match_rule",
        "ciq_match_rule", "step88_proposed_gvkey", "step88_proposed_cik",
        "candidate_gvkey", "candidate_cik", "ciq_crosswalk_gvkey", "ciq_companyid",
        "ciq_isin", "candidate_date_overlap", "candidate_sic_support", "sic_files",
        "step87_refined_resolution_suggestion", "step87_refined_reason",
        "step87_refined_n_distinct_public_ids", "step87_refined_score_gap",
        "pattern_category", "years", "llm_classification", "llm_decision", "llm_confidence",
    ]
    review = master.loc[master["step88_manual_review_needed"], [c for c in review_cols if c in master.columns]].copy()
    review["manual_decision"] = ""
    review["approved_name"] = ""
    review["approved_gvkey"] = ""
    review["approved_cik"] = ""
    review["reviewer_notes"] = ""
    review = review.sort_values(["step88_proposed_action", "frequency"], ascending=[True, False])
    review.to_csv(OUT_REVIEW, index=False)

    summary = (
        master.groupby(["step88_proposed_action", "step88_review_bucket"], dropna=False)
        .agg(aliases=("record_id", "size"), frequency_sum=("frequency", "sum"))
        .reset_index()
        .sort_values("frequency_sum", ascending=False)
    )
    summary.to_csv(OUT_SUMMARY, index=False)

    source_summary = (
        master.groupby(["step88_proposed_action", "candidate_source", "candidate_match_rule"], dropna=False)
        .agg(aliases=("record_id", "size"), frequency_sum=("frequency", "sum"))
        .reset_index()
        .sort_values("frequency_sum", ascending=False)
    )
    source_summary.to_csv(OUT_SOURCE_SUMMARY, index=False)

    unresolved = master[master["step88_proposed_action"].isin(["remain_unresolved_no_evidence", "remain_unresolved_reason_coded"])].copy()
    unresolved = unresolved.sort_values("frequency", ascending=False).head(500)
    unresolved[[c for c in review_cols if c in unresolved.columns]].to_csv(OUT_TOP_UNRESOLVED, index=False)

    print("Step 8.8 consolidated summary:")
    print(summary.to_string(index=False))
    print(f"Wrote: {OUT_MASTER}")
    print(f"Wrote: {OUT_REVIEW}")


if __name__ == "__main__":
    main()
