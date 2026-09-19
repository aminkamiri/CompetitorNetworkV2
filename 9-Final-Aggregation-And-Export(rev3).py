
from __future__ import annotations

import math
import re
import unicodedata
from pathlib import Path

import pandas as pd

PROJECT = Path(r"C:\Users\mnasiri\Documents\GitHub\CompetitorNetworkV2")
FINAL_DIR = PROJECT / "data" / "results" / "final"
STEP87_DIR = FINAL_DIR / "step87_unresolved_recovery"

BASE_LONG = FINAL_DIR / "final_competitor_mentions_long_with_status_rev1.csv"
STEP88B_MASTER = STEP87_DIR / "step88_unresolved_recovery_consolidated_master_with_partial_evidence.csv"
STEP2_REVIEW = STEP87_DIR / "step88b_step2_partial_evidence_review_friendly_v2.xlsx"
STEP3_REVIEW = STEP87_DIR / "step88b_step3_remaining_unresolved_review_friendly_v2.xlsx"

IDENTIFIER_YEAR_PANEL = PROJECT / "company_identifier_year_panel.csv"
YEAR_SPECIFIC_BRIDGE = PROJECT / "company_alias_bridge_year_specific.csv"
LEGACY_CIK_GVKEY = PROJECT / "cik_tic_gvkey_full_combined_cleaned.csv"

OUT_INTERNAL = FINAL_DIR / "final_competitor_mentions_internal_audit_step9_rev3.csv"
OUT_EXTERNAL_IDENTIFIED = FINAL_DIR / "final_competitor_mentions_clean_identified_only_step9_rev3.csv"
OUT_EXTERNAL_ALL_STATUS = FINAL_DIR / "final_competitor_mentions_clean_all_status_step9_rev3.csv"
OUT_EDGES = FINAL_DIR / "final_competitor_edges_clean_identified_only_step9_rev3.csv"
OUT_STATUS_SUMMARY = FINAL_DIR / "final_step9_status_summary_rev3.csv"
OUT_UNIQUE_SUMMARY = FINAL_DIR / "final_step9_unique_name_summary_rev3.csv"
OUT_ERROR_SUMMARY = FINAL_DIR / "final_step9_validation_error_rate_summary_rev3.csv"
OUT_RULE_SUMMARY = FINAL_DIR / "final_step9_rule_extension_summary_rev3.csv"
OUT_UNRESOLVED = FINAL_DIR / "final_step9_internal_unresolved_excluded_from_external_rev3.csv"
OUT_REJECTED_CORRECTIONS = FINAL_DIR / "final_step9_human_rejected_or_corrected_aliases_rev3.csv"
OUT_FOCAL_GVKEY_AUDIT = FINAL_DIR / "final_step9_focal_gvkey_recovery_audit_rev3.csv"

LEGAL_SUFFIX_PATTERN = re.compile(
    r"\b(INC|INCORPORATED|CORP|CORPORATION|COMPANY|CO|LTD|LIMITED|LLC|LP|LLP|PLC|AG|SA|SAS|NV|BV|GMBH|SPA|S P A|SRL|S R L|SARL|S A R L|PTE|PTY|KK|K K|AS|A S|AB|OY|BHD|CO LTD|CO\.?\s*LTD|BVBA)\b",
    re.IGNORECASE,
)
BAD_LLM_CLASSES = {
    "multiple_entities",
    "unclear",
    "brand_or_product",
    "generic_phrase",
    "technical_term",
    "artifact",
    "person",
    "government_or_public_institution",
    "association_or_nonprofit",
}
RISK_TERMS = set(
    "PAKISTAN INDIA CHINA KOREA JAPAN EUROPE MEXICO MUNICIPAL INCOME FUND TRUST REIT "
    "OFFSHORE PARTNER FINANCE FINANCIAL INTERNATIONAL AMERICA AMERICAS USA US".split()
)

INTERNAL_KEEP_COLS = [
    "sic_file", "filename", "focal_cik", "fyear", "competitor_order", "competitor_name",
    "competitor_name_standardized", "competitor_cik", "competitor_gvkey", "competitor_match_source",
    "competitor_match_method", "competitor_matched_bridge_name", "competitor_matched_bridge_original_name",
    "original_step5_6_has_identifier", "step85_review_applied", "step85_human_decision",
    "step85_conservative_disposition", "final_competitor_name_standardized", "final_competitor_gvkey",
    "final_competitor_cik", "final_match_source", "final_match_method", "final_match_stage",
    "final_resolution", "final_identifier_status", "final_status", "final_status_stage", "merge_key",
    "llm_classification", "llm_decision", "llm_confidence", "needs_manual_check", "llm_reason",
    "suggested_alias_name", "suggested_alias_scope", "suggested_alias_reason",
]

EXTERNAL_COLS = [
    "focal_sic", "filename", "focal_cik", "focal_gvkey", "fyear", "competitor_order",
    "competitor_name_original", "competitor_name_final", "competitor_gvkey", "competitor_cik",
    "competitor_identifier_status",
]


def clean(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "<na>"}:
        return ""
    return text


def normalize_key(value) -> str:
    text = unicodedata.normalize("NFKD", clean(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).upper()
    text = text.replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def has_valid_id(value) -> bool:
    text = clean(value)
    if not text:
        return False
    try:
        number = float(text)
        return not (math.isnan(number) or number in {-1.0, -88888.0, -99999.0})
    except Exception:
        return text not in {"-1", "-1.0", "-88888", "-88888.0", "-99999", "-99999.0"}


def safe_id(value, missing="-1") -> str:
    return clean(value) if has_valid_id(value) else missing


def first_valid(row: pd.Series, columns: list[str], missing="-1") -> str:
    for col in columns:
        if col in row and has_valid_id(row.get(col, "")):
            return clean(row.get(col, ""))
    return missing


def external_id_value(value, status: str) -> str:
    """External files never show blanks or -1.

    -99999 means verified company with no public identifier.
    -88888 means this specific identifier is unavailable/not assigned in the external file.
    """
    if has_valid_id(value):
        text = clean(value)
        try:
            number = float(text)
            if number.is_integer():
                return str(int(number))
        except Exception:
            pass
        return text
    if status == "verified_company_no_public_identifier":
        return "-99999"
    return "-88888"


def first_text(row: pd.Series, columns: list[str]) -> str:
    for col in columns:
        if col in row:
            val = clean(row.get(col, ""))
            if val:
                return val
    return ""


def exactish_step2(row: pd.Series) -> bool:
    return clean(row.get("partial_partial_match_rule", "")) in {"possessive_or_exact_name", "legal_canonical_name"}


def format_identifier(value) -> str:
    text = clean(value)
    if not text:
        return "-88888"
    try:
        number = float(text)
        if math.isnan(number):
            return "-88888"
        if number.is_integer():
            return str(int(number))
    except Exception:
        pass
    return text


def format_sic(value) -> str:
    text = clean(value)
    if not text:
        return ""
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number)).zfill(4)
    except Exception:
        pass
    digits = re.sub(r"\D+", "", text)
    return digits.zfill(4) if digits else text


def build_focal_gvkey_lookup(target_keys: pd.DataFrame) -> pd.DataFrame:
    target = target_keys[["focal_cik", "fyear"]].drop_duplicates().copy()
    target["focal_cik"] = pd.to_numeric(target["focal_cik"], errors="coerce")
    target["fyear"] = pd.to_numeric(target["fyear"], errors="coerce")
    target = target.dropna(subset=["focal_cik", "fyear"])
    target["focal_cik"] = target["focal_cik"].astype("int64")
    target["fyear"] = target["fyear"].astype("int64")

    panel = pd.read_csv(IDENTIFIER_YEAR_PANEL, low_memory=False)
    panel = panel[["cik", "gvkey", "fyear"]].copy()
    panel["focal_cik"] = pd.to_numeric(panel["cik"], errors="coerce")
    panel["fyear"] = pd.to_numeric(panel["fyear"], errors="coerce")
    panel["gvkey_clean"] = panel["gvkey"].map(format_identifier)
    panel = panel.dropna(subset=["focal_cik", "fyear"])
    panel = panel[panel["gvkey_clean"].ne("-88888")]

    panel_same = (
        panel.sort_values(["focal_cik", "fyear", "gvkey_clean"])
        .drop_duplicates(["focal_cik", "fyear"], keep="first")
        [["focal_cik", "fyear", "gvkey_clean"]]
        .rename(columns={"gvkey_clean": "gvkey_panel_same_year"})
    )

    bridge_cols = ["cik", "gvkey", "fyear", "source", "matching_priority"]
    bridge = pd.read_csv(YEAR_SPECIFIC_BRIDGE, usecols=lambda c: c in bridge_cols, low_memory=False)
    bridge["focal_cik"] = pd.to_numeric(bridge["cik"], errors="coerce")
    bridge["fyear"] = pd.to_numeric(bridge["fyear"], errors="coerce")
    bridge["gvkey_clean"] = bridge["gvkey"].map(format_identifier)
    bridge = bridge.dropna(subset=["focal_cik", "fyear"])
    bridge = bridge[bridge["gvkey_clean"].ne("-88888")].copy()
    bridge["matching_priority"] = pd.to_numeric(bridge.get("matching_priority"), errors="coerce").fillna(99)

    bridge_same = (
        bridge.sort_values(["focal_cik", "fyear", "matching_priority", "source", "gvkey_clean"])
        .drop_duplicates(["focal_cik", "fyear"], keep="first")
        [["focal_cik", "fyear", "gvkey_clean"]]
        .rename(columns={"gvkey_clean": "gvkey_bridge_same_year"})
    )

    bridge_any_counts = (
        bridge.drop_duplicates(["focal_cik", "gvkey_clean"])
        .groupby("focal_cik", dropna=False)
        .agg(
            n_unique_any_year_gvkeys=("gvkey_clean", "nunique"),
            gvkey_unique_any_year=("gvkey_clean", lambda s: sorted(set(s))[0] if len(set(s)) == 1 else ""),
            any_year_min=("fyear", "min"),
            any_year_max=("fyear", "max"),
            any_year_sources=("source", lambda s: "|".join(sorted(set(s.dropna().astype(str))))),
        )
        .reset_index()
    )
    bridge_any_counts.loc[bridge_any_counts["n_unique_any_year_gvkeys"].ne(1), "gvkey_unique_any_year"] = ""

    legacy = pd.read_csv(LEGACY_CIK_GVKEY, low_memory=False)
    legacy["focal_cik"] = pd.to_numeric(legacy.get("cik"), errors="coerce")
    legacy["legacy_gvkey_clean"] = legacy.get("gvkey").map(format_identifier)
    legacy = legacy.dropna(subset=["focal_cik"])
    legacy = legacy[legacy["legacy_gvkey_clean"].ne("-88888")].copy()
    legacy["focal_cik"] = legacy["focal_cik"].astype("int64")
    if "conm" in legacy.columns:
        legacy["legacy_conm_clean"] = legacy["conm"].map(clean)
    else:
        legacy["legacy_conm_clean"] = ""
    legacy_counts = (
        legacy.drop_duplicates(["focal_cik", "legacy_gvkey_clean"])
        .groupby("focal_cik", dropna=False)
        .agg(
            n_legacy_gvkeys=("legacy_gvkey_clean", "nunique"),
            legacy_unique_gvkey=("legacy_gvkey_clean", lambda s: sorted(set(s))[0] if len(set(s)) == 1 else ""),
            legacy_conm_examples=(
                "legacy_conm_clean",
                lambda s: "|".join([x for x in dict.fromkeys(s.dropna().astype(str)) if x][:5]),
            ),
        )
        .reset_index()
    )
    legacy_counts.loc[legacy_counts["n_legacy_gvkeys"].ne(1), "legacy_unique_gvkey"] = ""

    focal_lookup = target.merge(panel_same, on=["focal_cik", "fyear"], how="left")
    focal_lookup = focal_lookup.merge(bridge_same, on=["focal_cik", "fyear"], how="left")
    focal_lookup = focal_lookup.merge(bridge_any_counts, on="focal_cik", how="left")
    focal_lookup = focal_lookup.merge(legacy_counts, on="focal_cik", how="left")
    focal_lookup["focal_gvkey"] = focal_lookup["gvkey_panel_same_year"].fillna("")
    focal_lookup["focal_gvkey_source"] = "identifier_year_panel_same_year"

    missing_panel = focal_lookup["focal_gvkey"].eq("")
    focal_lookup.loc[missing_panel, "focal_gvkey"] = focal_lookup.loc[missing_panel, "gvkey_bridge_same_year"].fillna("")
    focal_lookup.loc[missing_panel & focal_lookup["focal_gvkey"].ne(""), "focal_gvkey_source"] = "year_specific_bridge_same_year"

    missing_same_year = focal_lookup["focal_gvkey"].eq("")
    unique_any = focal_lookup["gvkey_unique_any_year"].fillna("").ne("")
    focal_lookup.loc[missing_same_year & unique_any, "focal_gvkey"] = focal_lookup.loc[missing_same_year & unique_any, "gvkey_unique_any_year"]
    focal_lookup.loc[missing_same_year & unique_any, "focal_gvkey_source"] = "unique_any_year_cik_gvkey"

    missing_bridge_any = focal_lookup["focal_gvkey"].eq("")
    legacy_unique = focal_lookup["legacy_unique_gvkey"].fillna("").ne("")
    focal_lookup.loc[missing_bridge_any & legacy_unique, "focal_gvkey"] = focal_lookup.loc[missing_bridge_any & legacy_unique, "legacy_unique_gvkey"]
    focal_lookup.loc[missing_bridge_any & legacy_unique, "focal_gvkey_source"] = "legacy_unique_cik_gvkey_crosswalk"

    still_missing = focal_lookup["focal_gvkey"].fillna("").eq("")
    focal_lookup.loc[still_missing, "focal_gvkey"] = "-88888"
    focal_lookup.loc[still_missing, "focal_gvkey_source"] = "unresolved_no_unique_cik_gvkey"
    focal_lookup["focal_cik"] = focal_lookup["focal_cik"].astype("int64")
    focal_lookup["fyear"] = focal_lookup["fyear"].astype("int64")
    return focal_lookup


def risky_candidate(row: pd.Series) -> bool:
    candidate = first_text(row, ["partial_partial_candidate_name", "candidate_conm", "candidate_name"]).upper()
    tokens = set(re.findall(r"[A-Z0-9]+", candidate))
    return bool(tokens & RISK_TERMS)


def high_conf_step3(row: pd.Series, threshold=90) -> bool:
    classification = clean(row.get("llm_classification", "")).lower()
    decision = clean(row.get("llm_decision", "")).lower()
    confidence = pd.to_numeric(row.get("llm_confidence", ""), errors="coerce")
    if pd.isna(confidence):
        confidence = 0
    if decision != "accept_for_manual_alias_bridge" or confidence < threshold:
        return False
    if any(term in classification for term in ["multiple_entities", "unclear"]):
        return False
    return "company" in classification or "subsidiary_or_business_unit" in classification


def legal_suffix_firm_like(row: pd.Series) -> bool:
    classification = clean(row.get("llm_classification", "")).lower()
    if any(term in classification for term in ["multiple_entities", "unclear", "generic_phrase", "artifact", "person"]):
        return False
    text = " | ".join(
        clean(row.get(col, ""))
        for col in ["competitor_name", "suggested_alias_name", "candidate_input_name", "competitor_name_standardized"]
    )
    return bool(LEGAL_SUFFIX_PATTERN.search(text))


def load_review_decisions() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    step2_frames = []
    for sheet in ["review_all", "top500_by_frequency"]:
        if STEP2_REVIEW.exists():
            step2_frames.append(pd.read_excel(STEP2_REVIEW, sheet_name=sheet, engine="openpyxl"))
    step2 = pd.concat(step2_frames, ignore_index=True) if step2_frames else pd.DataFrame()
    if not step2.empty:
        step2["manual_decision_norm"] = step2["manual_decision"].map(lambda x: clean(x).lower())
        step2["reviewer_notes_clean"] = step2["reviewer_notes"].map(clean)
        step2 = step2[(step2["manual_decision_norm"].ne("")) | (step2["reviewer_notes_clean"].ne(""))]
        step2 = step2.drop_duplicates("record_id", keep="last")
        step2_dec = step2.set_index("record_id")["manual_decision_norm"].to_dict()
        step2_note = step2.set_index("record_id")["reviewer_notes_clean"].to_dict()
    else:
        step2_dec, step2_note = {}, {}

    step3 = pd.read_excel(STEP3_REVIEW, sheet_name="review_all", engine="openpyxl") if STEP3_REVIEW.exists() else pd.DataFrame()
    if not step3.empty:
        step3["manual_decision_norm"] = step3["manual_decision"].map(lambda x: clean(x).lower())
        step3 = step3[step3["manual_decision_norm"].ne("")].drop_duplicates("record_id", keep="last")
        step3_dec = step3.set_index("record_id")["manual_decision_norm"].to_dict()
    else:
        step3_dec = {}
    return step2_dec, step2_note, step3_dec


def build_alias_decisions() -> pd.DataFrame:
    step2_dec, step2_note, step3_dec = load_review_decisions()
    aliases = pd.read_csv(STEP88B_MASTER, low_memory=False)
    rows = []
    for _, row in aliases.iterrows():
        rid = clean(row.get("record_id", ""))
        action = clean(row.get("step88b_revised_action", ""))
        dec2 = step2_dec.get(rid, "")
        note2 = step2_note.get(rid, "")
        dec3 = step3_dec.get(rid, "")

        status = "unresolved_excluded_from_external"
        decision_source = "step9_unresolved_excluded"
        decision_rule = "no_safe_final_recovery_rule"
        name = first_text(row, ["suggested_alias_name", "candidate_input_name", "competitor_name_standardized", "competitor_name"])
        gvkey = "-1"
        cik = "-1"
        identifier_status = "unresolved_excluded"
        include_external = False

        if action in {"auto_recover_public_identifier", "auto_recover_public_identifier_ciq_crosswalk", "manual_review_public_candidate_ciq_new", "already_resolved_in_step85"}:
            status = "identified_public_firm"
            decision_source = "step8_previously_recovered_public_id"
            decision_rule = action
            name = first_text(row, ["candidate_conm", "candidate_name", "candidate_original_name", "candidate_bridge_name", "suggested_alias_name"])
            gvkey = first_valid(row, ["step88_proposed_gvkey", "candidate_gvkey", "ciq_crosswalk_gvkey"])
            cik = first_valid(row, ["step88_proposed_cik", "candidate_cik"])
            identifier_status = "public_identifier_available"
            include_external = True
        elif action in {"verified_company_no_public_identifier", "manual_review_company_no_identifier"}:
            status = "identified_verified_company_no_public_id"
            decision_source = "step8_company_evidence_no_public_id"
            decision_rule = action
            name = first_text(row, ["candidate_conm", "candidate_name", "suggested_alias_name", "candidate_input_name"])
            gvkey = cik = "-99999"
            identifier_status = "verified_company_no_public_identifier"
            include_external = True
        elif action == "manual_review_public_candidate":
            if any(has_valid_id(row.get(col, "")) for col in ["candidate_gvkey", "candidate_cik", "step88_proposed_gvkey", "step88_proposed_cik"]):
                status = "identified_public_firm"
                decision_source = "step8_broad_public_candidate_accepted_by_wrapup"
                decision_rule = "valid_identifier_candidate_retained"
                name = first_text(row, ["candidate_conm", "candidate_name", "suggested_alias_name"])
                gvkey = first_valid(row, ["candidate_gvkey", "step88_proposed_gvkey"])
                cik = first_valid(row, ["candidate_cik", "step88_proposed_cik"])
                identifier_status = "public_identifier_available"
                include_external = True
            else:
                status = "identified_verified_company_no_public_id"
                decision_source = "step8_public_candidate_without_identifier"
                decision_rule = "firm_like_candidate_no_public_id"
                name = first_text(row, ["candidate_conm", "candidate_name", "suggested_alias_name"])
                gvkey = cik = "-99999"
                identifier_status = "verified_company_no_public_identifier"
                include_external = True

        if dec2:
            if dec2 == "approve_public_id":
                status = "identified_public_firm"
                decision_source = "step2_human_approved_public_id"
                decision_rule = "manual_decision_approve_public_id"
                name = first_text(row, ["partial_partial_candidate_name", "candidate_conm", "candidate_name", "suggested_alias_name"])
                gvkey = first_valid(row, ["partial_partial_gvkey", "candidate_gvkey", "step88_proposed_gvkey"])
                cik = first_valid(row, ["partial_partial_cik", "candidate_cik", "step88_proposed_cik"])
                identifier_status = "public_identifier_available"
                include_external = True
            elif dec2 == "approve_verified_company_no_id":
                status = "identified_verified_company_no_public_id"
                decision_source = "step2_human_approved_verified_no_id"
                decision_rule = "manual_decision_approve_verified_company_no_id"
                name = first_text(row, ["partial_partial_candidate_name", "suggested_alias_name", "competitor_name"])
                gvkey = cik = "-99999"
                identifier_status = "verified_company_no_public_identifier"
                include_external = True
            elif dec2 == "reject_wrong_match_or_nonfirm" and note2:
                status = "identified_verified_company_no_public_id"
                decision_source = "step2_human_corrected_wrong_candidate"
                decision_rule = "reviewer_note_used_as_corrected_firm_name_no_id"
                name = note2
                gvkey = cik = "-99999"
                identifier_status = "verified_company_no_public_identifier"
                include_external = True
            elif dec2 == "reject_wrong_match_or_nonfirm":
                status = "unresolved_rejected_wrong_partial_candidate"
                decision_source = "step2_human_rejected_candidate"
                decision_rule = "manual_reject_no_corrected_name"
                include_external = False
            elif dec2 == "unclear":
                status = "unresolved_unclear"
                decision_source = "step2_human_unclear"
                decision_rule = "manual_unclear"
                include_external = False

        if dec3:
            if dec3 == "approve_verified_company_no_id":
                status = "identified_verified_company_no_public_id"
                decision_source = "step3_human_approved_verified_no_id"
                decision_rule = "manual_decision_approve_verified_company_no_id"
                name = first_text(row, ["suggested_alias_name", "candidate_input_name", "competitor_name"])
                gvkey = cik = "-99999"
                identifier_status = "verified_company_no_public_identifier"
                include_external = True
            elif dec3 == "unclear":
                status = "unresolved_unclear"
                decision_source = "step3_human_unclear"
                decision_rule = "manual_unclear"
                include_external = False
            elif "reject" in dec3:
                status = "dropped_human_rejected"
                decision_source = "step3_human_rejected"
                decision_rule = "manual_reject"
                include_external = False

        if not include_external and decision_source == "step9_unresolved_excluded":
            if action == "manual_review_public_candidate_partial_external" and exactish_step2(row) and not risky_candidate(row) and any(has_valid_id(row.get(col, "")) for col in ["partial_partial_gvkey", "partial_partial_cik"]):
                status = "identified_public_firm"
                decision_source = "step2_rule_extended_strict_public_id"
                decision_rule = "exact_or_legal_partial_external_with_identifier_no_risk_terms"
                name = first_text(row, ["partial_partial_candidate_name", "suggested_alias_name"])
                gvkey = first_valid(row, ["partial_partial_gvkey", "candidate_gvkey"])
                cik = first_valid(row, ["partial_partial_cik", "candidate_cik"])
                identifier_status = "public_identifier_available"
                include_external = True
            elif action == "external_partial_evidence_needs_review" and exactish_step2(row) and not risky_candidate(row):
                status = "identified_verified_company_no_public_id"
                decision_source = "step2_rule_extended_verified_no_id"
                decision_rule = "exact_or_legal_partial_external_no_risk_terms"
                name = first_text(row, ["partial_partial_candidate_name", "suggested_alias_name"])
                gvkey = cik = "-99999"
                identifier_status = "verified_company_no_public_identifier"
                include_external = True
            elif action in {"unresolved_no_accepted_evidence", "remain_unresolved_reason_coded"} and high_conf_step3(row, threshold=90):
                status = "identified_verified_company_no_public_id"
                decision_source = "step3_rule_extended_high_confidence_no_id"
                decision_rule = "llm_company_like_confidence_ge_90_no_external_id"
                name = first_text(row, ["suggested_alias_name", "candidate_input_name", "competitor_name"])
                gvkey = cik = "-99999"
                identifier_status = "verified_company_no_public_identifier"
                include_external = True
            elif action in {"unresolved_no_accepted_evidence", "remain_unresolved_reason_coded"} and legal_suffix_firm_like(row):
                status = "identified_verified_company_no_public_id"
                decision_source = "step9_legal_suffix_verified_no_id"
                decision_rule = "unresolved_name_contains_legal_entity_suffix_no_public_id"
                name = first_text(row, ["suggested_alias_name", "candidate_input_name", "competitor_name"])
                gvkey = cik = "-99999"
                identifier_status = "verified_company_no_public_identifier"
                include_external = True
            elif action in {"manual_review_public_candidate_partial_external", "external_partial_evidence_needs_review"}:
                status = "unresolved_risky_partial_external_excluded"
                decision_rule = "partial_external_evidence_risky_not_exported"
            else:
                status = "unresolved_no_safe_candidate_excluded"

        rows.append(
            {
                "record_id": rid,
                "merge_key": clean(row.get("record_key", "")) or normalize_key(row.get("competitor_name_standardized", "")),
                "step9_alias_final_status": status,
                "step9_alias_final_name": name,
                "step9_alias_final_gvkey": gvkey,
                "step9_alias_final_cik": cik,
                "step9_alias_identifier_status": identifier_status,
                "step9_decision_source": decision_source,
                "step9_decision_rule": decision_rule,
                "step9_include_external": include_external,
                "step9_review_decision_step2": dec2,
                "step9_reviewer_note_step2": note2,
                "step9_review_decision_step3": dec3,
                "step88b_revised_action": action,
                "step88b_revised_reason": clean(row.get("step88b_revised_reason", "")),
                "step9_alias_frequency": pd.to_numeric(row.get("frequency", 0), errors="coerce"),
            }
        )
    decisions = pd.DataFrame(rows)
    decisions = decisions.sort_values(["merge_key", "step9_include_external", "step9_alias_frequency"], ascending=[True, False, False])
    decisions = decisions.drop_duplicates("merge_key", keep="first")
    return decisions


def final_has_public_id(df: pd.DataFrame) -> pd.Series:
    return df["step9_final_gvkey"].map(has_valid_id) | df["step9_final_cik"].map(has_valid_id)


def main() -> None:
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    alias_decisions = build_alias_decisions()
    print(f"Alias decisions: {len(alias_decisions):,}")
    print(alias_decisions["step9_alias_final_status"].value_counts().to_string())

    long_df = pd.read_csv(BASE_LONG, low_memory=False)
    long_df = long_df[pd.to_numeric(long_df["fyear"], errors="coerce").lt(2026)].copy()
    focal_lookup = build_focal_gvkey_lookup(long_df[["focal_cik", "fyear"]])
    focal_lookup.to_csv(OUT_FOCAL_GVKEY_AUDIT, index=False)
    if "merge_key" not in long_df.columns:
        long_df["merge_key"] = long_df["competitor_name_standardized"].map(normalize_key)
    enriched = long_df.merge(alias_decisions, on="merge_key", how="left")
    enriched = enriched.merge(
        focal_lookup[
            [
                "focal_cik", "fyear", "focal_gvkey", "focal_gvkey_source",
                "gvkey_panel_same_year", "gvkey_bridge_same_year", "gvkey_unique_any_year",
                "n_unique_any_year_gvkeys", "any_year_min", "any_year_max", "any_year_sources",
                "legacy_unique_gvkey", "n_legacy_gvkeys", "legacy_conm_examples",
            ]
        ],
        on=["focal_cik", "fyear"],
        how="left",
        validate="many_to_one",
    )
    enriched["focal_gvkey"] = enriched["focal_gvkey"].fillna("-88888").map(format_identifier)
    enriched["focal_gvkey_source"] = enriched["focal_gvkey_source"].fillna("unresolved_no_unique_cik_gvkey")

    has_step9 = enriched["step9_alias_final_status"].notna()
    enriched["step9_final_status"] = enriched["final_status"]
    enriched["step9_final_name"] = enriched["final_competitor_name_standardized"]
    enriched["step9_final_gvkey"] = enriched["final_competitor_gvkey"].astype(str)
    enriched["step9_final_cik"] = enriched["final_competitor_cik"].astype(str)
    enriched["step9_identifier_status"] = enriched["final_identifier_status"]
    enriched["step9_decision_source_final"] = "pre_step9_existing_final_status"
    enriched["step9_decision_rule_final"] = enriched["final_status_stage"].fillna("")
    enriched["step9_include_external"] = False

    idx = has_step9
    enriched.loc[idx, "step9_final_status"] = enriched.loc[idx, "step9_alias_final_status"]
    enriched.loc[idx, "step9_final_name"] = enriched.loc[idx, "step9_alias_final_name"]
    enriched.loc[idx, "step9_final_gvkey"] = enriched.loc[idx, "step9_alias_final_gvkey"]
    enriched.loc[idx, "step9_final_cik"] = enriched.loc[idx, "step9_alias_final_cik"]
    enriched.loc[idx, "step9_identifier_status"] = enriched.loc[idx, "step9_alias_identifier_status"]
    enriched.loc[idx, "step9_decision_source_final"] = enriched.loc[idx, "step9_decision_source"]
    enriched.loc[idx, "step9_decision_rule_final"] = enriched.loc[idx, "step9_decision_rule"]

    existing_identified = enriched["final_status"].isin(["identified_public_firm", "identified_verified_company_no_public_id"])
    step9_identified = enriched["step9_final_status"].isin(["identified_public_firm", "identified_verified_company_no_public_id"])
    enriched["step9_include_external"] = existing_identified | step9_identified
    enriched.loc[enriched["step9_final_status"].eq("identified_public_firm"), "step9_identifier_status"] = "public_identifier_available"
    enriched.loc[enriched["step9_final_status"].eq("identified_verified_company_no_public_id"), "step9_identifier_status"] = "verified_company_no_public_identifier"

    # Internal audit keeps all rows.
    internal_cols = [c for c in INTERNAL_KEEP_COLS if c in enriched.columns] + [
        "focal_gvkey", "focal_gvkey_source", "gvkey_panel_same_year", "gvkey_bridge_same_year",
        "gvkey_unique_any_year", "n_unique_any_year_gvkeys", "any_year_min", "any_year_max",
        "any_year_sources", "legacy_unique_gvkey", "n_legacy_gvkeys", "legacy_conm_examples",
        "step9_final_status", "step9_final_name", "step9_final_gvkey", "step9_final_cik",
        "step9_identifier_status", "step9_decision_source_final", "step9_decision_rule_final",
        "step9_include_external", "step9_review_decision_step2", "step9_reviewer_note_step2",
        "step9_review_decision_step3", "step88b_revised_action", "step88b_revised_reason",
    ]
    enriched[internal_cols].to_csv(OUT_INTERNAL, index=False)

    # External clean all-status is intentionally clean but still includes status labels; identified-only has no -1.
    clean_all = pd.DataFrame(
        {
            "focal_sic": enriched["sic_file"].map(format_sic),
            "filename": enriched["filename"],
            "focal_cik": enriched["focal_cik"],
            "focal_gvkey": enriched["focal_gvkey"],
            "fyear": enriched["fyear"],
            "original_competitor_order": enriched["competitor_order"],
            "competitor_name_original": enriched["competitor_name"],
            "competitor_name_final": enriched["step9_final_name"],
            "competitor_gvkey": enriched["step9_final_gvkey"],
            "competitor_cik": enriched["step9_final_cik"],
            "competitor_identifier_status": enriched["step9_identifier_status"],
            "competitor_record_status": enriched["step9_final_status"],
        }
    )
    clean_all["competitor_gvkey"] = [
        external_id_value(v, s)
        for v, s in zip(clean_all["competitor_gvkey"], clean_all["competitor_identifier_status"])
    ]
    clean_all["competitor_cik"] = [
        external_id_value(v, s)
        for v, s in zip(clean_all["competitor_cik"], clean_all["competitor_identifier_status"])
    ]
    clean_all.to_csv(OUT_EXTERNAL_ALL_STATUS, index=False)

    identified = clean_all[clean_all["competitor_record_status"].isin(["identified_public_firm", "identified_verified_company_no_public_id"])].copy()
    identified = identified.sort_values(["focal_cik", "fyear", "filename", "original_competitor_order"])
    identified["competitor_order"] = (
        identified.groupby(["focal_cik", "fyear", "filename"], dropna=False)
        .cumcount()
        .add(1)
    )
    identified[EXTERNAL_COLS].to_csv(OUT_EXTERNAL_IDENTIFIED, index=False)

    edges = (
        identified.groupby(["focal_sic", "filename", "focal_cik", "focal_gvkey", "fyear", "competitor_name_final", "competitor_gvkey", "competitor_cik", "competitor_identifier_status"], dropna=False)
        .agg(first_competitor_order=("competitor_order", "min"))
        .reset_index()
        .sort_values(["focal_cik", "fyear", "first_competitor_order"])
    )
    edges = edges[
        [
            "focal_sic", "filename", "focal_cik", "focal_gvkey", "fyear", "first_competitor_order",
            "competitor_name_final", "competitor_gvkey", "competitor_cik", "competitor_identifier_status",
        ]
    ]
    edges.to_csv(OUT_EDGES, index=False)

    status_summary = (
        enriched.groupby(["step9_final_status", "step9_identifier_status", "step9_decision_source_final", "step9_decision_rule_final"], dropna=False)
        .agg(mentions=("competitor_name", "size"), unique_names=("merge_key", "nunique"))
        .reset_index()
        .sort_values("mentions", ascending=False)
    )
    status_summary.to_csv(OUT_STATUS_SUMMARY, index=False)

    unique_summary = (
        enriched.groupby(["step9_final_status", "step9_identifier_status"], dropna=False)
        .agg(unique_names=("merge_key", "nunique"), mentions=("competitor_name", "size"))
        .reset_index()
        .sort_values("mentions", ascending=False)
    )
    unique_summary.to_csv(OUT_UNIQUE_SUMMARY, index=False)

    rule_summary = (
        enriched.groupby(["step9_decision_source_final", "step9_decision_rule_final", "step9_final_status"], dropna=False)
        .agg(mentions=("competitor_name", "size"), unique_names=("merge_key", "nunique"))
        .reset_index()
        .sort_values("mentions", ascending=False)
    )
    rule_summary.to_csv(OUT_RULE_SUMMARY, index=False)

    # Error-rate summary from human-reviewed Step 2/3 samples.
    step2_frames = [pd.read_excel(STEP2_REVIEW, sheet_name=s, engine="openpyxl") for s in ["review_all", "top500_by_frequency"] if STEP2_REVIEW.exists()]
    step2 = pd.concat(step2_frames, ignore_index=True)
    step2["decision"] = step2["manual_decision"].map(lambda x: clean(x).lower())
    step2["note"] = step2["reviewer_notes"].map(clean)
    step2 = step2[(step2["decision"].ne("")) | (step2["note"].ne(""))].drop_duplicates("record_id", keep="last")
    step3 = pd.read_excel(STEP3_REVIEW, sheet_name="review_all", engine="openpyxl")
    step3["decision"] = step3["manual_decision"].map(lambda x: clean(x).lower())
    step3 = step3[step3["decision"].ne("")].drop_duplicates("record_id", keep="last")
    error_rows = []
    if len(step2):
        accepted = step2["decision"].isin(["approve_public_id", "approve_verified_company_no_id"]).sum()
        wrong_or_unclear = step2["decision"].isin(["reject_wrong_match_or_nonfirm", "unclear"]).sum()
        corrected = ((step2["decision"].eq("reject_wrong_match_or_nonfirm")) & step2["note"].ne("")).sum()
        error_rows += [
            {"validation_group": "step2_partial_external_candidate", "metric": "reviewed_rows", "value": len(step2)},
            {"validation_group": "step2_partial_external_candidate", "metric": "candidate_acceptance_precision", "value": accepted / len(step2)},
            {"validation_group": "step2_partial_external_candidate", "metric": "wrong_or_unclear_candidate_rate", "value": wrong_or_unclear / len(step2)},
            {"validation_group": "step2_partial_external_candidate", "metric": "rejected_with_corrected_firm_name_share", "value": corrected / len(step2)},
        ]
    if len(step3):
        approved = step3["decision"].eq("approve_verified_company_no_id").sum()
        error_rows += [
            {"validation_group": "step3_no_candidate_company_like", "metric": "reviewed_rows", "value": len(step3)},
            {"validation_group": "step3_no_candidate_company_like", "metric": "verified_no_id_approval_rate", "value": approved / len(step3)},
        ]
    pd.DataFrame(error_rows).to_csv(OUT_ERROR_SUMMARY, index=False)

    unresolved = enriched[~enriched["step9_include_external"]].copy()
    unresolved[internal_cols].to_csv(OUT_UNRESOLVED, index=False)
    corrected = enriched[enriched["step9_decision_source_final"].eq("step2_human_corrected_wrong_candidate")].copy()
    corrected[internal_cols].to_csv(OUT_REJECTED_CORRECTIONS, index=False)

    print("Step 9 complete")
    print(f"Internal rows: {len(enriched):,}")
    print(f"External identified rows: {len(identified):,}")
    print(f"External all-status rows: {len(clean_all):,}")
    print(f"External identified -1 gvkey rows: {identified['competitor_gvkey'].astype(str).isin(['-1','-1.0']).sum():,}")
    print(f"External identified -1 cik rows: {identified['competitor_cik'].astype(str).isin(['-1','-1.0']).sum():,}")
    print(f"External all-status -1 gvkey rows: {clean_all['competitor_gvkey'].astype(str).isin(['-1','-1.0']).sum():,}")
    print(f"External all-status -1 cik rows: {clean_all['competitor_cik'].astype(str).isin(['-1','-1.0']).sum():,}")
    print("Focal GVKEY source counts, focal CIK-year level:")
    print(
        enriched[["focal_cik", "fyear", "focal_gvkey_source"]]
        .drop_duplicates()
        ["focal_gvkey_source"]
        .value_counts(dropna=False)
        .to_string()
    )
    print("Status summary:")
    print(unique_summary.to_string(index=False))


if __name__ == "__main__":
    main()
