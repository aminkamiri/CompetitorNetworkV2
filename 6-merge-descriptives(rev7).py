# 6-merge-descriptives.py

from pathlib import Path
from datetime import datetime
import pandas as pd
import re

RESULTS_DIR = Path("data/results")
MAPPED_DIR = RESULTS_DIR / "mapped"
OUT_DIR = RESULTS_DIR / "descriptives"
OUT_DIR.mkdir(parents=True, exist_ok=True)

FILENAME_COL = "filename"
COMPETITORS_COL = "competitors"
STD_COL = "competitors_standardized"
CIK_COL = "competitors_ciks"
GVKEY_COL = "competitors_gvkeys"
SOURCE_COL = "competitors_match_sources"
METHOD_COL = "competitors_match_methods"
BRIDGE_NAME_COL = "competitors_matched_bridge_names"
BRIDGE_ORIGINAL_COL = "competitors_matched_bridge_original_names"

RECOVERY_DIAGNOSTIC_WIDE_TO_LONG = {
    "competitors_recovered_parent_prefixes": "recovered_parent_prefix",
    "competitors_recovered_parent_prefix_n_tokens": "recovered_parent_prefix_n_tokens",
    "competitors_recovery_priority_rules": "recovery_priority_rule",
    "competitors_recovery_n_candidates_all": "recovery_n_candidates_all",
    "competitors_recovery_n_candidates_priority": "recovery_n_candidates_priority",
    "competitors_recovery_n_unique_identity_pairs_all": "recovery_n_unique_identity_pairs_all",
    "competitors_recovery_n_unique_identity_pairs_priority": "recovery_n_unique_identity_pairs_priority",
    "competitors_recovery_candidate_parent_names_all": "recovery_candidate_parent_names_all",
    "competitors_recovery_candidate_parent_names_priority": "recovery_candidate_parent_names_priority",
    "competitors_recovery_candidate_original_names_all": "recovery_candidate_original_names_all",
    "competitors_recovery_candidate_original_names_priority": "recovery_candidate_original_names_priority",
    "competitors_recovery_candidate_sources_all": "recovery_candidate_sources_all",
    "competitors_recovery_candidate_sources_priority": "recovery_candidate_sources_priority",
    "competitors_recovery_candidate_ciks_all": "recovery_candidate_ciks_all",
    "competitors_recovery_candidate_gvkeys_all": "recovery_candidate_gvkeys_all",
    "competitors_recovery_candidate_ciks_priority": "recovery_candidate_ciks_priority",
    "competitors_recovery_candidate_gvkeys_priority": "recovery_candidate_gvkeys_priority",
    "competitors_global_parent_recovery_continuation_terms": "global_parent_recovery_continuation_terms",
    "competitors_global_parent_recovery_unsafe_continuation_terms": "global_parent_recovery_unsafe_continuation_terms",
    "competitors_global_parent_recovery_safety_rules": "global_parent_recovery_safety_rule",
}


def extract_year(x):
    if pd.isna(x):
        return None
    m = re.search(r"_(\d{8})\.txt$", str(x))
    return int(m.group(1)[:4]) if m else None


def extract_focal_cik(x):
    if pd.isna(x):
        return None
    m = re.search(r"CIK(\d+)_", str(x))
    return m.group(1) if m else None


def split_list(x):
    if pd.isna(x) or str(x).strip() == "":
        return []
    return [v.strip() for v in str(x).split("|")]


def is_valid_id(x):
    return str(x).strip() not in {"", "-1", "nan", "None", "NaN"}


def count_mentions(x):
    return len(split_list(x))


def count_valid_ids(x):
    return sum(is_valid_id(v) for v in split_list(x))


def pad_list(lst, length, fill_value=""):
    return lst + [fill_value] * (length - len(lst))


def safe_to_csv(df, path, index=False):
    path = Path(path)

    try:
        df.to_csv(path, index=index)
        return path
    except PermissionError:
        fallback = path.with_name(
            f"{path.stem}_{datetime.now():%Y%m%d_%H%M%S}{path.suffix}"
        )
        df.to_csv(fallback, index=index)
        print(f"Permission denied writing {path}; wrote {fallback} instead.")
        return fallback


GENERIC_TERMS = {
    "large", "small", "numerous", "multiple", "local", "regional",
    "international", "multinational", "branded", "unbranded",
    "producer", "producers", "distributor", "distributors",
    "retailer", "retailers", "supplier", "suppliers",
    "vendor", "vendors", "provider", "providers",
    "operator", "operators", "company", "companies",
    "competitor", "competitors", "manufacturer", "manufacturers",
    "industry", "market", "business", "businesses", "products",
    "bank", "banks", "union", "unions", "fund", "funds",
    "firm", "firms", "association", "associations",
    "loan", "loans", "mortgage", "mortgages", "banking",
    "finance", "financial", "insurance", "commercial",
    "consumer", "savings", "brokerage", "leasing",
    "lender", "lenders", "institution", "institutions",
    "solutions", "services", "systems"
}

CATEGORY_HEAD_NOUNS = {
    "companies", "firms", "banks", "funds", "unions", "associations",
    "producers", "distributors", "retailers", "suppliers", "vendors",
    "providers", "operators", "manufacturers", "institutions",
    "businesses", "competitors", "lenders", "services", "systems",
    "solutions"
}


def generic_score(name):
    s = str(name).lower()
    tokens = re.findall(r"[a-z]+", s)
    return sum(t in GENERIC_TERMS for t in tokens)


def is_likely_generic_category(name):
    s = str(name).strip()
    s_lower = s.lower()
    tokens = re.findall(r"[a-z]+", s_lower)

    if len(tokens) < 2:
        return False

    if tokens[-1] in CATEGORY_HEAD_NOUNS:
        return True

    financial_phrases = {
        "insurance companies",
        "credit unions",
        "commercial banks",
        "finance companies",
        "savings banks",
        "mutual funds",
        "brokerage firms",
        "mortgage companies",
        "mortgage banking companies",
        "savings and loan associations",
        "consumer finance companies"
    }

    return s_lower in financial_phrases


# ------------------------------------------------------------
# 1. Merge all SIC-level mapped files into WIDE file
# ------------------------------------------------------------
all_dfs = []

for file in sorted(MAPPED_DIR.glob("*.xlsx")):
    stem = file.stem.lower()

    if "diagnostic" in stem or "descriptive" in stem:
        continue

    sic_code = file.stem
    print("Reading:", file.name)

    df = pd.read_excel(file)
    df["sic_file"] = sic_code

    for col in [
        STD_COL,
        CIK_COL,
        GVKEY_COL,
        SOURCE_COL,
        METHOD_COL,
        BRIDGE_NAME_COL,
        BRIDGE_ORIGINAL_COL,
        *RECOVERY_DIAGNOSTIC_WIDE_TO_LONG.keys(),
    ]:
        if col not in df.columns:
            df[col] = ""

    all_dfs.append(df)

print("\nTotal files read:", len(all_dfs))

wide = pd.concat(all_dfs, ignore_index=True)

print("Total merged rows:", len(wide))

wide = wide[~wide[FILENAME_COL].astype(str).str.contains("_20F_", case=False, na=False)].copy()

wide["fyear"] = wide[FILENAME_COL].apply(extract_year)
wide["focal_cik"] = wide[FILENAME_COL].apply(extract_focal_cik)

wide["n_competitor_mentions"] = wide[COMPETITORS_COL].apply(count_mentions)
wide["n_standardized_mentions"] = wide[STD_COL].apply(count_mentions)
wide["n_cik_entries"] = wide[CIK_COL].apply(count_mentions)
wide["n_gvkey_entries"] = wide[GVKEY_COL].apply(count_mentions)
wide["n_source_entries"] = wide[SOURCE_COL].apply(count_mentions)
wide["n_method_entries"] = wide[METHOD_COL].apply(count_mentions)
wide["n_matched_bridge_name_entries"] = wide[BRIDGE_NAME_COL].apply(count_mentions)
wide["n_matched_bridge_original_entries"] = wide[BRIDGE_ORIGINAL_COL].apply(count_mentions)

wide["n_matched_cik_mentions"] = wide[CIK_COL].apply(count_valid_ids)
wide["n_matched_gvkey_mentions"] = wide[GVKEY_COL].apply(count_valid_ids)

wide["has_named_competitor"] = wide["n_competitor_mentions"] > 0
wide["has_matched_cik"] = wide["n_matched_cik_mentions"] > 0
wide["has_matched_gvkey"] = wide["n_matched_gvkey_mentions"] > 0
wide["has_any_identifier"] = wide["has_matched_cik"] | wide["has_matched_gvkey"]

wide["list_length_mismatch"] = (
    (wide["n_competitor_mentions"] != wide["n_standardized_mentions"]) |
    (wide["n_competitor_mentions"] != wide["n_cik_entries"]) |
    (wide["n_competitor_mentions"] != wide["n_gvkey_entries"]) |
    (wide["n_competitor_mentions"] != wide["n_source_entries"]) |
    (wide["n_competitor_mentions"] != wide["n_method_entries"])
)

wide["bridge_name_missing_when_matched"] = (
    wide["has_any_identifier"] &
    (wide["n_matched_bridge_name_entries"] == 0)
)

wide["bridge_original_name_missing_when_matched"] = (
    wide["has_any_identifier"] &
    (wide["n_matched_bridge_original_entries"] == 0)
)

alignment_issues = wide[wide["list_length_mismatch"]].copy()
safe_to_csv(alignment_issues, OUT_DIR / "step6_alignment_issues.csv", index=False)

bridge_audit_issues = wide[
    wide["bridge_name_missing_when_matched"] |
    wide["bridge_original_name_missing_when_matched"]
].copy()
safe_to_csv(bridge_audit_issues, OUT_DIR / "step6_bridge_audit_issues.csv", index=False)

safe_to_csv(wide, OUT_DIR / "merged_mapped_wide_no20f.csv", index=False)
wide.to_excel(OUT_DIR / "merged_mapped_wide_no20f.xlsx", index=False)


# ------------------------------------------------------------
# 2. Create LONG file: one row per competitor mention
# ------------------------------------------------------------
long_rows = []

for _, row in wide.iterrows():
    competitors = split_list(row.get(COMPETITORS_COL))
    standardized = split_list(row.get(STD_COL))
    ciks = split_list(row.get(CIK_COL))
    gvkeys = split_list(row.get(GVKEY_COL))
    sources = split_list(row.get(SOURCE_COL))
    methods = split_list(row.get(METHOD_COL))
    matched_bridge_names = split_list(row.get(BRIDGE_NAME_COL))
    matched_bridge_original_names = split_list(row.get(BRIDGE_ORIGINAL_COL))
    recovery_diagnostics = {
        wide_col: split_list(row.get(wide_col))
        for wide_col in RECOVERY_DIAGNOSTIC_WIDE_TO_LONG
    }

    n = max(
        len(competitors),
        len(standardized),
        len(ciks),
        len(gvkeys),
        len(sources),
        len(methods),
        len(matched_bridge_names),
        len(matched_bridge_original_names),
        *(len(values) for values in recovery_diagnostics.values())
    )

    competitors = pad_list(competitors, n, "")
    standardized = pad_list(standardized, n, "")
    ciks = pad_list(ciks, n, "-1")
    gvkeys = pad_list(gvkeys, n, "-1")
    sources = pad_list(sources, n, "unmatched")
    methods = pad_list(methods, n, "alignment_padding_missing")
    matched_bridge_names = pad_list(matched_bridge_names, n, "")
    matched_bridge_original_names = pad_list(matched_bridge_original_names, n, "")
    recovery_diagnostics = {
        wide_col: pad_list(values, n, "")
        for wide_col, values in recovery_diagnostics.items()
    }

    for i in range(n):
        competitor_name = competitors[i]

        if competitor_name == "":
            continue

        competitor_standardized = standardized[i]
        competitor_cik = ciks[i]
        competitor_gvkey = gvkeys[i]
        competitor_source = sources[i]
        competitor_method = methods[i]
        competitor_matched_bridge_name = matched_bridge_names[i]
        competitor_matched_bridge_original_name = matched_bridge_original_names[i]
        competitor_recovery_diagnostics = {
            long_col: recovery_diagnostics[wide_col][i]
            for wide_col, long_col in RECOVERY_DIAGNOSTIC_WIDE_TO_LONG.items()
        }

        long_rows.append({
            "sic_file": row.get("sic_file"),
            "filename": row.get(FILENAME_COL),
            "focal_cik": row.get("focal_cik"),
            "fyear": row.get("fyear"),
            "competitor_order": i + 1,
            "competitor_name": competitor_name,
            "competitor_name_standardized": competitor_standardized,
            "competitor_cik": competitor_cik,
            "competitor_gvkey": competitor_gvkey,
            "competitor_match_source": competitor_source,
            "competitor_match_method": competitor_method,
            "competitor_matched_bridge_name": competitor_matched_bridge_name,
            "competitor_matched_bridge_original_name": competitor_matched_bridge_original_name,
            **competitor_recovery_diagnostics,
            "has_competitor_cik": is_valid_id(competitor_cik),
            "has_competitor_gvkey": is_valid_id(competitor_gvkey),
            "has_any_competitor_identifier": is_valid_id(competitor_cik) or is_valid_id(competitor_gvkey),
            "gvkey_without_cik": (not is_valid_id(competitor_cik)) and is_valid_id(competitor_gvkey),
            "standardized_missing": str(competitor_standardized).strip() == "",
            "unmatched_both_ids": (not is_valid_id(competitor_cik)) and (not is_valid_id(competitor_gvkey)),
            "generic_score_raw": generic_score(competitor_name),
            "generic_score_standardized": generic_score(competitor_standardized),
            "is_likely_generic_category_raw": is_likely_generic_category(competitor_name),
            "is_likely_generic_category_standardized": is_likely_generic_category(competitor_standardized),
        })

long = pd.DataFrame(long_rows)

long["is_likely_generic_category"] = (
    (long["generic_score_raw"] >= 2) |
    (long["generic_score_standardized"] >= 2) |
    (long["is_likely_generic_category_raw"]) |
    (long["is_likely_generic_category_standardized"])
)

safe_to_csv(long, OUT_DIR / "merged_mapped_long_no20f.csv", index=False)
long.to_excel(OUT_DIR / "merged_mapped_long_no20f.xlsx", index=False)


# ------------------------------------------------------------
# 2B. Audit files for parent-prefix recovery and generic flags
# ------------------------------------------------------------
parent_recovery_cases = long[
    long["competitor_match_method"].astype(str).str.startswith("parent_prefix_recovery_", na=False)
].copy()

safe_to_csv(
    parent_recovery_cases,
    OUT_DIR / "parent_prefix_recovery_matched_cases.csv",
    index=False
)

parent_prefix_recovery_ambiguity_diagnostics = (
    parent_recovery_cases
    .groupby(
        [
            "competitor_match_source",
            "recovery_priority_rule",
            "recovered_parent_prefix_n_tokens",
            "recovery_n_candidates_all",
            "recovery_n_candidates_priority",
            "recovery_n_unique_identity_pairs_all",
            "recovery_n_unique_identity_pairs_priority",
        ],
        dropna=False
    )
    .agg(
        mentions=("competitor_name", "count"),
        unique_competitor_names=("competitor_name", "nunique"),
        unique_matched_bridge_names=("competitor_matched_bridge_name", "nunique"),
    )
    .reset_index()
    .sort_values("mentions", ascending=False)
)

safe_to_csv(
    parent_prefix_recovery_ambiguity_diagnostics,
    OUT_DIR / "parent_prefix_recovery_ambiguity_diagnostics.csv",
    index=False
)

global_parent_recovery_safety_summary = (
    parent_recovery_cases[
        parent_recovery_cases["competitor_match_source"].astype(str)
        == "parent_token_recovery_ALL_SOURCES_COMPUSTAT_GLOBAL"
    ]
    .groupby(
        [
            "global_parent_recovery_safety_rule",
            "global_parent_recovery_continuation_terms",
            "global_parent_recovery_unsafe_continuation_terms",
            "recovered_parent_prefix_n_tokens",
        ],
        dropna=False
    )
    .agg(
        mentions=("competitor_name", "count"),
        unique_competitor_names=("competitor_name", "nunique"),
        unique_matched_bridge_names=("competitor_matched_bridge_name", "nunique"),
    )
    .reset_index()
    .sort_values("mentions", ascending=False)
)

safe_to_csv(
    global_parent_recovery_safety_summary,
    OUT_DIR / "global_parent_recovery_safety_summary.csv",
    index=False
)

parent_recovery_review = (
    parent_recovery_cases
    .groupby(
        [
            "competitor_name",
            "competitor_name_standardized",
            "competitor_matched_bridge_name",
            "competitor_matched_bridge_original_name",
            "recovered_parent_prefix",
            "recovered_parent_prefix_n_tokens",
            "recovery_priority_rule",
            "recovery_n_candidates_all",
            "recovery_n_candidates_priority",
            "recovery_n_unique_identity_pairs_all",
            "recovery_n_unique_identity_pairs_priority",
            "recovery_candidate_parent_names_all",
            "recovery_candidate_parent_names_priority",
            "recovery_candidate_original_names_all",
            "recovery_candidate_original_names_priority",
            "recovery_candidate_sources_all",
            "recovery_candidate_sources_priority",
            "recovery_candidate_ciks_all",
            "recovery_candidate_gvkeys_all",
            "recovery_candidate_ciks_priority",
            "recovery_candidate_gvkeys_priority",
            "global_parent_recovery_continuation_terms",
            "global_parent_recovery_unsafe_continuation_terms",
            "global_parent_recovery_safety_rule",
            "competitor_match_source",
            "competitor_match_method",
            "competitor_cik",
            "competitor_gvkey",
        ],
        dropna=False
    )
    .agg(
        frequency=("competitor_name", "count"),
        sic_files=("sic_file", lambda x: "|".join(sorted(set(map(str, x))))),
        years=("fyear", lambda x: "|".join(map(str, sorted(set(x.dropna().astype(int)))))),
        example_filename=("filename", "first"),
    )
    .reset_index()
    .sort_values("frequency", ascending=False)
)

parent_recovery_review["manual_validation"] = ""
parent_recovery_review["notes"] = ""
parent_recovery_review = parent_recovery_review[
    [
        "competitor_name",
        "competitor_name_standardized",
        "competitor_matched_bridge_name",
        "competitor_matched_bridge_original_name",
        "recovered_parent_prefix",
        "recovered_parent_prefix_n_tokens",
        "recovery_priority_rule",
        "recovery_n_candidates_all",
        "recovery_n_candidates_priority",
        "recovery_n_unique_identity_pairs_all",
        "recovery_n_unique_identity_pairs_priority",
        "recovery_candidate_parent_names_all",
        "recovery_candidate_parent_names_priority",
        "recovery_candidate_original_names_all",
        "recovery_candidate_original_names_priority",
        "recovery_candidate_sources_all",
        "recovery_candidate_sources_priority",
        "recovery_candidate_ciks_all",
        "recovery_candidate_gvkeys_all",
        "recovery_candidate_ciks_priority",
        "recovery_candidate_gvkeys_priority",
        "global_parent_recovery_continuation_terms",
        "global_parent_recovery_unsafe_continuation_terms",
        "global_parent_recovery_safety_rule",
        "competitor_match_source",
        "competitor_match_method",
        "competitor_cik",
        "competitor_gvkey",
        "frequency",
        "sic_files",
        "years",
        "example_filename",
        "manual_validation",
        "notes",
    ]
]

safe_to_csv(
    parent_recovery_review,
    OUT_DIR / "parent_prefix_recovery_review_ranked.csv",
    index=False
)

VALIDATION_DIR = OUT_DIR / "validation_samples"
VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

VALIDATION_COLUMNS = [
    "competitor_name",
    "competitor_name_standardized",
    "competitor_matched_bridge_name",
    "competitor_matched_bridge_original_name",
    "recovered_parent_prefix",
    "recovered_parent_prefix_n_tokens",
    "recovery_priority_rule",
    "recovery_n_candidates_all",
    "recovery_n_candidates_priority",
    "recovery_n_unique_identity_pairs_all",
    "recovery_n_unique_identity_pairs_priority",
    "recovery_candidate_parent_names_all",
    "recovery_candidate_parent_names_priority",
    "recovery_candidate_original_names_all",
    "recovery_candidate_original_names_priority",
    "recovery_candidate_sources_all",
    "recovery_candidate_sources_priority",
    "recovery_candidate_ciks_all",
    "recovery_candidate_gvkeys_all",
    "recovery_candidate_ciks_priority",
    "recovery_candidate_gvkeys_priority",
    "global_parent_recovery_continuation_terms",
    "global_parent_recovery_unsafe_continuation_terms",
    "global_parent_recovery_safety_rule",
    "competitor_match_source",
    "competitor_match_method",
    "competitor_cik",
    "competitor_gvkey",
    "sic_file",
    "fyear",
    "filename",
    "manual_validation",
    "notes",
]

validation_sources = [
    "DISCERN",
    "CCM_COMPUSTAT_EXTENSION",
    "COMPUSTAT_GLOBAL",
    "parent_token_recovery_DISCERN_PRIORITY_DISCERN",
    "parent_token_recovery_CCM_PRIORITY_CCM_COMPUSTAT_EXTENSION",
    "parent_token_recovery_ALL_SOURCES_COMPUSTAT_GLOBAL",
    "unmatched",
]

for source in validation_sources:
    source_rows = long[long["competitor_match_source"].astype(str) == source].copy()

    if source_rows.empty:
        continue

    n_sample = min(100, len(source_rows))
    sample = source_rows.sample(n=n_sample, random_state=42).copy()
    sample["manual_validation"] = ""
    sample["notes"] = ""

    safe_source = re.sub(r"[^A-Za-z0-9_]+", "_", source).strip("_").lower()
    safe_to_csv(
        sample[VALIDATION_COLUMNS],
        VALIDATION_DIR / f"validation_sample_{safe_source}.csv",
        index=False
    )

high_frequency_parent_global_review = parent_recovery_review[
    parent_recovery_review["competitor_match_source"].astype(str)
    == "parent_token_recovery_ALL_SOURCES_COMPUSTAT_GLOBAL"
].copy()

high_frequency_parent_global_review = high_frequency_parent_global_review.sort_values(
    "frequency",
    ascending=False
).head(500)

safe_to_csv(
    high_frequency_parent_global_review,
    VALIDATION_DIR / "high_frequency_parent_global_review.csv",
    index=False
)

high_ambiguity_parent_recovery_review = parent_recovery_review[
    (
        parent_recovery_review["competitor_match_source"].astype(str)
        == "parent_token_recovery_ALL_SOURCES_COMPUSTAT_GLOBAL"
    ) &
    (
        (pd.to_numeric(parent_recovery_review["recovery_n_candidates_all"], errors="coerce") > 1) |
        (pd.to_numeric(parent_recovery_review["recovery_n_unique_identity_pairs_all"], errors="coerce") > 1)
    )
].copy()

high_ambiguity_parent_recovery_review = high_ambiguity_parent_recovery_review.sort_values(
    "frequency",
    ascending=False
).head(500)

safe_to_csv(
    high_ambiguity_parent_recovery_review,
    VALIDATION_DIR / "high_ambiguity_parent_recovery_review.csv",
    index=False
)

generic_flagged_mentions = long[
    long["is_likely_generic_category"]
].copy()

safe_to_csv(
    generic_flagged_mentions,
    OUT_DIR / "generic_category_flagged_mentions.csv",
    index=False
)


# ------------------------------------------------------------
# 3A. WIDE / focal-firm-year descriptives
# ------------------------------------------------------------
overall_wide = pd.DataFrame({
    "metric": [
        "total_firm_years",
        "total_unique_focal_firms",
        "firm_years_with_named_competitors",
        "unique_focal_firms_with_named_competitors",
        "firm_years_with_matched_cik",
        "firm_years_with_matched_gvkey",
        "firm_years_with_any_identifier",
        "firm_years_with_list_length_mismatch",
        "firm_years_with_bridge_name_missing_when_matched",
        "firm_years_with_bridge_original_name_missing_when_matched"
    ],
    "value": [
        len(wide),
        wide["focal_cik"].nunique(),
        wide["has_named_competitor"].sum(),
        wide.loc[wide["has_named_competitor"], "focal_cik"].nunique(),
        wide["has_matched_cik"].sum(),
        wide["has_matched_gvkey"].sum(),
        wide["has_any_identifier"].sum(),
        wide["list_length_mismatch"].sum(),
        wide["bridge_name_missing_when_matched"].sum(),
        wide["bridge_original_name_missing_when_matched"].sum()
    ]
})

yearly_wide = wide.groupby("fyear", dropna=False).agg(
    firm_years=("focal_cik", "count"),
    unique_focal_firms=("focal_cik", "nunique"),
    firm_years_with_named_competitors=("has_named_competitor", "sum"),
    firm_years_with_matched_cik=("has_matched_cik", "sum"),
    firm_years_with_matched_gvkey=("has_matched_gvkey", "sum"),
    total_competitor_mentions=("n_competitor_mentions", "sum"),
    matched_cik_mentions=("n_matched_cik_mentions", "sum"),
    matched_gvkey_mentions=("n_matched_gvkey_mentions", "sum"),
    list_length_mismatches=("list_length_mismatch", "sum"),
    firm_years_with_bridge_name_missing_when_matched=("bridge_name_missing_when_matched", "sum"),
    firm_years_with_bridge_original_name_missing_when_matched=("bridge_original_name_missing_when_matched", "sum")
).reset_index()

yearly_wide["share_firm_years_with_named_competitors"] = (
    yearly_wide["firm_years_with_named_competitors"] / yearly_wide["firm_years"]
)

sic_wide = wide.groupby("sic_file", dropna=False).agg(
    firm_years=("focal_cik", "count"),
    unique_focal_firms=("focal_cik", "nunique"),
    firm_years_with_named_competitors=("has_named_competitor", "sum"),
    total_competitor_mentions=("n_competitor_mentions", "sum"),
    matched_cik_mentions=("n_matched_cik_mentions", "sum"),
    matched_gvkey_mentions=("n_matched_gvkey_mentions", "sum"),
    list_length_mismatches=("list_length_mismatch", "sum"),
    firm_years_with_bridge_name_missing_when_matched=("bridge_name_missing_when_matched", "sum"),
    firm_years_with_bridge_original_name_missing_when_matched=("bridge_original_name_missing_when_matched", "sum")
).reset_index()

sic_wide["share_firm_years_with_named_competitors"] = (
    sic_wide["firm_years_with_named_competitors"] / sic_wide["firm_years"]
)


# ------------------------------------------------------------
# 3B. LONG / competitor-mention descriptives
# ------------------------------------------------------------
overall_long = pd.DataFrame({
    "metric": [
        "total_competitor_mentions",
        "mentions_with_cik",
        "mentions_with_gvkey",
        "mentions_with_any_identifier",
        "mentions_with_gvkey_without_cik",
        "mentions_unmatched_both_ids",
        "mentions_with_missing_standardized_name",
        "mentions_flagged_generic_category",
        "unique_competitor_names",
        "unique_competitor_names_standardized",
        "unique_competitor_ciks",
        "unique_competitor_gvkeys",
        "unique_gvkeys_without_cik_mentions"
    ],
    "value": [
        len(long),
        long["has_competitor_cik"].sum(),
        long["has_competitor_gvkey"].sum(),
        long["has_any_competitor_identifier"].sum(),
        long["gvkey_without_cik"].sum(),
        long["unmatched_both_ids"].sum(),
        long["standardized_missing"].sum(),
        long["is_likely_generic_category"].sum(),
        long["competitor_name"].nunique(),
        long["competitor_name_standardized"].nunique(),
        long.loc[long["has_competitor_cik"], "competitor_cik"].nunique(),
        long.loc[long["has_competitor_gvkey"], "competitor_gvkey"].nunique(),
        long.loc[long["gvkey_without_cik"], "competitor_gvkey"].nunique()
    ]
})

yearly_long = long.groupby("fyear", dropna=False).agg(
    competitor_mentions=("competitor_name", "count"),
    mentions_with_cik=("has_competitor_cik", "sum"),
    mentions_with_gvkey=("has_competitor_gvkey", "sum"),
    mentions_with_any_identifier=("has_any_competitor_identifier", "sum"),
    mentions_with_gvkey_without_cik=("gvkey_without_cik", "sum"),
    mentions_unmatched_both_ids=("unmatched_both_ids", "sum"),
    mentions_with_missing_standardized_name=("standardized_missing", "sum"),
    mentions_flagged_generic_category=("is_likely_generic_category", "sum"),
    unique_competitor_names=("competitor_name", "nunique"),
    unique_competitor_names_standardized=("competitor_name_standardized", "nunique"),
    unique_competitor_ciks=("competitor_cik", lambda x: x[long.loc[x.index, "has_competitor_cik"]].nunique()),
    unique_competitor_gvkeys=("competitor_gvkey", lambda x: x[long.loc[x.index, "has_competitor_gvkey"]].nunique())
).reset_index()

yearly_long["cik_match_rate"] = yearly_long["mentions_with_cik"] / yearly_long["competitor_mentions"]
yearly_long["gvkey_match_rate"] = yearly_long["mentions_with_gvkey"] / yearly_long["competitor_mentions"]

sic_long = long.groupby("sic_file", dropna=False).agg(
    competitor_mentions=("competitor_name", "count"),
    mentions_with_cik=("has_competitor_cik", "sum"),
    mentions_with_gvkey=("has_competitor_gvkey", "sum"),
    mentions_with_any_identifier=("has_any_competitor_identifier", "sum"),
    mentions_with_gvkey_without_cik=("gvkey_without_cik", "sum"),
    mentions_unmatched_both_ids=("unmatched_both_ids", "sum"),
    mentions_with_missing_standardized_name=("standardized_missing", "sum"),
    mentions_flagged_generic_category=("is_likely_generic_category", "sum"),
    unique_competitor_names=("competitor_name", "nunique"),
    unique_competitor_names_standardized=("competitor_name_standardized", "nunique"),
    unique_competitor_ciks=("competitor_cik", lambda x: x[long.loc[x.index, "has_competitor_cik"]].nunique()),
    unique_competitor_gvkeys=("competitor_gvkey", lambda x: x[long.loc[x.index, "has_competitor_gvkey"]].nunique())
).reset_index()

sic_long["cik_match_rate"] = sic_long["mentions_with_cik"] / sic_long["competitor_mentions"]
sic_long["gvkey_match_rate"] = sic_long["mentions_with_gvkey"] / sic_long["competitor_mentions"]


# ------------------------------------------------------------
# 3C. Match-source and match-method diagnostics
# ------------------------------------------------------------
source_diagnostics = (
    long.groupby("competitor_match_source", dropna=False)
    .agg(
        mentions=("competitor_name", "count"),
        unique_names=("competitor_name", "nunique"),
        mentions_with_any_identifier=("has_any_competitor_identifier", "sum")
    )
    .reset_index()
    .sort_values("mentions", ascending=False)
)

method_diagnostics = (
    long.groupby("competitor_match_method", dropna=False)
    .agg(
        mentions=("competitor_name", "count"),
        unique_names=("competitor_name", "nunique"),
        mentions_with_any_identifier=("has_any_competitor_identifier", "sum")
    )
    .reset_index()
    .sort_values("mentions", ascending=False)
)

sic_method_diagnostics = (
    long.groupby(["sic_file", "competitor_match_method"], dropna=False)
    .agg(
        mentions=("competitor_name", "count"),
        unique_names=("competitor_name", "nunique"),
        mentions_with_any_identifier=("has_any_competitor_identifier", "sum")
    )
    .reset_index()
    .sort_values(["sic_file", "mentions"], ascending=[True, False])
)


# ------------------------------------------------------------
# 4. Save descriptives
# ------------------------------------------------------------
with pd.ExcelWriter(OUT_DIR / "step6_descriptives.xlsx") as writer:
    overall_wide.to_excel(writer, sheet_name="overall_focal_year", index=False)
    yearly_wide.to_excel(writer, sheet_name="yearly_focal_year", index=False)
    sic_wide.to_excel(writer, sheet_name="sic_focal_year", index=False)

    overall_long.to_excel(writer, sheet_name="overall_mentions", index=False)
    yearly_long.to_excel(writer, sheet_name="yearly_mentions", index=False)
    sic_long.to_excel(writer, sheet_name="sic_mentions", index=False)

    source_diagnostics.to_excel(writer, sheet_name="match_sources", index=False)
    method_diagnostics.to_excel(writer, sheet_name="match_methods", index=False)
    sic_method_diagnostics.to_excel(writer, sheet_name="sic_match_methods", index=False)

safe_to_csv(overall_wide, OUT_DIR / "overall_focal_year.csv", index=False)
safe_to_csv(yearly_wide, OUT_DIR / "yearly_focal_year.csv", index=False)
safe_to_csv(sic_wide, OUT_DIR / "sic_focal_year.csv", index=False)

safe_to_csv(overall_long, OUT_DIR / "overall_mentions.csv", index=False)
safe_to_csv(yearly_long, OUT_DIR / "yearly_mentions.csv", index=False)
safe_to_csv(sic_long, OUT_DIR / "sic_mentions.csv", index=False)

safe_to_csv(source_diagnostics, OUT_DIR / "match_source_diagnostics.csv", index=False)
safe_to_csv(method_diagnostics, OUT_DIR / "match_method_diagnostics.csv", index=False)
safe_to_csv(sic_method_diagnostics, OUT_DIR / "sic_match_method_diagnostics.csv", index=False)

print("Step 6 completed.")
print("\nFocal firm-year descriptives:")
print(overall_wide)
print("\nCompetitor mention descriptives:")
print(overall_long)
print("\nOutputs saved in:", OUT_DIR)


# ------------------------------------------------------------
# 5. Unified missing-name review file for post-processing
# ------------------------------------------------------------
REVIEW_DIR = OUT_DIR / "missing_review"
REVIEW_DIR.mkdir(parents=True, exist_ok=True)

missing = long[
    (~long["has_competitor_cik"]) &
    (~long["has_competitor_gvkey"])
].copy()

missing_ranked = (
    missing.groupby(
        [
            "competitor_name",
            "competitor_name_standardized",
            "competitor_match_method"
        ],
        dropna=False
    )
    .agg(
        frequency=("competitor_name", "count"),
        sic_files=("sic_file", lambda x: "|".join(sorted(set(map(str, x))))),
        years=("fyear", lambda x: "|".join(map(str, sorted(set(x.dropna().astype(int)))))),
        example_filename=("filename", "first"),
        generic_score_raw=("generic_score_raw", "max"),
        generic_score_standardized=("generic_score_standardized", "max"),
        is_likely_generic_category_raw=("is_likely_generic_category_raw", "max"),
        is_likely_generic_category_standardized=("is_likely_generic_category_standardized", "max"),
        is_likely_generic_category=("is_likely_generic_category", "max")
    )
    .reset_index()
    .sort_values("frequency", ascending=False)
)

missing_ranked["suggested_action"] = "review_alias_or_keep_unmatched"

missing_ranked.loc[
    missing_ranked["is_likely_generic_category"],
    "suggested_action"
] = "review_remove_generic"

missing_ranked["manual_decision"] = ""
missing_ranked["alias_name"] = ""
missing_ranked["notes"] = ""

missing_ranked = missing_ranked[
    [
        "competitor_name",
        "competitor_name_standardized",
        "competitor_match_method",
        "frequency",
        "suggested_action",
        "manual_decision",
        "alias_name",
        "generic_score_raw",
        "generic_score_standardized",
        "is_likely_generic_category_raw",
        "is_likely_generic_category_standardized",
        "is_likely_generic_category",
        "sic_files",
        "years",
        "example_filename",
        "notes"
    ]
]

safe_to_csv(missing_ranked, REVIEW_DIR / "unified_missing_name_review.csv", index=False)

step7_action_col = (
    "recommended_action"
    if "recommended_action" in missing_ranked.columns
    else "suggested_action"
)

unmatched_review_for_step7 = missing_ranked[
    (missing_ranked[step7_action_col] == "review_alias_or_keep_unmatched") &
    (~missing_ranked["is_likely_generic_category"])
].copy()

unmatched_review_for_step7 = unmatched_review_for_step7.reset_index(drop=True)
unmatched_review_for_step7.insert(
    0,
    "record_id",
    ["step7_residual_{:06d}".format(i + 1) for i in range(len(unmatched_review_for_step7))]
)
unmatched_review_for_step7["step7_input_scope"] = "full_residual_review_no_frequency_threshold"

step7_columns = [
    "record_id",
    "competitor_name",
    "competitor_name_standardized",
    "frequency",
    "sic_files",
    "years",
    "example_filename",
    "generic_score_raw",
    "generic_score_standardized",
    "is_likely_generic_category_raw",
    "is_likely_generic_category_standardized",
    "is_likely_generic_category",
    "step7_input_scope",
    "notes",
]

unmatched_review_for_step7 = unmatched_review_for_step7[step7_columns]

safe_to_csv(
    unmatched_review_for_step7,
    REVIEW_DIR / "unmatched_review_for_step7.csv",
    index=False
)

unmatched_review_for_step7_highfreq_pilot = unmatched_review_for_step7[
    unmatched_review_for_step7["frequency"] >= 10
].copy()
unmatched_review_for_step7_highfreq_pilot["step7_input_scope"] = "high_frequency_pilot_frequency_ge_10"

safe_to_csv(
    unmatched_review_for_step7_highfreq_pilot,
    REVIEW_DIR / "unmatched_review_for_step7_highfreq_pilot.csv",
    index=False
)

print("\nUnified missing-name review file created:")
print("Unmatched unique name-method combinations:", len(missing_ranked))
print(
    "Suggested generic removals:",
    (missing_ranked["suggested_action"] == "review_remove_generic").sum()
)
print(
    "Suggested alias/keep review:",
    (missing_ranked["suggested_action"] == "review_alias_or_keep_unmatched").sum()
)
print("Review file saved in:", REVIEW_DIR / "unified_missing_name_review.csv")
print("Step 7 input saved in:", REVIEW_DIR / "unmatched_review_for_step7.csv")
print("Step 7 high-frequency pilot saved in:", REVIEW_DIR / "unmatched_review_for_step7_highfreq_pilot.csv")
print("Step 7 full residual review rows:", len(unmatched_review_for_step7))
print("Step 7 high-frequency pilot rows:", len(unmatched_review_for_step7_highfreq_pilot))
