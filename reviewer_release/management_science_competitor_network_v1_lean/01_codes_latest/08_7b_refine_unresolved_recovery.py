from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd


PROJECT = Path(r"C:\Users\mnasiri\Documents\GitHub\CompetitorNetworkV2")
STEP87_DIR = PROJECT / "data" / "results" / "final" / "step87_unresolved_recovery"
STEP85_DECISIONS = PROJECT / "data" / "results" / "final" / "step85_human_review" / "step85_consolidated_review_decisions_rev1.csv"

IN_CANDIDATES = STEP87_DIR / "step87_unresolved_recovery_candidates.csv"
IN_BEST = STEP87_DIR / "step87_unresolved_recovery_best_candidate.csv"

OUT_CANDIDATES = STEP87_DIR / "step87_unresolved_recovery_candidates_refined.csv"
OUT_BEST = STEP87_DIR / "step87_unresolved_recovery_best_candidate_refined.csv"
OUT_REVIEW = STEP87_DIR / "step87_unresolved_recovery_review_refined.csv"
OUT_SUMMARY = STEP87_DIR / "step87_unresolved_recovery_refined_summary.csv"
OUT_SOURCE_RULE = STEP87_DIR / "step87_unresolved_recovery_refined_source_rule_summary.csv"


LEGAL_SUFFIXES = {
    "INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC",
    "AG", "SA", "SE", "NV", "BV", "GMBH", "LLC", "LP", "LLP", "SPA", "AB",
    "AS", "SARL", "SRL",
}
PARENT_ENTITY_TERMS = {"HLDG", "HLDGS", "HOLDING", "HOLDINGS", "GROUP", "GRP"}
GEOGRAPHIC_TERMS = {
    "INDIA", "CHINA", "PAKISTAN", "KOREA", "JAPAN", "EUROPE", "MEXICO",
    "CANADA", "BRAZIL", "FRANCE", "GERMANY", "ITALY", "SPAIN", "UK", "USA",
}
BUSINESS_UNIT_TERMS = {
    "BIOLOGICS", "DIAGNOSTICS", "MEDICAL", "CONSUMER", "HEALTHCARE",
    "PHARMA", "PHARMACEUTICALS", "SPECIALTY", "DIVISION", "BUSINESS",
    "SERVICES", "SOLUTIONS",
}


def clean_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "<na>"}:
        return ""
    return text


def normalize(value) -> str:
    text = unicodedata.normalize("NFKD", clean_text(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).upper()
    text = re.sub(r"&", " AND ", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def core_name(value) -> str:
    tokens = normalize(value).split()
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def valid_id(value) -> bool:
    text = clean_text(value)
    if text == "" or text.lower() in {"-1", "-1.0", "-99999", "nan", "none", "null"}:
        return False
    num = pd.to_numeric(text, errors="coerce")
    if not pd.isna(num) and num in {-1, -99999}:
        return False
    return True


def extract_sics(value) -> set[str]:
    sics = set()
    for token in re.findall(r"\d{2,4}", clean_text(value)):
        if len(token) >= 2:
            sics.add(token.zfill(4)[-4:])
    return sics


def sic_support(row: pd.Series) -> tuple[str, int]:
    focal = extract_sics(row.get("sic_files"))
    cand_text = clean_text(row.get("candidate_sic"))
    if not focal or not cand_text:
        return "no_sic_available", 0
    cand = re.sub(r"\D", "", cand_text)
    if not cand:
        return "no_sic_available", 0
    cand = cand.zfill(4)[-4:]
    if cand in focal:
        return "sic4_match", 20
    if any(cand[:3] == s[:3] for s in focal):
        return "sic3_match", 12
    if any(cand[:2] == s[:2] for s in focal):
        return "sic2_match", 8
    return "sic_mismatch", -8


def load_step85_keys() -> pd.DataFrame:
    if not STEP85_DECISIONS.exists():
        return pd.DataFrame(columns=["key", "step85_conservative_disposition", "step85_human_decision"])
    df = pd.read_csv(STEP85_DECISIONS, low_memory=False)
    key_cols = [
        "original_extracted_competitor_name",
        "suggested_alias_name",
        "final_candidate_name",
        "reviewer_supplied_correction",
        "algorithm_candidate_name",
        "external_candidate_name",
        "merge_key",
    ]
    parts = []
    for col in key_cols:
        if col not in df.columns:
            continue
        tmp = df[[col, "conservative_disposition", "human_decision", "mapping_allowed", "company_like_no_identifier"]].copy()
        tmp["key"] = tmp[col].map(normalize)
        tmp = tmp[tmp["key"].ne("")]
        parts.append(tmp)
    if not parts:
        return pd.DataFrame(columns=["key", "step85_conservative_disposition", "step85_human_decision"])
    out = pd.concat(parts, ignore_index=True).drop_duplicates("key", keep="first")
    return out.rename(
        columns={
            "conservative_disposition": "step85_conservative_disposition",
            "human_decision": "step85_human_decision",
        }
    )


def refine_candidates() -> tuple[pd.DataFrame, pd.DataFrame]:
    cand = pd.read_csv(IN_CANDIDATES, low_memory=False)
    step85 = load_step85_keys()

    cand["alias_norm"] = cand["alias_exact_key"].map(normalize)
    cand.loc[cand["alias_norm"].eq(""), "alias_norm"] = cand.loc[cand["alias_norm"].eq(""), "candidate_input_name"].map(normalize)
    cand["alias_core"] = cand["alias_canonical_key"].map(normalize)
    cand.loc[cand["alias_core"].eq(""), "alias_core"] = cand.loc[cand["alias_core"].eq(""), "candidate_input_name"].map(core_name)
    cand["candidate_norm"] = cand["candidate_name"].map(normalize)
    cand["candidate_core"] = cand["candidate_name"].map(core_name)
    cand["candidate_tokens"] = cand["candidate_norm"].str.split()
    cand["candidate_has_public_identifier"] = cand["candidate_gvkey"].map(valid_id) | cand["candidate_cik"].map(valid_id)
    cand["candidate_core_equals_alias_core"] = cand["candidate_core"].eq(cand["alias_core"]) & cand["alias_core"].ne("")
    cand["candidate_starts_with_alias_core"] = cand.apply(
        lambda r: clean_text(r["alias_core"]) != "" and clean_text(r["candidate_norm"]).startswith(clean_text(r["alias_core"]) + " "),
        axis=1,
    )
    cand["candidate_has_legal_entity_suffix"] = cand["candidate_tokens"].map(
        lambda toks: bool(toks) and toks[-1] in LEGAL_SUFFIXES
    )
    cand["candidate_has_parent_entity_term"] = cand["candidate_tokens"].map(
        lambda toks: bool(set(toks) & PARENT_ENTITY_TERMS)
    )
    cand["candidate_has_geo_continuation"] = cand["candidate_tokens"].map(
        lambda toks: bool(set(toks) & GEOGRAPHIC_TERMS)
    )
    cand["candidate_has_business_unit_continuation"] = cand["candidate_tokens"].map(
        lambda toks: bool(set(toks) & BUSINESS_UNIT_TERMS)
    )
    sic = cand.apply(sic_support, axis=1, result_type="expand")
    cand["candidate_sic_support"] = sic[0]
    cand["candidate_sic_bonus"] = sic[1]

    cand = cand.merge(
        step85[["key", "step85_conservative_disposition", "step85_human_decision"]],
        left_on="alias_norm",
        right_on="key",
        how="left",
    )
    cand["step85_overlap"] = cand["key"].notna()

    base = pd.to_numeric(cand["candidate_rank_score"], errors="coerce").fillna(0)
    refined = base.copy()
    refined += cand["candidate_has_public_identifier"].astype(int) * 35
    refined += cand["candidate_core_equals_alias_core"].astype(int) * 35
    refined += cand["candidate_starts_with_alias_core"].astype(int) * 15
    refined += cand["candidate_has_legal_entity_suffix"].astype(int) * 15
    refined += cand["candidate_has_parent_entity_term"].astype(int) * 12
    refined += cand["candidate_sic_bonus"]
    refined -= cand["candidate_has_geo_continuation"].astype(int) * 18
    refined -= cand["candidate_has_business_unit_continuation"].astype(int) * 12
    refined += cand["candidate_match_rule"].fillna("").str.contains("year_specific", case=False).astype(int) * 12
    refined += cand["candidate_match_rule"].fillna("").str.contains("exact", case=False).astype(int) * 8
    cand["step87_refined_rank_score"] = refined

    cand = cand.sort_values(
        ["record_id", "step87_refined_rank_score", "candidate_has_public_identifier", "candidate_source", "candidate_name"],
        ascending=[True, False, False, True, True],
    )
    cand["step87_refined_rank"] = cand.groupby("record_id").cumcount() + 1
    best = cand[cand["step87_refined_rank"].eq(1)].copy()
    second = (
        cand[cand["step87_refined_rank"].eq(2)][["record_id", "step87_refined_rank_score"]]
        .rename(columns={"step87_refined_rank_score": "step87_second_rank_score"})
    )
    best = best.merge(second, on="record_id", how="left")
    best["step87_refined_score_gap"] = best["step87_refined_rank_score"] - pd.to_numeric(best["step87_second_rank_score"], errors="coerce").fillna(-9999)

    n_public = (
        cand.assign(public_key=cand["candidate_gvkey"].where(cand["candidate_gvkey"].map(valid_id), cand["candidate_cik"]))
        .groupby("record_id")["public_key"]
        .agg(lambda s: len({clean_text(x) for x in s if valid_id(x)}))
        .rename("step87_refined_n_distinct_public_ids")
        .reset_index()
    )
    best = best.merge(n_public, on="record_id", how="left")
    return cand, best


def assign_refined_status(best: pd.DataFrame) -> pd.DataFrame:
    best = best.copy()
    status = []
    reason = []
    for _, row in best.iterrows():
        overlap_disposition = clean_text(row.get("step85_conservative_disposition"))
        has_public = bool(row.get("candidate_has_public_identifier"))
        unique_public = int(row.get("step87_refined_n_distinct_public_ids") or 0) <= 1
        strong_name = bool(row.get("candidate_core_equals_alias_core")) or bool(row.get("candidate_starts_with_alias_core"))
        sic_ok = clean_text(row.get("candidate_sic_support")) in {"sic4_match", "sic3_match", "sic2_match"}
        score_gap = float(row.get("step87_refined_score_gap") or 0)
        if overlap_disposition in {"accept_identifier_mapping", "accept_text_only_needs_identifier"}:
            status.append("already_resolved_in_step85")
            reason.append(f"Step 8.5 disposition: {overlap_disposition}")
        elif has_public and unique_public and (strong_name or sic_ok or score_gap >= 30):
            status.append("recovered_public_identifier_refined")
            reason.append("public identifier candidate prioritized by parent/legal entity, name-core, or SIC support")
        elif has_public:
            status.append("needs_manual_review_broad_alias")
            reason.append("identifier-backed candidate exists but alias is broad or multiple public identities remain")
        elif clean_text(row.get("step87_resolution_suggestion")) == "verified_company_no_public_identifier":
            status.append("company_evidence_public_identifier_missing")
            reason.append("external company-name evidence exists but no usable GVKEY/CIK in this pass")
        elif clean_text(row.get("step87_resolution_suggestion")) == "no_external_evidence":
            status.append("no_external_evidence")
            reason.append("no deterministic candidate in current Step 8.7 sources")
        else:
            status.append("needs_manual_review_broad_alias")
            reason.append("candidate evidence exists but not strong enough for automatic recovery")
    best["step87_refined_resolution_suggestion"] = status
    best["step87_refined_reason"] = reason
    return best


def main() -> None:
    cand, best = refine_candidates()
    best = assign_refined_status(best)

    cand.to_csv(OUT_CANDIDATES, index=False)
    best.to_csv(OUT_BEST, index=False)

    review_cols = [
        "step87_refined_resolution_suggestion",
        "step87_refined_reason",
        "step87_resolution_suggestion",
        "frequency",
        "competitor_name",
        "suggested_alias_name",
        "candidate_name",
        "candidate_conm",
        "candidate_source",
        "candidate_match_rule",
        "candidate_gvkey",
        "candidate_cik",
        "candidate_sic",
        "sic_files",
        "candidate_sic_support",
        "candidate_core_equals_alias_core",
        "candidate_starts_with_alias_core",
        "candidate_has_legal_entity_suffix",
        "candidate_has_parent_entity_term",
        "candidate_has_geo_continuation",
        "candidate_has_business_unit_continuation",
        "step87_refined_rank_score",
        "step87_refined_score_gap",
        "step87_refined_n_distinct_public_ids",
        "step85_overlap",
        "step85_conservative_disposition",
        "years",
        "llm_classification",
        "llm_decision",
        "llm_confidence",
    ]
    best[review_cols].sort_values(
        ["step87_refined_resolution_suggestion", "frequency"], ascending=[True, False]
    ).to_csv(OUT_REVIEW, index=False)

    summary = (
        best.groupby("step87_refined_resolution_suggestion", dropna=False)
        .agg(aliases=("record_id", "size"), frequency_sum=("frequency", "sum"))
        .reset_index()
        .sort_values("frequency_sum", ascending=False)
    )
    summary.to_csv(OUT_SUMMARY, index=False)

    source_rule = (
        best.groupby(["step87_refined_resolution_suggestion", "candidate_source", "candidate_match_rule"], dropna=False)
        .agg(aliases=("record_id", "size"), frequency_sum=("frequency", "sum"))
        .reset_index()
        .sort_values("frequency_sum", ascending=False)
    )
    source_rule.to_csv(OUT_SOURCE_RULE, index=False)

    print("Step 8.7 refined summary:")
    print(summary.to_string(index=False))
    print(f"Wrote: {OUT_REVIEW}")


if __name__ == "__main__":
    main()
