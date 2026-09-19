from __future__ import annotations

import csv
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd


PROJECT = Path(r"C:\Users\mnasiri\Documents\GitHub\CompetitorNetworkV2")
FINAL = PROJECT / "data" / "results" / "final"
DESCRIPTIVES = PROJECT / "data" / "results" / "descriptives"
RELEASE = PROJECT / "reviewer_release" / "management_science_competitor_network_v1_lean"

POPULATION = DESCRIPTIVES / "merged_mapped_wide_no20f.csv"
IDENTIFIED_MENTIONS = FINAL / "final_competitor_mentions_clean_identified_only_step9_rev3.csv"
ALL_STATUS = FINAL / "final_competitor_mentions_clean_all_status_step9_rev3.csv"
FOCAL_GVKEY_AUDIT = FINAL / "final_step9_focal_gvkey_recovery_audit_rev3.csv"
DOWNLOAD_METADATA_DIR = PROJECT / "data" / "results" / "downloads"
IDENTIFIER_YEAR_PANEL = PROJECT / "company_identifier_year_panel.csv"
YEAR_SPECIFIC_BRIDGE = PROJECT / "company_alias_bridge_year_specific.csv"
LEGACY_CIK_GVKEY = PROJECT / "cik_tic_gvkey_full_combined_cleaned.csv"

OUT_EXTERNAL = FINAL / "final_competitor_filing_population_with_named_competitors_step9_rev7.csv"
OUT_AUDIT = FINAL / "final_competitor_filing_population_coverage_audit_step9_rev7.csv"
OUT_SUMMARY = FINAL / "final_competitor_filing_population_coverage_summary_step9_rev7.csv"
OUT_REPORT_PERIOD_METADATA = FINAL / "filing_report_period_metadata_step9_rev7.csv"
OUT_SELF_COMPETITOR_AUDIT = FINAL / "audit_removed_self_competitors_step9_rev7.csv"
OUT_MULTIGVKEY_AUDIT = FINAL / "audit_same_name_multiple_gvkeys_step9_rev7.csv"
OUT_MULTIGVKEY_REPAIR_AUDIT = FINAL / "audit_same_name_multigvkey_repairs_step9_rev7.csv"
OUT_PRE2000_EXCLUDED_AUDIT = FINAL / "audit_excluded_pre2000_observations_step9_rev7.csv"
OUT_ANALYSIS_WINDOW_EXCLUDED_AUDIT = FINAL / "audit_excluded_out_of_analysis_window_step9_rev8.csv"
OUT_BY_SIC = FINAL / "final_competitor_filing_population_by_sic_step9_rev7_current"

MIN_ANALYSIS_FYEAR = 2002
MAX_ANALYSIS_FYEAR = 2024

LEGAL_WORDS_FOR_SELF_NAME = {
    "INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "PLC", "AG", "SA", "NV",
    "BV", "LLC", "LP", "LLP", "GMBH", "SPA", "SE", "HOLDING", "HOLDINGS", "HLDG",
    "GROUP", "GRP", "THE",
}


def format_sic(value) -> str:
    text = "" if value is None else str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return ""
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number)).zfill(4)
    except Exception:
        pass
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(4) if digits else text


def blank_id(value) -> str:
    text = "" if value is None else str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return ""
    try:
        number = float(text)
        if number.is_integer():
            return str(int(number))
    except Exception:
        pass
    return text


def external_identifier(value) -> str:
    text = blank_id(value)
    return "" if text in {"-1", "0", "-88888", "-99999"} else text


def export_competitor_identifier(value) -> str:
    text = blank_id(value)
    if text in {"-1", "0"}:
        return "-88888"
    return text


def normalize_company_name_for_self_check(value) -> str:
    text = "" if value is None else str(value).upper()
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    tokens = [token for token in text.split() if token and token not in LEGAL_WORDS_FOR_SELF_NAME]
    return " ".join(tokens)


def normalize_company_core(value) -> str:
    return normalize_company_name_for_self_check(value)


def load_filing_report_period_metadata() -> pd.DataFrame:
    parts = []
    usecols = ["cik", "downloaded_file_name", "filingDate", "reportDate", "doc_name", "href"]
    for source in sorted(DOWNLOAD_METADATA_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(source, usecols=usecols, dtype=str, keep_default_na=False, low_memory=False)
        except Exception:
            continue
        df["sic_file_metadata"] = source.stem
        parts.append(df)
    if not parts:
        raise FileNotFoundError(f"No SEC download metadata CSV files found in {DOWNLOAD_METADATA_DIR}")

    meta = pd.concat(parts, ignore_index=True)
    meta["focal_cik"] = pd.to_numeric(meta["cik"], errors="coerce").astype("Int64")
    meta = meta.dropna(subset=["focal_cik"]).copy()
    meta["focal_cik"] = meta["focal_cik"].astype("int64")
    meta["filename"] = meta["downloaded_file_name"].astype(str).str.replace(".html", ".txt", regex=False)
    meta["filing_date"] = pd.to_datetime(meta["filingDate"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    meta["report_period_date"] = pd.to_datetime(meta["reportDate"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    meta["filing_year"] = pd.to_datetime(meta["filingDate"], errors="coerce").dt.year.astype("Int64")
    meta["report_year"] = pd.to_datetime(meta["reportDate"], errors="coerce").dt.year.astype("Int64")
    meta = (
        meta.sort_values(["filename", "focal_cik", "report_period_date", "filing_date"])
        .drop_duplicates(["filename", "focal_cik"], keep="first")
        .rename(columns={"doc_name": "sec_form_type", "href": "sec_filing_href"})
    )
    return meta[
        [
            "filename",
            "focal_cik",
            "filing_date",
            "report_period_date",
            "filing_year",
            "report_year",
            "sec_form_type",
            "sec_filing_href",
            "sic_file_metadata",
        ]
    ]


def fiscal_year_from_report_period(report_period_date: pd.Series) -> pd.Series:
    dates = pd.to_datetime(report_period_date, errors="coerce")
    fyear = dates.dt.year.where(
        (dates.dt.month.gt(5)) | ((dates.dt.month.eq(5)) & (dates.dt.day.gt(31))),
        dates.dt.year - 1,
    )
    return fyear.astype("Int64")


def load_population() -> pd.DataFrame:
    usecols = [
        "filename",
        "fyear",
        "sic_file",
        "focal_cik",
        "n_competitor_mentions",
        "has_named_competitor",
    ]
    pop = pd.read_csv(POPULATION, usecols=usecols, low_memory=False)
    pop["fyear"] = pd.to_numeric(pop["fyear"], errors="coerce")
    pop = pop[pop["fyear"].lt(2026)].copy()
    pop["fyear"] = pop["fyear"].astype("int64")
    pop["focal_cik"] = pd.to_numeric(pop["focal_cik"], errors="coerce").astype("Int64")
    pop = pop.dropna(subset=["focal_cik"])
    pop["focal_cik"] = pop["focal_cik"].astype("int64")
    pop["focal_sic"] = pop["sic_file"].map(format_sic)
    pop["n_step4_extracted_names"] = pd.to_numeric(pop["n_competitor_mentions"], errors="coerce").fillna(0).astype("int64")
    sic_audit = (
        pop.groupby(["filename", "focal_cik", "fyear"], dropna=False)
        .agg(
            focal_sics_all=("focal_sic", lambda s: "|".join(sorted({str(x).strip() for x in s if str(x).strip()}))),
            n_focal_sics=("focal_sic", lambda s: len({str(x).strip() for x in s if str(x).strip()})),
        )
        .reset_index()
    )
    pop = (
        pop.sort_values(["filename", "focal_cik", "fyear", "focal_sic"])
        .drop_duplicates(["filename", "focal_cik", "fyear"], keep="first")
        .copy()
    )
    pop = pop.merge(sic_audit, on=["filename", "focal_cik", "fyear"], how="left", validate="one_to_one")
    metadata = load_filing_report_period_metadata()
    pop = pop.merge(metadata, on=["filename", "focal_cik"], how="left", validate="many_to_one")
    pop["filing_year_from_filename"] = pop["fyear"]
    pop["fyear_from_report_period"] = fiscal_year_from_report_period(pop["report_period_date"])
    pop["fyear_matches_report_year"] = (
        pd.to_numeric(pop["filing_year_from_filename"], errors="coerce")
        .eq(pd.to_numeric(pop["report_year"], errors="coerce"))
    )
    return pop


def add_focal_gvkey(pop: pd.DataFrame) -> pd.DataFrame:
    audit = pd.read_csv(
        FOCAL_GVKEY_AUDIT,
        usecols=["focal_cik", "fyear", "focal_gvkey"],
        low_memory=False,
    )
    audit["focal_cik"] = pd.to_numeric(audit["focal_cik"], errors="coerce").astype("Int64")
    audit["fyear"] = pd.to_numeric(audit["fyear"], errors="coerce").astype("Int64")
    audit = audit.dropna(subset=["focal_cik", "fyear"]).copy()
    audit["focal_cik"] = audit["focal_cik"].astype("int64")
    audit["fyear"] = audit["fyear"].astype("int64")
    audit["focal_gvkey"] = audit["focal_gvkey"].map(blank_id)
    audit = audit.drop_duplicates(["focal_cik", "fyear"], keep="first")
    out = pop.merge(audit, on=["focal_cik", "fyear"], how="left", validate="many_to_one")
    out["focal_gvkey"] = out["focal_gvkey"].fillna("")
    missing = out["focal_gvkey"].astype(str).str.strip().eq("")
    if missing.any():
        fallback = build_focal_gvkey_fallback(out.loc[missing, ["focal_cik", "fyear"]])
        out = out.merge(fallback, on=["focal_cik", "fyear"], how="left", validate="many_to_one")
        out["focal_gvkey"] = out["focal_gvkey"].where(
            out["focal_gvkey"].astype(str).str.strip().ne(""),
            out["focal_gvkey_fallback"].fillna(""),
        )
        out = out.drop(columns=["focal_gvkey_fallback"])
    return out


def build_focal_gvkey_fallback(target_keys: pd.DataFrame) -> pd.DataFrame:
    target = target_keys[["focal_cik", "fyear"]].drop_duplicates().copy()
    target["focal_cik"] = pd.to_numeric(target["focal_cik"], errors="coerce")
    target["fyear"] = pd.to_numeric(target["fyear"], errors="coerce")
    target = target.dropna(subset=["focal_cik", "fyear"])
    target["focal_cik"] = target["focal_cik"].astype("int64")
    target["fyear"] = target["fyear"].astype("int64")

    panel = pd.read_csv(IDENTIFIER_YEAR_PANEL, usecols=lambda c: c in {"cik", "gvkey", "fyear"}, low_memory=False)
    panel["focal_cik"] = pd.to_numeric(panel["cik"], errors="coerce")
    panel["fyear"] = pd.to_numeric(panel["fyear"], errors="coerce")
    panel["gvkey_clean"] = panel["gvkey"].map(blank_id)
    panel = panel.dropna(subset=["focal_cik", "fyear"])
    panel = panel[panel["gvkey_clean"].astype(str).str.strip().ne("")]
    panel["focal_cik"] = panel["focal_cik"].astype("int64")
    panel["fyear"] = panel["fyear"].astype("int64")
    panel_same = (
        panel.sort_values(["focal_cik", "fyear", "gvkey_clean"])
        .drop_duplicates(["focal_cik", "fyear"], keep="first")
        [["focal_cik", "fyear", "gvkey_clean"]]
        .rename(columns={"gvkey_clean": "gvkey_panel_same_year"})
    )

    bridge = pd.read_csv(YEAR_SPECIFIC_BRIDGE, usecols=lambda c: c in {"cik", "gvkey", "fyear", "matching_priority"}, low_memory=False)
    bridge["focal_cik"] = pd.to_numeric(bridge["cik"], errors="coerce")
    bridge["fyear"] = pd.to_numeric(bridge["fyear"], errors="coerce")
    bridge["gvkey_clean"] = bridge["gvkey"].map(blank_id)
    bridge = bridge.dropna(subset=["focal_cik", "fyear"])
    bridge = bridge[bridge["gvkey_clean"].astype(str).str.strip().ne("")]
    bridge["focal_cik"] = bridge["focal_cik"].astype("int64")
    bridge["fyear"] = bridge["fyear"].astype("int64")
    bridge["matching_priority"] = pd.to_numeric(bridge.get("matching_priority"), errors="coerce").fillna(99)
    bridge_same = (
        bridge.sort_values(["focal_cik", "fyear", "matching_priority", "gvkey_clean"])
        .drop_duplicates(["focal_cik", "fyear"], keep="first")
        [["focal_cik", "fyear", "gvkey_clean"]]
        .rename(columns={"gvkey_clean": "gvkey_bridge_same_year"})
    )
    bridge_any = (
        bridge.drop_duplicates(["focal_cik", "gvkey_clean"])
        .groupby("focal_cik", dropna=False)
        .agg(
            n_bridge_any_gvkeys=("gvkey_clean", "nunique"),
            gvkey_bridge_any=("gvkey_clean", lambda s: sorted(set(s))[0] if len(set(s)) == 1 else ""),
        )
        .reset_index()
    )
    bridge_any.loc[bridge_any["n_bridge_any_gvkeys"].ne(1), "gvkey_bridge_any"] = ""

    legacy = pd.read_csv(LEGACY_CIK_GVKEY, usecols=lambda c: c in {"cik", "gvkey"}, low_memory=False)
    legacy["focal_cik"] = pd.to_numeric(legacy["cik"], errors="coerce")
    legacy["gvkey_clean"] = legacy["gvkey"].map(blank_id)
    legacy = legacy.dropna(subset=["focal_cik"])
    legacy = legacy[legacy["gvkey_clean"].astype(str).str.strip().ne("")]
    legacy["focal_cik"] = legacy["focal_cik"].astype("int64")
    legacy_any = (
        legacy.drop_duplicates(["focal_cik", "gvkey_clean"])
        .groupby("focal_cik", dropna=False)
        .agg(
            n_legacy_gvkeys=("gvkey_clean", "nunique"),
            gvkey_legacy_any=("gvkey_clean", lambda s: sorted(set(s))[0] if len(set(s)) == 1 else ""),
        )
        .reset_index()
    )
    legacy_any.loc[legacy_any["n_legacy_gvkeys"].ne(1), "gvkey_legacy_any"] = ""

    out = target.merge(panel_same, on=["focal_cik", "fyear"], how="left")
    out = out.merge(bridge_same, on=["focal_cik", "fyear"], how="left")
    out = out.merge(bridge_any, on="focal_cik", how="left")
    out = out.merge(legacy_any, on="focal_cik", how="left")
    out["focal_gvkey_fallback"] = ""
    for col in ["gvkey_panel_same_year", "gvkey_bridge_same_year", "gvkey_bridge_any", "gvkey_legacy_any"]:
        missing = out["focal_gvkey_fallback"].astype(str).str.strip().eq("")
        out.loc[missing, "focal_gvkey_fallback"] = out.loc[missing, col].fillna("")
    return out[["focal_cik", "fyear", "focal_gvkey_fallback"]]


def load_identified_mentions() -> pd.DataFrame:
    usecols = [
        "focal_sic",
        "filename",
        "focal_cik",
        "focal_gvkey",
        "fyear",
        "competitor_order",
        "competitor_name_original",
        "competitor_name_final",
        "competitor_gvkey",
        "competitor_cik",
    ]
    df = pd.read_csv(IDENTIFIED_MENTIONS, usecols=usecols, low_memory=False)
    df["fyear"] = pd.to_numeric(df["fyear"], errors="coerce")
    df = df[df["fyear"].lt(2026)].copy()
    df["fyear"] = df["fyear"].astype("int64")
    df["focal_cik"] = pd.to_numeric(df["focal_cik"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["focal_cik"])
    df["focal_cik"] = df["focal_cik"].astype("int64")
    for col in ["focal_sic", "focal_gvkey"]:
        df[col] = df[col].map(blank_id)
    for col in ["competitor_gvkey", "competitor_cik"]:
        df[col] = df[col].map(export_competitor_identifier)
    df["focal_sic"] = df["focal_sic"].map(format_sic)
    return dedupe_identified_competitors(df)


def competitor_identity_key(row: pd.Series) -> str:
    cik = external_identifier(row.get("competitor_cik", ""))
    gvkey = external_identifier(row.get("competitor_gvkey", ""))
    name = str(row.get("competitor_name_final", "")).strip().upper()
    if cik:
        return f"CIK:{cik}"
    if gvkey:
        return f"GVKEY:{gvkey}"
    return f"NAME:{name}"


def unique_join(values: pd.Series) -> str:
    seen = []
    for value in values:
        text = "" if value is None else str(value).strip()
        if text and text not in seen:
            seen.append(text)
    return " | ".join(seen)


def first_nonblank(values: pd.Series) -> str:
    for value in values:
        text = "" if value is None else str(value).strip()
        if text:
            return text
    return ""


def dedupe_identified_competitors(df: pd.DataFrame) -> pd.DataFrame:
    """Collapse repeated extracted variants that resolve to the same final competitor identity."""
    df = df.copy()
    df["competitor_order_numeric"] = pd.to_numeric(df["competitor_order"], errors="coerce").fillna(10**9).astype("int64")
    df["competitor_identity_key"] = df.apply(competitor_identity_key, axis=1)
    grouped = (
        df.sort_values(["filename", "focal_cik", "fyear", "competitor_order_numeric", "competitor_name_original"])
        .groupby(["filename", "focal_cik", "fyear", "competitor_identity_key"], dropna=False)
        .agg(
            focal_sic=("focal_sic", first_nonblank),
            focal_gvkey=("focal_gvkey", first_nonblank),
            competitor_order_first=("competitor_order_numeric", "min"),
            competitor_name_original=("competitor_name_original", unique_join),
            competitor_name_final=("competitor_name_final", first_nonblank),
            competitor_gvkey=("competitor_gvkey", first_nonblank),
            competitor_cik=("competitor_cik", first_nonblank),
            n_original_mentions_collapsed=("competitor_name_original", "size"),
            competitor_original_names_all=("competitor_name_original", unique_join),
        )
        .reset_index()
    )
    grouped = grouped.sort_values(["filename", "focal_cik", "fyear", "competitor_order_first", "competitor_name_final"])
    grouped["competitor_order"] = (
        grouped.groupby(["filename", "focal_cik", "fyear"], dropna=False).cumcount() + 1
    ).astype(str)
    return grouped[
        [
            "focal_sic",
            "filename",
            "focal_cik",
            "focal_gvkey",
            "fyear",
            "competitor_order",
            "competitor_name_original",
            "competitor_name_final",
            "competitor_gvkey",
            "competitor_cik",
            "n_original_mentions_collapsed",
            "competitor_original_names_all",
        ]
    ]


def build_audit(pop: pd.DataFrame, identified: pd.DataFrame) -> pd.DataFrame:
    all_status = pd.read_csv(
        ALL_STATUS,
        usecols=["filename", "focal_cik", "fyear", "competitor_record_status"],
        low_memory=False,
    )
    all_status["fyear"] = pd.to_numeric(all_status["fyear"], errors="coerce")
    all_status = all_status[all_status["fyear"].lt(2026)].copy()
    all_status["fyear"] = all_status["fyear"].astype("int64")
    all_status["focal_cik"] = pd.to_numeric(all_status["focal_cik"], errors="coerce").astype("Int64")
    all_status = all_status.dropna(subset=["focal_cik"])
    all_status["focal_cik"] = all_status["focal_cik"].astype("int64")

    status_counts = (
        all_status.pivot_table(
            index=["filename", "focal_cik", "fyear"],
            columns="competitor_record_status",
            values="competitor_record_status",
            aggfunc="size",
            fill_value=0,
        )
        .reset_index()
    )
    status_counts.columns = [str(c) for c in status_counts.columns]
    identified_counts = (
        identified.groupby(["filename", "focal_cik", "fyear"], dropna=False)
        .agg(
            n_final_named_competitors=("competitor_name_final", "size"),
            n_original_mentions_behind_final_competitors=("n_original_mentions_collapsed", "sum"),
            n_final_public_identifier_competitors=(
                "competitor_gvkey",
                lambda s: sum(str(x).strip() not in {"", "-88888", "-99999"} for x in s),
            ),
            n_final_verified_no_public_id_competitors=(
                "competitor_gvkey",
                lambda s: sum(str(x).strip() == "-99999" for x in s),
            ),
        )
        .reset_index()
    )

    audit = pop[
        [
            "focal_sic",
            "filename",
            "focal_cik",
            "focal_gvkey",
            "fyear",
            "filing_date",
            "report_period_date",
            "fyear_from_report_period",
            "filing_year_from_filename",
            "report_year",
            "fyear_matches_report_year",
            "sec_form_type",
            "sec_filing_href",
            "sic_file_metadata",
            "focal_sics_all",
            "n_focal_sics",
            "n_step4_extracted_names",
        ]
    ].merge(status_counts, on=["filename", "focal_cik", "fyear"], how="left")
    audit = audit.merge(identified_counts, on=["filename", "focal_cik", "fyear"], how="left")
    count_cols = [c for c in audit.columns if c.startswith(("identified_", "dropped_", "unresolved_", "n_final_", "n_original_"))]
    for col in count_cols:
        audit[col] = pd.to_numeric(audit[col], errors="coerce").fillna(0).astype("int64")

    audit["has_step4_extracted_names"] = audit["n_step4_extracted_names"].gt(0)
    audit["has_final_named_competitor"] = audit["n_final_named_competitors"].gt(0)
    audit["has_multiple_focal_sics"] = audit["n_focal_sics"].gt(1)
    audit["final_competitor_coverage_status"] = "names_extracted_but_none_identified"
    audit.loc[audit["n_step4_extracted_names"].eq(0), "final_competitor_coverage_status"] = "no_names_extracted_from_competition_text"
    audit.loc[audit["has_final_named_competitor"], "final_competitor_coverage_status"] = "has_final_named_competitor"
    return audit


def build_external(pop: pd.DataFrame, identified: pd.DataFrame, audit: pd.DataFrame) -> pd.DataFrame:
    pop_keys = pop[
        [
            "focal_sic",
            "filename",
            "focal_cik",
            "focal_gvkey",
            "fyear",
            "fyear_from_report_period",
            "filing_date",
            "report_period_date",
        ]
    ].drop_duplicates()
    identified = identified.drop(columns=["focal_sic", "focal_gvkey"], errors="ignore").merge(
        pop_keys,
        on=["filename", "focal_cik", "fyear"],
        how="left",
        validate="many_to_one",
    )
    identified_keys = identified[["filename", "focal_cik", "fyear"]].drop_duplicates()
    no_comp = pop_keys.merge(identified_keys, on=["filename", "focal_cik", "fyear"], how="left", indicator=True)
    no_comp = no_comp[no_comp["_merge"].eq("left_only")].drop(columns=["_merge"])
    for col in ["competitor_order", "competitor_name_original", "competitor_name_final", "competitor_gvkey", "competitor_cik"]:
        no_comp[col] = ""

    external = pd.concat(
        [
            identified[
                [
                    "focal_sic",
                    "filename",
                    "focal_cik",
                    "focal_gvkey",
                    "fyear",
                    "fyear_from_report_period",
                    "filing_date",
                    "report_period_date",
                    "competitor_order",
                    "competitor_name_original",
                    "competitor_name_final",
                    "competitor_gvkey",
                    "competitor_cik",
                ]
            ],
            no_comp[
                [
                    "focal_sic",
                    "filename",
                    "focal_cik",
                    "focal_gvkey",
                    "fyear",
                    "fyear_from_report_period",
                    "filing_date",
                    "report_period_date",
                    "competitor_order",
                    "competitor_name_original",
                    "competitor_name_final",
                    "competitor_gvkey",
                    "competitor_cik",
                ]
            ],
        ],
        ignore_index=True,
    )
    external["has_named_competitor_in_final_data"] = external["competitor_name_final"].astype(str).str.strip().ne("")
    external["competitor_order_numeric"] = pd.to_numeric(external["competitor_order"], errors="coerce").fillna(10**9).astype("int64")
    external = external.sort_values(
        ["focal_cik", "fyear", "filename", "has_named_competitor_in_final_data", "competitor_order_numeric"],
        ascending=[True, True, True, False, True],
    )
    external = external.drop(columns=["competitor_order_numeric"])
    external = external.drop(columns=["has_named_competitor_in_final_data"])
    external = external.drop(columns=["fyear"])
    external = external.rename(columns={"fyear_from_report_period": "fyear"})
    external = external[
        [
            "focal_sic",
            "filename",
            "focal_cik",
            "focal_gvkey",
            "fyear",
            "filing_date",
            "report_period_date",
            "competitor_order",
            "competitor_name_original",
            "competitor_name_final",
            "competitor_gvkey",
            "competitor_cik",
        ]
    ]
    return external


def bridge_name_key(value) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", str(value).upper()).strip()


def build_bridge_priority_tables() -> tuple[pd.DataFrame, pd.DataFrame]:
    bridge = pd.read_csv(
        YEAR_SPECIFIC_BRIDGE,
        usecols=lambda c: c in {"name_std", "fyear", "gvkey", "cik", "conm", "source", "matching_priority"},
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    bridge["competitor_name_key"] = bridge["name_std"].map(bridge_name_key)
    bridge["report_year"] = pd.to_numeric(bridge["fyear"], errors="coerce").astype("Int64")
    bridge["bridge_gvkey_clean"] = bridge["gvkey"].map(external_identifier)
    bridge["bridge_cik_clean"] = bridge["cik"].map(external_identifier)
    bridge["matching_priority_num"] = pd.to_numeric(bridge["matching_priority"], errors="coerce").fillna(99)
    bridge = bridge[bridge["competitor_name_key"].ne("") & bridge["report_year"].notna() & bridge["bridge_gvkey_clean"].ne("")]

    current_priority = (
        bridge.groupby(["competitor_name_key", "report_year", "bridge_gvkey_clean"], dropna=False)
        .agg(
            current_bridge_min_priority=("matching_priority_num", "min"),
            current_bridge_sources=("source", lambda s: "|".join(sorted(set(map(str, s))))),
        )
        .reset_index()
        .rename(columns={"bridge_gvkey_clean": "competitor_gvkey_clean"})
    )

    min_priority = bridge.groupby(["competitor_name_key", "report_year"], dropna=False)["matching_priority_num"].transform("min")
    preferred_source_rows = bridge[bridge["matching_priority_num"].eq(min_priority)].copy()
    preferred = (
        preferred_source_rows.groupby(["competitor_name_key", "report_year"], dropna=False)
        .agg(
            n_preferred_gvkeys=("bridge_gvkey_clean", "nunique"),
            preferred_gvkey=("bridge_gvkey_clean", lambda s: sorted(set(s))[0] if len(set(s)) == 1 else ""),
            preferred_ciks=("bridge_cik_clean", lambda s: "|".join(sorted({x for x in s if x}))),
            preferred_sources=("source", lambda s: "|".join(sorted(set(map(str, s))))),
            preferred_priority=("matching_priority_num", "min"),
            preferred_conm=("conm", lambda s: " | ".join(sorted({str(x).strip() for x in s if str(x).strip()}))),
        )
        .reset_index()
    )
    return preferred, current_priority


def apply_conservative_multigvkey_repairs(external: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    external = external.copy()
    named = external["competitor_name_final"].astype(str).str.strip().ne("")
    external["report_year"] = pd.to_datetime(external["report_period_date"], errors="coerce").dt.year.astype("Int64")
    external["competitor_name_key"] = external["competitor_name_final"].map(bridge_name_key)
    external["competitor_gvkey_clean"] = external["competitor_gvkey"].map(external_identifier)

    preferred, current_priority = build_bridge_priority_tables()
    work = external.loc[named].merge(
        preferred,
        on=["competitor_name_key", "report_year"],
        how="left",
        validate="many_to_one",
    )
    work = work.merge(
        current_priority,
        on=["competitor_name_key", "report_year", "competitor_gvkey_clean"],
        how="left",
        validate="many_to_one",
    )
    work["original_name_core"] = work["competitor_name_original"].map(normalize_company_core)
    work["final_name_core"] = work["competitor_name_final"].map(normalize_company_core)
    work["preferred_conm_core"] = work["preferred_conm"].map(normalize_company_core)
    work["original_aligns_with_final_name"] = (
        work["original_name_core"].ne("")
        & work["final_name_core"].ne("")
        & (
            work.apply(lambda r: r["final_name_core"] in r["original_name_core"] or r["original_name_core"] in r["final_name_core"], axis=1)
        )
    )
    work["preferred_conm_aligns_with_final_name"] = (
        work["preferred_conm_core"].ne("")
        & work["final_name_core"].ne("")
        & work["preferred_conm_core"].eq(work["final_name_core"])
    )
    work["repair_applied"] = (
        work["n_preferred_gvkeys"].eq(1)
        & work["preferred_gvkey"].astype(str).str.strip().ne("")
        & work["competitor_gvkey_clean"].astype(str).str.strip().ne("")
        & work["competitor_gvkey_clean"].ne(work["preferred_gvkey"])
        & pd.to_numeric(work["current_bridge_min_priority"], errors="coerce").gt(pd.to_numeric(work["preferred_priority"], errors="coerce"))
        & work["original_aligns_with_final_name"]
        & work["preferred_conm_aligns_with_final_name"]
    )
    repairs = work[work["repair_applied"]].copy()
    if repairs.empty:
        external = external.drop(columns=["report_year", "competitor_name_key", "competitor_gvkey_clean"])
        return external, repairs

    repairs["old_competitor_gvkey"] = repairs["competitor_gvkey"]
    repairs["old_competitor_cik"] = repairs["competitor_cik"]
    repairs["new_competitor_gvkey"] = repairs["preferred_gvkey"].map(external_identifier)
    repairs["new_competitor_cik"] = repairs["preferred_ciks"].map(lambda x: sorted([v for v in str(x).split("|") if v.strip()])[0] if str(x).strip() else "")
    repairs["repair_reason"] = "unique_same_year_bridge_preferred_gvkey_with_stronger_matching_priority"

    repair_cols = [
        "focal_sic", "filename", "focal_cik", "focal_gvkey", "filing_date", "report_period_date",
        "competitor_order", "competitor_name_original", "competitor_name_final", "old_competitor_gvkey",
        "old_competitor_cik", "new_competitor_gvkey", "new_competitor_cik", "preferred_sources",
        "preferred_priority", "preferred_conm", "current_bridge_min_priority", "current_bridge_sources",
        "original_name_core", "final_name_core", "preferred_conm_core",
        "original_aligns_with_final_name", "preferred_conm_aligns_with_final_name", "repair_reason",
    ]
    repair_key = repairs[["filename", "focal_cik", "competitor_order", "new_competitor_gvkey", "new_competitor_cik"]].copy()
    external = external.merge(
        repair_key,
        on=["filename", "focal_cik", "competitor_order"],
        how="left",
        validate="one_to_one",
    )
    external["competitor_gvkey"] = external["competitor_gvkey"].where(external["new_competitor_gvkey"].fillna("").eq(""), external["new_competitor_gvkey"])
    external["competitor_cik"] = external["competitor_cik"].where(external["new_competitor_cik"].fillna("").eq(""), external["new_competitor_cik"])
    external = external.drop(columns=["new_competitor_gvkey", "new_competitor_cik", "report_year", "competitor_name_key", "competitor_gvkey_clean"])
    return external, repairs[repair_cols]


def load_focal_names_for_self_check(external: pd.DataFrame) -> pd.DataFrame:
    keys = external[["focal_cik", "report_period_date"]].drop_duplicates().copy()
    keys["report_year"] = pd.to_datetime(keys["report_period_date"], errors="coerce").dt.year.astype("Int64")
    keys["focal_cik_clean"] = keys["focal_cik"].map(external_identifier)

    bridge = pd.read_csv(
        YEAR_SPECIFIC_BRIDGE,
        usecols=lambda c: c in {"cik", "fyear", "conm", "name_raw", "source", "matching_priority"},
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )
    bridge["focal_cik_clean"] = bridge["cik"].map(external_identifier)
    bridge["report_year"] = pd.to_numeric(bridge["fyear"], errors="coerce").astype("Int64")
    bridge["matching_priority_num"] = pd.to_numeric(bridge["matching_priority"], errors="coerce").fillna(99)
    bridge["focal_name_bridge"] = bridge["conm"].where(bridge["conm"].astype(str).str.strip().ne(""), bridge["name_raw"])
    bridge = bridge[bridge["focal_cik_clean"].ne("") & bridge["report_year"].notna()]
    bridge = (
        bridge.sort_values(["focal_cik_clean", "report_year", "matching_priority_num", "source", "focal_name_bridge"])
        .drop_duplicates(["focal_cik_clean", "report_year"], keep="first")
    )
    out = keys.merge(
        bridge[["focal_cik_clean", "report_year", "focal_name_bridge", "source"]],
        on=["focal_cik_clean", "report_year"],
        how="left",
        validate="many_to_one",
    )
    return out[["focal_cik", "report_period_date", "focal_name_bridge", "source"]].rename(columns={"source": "focal_name_source"})


def remove_self_competitors(external: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    external = external.copy()
    focal_names = load_focal_names_for_self_check(external)
    work = external.merge(focal_names, on=["focal_cik", "report_period_date"], how="left", validate="many_to_one")
    named = work["competitor_name_final"].astype(str).str.strip().ne("")
    work["self_by_cik"] = named & work["competitor_cik"].map(external_identifier).ne("") & work["competitor_cik"].map(external_identifier).eq(work["focal_cik"].map(external_identifier))
    work["self_by_gvkey"] = named & work["competitor_gvkey"].map(external_identifier).ne("") & work["competitor_gvkey"].map(external_identifier).eq(work["focal_gvkey"].map(external_identifier))
    work["focal_name_norm"] = work["focal_name_bridge"].map(normalize_company_name_for_self_check)
    work["competitor_name_norm"] = work["competitor_name_final"].map(normalize_company_name_for_self_check)
    work["self_by_normalized_name"] = named & work["focal_name_norm"].ne("") & work["competitor_name_norm"].ne("") & work["focal_name_norm"].eq(work["competitor_name_norm"])
    work["self_competitor_removed"] = work["self_by_cik"] | work["self_by_gvkey"] | work["self_by_normalized_name"]

    audit_cols = [
        "focal_sic", "filename", "focal_cik", "focal_gvkey", "filing_date", "report_period_date",
        "focal_name_bridge", "focal_name_source", "competitor_order", "competitor_name_original",
        "competitor_name_final", "competitor_gvkey", "competitor_cik", "self_by_cik",
        "self_by_gvkey", "self_by_normalized_name", "focal_name_norm", "competitor_name_norm",
    ]
    removed = work[work["self_competitor_removed"]].copy()
    kept = work[~work["self_competitor_removed"]].drop(
        columns=[
            "focal_name_bridge", "focal_name_source", "self_by_cik", "self_by_gvkey",
            "focal_name_norm", "competitor_name_norm", "self_by_normalized_name",
            "self_competitor_removed",
        ]
    )
    return reset_competitor_order(kept), removed[audit_cols]


def reset_competitor_order(external: pd.DataFrame) -> pd.DataFrame:
    external = external.copy()
    named = external["competitor_name_final"].astype(str).str.strip().ne("")
    external["competitor_order_numeric"] = pd.to_numeric(external["competitor_order"], errors="coerce").fillna(10**9).astype("int64")
    external = external.sort_values(["focal_cik", "report_period_date", "filename", "competitor_order_numeric", "competitor_name_final"])
    external.loc[named, "competitor_order"] = (
        external.loc[named]
        .groupby(["filename", "focal_cik"], dropna=False)
        .cumcount()
        .add(1)
        .astype(str)
    )
    return external.drop(columns=["competitor_order_numeric"])


def restore_blank_rows_for_focal_filings_without_external_competitors(external: pd.DataFrame, audit: pd.DataFrame) -> pd.DataFrame:
    external = external.copy()
    present = external[["filename", "focal_cik"]].drop_duplicates()
    population = audit[
        [
            "focal_sic",
            "filename",
            "focal_cik",
            "focal_gvkey",
            "fyear_from_report_period",
            "filing_date",
            "report_period_date",
        ]
    ].drop_duplicates().rename(columns={"fyear_from_report_period": "fyear"})
    missing = population.merge(present, on=["filename", "focal_cik"], how="left", indicator=True)
    missing = missing[missing["_merge"].eq("left_only")].drop(columns=["_merge"])
    if missing.empty:
        return external
    for col in ["competitor_order", "competitor_name_original", "competitor_name_final", "competitor_gvkey", "competitor_cik"]:
        missing[col] = ""
    out = pd.concat([external, missing[external.columns]], ignore_index=True)
    out["has_named_competitor_in_final_data"] = out["competitor_name_final"].astype(str).str.strip().ne("")
    out["competitor_order_numeric"] = pd.to_numeric(out["competitor_order"], errors="coerce").fillna(10**9).astype("int64")
    out = out.sort_values(
        ["focal_cik", "report_period_date", "filename", "has_named_competitor_in_final_data", "competitor_order_numeric"],
        ascending=[True, True, True, False, True],
    )
    return out.drop(columns=["has_named_competitor_in_final_data", "competitor_order_numeric"])


def build_multigvkey_conflict_audit(external: pd.DataFrame) -> pd.DataFrame:
    work = external[external["competitor_name_final"].astype(str).str.strip().ne("")].copy()
    work["report_year"] = pd.to_datetime(work["report_period_date"], errors="coerce").dt.year.astype("Int64")
    work["competitor_gvkey_clean"] = work["competitor_gvkey"].map(external_identifier)
    work = work[work["competitor_gvkey_clean"].ne("")]
    conflict = (
        work.groupby(["competitor_name_final", "report_year"], dropna=False)
        .agg(
            rows=("filename", "size"),
            n_gvkeys=("competitor_gvkey_clean", "nunique"),
            gvkeys=("competitor_gvkey_clean", lambda s: "|".join(sorted(set(s)))),
            ciks=("competitor_cik", lambda s: "|".join(sorted({external_identifier(x) for x in s if external_identifier(x)}))),
            example_original_names=("competitor_name_original", lambda s: " | ".join(list(dict.fromkeys(map(str, s)))[:8])),
            example_filenames=("filename", lambda s: " | ".join(list(dict.fromkeys(map(str, s)))[:5])),
        )
        .reset_index()
    )
    return conflict[conflict["n_gvkeys"].gt(1)].sort_values(["rows", "n_gvkeys"], ascending=[False, False])


def apply_analysis_year_window(external: pd.DataFrame, audit: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    external = external.copy()
    audit = audit.copy()
    external_fyear = pd.to_numeric(external["fyear"], errors="coerce")
    audit_fyear = pd.to_numeric(audit["fyear_from_report_period"], errors="coerce")

    external_in_window = external_fyear.between(MIN_ANALYSIS_FYEAR, MAX_ANALYSIS_FYEAR, inclusive="both")
    audit_in_window = audit_fyear.between(MIN_ANALYSIS_FYEAR, MAX_ANALYSIS_FYEAR, inclusive="both")

    excluded_external = external[~external_in_window].copy()
    excluded_audit = audit[~audit_in_window].copy()
    excluded_counts = (
        excluded_external.assign(
            has_named_competitor_row=excluded_external["competitor_name_final"].astype(str).str.strip().ne("")
        )
        .groupby(["filename", "focal_cik"], dropna=False)
        .agg(
            excluded_external_rows=("filename", "size"),
            excluded_named_competitor_rows=("has_named_competitor_row", "sum"),
            excluded_blank_competitor_rows=("has_named_competitor_row", lambda s: int((~s).sum())),
        )
        .reset_index()
    )
    excluded = excluded_audit.merge(excluded_counts, on=["filename", "focal_cik"], how="left", validate="one_to_one")
    excluded["analysis_fyear_min"] = MIN_ANALYSIS_FYEAR
    excluded["analysis_fyear_max"] = MAX_ANALYSIS_FYEAR
    excluded["exclusion_reason"] = "report_period_fyear_outside_2002_2024"

    return external[external_in_window].copy(), audit[audit_in_window].copy(), excluded


def summarize(external: pd.DataFrame, audit: pd.DataFrame) -> pd.DataFrame:
    external_named_focal_filings = external.loc[
        external["competitor_name_final"].astype(str).str.strip().ne(""),
        ["filename", "focal_cik"],
    ].drop_duplicates().shape[0]
    external_blank_focal_filings = external.loc[
        external["competitor_name_final"].astype(str).str.strip().eq(""),
        ["filename", "focal_cik"],
    ].drop_duplicates().shape[0]
    rows = [
        {"metric": "population_focal_filings", "value": audit[["filename", "focal_cik", "fyear"]].drop_duplicates().shape[0]},
        {"metric": "external_rows", "value": len(external)},
        {"metric": "external_rows_with_named_competitor", "value": int(external["competitor_name_final"].astype(str).str.strip().ne("").sum())},
        {"metric": "external_blank_competitor_rows", "value": int(external["competitor_name_final"].astype(str).str.strip().eq("").sum())},
        {"metric": "external_focal_filings_with_final_named_competitor", "value": external_named_focal_filings},
        {"metric": "external_focal_filings_without_final_named_competitor", "value": external_blank_focal_filings},
        {"metric": "pre_integrity_focal_filings_with_final_named_competitor", "value": int(audit["has_final_named_competitor"].sum())},
        {"metric": "pre_integrity_focal_filings_without_final_named_competitor", "value": int((~audit["has_final_named_competitor"]).sum())},
        {"metric": "focal_filings_with_report_period_date", "value": int(audit["report_period_date"].astype(str).str.strip().ne("").sum())},
        {"metric": "focal_filings_missing_report_period_date", "value": int(audit["report_period_date"].astype(str).str.strip().eq("").sum())},
        {"metric": "focal_filings_where_filename_year_differs_from_report_year", "value": int((~audit["fyear_matches_report_year"]).sum())},
    ]
    status = (
        audit.groupby("final_competitor_coverage_status", dropna=False)
        .agg(value=("filename", "size"))
        .reset_index()
        .rename(columns={"final_competitor_coverage_status": "metric"})
    )
    return pd.concat([pd.DataFrame(rows), status], ignore_index=True)


def write_by_sic_external(external: pd.DataFrame, audit: pd.DataFrame) -> None:
    audit_sics = audit[["filename", "focal_cik", "focal_sics_all"]].drop_duplicates(["filename", "focal_cik"]).copy()
    sic_expanded = external.merge(
        audit_sics,
        on=["filename", "focal_cik"],
        how="left",
        validate="many_to_one",
    )
    sic_expanded["sic_output"] = sic_expanded["focal_sics_all"].fillna("").astype(str).str.split("|")
    sic_expanded = sic_expanded.explode("sic_output")
    sic_expanded["sic_output"] = sic_expanded["sic_output"].map(format_sic)
    missing_sic_output = sic_expanded["sic_output"].astype(str).str.strip().eq("")
    sic_expanded.loc[missing_sic_output, "sic_output"] = sic_expanded.loc[missing_sic_output, "focal_sic"].to_numpy()
    sic_expanded["is_primary_focal_sic"] = sic_expanded["sic_output"].astype(str).eq(sic_expanded["focal_sic"].astype(str))
    sic_expanded = sic_expanded.drop(columns=["focal_sics_all"])

    OUT_BY_SIC.mkdir(parents=True, exist_ok=True)
    rows = []
    for sic, part in sic_expanded.groupby("sic_output", dropna=False):
        sic_text = format_sic(sic)
        sic_dir = OUT_BY_SIC / f"sic_{sic_text}"
        sic_dir.mkdir(parents=True, exist_ok=True)
        out = sic_dir / f"focal_filing_competitors_sic_{sic_text}.csv"
        part.to_csv(out, index=False)
        rows.append(
            {
                "focal_sic": sic_text,
                "rows": len(part),
                "focal_filings": part[["filename", "focal_cik"]].drop_duplicates().shape[0],
                "primary_focal_sic_rows": int(part["is_primary_focal_sic"].sum()),
                "secondary_focal_sic_rows": int((~part["is_primary_focal_sic"]).sum()),
                "primary_focal_sic_filings": part.loc[part["is_primary_focal_sic"], ["filename", "focal_cik"]].drop_duplicates().shape[0],
                "secondary_focal_sic_filings": part.loc[~part["is_primary_focal_sic"], ["filename", "focal_cik"]].drop_duplicates().shape[0],
                "rows_with_named_competitor": int(part["competitor_name_final"].astype(str).str.strip().ne("").sum()),
                "blank_competitor_rows": int(part["competitor_name_final"].astype(str).str.strip().eq("").sum()),
                "file": str(out.relative_to(OUT_BY_SIC)).replace("\\", "/"),
            }
        )
    pd.DataFrame(rows).sort_values("focal_sic").to_csv(OUT_BY_SIC / "SIC_FILE_INDEX.csv", index=False)


def update_lean_release() -> None:
    agg = RELEASE / "03_outcomes_aggregate"
    sic = RELEASE / "04_outcomes_by_sic"
    if agg.exists():
        shutil.rmtree(agg)
    agg.mkdir(parents=True, exist_ok=True)
    sic.mkdir(parents=True, exist_ok=True)

    shutil.copy2(OUT_EXTERNAL, agg / "external_focal_filing_competitors.csv")
    shutil.copy2(OUT_AUDIT, agg / "audit_focal_filing_competitor_coverage.csv")
    shutil.copy2(OUT_SUMMARY, agg / "focal_filing_competitor_coverage_summary.csv")
    if OUT_REPORT_PERIOD_METADATA.exists():
        shutil.copy2(OUT_REPORT_PERIOD_METADATA, agg / "audit_filing_report_period_metadata.csv")
    if OUT_SELF_COMPETITOR_AUDIT.exists():
        shutil.copy2(OUT_SELF_COMPETITOR_AUDIT, agg / "audit_removed_self_competitors.csv")
    if OUT_MULTIGVKEY_AUDIT.exists():
        shutil.copy2(OUT_MULTIGVKEY_AUDIT, agg / "audit_same_name_multiple_gvkeys.csv")
    if OUT_MULTIGVKEY_REPAIR_AUDIT.exists():
        shutil.copy2(OUT_MULTIGVKEY_REPAIR_AUDIT, agg / "audit_same_name_multigvkey_repairs.csv")
    if OUT_ANALYSIS_WINDOW_EXCLUDED_AUDIT.exists():
        shutil.copy2(OUT_ANALYSIS_WINDOW_EXCLUDED_AUDIT, agg / "audit_excluded_out_of_analysis_window.csv")
    shutil.copytree(OUT_BY_SIC, sic, dirs_exist_ok=True)

    readme = RELEASE / "README.txt"
    if readme.exists():
        text = readme.read_text(encoding="utf-8")
    else:
        text = ""
    replacement = (
        "03_outcomes_aggregate\n"
        "Main aggregate outcome files:\n"
        "- external_focal_filing_competitors.csv: primary external product. It includes every focal filing in the Step 4/6 population. If no final named competitor exists, competitor fields are blank.\n"
        "- audit_focal_filing_competitor_coverage.csv: internal/audit file explaining why focal filings have or do not have final named competitors.\n"
        "- audit_filing_report_period_metadata.csv: SEC filing metadata crosswalk from filename/focal CIK to filing date and report-period date.\n"
        "- audit_removed_self_competitors.csv: rows removed from the clean external file because focal and competitor identifiers/names indicate self-competition.\n"
        "- audit_same_name_multiple_gvkeys.csv: remaining cases where the same displayed competitor name maps to multiple GVKEYs in a report year.\n"
        "- audit_same_name_multigvkey_repairs.csv: conservative same-name/GVKEY repairs applied before export.\n"
        "- audit_excluded_out_of_analysis_window.csv: focal filings excluded because report-period fyear is outside 2002-2024.\n"
        "- focal_filing_competitor_coverage_summary.csv: compact counts for the external population file.\n\n"
        "04_outcomes_by_sic\n"
        "Inclusive SIC-based extracts of the external focal-filing competitor file. Multi-SIC focal filings appear in each relevant SIC folder; is_primary_focal_sic marks the deterministic aggregate SIC. Start with SIC_FILE_INDEX.csv.\n"
    )
    if "03_outcomes_aggregate\n" in text and "04_outcomes_by_sic\n" in text:
        start = text.find("03_outcomes_aggregate\n")
        end = text.find("How to Read the Main Files")
        if end != -1:
            text = text[:start] + replacement + "\n" + text[end:]
    else:
        text += "\n" + replacement
    text = text.replace(
        "Edge-level identified file: unique usable focal-competitor links per filing after collapsing repeated mentions of the same final competitor. This is the primary analysis file.\n"
        "Mention-level identified files are sample-only audit aids in this lean release.\n"
        "All-status mention files are sample-only accounting aids in this lean release.",
        "External focal-filing competitor file: every focal filing is present. Filings with final named competitors have one row per retained named competitor; filings without final named competitors have one row with blank competitor fields. The external file reports fyear derived from SEC report_period_date using a May 31 cutoff, plus SEC filing_date and report_period_date; the old filename-derived year is retained only in audit. Edge files can be created later by deduplicating this file as needed.",
    )
    readme.write_text(text, encoding="utf-8", newline="\n")

    nav_rows = []
    for path in sorted(RELEASE.rglob("*")):
        if path.is_file() and path.name not in {"FILE_NAVIGATOR.xlsx"}:
            nav_rows.append(
                {
                    "release_path": str(path.relative_to(RELEASE)).replace("\\", "/"),
                    "bytes": path.stat().st_size,
                    "last_modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
                    "section": str(path.relative_to(RELEASE)).replace("\\", "/").split("/")[0],
                }
            )
    nav_source = RELEASE / "_navigator_source_tables"
    nav_source.mkdir(exist_ok=True)
    pd.DataFrame(nav_rows).to_csv(nav_source / "manifest.csv", index=False)
    pd.DataFrame(
        [
            {
                "folder": "03_outcomes_aggregate",
                "file": "external_focal_filing_competitors.csv",
                "purpose": "Primary external product: every focal filing, with named competitors where retained and blank competitor fields otherwise.",
                "reviewer_use": "Use this for analysis; create edges by deduplicating if desired.",
            },
            {
                "folder": "03_outcomes_aggregate",
                "file": "audit_focal_filing_competitor_coverage.csv",
                "purpose": "Audit-only coverage/status accounting for focal filings.",
                "reviewer_use": "Use to explain no-competitor filings; not a clean external outcome.",
            },
            {
                "folder": "03_outcomes_aggregate",
                "file": "audit_filing_report_period_metadata.csv",
                "purpose": "Audit-only SEC metadata crosswalk from filename/focal CIK to filing date and report-period date.",
                "reviewer_use": "Use to verify that report_period_date comes from SEC submissions metadata.",
            },
            {
                "folder": "03_outcomes_aggregate",
                "file": "audit_removed_self_competitors.csv",
                "purpose": "Audit-only list of self-competitor rows removed from the clean external file.",
                "reviewer_use": "Use to inspect focal-equals-competitor removals.",
            },
            {
                "folder": "03_outcomes_aggregate",
                "file": "audit_same_name_multiple_gvkeys.csv",
                "purpose": "Audit-only list of remaining same displayed competitor name/report-year cases with multiple GVKEYs.",
                "reviewer_use": "Use to inspect unresolved historical/name ambiguity.",
            },
            {
                "folder": "03_outcomes_aggregate",
                "file": "audit_same_name_multigvkey_repairs.csv",
                "purpose": "Audit-only list of conservative same-name/GVKEY repairs applied before export.",
                "reviewer_use": "Use to inspect identifier corrections made by bridge-priority rule.",
            },
            {
                "folder": "03_outcomes_aggregate",
                "file": "audit_excluded_out_of_analysis_window.csv",
                "purpose": "Audit-only list of focal filings excluded because report-period fyear is outside 2002-2024.",
                "reviewer_use": "Use to inspect exclusions caused by the final analysis window.",
            },
            {
                "folder": "04_outcomes_by_sic",
                "file": "sic_XXXX/focal_filing_competitors_sic_XXXX.csv",
                "purpose": "Inclusive SIC-specific extracts of the primary external product; multi-SIC focal filings appear in each relevant SIC.",
                "reviewer_use": "Use for industry-specific analysis. The is_primary_focal_sic flag identifies the deterministic aggregate SIC.",
            },
        ]
    ).to_csv(nav_source / "file_navigator.csv", index=False)
    pd.DataFrame(RESTRICTED_INPUTS).to_csv(nav_source / "restricted_inputs_manifest.csv", index=False)
    summarize(pd.read_csv(OUT_EXTERNAL, low_memory=False), pd.read_csv(OUT_AUDIT, low_memory=False)).to_csv(
        nav_source / "package_summary.csv", index=False
    )


RESTRICTED_INPUTS = [
    {"input_name": "Compustat/WRDS/Capital IQ/RepRisk/IBES and related proprietary sources", "release_policy": "Listed for reproducibility but not redistributed."},
    {"input_name": "SEC EDGAR filings", "release_policy": "Acquisition code included; bulky raw filing text not redistributed in lean package."},
]


def zip_lean_release() -> Path:
    zip_path = PROJECT / "reviewer_release" / "management_science_competitor_network_v1_lean.zip"
    if zip_path.exists():
        zip_path.unlink()
    files = [p for p in RELEASE.rglob("*") if p.is_file() and "_navigator_source_tables" not in p.parts]
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
        for path in files:
            zf.write(path, RELEASE.name / path.relative_to(RELEASE))
    return zip_path


def main() -> None:
    pop = add_focal_gvkey(load_population())
    identified = load_identified_mentions()
    audit = build_audit(pop, identified)
    external = build_external(pop, identified, audit)
    external, repair_audit = apply_conservative_multigvkey_repairs(external)
    external, self_audit = remove_self_competitors(external)
    external = restore_blank_rows_for_focal_filings_without_external_competitors(external, audit)
    external, audit, analysis_window_excluded_audit = apply_analysis_year_window(external, audit)
    self_audit = self_audit[
        pd.to_numeric(pd.to_datetime(self_audit["report_period_date"], errors="coerce").dt.year, errors="coerce")
        .where(pd.to_datetime(self_audit["report_period_date"], errors="coerce").dt.month.gt(5), pd.to_datetime(self_audit["report_period_date"], errors="coerce").dt.year - 1)
        .between(MIN_ANALYSIS_FYEAR, MAX_ANALYSIS_FYEAR, inclusive="both")
    ].copy()
    repair_audit = repair_audit[
        pd.to_numeric(pd.to_datetime(repair_audit["report_period_date"], errors="coerce").dt.year, errors="coerce")
        .where(pd.to_datetime(repair_audit["report_period_date"], errors="coerce").dt.month.gt(5), pd.to_datetime(repair_audit["report_period_date"], errors="coerce").dt.year - 1)
        .between(MIN_ANALYSIS_FYEAR, MAX_ANALYSIS_FYEAR, inclusive="both")
    ].copy()
    multigvkey_audit = build_multigvkey_conflict_audit(external)
    summary = summarize(external, audit)
    summary = pd.concat(
        [
            summary,
            pd.DataFrame(
                [
                    {"metric": "self_competitor_rows_removed_from_external", "value": len(self_audit)},
                    {"metric": "same_name_multigvkey_repairs_applied", "value": len(repair_audit)},
                    {"metric": "remaining_same_name_report_year_multigvkey_groups", "value": len(multigvkey_audit)},
                    {"metric": "analysis_fyear_min", "value": MIN_ANALYSIS_FYEAR},
                    {"metric": "analysis_fyear_max", "value": MAX_ANALYSIS_FYEAR},
                    {"metric": "out_of_analysis_window_focal_filings_excluded", "value": len(analysis_window_excluded_audit)},
                    {"metric": "out_of_analysis_window_external_rows_excluded", "value": int(analysis_window_excluded_audit["excluded_external_rows"].sum()) if not analysis_window_excluded_audit.empty else 0},
                ]
            ),
        ],
        ignore_index=True,
    )

    external.to_csv(OUT_EXTERNAL, index=False)
    audit.to_csv(OUT_AUDIT, index=False)
    summary.to_csv(OUT_SUMMARY, index=False)
    load_filing_report_period_metadata().to_csv(OUT_REPORT_PERIOD_METADATA, index=False)
    self_audit.to_csv(OUT_SELF_COMPETITOR_AUDIT, index=False)
    multigvkey_audit.to_csv(OUT_MULTIGVKEY_AUDIT, index=False)
    repair_audit.to_csv(OUT_MULTIGVKEY_REPAIR_AUDIT, index=False)
    analysis_window_excluded_audit.to_csv(OUT_ANALYSIS_WINDOW_EXCLUDED_AUDIT, index=False)
    write_by_sic_external(external, audit)
    update_lean_release()
    zip_path = zip_lean_release()

    print("Saved external:", OUT_EXTERNAL)
    print("Saved audit:", OUT_AUDIT)
    print("Saved summary:", OUT_SUMMARY)
    print("Saved report-period metadata:", OUT_REPORT_PERIOD_METADATA)
    print("Saved self-competitor audit:", OUT_SELF_COMPETITOR_AUDIT)
    print("Saved same-name/multiple-GVKEY audit:", OUT_MULTIGVKEY_AUDIT)
    print("Saved same-name/multiple-GVKEY repair audit:", OUT_MULTIGVKEY_REPAIR_AUDIT)
    print("Saved analysis-window exclusion audit:", OUT_ANALYSIS_WINDOW_EXCLUDED_AUDIT)
    print("Saved SIC folder:", OUT_BY_SIC)
    print("Updated lean release:", RELEASE)
    print("Updated zip:", zip_path, zip_path.stat().st_size)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
