# 8.5-Alias-Candidate-Generation.py

from pathlib import Path
import re

import pandas as pd
import yaml

from utils import get_uniform_format_company_name


INPUT_FILE = Path("data/results/descriptives/step7_residual_classification/step7_llm_residual_classified.csv")
FINAL_DIR = Path("data/results/final")
OUTPUT_FILE = FINAL_DIR / "candidate_alias_review.csv"
ALL_OUTPUT_FILE = FINAL_DIR / "candidate_alias_review_all_residuals.csv"
SUMMARY_FILE = FINAL_DIR / "candidate_alias_review_summary.csv"
TOP100_FILE = FINAL_DIR / "candidate_alias_review_top100.csv"

SOURCE_PRIORITY = {
    "DISCERN": 1,
    "CCM_COMPUSTAT_EXTENSION": 2,
    "COMPUSTAT_GLOBAL": 3,
}

STANDARDIZATION_MAP = {
    "HLDG": "HLDG", "HLDGS": "HLDG", "HLDNG": "HLDG", "HOLD": "HLDG",
    "HOLDING": "HLDG", "HOLDINGS": "HLDG",
    "GRP": "GRP", "GROUP": "GRP", "GROUPE": "GRP",
    "INCORPORATED": "INC", "CORPORATION": "CORP", "COMPANY": "CO", "LIMITED": "LTD",
    "TECH": "TECH", "TECHNOLOGY": "TECH", "TECHNOLOGIES": "TECH", "TECHNOLOGIE": "TECH",
    "TECHNOLGIES": "TECH", "TECHNLGY": "TECH", "TECHNO": "TECH", "TEK": "TECH",
    "RESEARCH": "RES", "SERV": "SERV", "SERVICE": "SERV", "SERVICES": "SERV",
    "SOLUT": "SOLUT", "SOLUTION": "SOLUT", "SOLUTIONS": "SOLUT",
    "SYS": "SYS", "SYSTEM": "SYS", "SYSTEMS": "SYS",
    "INTL": "INTL", "INTERNATIONAL": "INTL",
    "MFG": "MFG", "MANUFACTURING": "MFG", "MANUFACTURER": "MFG", "MANUFACTURERS": "MFG",
    "LABORATORIES": "LAB", "LABORATORY": "LAB", "LABORATOIRES": "LAB", "LABS": "LAB",
    "IND": "IND", "INDUST": "IND", "INDUSTRY": "IND", "INDUSTRIES": "IND", "INDUSTRIAL": "IND",
    "PHARM": "PHARM", "PHARMA": "PHARM", "PHARMS": "PHARM",
    "PHARMACEUTICAL": "PHARM", "PHARMACEUTICALS": "PHARM",
    "BIOPHARMACEUTICALS": "BIOPHARM", "BIOPHARMACEUTICAL": "BIOPHARM",
    "BIOTECHNOLOGIES": "BIOTECH", "BIOTECHNOLOGY": "BIOTECH",
    "BIOLOGICS": "BIOLOGIC", "BIOLOGICAL": "BIOLOGIC", "BIOLOGY": "BIOLOGIC",
    "BIOSCIENCES": "BIOSCI", "BIOSCIENCE": "BIOSCI",
    "GENOMICS": "GENOMIC", "DIAGNOSTICS": "DIAGNOSTIC",
    "HEALTHCARE": "HLTHCR", "HEALTH": "HLTH",
    "MEDICAL": "MED", "MEDICINE": "MED", "MEDICINES": "MED",
    "CHEMICALS": "CHEM", "CHEMICAL": "CHEM",
    "THERAPEUTICS": "THER", "THERAPEUTIC": "THER", "THERAPIES": "THER",
    "SEMICONDUCTORS": "SEMICOND", "SEMICONDUCTOR": "SEMICOND", "SEMICON": "SEMICOND",
    "ELECTRONICS": "ELECTRONIC", "ELECTRO": "ELECTRONIC", "ELEC": "ELECTRONIC",
    "MICROELECTRONICS": "MICROELECTRONIC",
    "COMMUNICATIONS": "COMM", "COMMUNICATION": "COMM",
    "TELECOMMUNICATIONS": "TELECOM", "TELECOMM": "TELECOM",
    "ENGINEERING": "ENG", "DEVELOPMENT": "DEV",
    "GLOBAL": "GLOB", "WORLDWIDE": "WORLD",
    "ENTERPRISES": "ENTERPRISE", "COMPONENTS": "COMPONENT",
    "DEVICES": "DEVICE", "CONSUMERS": "CONSUMER",
    "FRANCHISES": "FRANCHISE",
}

REMOVABLE_SUFFIXES = {
    "INC", "CORP", "CO", "LTD", "LLC", "PLC", "NV", "SA", "AG", "BV",
    "GMBH", "LP", "LLP", "KGAA", "OY", "OYJ", "SAS", "SRL", "SARL",
    "SPA", "PTE", "PVT", "SL", "SAU", "SPRL", "KS", "AB", "AS", "APS",
    "ASA", "BVBA", "KK", "LTDA", "RT", "ZRT", "KFT", "KG", "PTY", "BHD",
    "SDN", "PJSC", "JSC", "OAO", "ZAO", "AO", "HLDG", "GRP", "IND"
}

LEGAL_FORM_SPACING_PATTERNS = [
    ("S A R L", "SARL"),
    ("G M B H", "GMBH"),
    ("K G A A", "KGAA"),
    ("S A S", "SAS"),
    ("S R L", "SRL"),
    ("S P A", "SPA"),
    ("P L C", "PLC"),
    ("L T D", "LTD"),
    ("L L C", "LLC"),
    ("B H D", "BHD"),
    ("P T E", "PTE"),
    ("P T Y", "PTY"),
    ("N V", "NV"),
    ("S A", "SA"),
    ("B V", "BV"),
    ("A G", "AG"),
    ("A B", "AB"),
    ("A S", "AS"),
]

LEGAL_FORM_NORMALIZATION_TERMS = {
    "INC", "CORP", "CORPORATION", "CO", "LTD", "PLC", "AG", "NV", "SA", "SE",
    "SPA", "GROUP", "GRP", "HOLDING", "HLDG",
}

SAFE_GLOBAL_PARENT_CONTINUATION_TERMS = (
    set(STANDARDIZATION_MAP.keys())
    | set(STANDARDIZATION_MAP.values())
    | REMOVABLE_SUFFIXES
    | {
        "COMPUTER", "COMPUTERS", "ELECTRIC", "ELECTRICAL", "NORDIC", "HEAVY",
        "CORP", "INC", "CO", "LTD", "PLC", "AG", "SA", "NV", "BV", "LLC",
        "LP", "GMBH", "SPA", "PTE", "PTY", "BHD", "AB", "AS", "SAS",
        "SARL", "SRL",
    }
)

OUTPUT_COLUMNS = [
    "record_id",
    "competitor_name",
    "competitor_name_standardized",
    "frequency",
    "sic_files",
    "years",
    "example_filename",
    "llm_classification",
    "llm_decision",
    "llm_confidence",
    "needs_manual_check",
    "llm_reason",
    "suggested_alias_name",
    "suggested_alias_scope",
    "suggested_alias_reason",
    "candidate_bridge_name",
    "candidate_bridge_original_name",
    "candidate_conm",
    "candidate_cik",
    "candidate_gvkey",
    "candidate_source",
    "candidate_match_rule",
    "n_candidates",
    "manual_decision",
    "approved_alias_name",
    "approved_cik",
    "approved_gvkey",
    "reviewer_notes",
]


def fix_encoding_artifacts(value):
    if pd.isna(value):
        return ""
    value = str(value)
    replacements = {
        "â€šÃ„Ã´s": "'s",
        "â€šÃ„Ã´": "'",
        "â€šÃ„Ãº": '"',
        "â€šÃ„Ã¹": '"',
        "â€šÃ„Ã¬": "-",
        "Â¬Ã†": "",
        "â„¢": "",
        "Â®": "",
        "TM": "",
        "âˆšÃ¢": "E",
        "âˆšÃ±": "O",
        "âˆšÃ–": "A",
        "âˆšÃ²": "O",
        "âˆšÃœ": "A",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value.strip()


def normalize_legal_form_spacing(value):
    for spaced, collapsed in LEGAL_FORM_SPACING_PATTERNS:
        pattern = r"\b" + r"\s+".join(spaced.split()) + r"\b"
        value = re.sub(pattern, collapsed, value)
    return value


def standardize_name_for_mapping(value):
    if pd.isna(value):
        return ""
    value = fix_encoding_artifacts(value)
    value = get_uniform_format_company_name(value)
    value = normalize_legal_form_spacing(value)
    value = value.replace("-OLD", "")
    value = value.replace("-NEW", "")
    value = value.replace("-PRO FORMA", "")
    value = value.replace("PRO FORMA", "")
    value = re.sub(r"\bCL [A-Z]\b", "", value)
    value = re.sub(r"\bTHE\b", "", value)
    parts = value.split()
    parts = [STANDARDIZATION_MAP.get(part, part) for part in parts]
    value = " ".join(parts)
    return re.sub(r"\s+", " ", value).strip()


def legal_form_normalized_key(value):
    standardized = standardize_name_for_mapping(value)
    parts = [
        STANDARDIZATION_MAP.get(part, part)
        for part in standardized.split()
        if part not in LEGAL_FORM_NORMALIZATION_TERMS
    ]
    return " ".join(parts).strip()


def strip_suffixes(value):
    parts = str(value).split()
    while len(parts) > 1 and parts[-1] in REMOVABLE_SUFFIXES:
        parts = parts[:-1]
    return " ".join(parts).strip()


def clean_identifier_value(value):
    if pd.isna(value):
        return ""
    value = str(value).strip()
    if value == "" or value.lower() in {"nan", "none", "null"}:
        return ""
    return re.sub(r"\.0$", "", value)


def output_identifier_value(value):
    cleaned = clean_identifier_value(value)
    return cleaned if cleaned else -1


def clean_name_value(value, fallback=""):
    if pd.isna(value):
        return fallback
    value = str(value).strip()
    if value == "" or value.lower() in {"nan", "none", "null"}:
        return fallback
    return value


def load_config():
    with open("config.yaml", "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def prepare_bridge(config):
    dict_dir = Path(config["dict_dir"])
    bridge_file = dict_dir / config["mapping_bridge_file"]
    if not bridge_file.exists():
        raise FileNotFoundError(f"Missing Step 5 bridge file: {bridge_file}")

    bridge = pd.read_csv(bridge_file)
    required = ["name_std", "fyear", "gvkey", "cik", "source"]
    missing = [col for col in required if col not in bridge.columns]
    if missing:
        raise ValueError(f"Bridge file is missing required columns: {missing}")

    if "name_original" not in bridge.columns:
        if "id_name" in bridge.columns:
            bridge["name_original"] = bridge["id_name"]
        else:
            bridge["name_original"] = bridge["name_std"]

    bridge = bridge.dropna(subset=["name_std"]).copy()
    bridge["candidate_bridge_name"] = bridge["name_std"].apply(standardize_name_for_mapping)
    bridge["candidate_bridge_original_name"] = bridge.apply(
        lambda row: clean_name_value(row.get("name_original"), fallback=row["name_std"]),
        axis=1,
    )
    bridge["candidate_conm"] = bridge.apply(
        lambda row: clean_name_value(
            row.get("id_name"),
            fallback=clean_name_value(row.get("name_original"), fallback=row["name_std"]),
        ),
        axis=1,
    )
    bridge["candidate_cik"] = bridge["cik"].apply(output_identifier_value)
    bridge["candidate_gvkey"] = bridge["gvkey"].apply(output_identifier_value)
    bridge["candidate_source"] = bridge["source"].apply(clean_name_value)
    bridge["source_priority"] = bridge["candidate_source"].map(SOURCE_PRIORITY).fillna(9)
    bridge["exact_key"] = bridge["candidate_bridge_name"]
    bridge["legal_key"] = bridge["candidate_bridge_name"].apply(legal_form_normalized_key)
    bridge["suffix_key"] = bridge["candidate_bridge_name"].apply(strip_suffixes)

    bridge = bridge.sort_values(
        by=["candidate_bridge_name", "source_priority", "candidate_cik", "candidate_gvkey"],
        ascending=[True, True, True, True],
    )
    identity_cols = [
        "candidate_bridge_name",
        "candidate_bridge_original_name",
        "candidate_conm",
        "candidate_cik",
        "candidate_gvkey",
        "candidate_source",
        "source_priority",
        "exact_key",
        "legal_key",
        "suffix_key",
    ]
    bridge = bridge[identity_cols].drop_duplicates(
        subset=["candidate_bridge_name", "candidate_cik", "candidate_gvkey", "candidate_source"],
        keep="first",
    )
    return bridge


def bridge_row_to_candidate(row, rule):
    return {
        "candidate_bridge_name": row["candidate_bridge_name"],
        "candidate_bridge_original_name": row["candidate_bridge_original_name"],
        "candidate_conm": row["candidate_conm"],
        "candidate_cik": row["candidate_cik"],
        "candidate_gvkey": row["candidate_gvkey"],
        "candidate_source": row["candidate_source"],
        "candidate_match_rule": rule,
        "source_priority": row.get("source_priority", 9),
    }


def add_candidates_from_key(candidates, lookup, key_value, rule):
    if not key_value:
        return
    matches = lookup.get(key_value, [])
    for row in matches:
        candidates.append(bridge_row_to_candidate(row, rule))


def extract_parent_prefixes(name_std, max_tokens=3):
    parts = str(name_std).strip().split()
    return [" ".join(parts[:n]) for n in range(min(max_tokens, len(parts)), 0, -1)]


def get_continuation_terms(parent_name, recovered_prefix):
    parent_parts = str(parent_name).strip().split()
    prefix_parts = str(recovered_prefix).strip().split()
    if prefix_parts and parent_parts[:len(prefix_parts)] == prefix_parts:
        return parent_parts[len(prefix_parts):]
    return parent_parts


def global_parent_recovery_is_safe(row, token):
    if str(row["candidate_source"]).upper() != "COMPUSTAT_GLOBAL":
        return True
    continuation_terms = get_continuation_terms(row["candidate_bridge_name"], token)
    unsafe_terms = [
        term for term in continuation_terms
        if term not in SAFE_GLOBAL_PARENT_CONTINUATION_TERMS
    ]
    return len(unsafe_terms) == 0


def add_parent_prefix_candidates(candidates, parent_prefix_lookup, alias_std):
    for token in extract_parent_prefixes(alias_std, max_tokens=3):
        if not token:
            continue
        matches = parent_prefix_lookup.get(token, [])
        for row in matches:
            if not global_parent_recovery_is_safe(row, token):
                continue
            candidate = bridge_row_to_candidate(row, "parent_prefix_recovery")
            candidate["candidate_match_rule"] = f"parent_prefix_recovery:{token}"
            candidates.append(candidate)


def candidate_identity(candidate):
    return (
        str(candidate["candidate_bridge_name"]),
        str(candidate["candidate_cik"]),
        str(candidate["candidate_gvkey"]),
        str(candidate["candidate_source"]),
    )


def dedupe_candidates(candidates):
    best_rule_order = {
        "exact_standardized": 1,
        "legal_form_normalization": 2,
        "approved_suffix_stripping": 3,
    }
    output = {}
    for candidate in candidates:
        identity = candidate_identity(candidate)
        rule = str(candidate["candidate_match_rule"])
        rule_order = best_rule_order.get(rule.split(":")[0], 4)
        candidate["_rule_order"] = rule_order
        current = output.get(identity)
        if current is None or (candidate["_rule_order"], candidate["source_priority"]) < (
            current["_rule_order"],
            current["source_priority"],
        ):
            output[identity] = candidate

    deduped = list(output.values())
    deduped.sort(
        key=lambda c: (
            c["_rule_order"],
            c["source_priority"],
            str(c["candidate_bridge_name"]),
            str(c["candidate_source"]),
        )
    )
    for candidate in deduped:
        candidate.pop("_rule_order", None)
        candidate.pop("source_priority", None)
    return deduped


def build_lookup(bridge, key_col):
    lookup = {}
    for _, row in bridge.iterrows():
        key = row.get(key_col, "")
        if not key:
            continue
        lookup.setdefault(key, []).append(row)
    return lookup


def build_parent_prefix_lookup(bridge):
    lookup = {}
    for _, row in bridge.iterrows():
        name = row.get("candidate_bridge_name", "")
        for token in extract_parent_prefixes(name, max_tokens=3):
            if token and token != name:
                lookup.setdefault(token, []).append(row)
    return lookup


def build_bridge_lookups(bridge):
    return {
        "exact": build_lookup(bridge, "exact_key"),
        "legal": build_lookup(bridge, "legal_key"),
        "suffix": build_lookup(bridge, "suffix_key"),
        "parent_prefix": build_parent_prefix_lookup(bridge),
    }


def find_candidates(alias_name, lookups):
    alias_std = standardize_name_for_mapping(alias_name)
    legal_key = legal_form_normalized_key(alias_name)
    suffix_key = strip_suffixes(alias_std)
    candidates = []

    add_candidates_from_key(candidates, lookups["exact"], alias_std, "exact_standardized")
    add_candidates_from_key(candidates, lookups["legal"], legal_key, "legal_form_normalization")
    add_candidates_from_key(candidates, lookups["suffix"], suffix_key, "approved_suffix_stripping")
    add_parent_prefix_candidates(candidates, lookups["parent_prefix"], alias_std)
    return dedupe_candidates(candidates)


def base_alias_fields(alias_row):
    return {
        "record_id": alias_row.get("record_id", ""),
        "competitor_name": alias_row.get("competitor_name", ""),
        "competitor_name_standardized": alias_row.get("competitor_name_standardized", ""),
        "frequency": alias_row.get("frequency", 0),
        "sic_files": alias_row.get("sic_files", ""),
        "years": alias_row.get("years", ""),
        "example_filename": alias_row.get("example_filename", ""),
        "llm_classification": alias_row.get("llm_classification", ""),
        "llm_decision": alias_row.get("llm_decision", ""),
        "llm_confidence": alias_row.get("llm_confidence", ""),
        "needs_manual_check": alias_row.get("needs_manual_check", ""),
        "llm_reason": alias_row.get("llm_reason", ""),
        "suggested_alias_name": alias_row.get("suggested_alias_name", ""),
        "suggested_alias_scope": alias_row.get("suggested_alias_scope", ""),
        "suggested_alias_reason": alias_row.get("suggested_alias_reason", ""),
    }


def blank_review_fields(row):
    row["manual_decision"] = ""
    row["approved_alias_name"] = ""
    row["approved_cik"] = ""
    row["approved_gvkey"] = ""
    row["reviewer_notes"] = ""
    return row


def build_candidate_review(aliases, lookups):
    rows = []
    for _, alias_row in aliases.iterrows():
        alias_name = clean_name_value(alias_row.get("suggested_alias_name"))
        base = base_alias_fields(alias_row)
        candidates = find_candidates(alias_name, lookups) if alias_name else []
        n_candidates = len(candidates)

        if n_candidates == 0:
            row = {
                **base,
                "candidate_bridge_name": "",
                "candidate_bridge_original_name": "",
                "candidate_conm": "",
                "candidate_cik": "",
                "candidate_gvkey": "",
                "candidate_source": "",
                "candidate_match_rule": "no_candidate",
                "n_candidates": 0,
            }
            rows.append(blank_review_fields(row))
            continue

        for candidate in candidates:
            row = {**base, **candidate, "n_candidates": n_candidates}
            rows.append(blank_review_fields(row))

    review = pd.DataFrame(rows)
    review = review[OUTPUT_COLUMNS]
    review["_frequency_sort"] = pd.to_numeric(review["frequency"], errors="coerce").fillna(0)
    review["_n_candidates_sort"] = pd.to_numeric(review["n_candidates"], errors="coerce").fillna(0)
    review = review.sort_values(
        by=["_frequency_sort", "_n_candidates_sort", "llm_decision"],
        ascending=[False, True, True],
    ).drop(columns=["_frequency_sort", "_n_candidates_sort"])
    return review


def build_summary(review):
    matched = review[review["candidate_match_rule"] != "no_candidate"].copy()
    if matched.empty:
        return pd.DataFrame(columns=["match_rule", "aliases", "total_frequency", "unique_candidates"])

    summary = (
        matched.groupby("candidate_match_rule", dropna=False)
        .agg(
            aliases=("suggested_alias_name", "nunique"),
            records=("record_id", "nunique"),
            total_frequency=("frequency", lambda x: pd.to_numeric(x, errors="coerce").fillna(0).sum()),
            unique_candidates=("candidate_bridge_name", "nunique"),
        )
        .reset_index()
        .rename(columns={"candidate_match_rule": "match_rule"})
        .sort_values("total_frequency", ascending=False)
    )
    return summary


def report_counts(review, aliases):
    per_alias = (
        review.groupby(["record_id"], dropna=False)
        .agg(
            n_candidates=("n_candidates", "max"),
            frequency=("frequency", "first"),
        )
        .reset_index()
    )
    aliases_with_unique = int((per_alias["n_candidates"] == 1).sum())
    aliases_with_multiple = int((per_alias["n_candidates"] > 1).sum())
    aliases_with_none = int((per_alias["n_candidates"] == 0).sum())
    unique_freq = pd.to_numeric(
        per_alias.loc[per_alias["n_candidates"] == 1, "frequency"],
        errors="coerce",
    ).fillna(0).sum()

    print("Step 8.5 alias candidate generation completed")
    print(f"Step 7 records processed: {len(aliases)}")
    print(f"Records with unique candidate: {aliases_with_unique}")
    print(f"Records with multiple candidates: {aliases_with_multiple}")
    print(f"Records with no candidate: {aliases_with_none}")
    print(f"Total recoverable frequency represented by unique candidates: {unique_freq:g}")
    print("llm_decision counts in candidate input:")
    print(aliases["llm_decision"].fillna("").replace("", "(missing)").value_counts(dropna=False).to_string())


def main():
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing Step 7 classified input: {INPUT_FILE}")

    config = load_config()
    aliases = pd.read_csv(INPUT_FILE, low_memory=False)
    required_alias_cols = ["record_id", "llm_decision", "suggested_alias_name"]
    missing_alias_cols = [col for col in required_alias_cols if col not in aliases.columns]
    if missing_alias_cols:
        raise ValueError(f"Input file is missing required columns: {missing_alias_cols}")

    aliases = aliases.copy()
    aliases["suggested_alias_name"] = aliases["suggested_alias_name"].apply(clean_name_value)
    aliases["llm_decision"] = aliases["llm_decision"].apply(clean_name_value)
    aliases = aliases[aliases["llm_decision"].str.lower() != "drop"].copy()
    aliases = aliases.drop_duplicates(subset=["record_id"], keep="first")

    bridge = prepare_bridge(config)
    lookups = build_bridge_lookups(bridge)
    review = build_candidate_review(aliases, lookups)
    summary = build_summary(review)
    top100 = review.drop_duplicates(subset=["suggested_alias_name"], keep="first").head(100)

    review.to_csv(OUTPUT_FILE, index=False)
    review.to_csv(ALL_OUTPUT_FILE, index=False)
    summary.to_csv(SUMMARY_FILE, index=False)
    top100.to_csv(TOP100_FILE, index=False)

    report_counts(review, aliases)
    print(f"Main output: {OUTPUT_FILE}")
    print(f"All residual output: {ALL_OUTPUT_FILE}")
    print(f"Summary output: {SUMMARY_FILE}")
    print(f"Top 100 output: {TOP100_FILE}")


if __name__ == "__main__":
    main()
