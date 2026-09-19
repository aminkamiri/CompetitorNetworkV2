# 8.5-Alias-Candidate-Generation(rev4).py

from pathlib import Path
import re
from datetime import datetime
import unicodedata
from functools import lru_cache

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

SOURCE_SCORE = {
    "DISCERN": 40,
    "CCM_COMPUSTAT_EXTENSION": 30,
    "COMPUSTAT_GLOBAL": 10,
}

MATCH_RULE_SCORE = {
    "exact_standardized_match": 50,
    "legal_form_normalization": 40,
    "suffix_stripped_match": 30,
    "parent_prefix_recovery": 10,
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

STRONG_PARENT_ENTITY_SUFFIXES = {"HLDG", "HLDGS", "HOLDING", "HOLDINGS", "GROUP", "GRP"}

MEDIUM_CORPORATE_ENTITY_SUFFIXES = {"INC", "CORP", "CORPORATION", "CO", "COMPANY"}

LOW_LEGAL_FORM_SUFFIXES = {
    "PLC", "SE", "NV", "AG", "SA", "BV", "GMBH", "LLP", "LP", "LLC", "LTD",
    "AB", "AS", "SPA", "SARL", "SRL", "KGAA", "OY", "OYJ", "SAS", "PTE",
    "PVT", "SL", "SAU", "SPRL", "KS", "APS", "ASA", "BVBA", "KK", "LTDA",
    "RT", "ZRT", "KFT", "KG", "PTY", "BHD", "SDN", "PJSC", "JSC", "OAO",
    "ZAO", "AO",
}

LEGAL_FORM_NORMALIZATION_TERMS = (
    STRONG_PARENT_ENTITY_SUFFIXES |
    MEDIUM_CORPORATE_ENTITY_SUFFIXES |
    LOW_LEGAL_FORM_SUFFIXES
)

PARENT_LEGAL_ENTITY_TERMS = LEGAL_FORM_NORMALIZATION_TERMS | {"LIMITED"}

LEGAL_FORM_SUFFIXES = LEGAL_FORM_NORMALIZATION_TERMS | {"LIMITED"}

SAFE_ALIAS_EQUIVALENCES = {
    "ELI LILLY AND CO": "ELI LILLY",
    "ELI LILLY CO": "ELI LILLY",
    "ELI LILLY AND COMPANY": "ELI LILLY",
    "ELI LILLY COMPANY": "ELI LILLY",
    "ELI LILLY & COMPANY": "ELI LILLY",
    "WAL MART STORES": "WAL MART",
    "WALMART STORES": "WAL MART",
    "WALMART": "WAL MART",
    "GLAXO SMITH KLINE": "GLAXOSMITHKLINE",
    "GLAXOSMITH KLINE": "GLAXOSMITHKLINE",
    "NESTLÉ": "NESTLE",
    "NESTLE": "NESTLE",
}

NORMALIZATION_DIAGNOSTICS = {
    "aliases_accent_normalized": 0,
    "aliases_company_suffix_normalized": 0,
    "aliases_punctuation_hyphen_normalized": 0,
}

GEOGRAPHIC_TOKENS = {
    "INDIA", "CHINA", "PAKISTAN", "KOREA", "JAPAN", "EUROPE", "MEXICO",
    "DE MEXICO",
}

BUSINESS_UNIT_TOKENS = {
    "BIOLOGICS", "BIOLOGIC", "PHARMA", "PHARM", "DIAGNOSTICS", "DIAGNOSTIC",
    "MEDICAL", "MED", "CONSUMER", "HEAVY", "ELECTRONICS", "ELECTRONIC",
    "CHEMICAL", "CHEMICALS", "CHEM", "HEALTHCARE", "HLTHCR",
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
    "candidate_rank_score",
    "candidate_rank",
    "recommended_candidate",
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


def normalize_unicode_accents(value):
    value = "" if pd.isna(value) else str(value)
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_punctuation_separators(value):
    value = "" if pd.isna(value) else str(value)
    value = re.sub(r"[\[\]\(\)\{\}]", " ", value)
    value = value.replace("&", " AND ")
    value = re.sub(r"[-/\\,.;:'\"`’‘“”]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def normalize_company_suffix_phrases(value):
    value = re.sub(r"\bAND\s+COMPANY\b", " CO ", value, flags=re.I)
    value = re.sub(r"\bAND\s+CO\b", " CO ", value, flags=re.I)
    value = re.sub(r"\bCOMPANY\b", " CO ", value, flags=re.I)
    value = re.sub(r"\bCO\.\b", " CO ", value, flags=re.I)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def apply_safe_alias_equivalences(value):
    return SAFE_ALIAS_EQUIVALENCES.get(value, value)


def standardize_name_for_mapping(value):
    if pd.isna(value):
        return ""
    return _standardize_name_for_mapping_cached(str(value))


@lru_cache(maxsize=500000)
def _standardize_name_for_mapping_cached(value):
    value = fix_encoding_artifacts(value)
    value = normalize_unicode_accents(value)
    value = normalize_punctuation_separators(value)
    value = normalize_company_suffix_phrases(value)
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
    value = re.sub(r"\s+", " ", value).strip()
    value = apply_safe_alias_equivalences(value)
    return value


def legal_form_normalized_key(value):
    return _legal_form_normalized_key_cached("" if pd.isna(value) else str(value))


@lru_cache(maxsize=500000)
def _legal_form_normalized_key_cached(value):
    standardized = standardize_name_for_mapping(value)
    parts = [
        STANDARDIZATION_MAP.get(part, part)
        for part in standardized.split()
        if part not in LEGAL_FORM_NORMALIZATION_TERMS
    ]
    return apply_safe_alias_equivalences(" ".join(parts).strip())


def strip_suffixes(value):
    return _strip_suffixes_cached("" if pd.isna(value) else str(value))


@lru_cache(maxsize=500000)
def _strip_suffixes_cached(value):
    parts = str(value).split()
    while len(parts) > 1 and parts[-1] in REMOVABLE_SUFFIXES:
        parts = parts[:-1]
    return apply_safe_alias_equivalences(" ".join(parts).strip())


def strip_legal_form_suffixes(value):
    return _strip_legal_form_suffixes_cached("" if pd.isna(value) else str(value))


@lru_cache(maxsize=500000)
def _strip_legal_form_suffixes_cached(value):
    parts = str(value).split()
    while len(parts) > 1 and parts[-1] in LEGAL_FORM_SUFFIXES:
        parts = parts[:-1]
    return apply_safe_alias_equivalences(" ".join(parts).strip())


def normalized_core_name(value):
    return _normalized_core_name_cached("" if pd.isna(value) else str(value))


@lru_cache(maxsize=500000)
def _normalized_core_name_cached(value):
    standardized = standardize_name_for_mapping(value)
    return strip_legal_form_suffixes(standardized)


def terminal_suffix_group(value):
    return _terminal_suffix_group_cached("" if pd.isna(value) else str(value))


@lru_cache(maxsize=500000)
def _terminal_suffix_group_cached(value):
    parts = standardize_name_for_mapping(value).split()
    if not parts:
        return ""
    last = parts[-1]
    if last in STRONG_PARENT_ENTITY_SUFFIXES:
        return "strong_parent_entity"
    if last in MEDIUM_CORPORATE_ENTITY_SUFFIXES:
        return "medium_corporate_entity"
    if last in LOW_LEGAL_FORM_SUFFIXES:
        return "low_legal_form"
    return ""


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


def is_numeric_only(value):
    value = clean_name_value(value)
    if value == "":
        return False
    return bool(re.fullmatch(r"[-+]?\d+(?:\.\d+)?", value))


def clean_conm_value(value, fallback=""):
    value = clean_name_value(value)
    if value == "" or is_numeric_only(value):
        fallback = clean_name_value(fallback)
        return "" if is_numeric_only(fallback) else fallback
    return value


def best_company_name_from_bridge_row(row):
    for col in ["id_name", "name_original", "name_std"]:
        value = clean_name_value(row.get(col))
        if value and not is_numeric_only(value):
            return value
    return ""


def is_valid_identifier(value):
    value = clean_name_value(value)
    if value == "" or value in {"-1", "-1.0"}:
        return False
    return not pd.isna(pd.to_numeric(value, errors="coerce")) or bool(re.search(r"[A-Za-z0-9]", value))


def load_config():
    with open("config.yaml", "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


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
    bridge["candidate_bridge_original_name"] = bridge.apply(best_company_name_from_bridge_row, axis=1)
    bridge["candidate_conm"] = bridge.apply(
        lambda row: clean_conm_value(
            row.get("id_name"),
            fallback=best_company_name_from_bridge_row(row),
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
        "exact_standardized_match": 1,
        "legal_form_normalization": 2,
        "suffix_stripped_match": 3,
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

    add_candidates_from_key(candidates, lookups["exact"], alias_std, "exact_standardized_match")
    add_candidates_from_key(candidates, lookups["legal"], legal_key, "legal_form_normalization")
    add_candidates_from_key(candidates, lookups["suffix"], suffix_key, "suffix_stripped_match")
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


def match_rule_base(rule):
    rule = str(rule)
    if rule.startswith("parent_prefix_recovery"):
        return "parent_prefix_recovery"
    return rule


def recovered_parent_prefix(rule):
    rule = str(rule)
    if not rule.startswith("parent_prefix_recovery:"):
        return ""
    return rule.split(":", 1)[1].strip()


def name_tokens(value):
    return standardize_name_for_mapping(value).split()


def parent_prefix_is_strong(row):
    if match_rule_base(row.get("candidate_match_rule", "")) != "parent_prefix_recovery":
        return False

    prefix = recovered_parent_prefix(row.get("candidate_match_rule", ""))
    prefix_tokens = [token for token in str(prefix).split() if token not in LEGAL_FORM_SUFFIXES]
    if len(prefix_tokens) >= 2:
        return True

    candidate_core = normalized_core_name(row.get("candidate_bridge_name", ""))
    alias_core = normalized_core_name(row.get("suggested_alias_name", ""))
    return candidate_core != "" and candidate_core == alias_core


def parent_prefix_is_weak(row):
    return match_rule_base(row.get("candidate_match_rule", "")) == "parent_prefix_recovery" and not parent_prefix_is_strong(row)


def has_geographic_continuation(candidate_name):
    text = " ".join(name_tokens(candidate_name))
    tokens = set(text.split())
    return bool(tokens & GEOGRAPHIC_TOKENS) or "DE MEXICO" in text


def has_business_unit_continuation(candidate_name):
    return bool(set(name_tokens(candidate_name)) & BUSINESS_UNIT_TOKENS)


def continuation_after_alias(candidate_name, alias_name):
    candidate_parts = name_tokens(candidate_name)
    alias_parts = name_tokens(alias_name)
    if alias_parts and candidate_parts[:len(alias_parts)] == alias_parts:
        return candidate_parts[len(alias_parts):]
    return []


def continuation_is_only_legal_or_parent_suffix(candidate_name, alias_name):
    continuation = continuation_after_alias(candidate_name, alias_name)
    if not continuation:
        return True
    return all(token in PARENT_LEGAL_ENTITY_TERMS or token in REMOVABLE_SUFFIXES for token in continuation)


def candidate_looks_parent_legal_entity(candidate_name):
    parts = name_tokens(candidate_name)
    if not parts:
        return False
    return any(token in PARENT_LEGAL_ENTITY_TERMS or token in REMOVABLE_SUFFIXES for token in parts[-3:])


def has_us_style_source_or_cik(row):
    return str(row.get("candidate_source", "")).upper() in {"DISCERN", "CCM_COMPUSTAT_EXTENSION"} or is_valid_identifier(row.get("candidate_cik"))


def first_two_informative_tokens(value):
    return [
        token for token in normalized_core_name(value).split()
        if token not in LEGAL_FORM_SUFFIXES
    ][:2]


def has_second_informative_token_mismatch(candidate_name, alias_name):
    candidate_tokens = first_two_informative_tokens(candidate_name)
    alias_tokens = first_two_informative_tokens(alias_name)
    return (
        len(candidate_tokens) >= 2
        and len(alias_tokens) >= 2
        and candidate_tokens[0] == alias_tokens[0]
        and candidate_tokens[1] != alias_tokens[1]
    )


def suffix_group_score(candidate_name):
    group = terminal_suffix_group(candidate_name)
    if group == "strong_parent_entity":
        return 25
    if group == "medium_corporate_entity":
        return 15
    if group == "low_legal_form":
        return 5
    return 0


def score_candidate(row):
    if str(row.get("candidate_match_rule", "")) == "no_candidate":
        return 0

    score = 0
    source = str(row.get("candidate_source", "")).upper()
    rule_base = match_rule_base(row.get("candidate_match_rule", ""))
    candidate_name = row.get("candidate_bridge_name", "")
    alias_name = row.get("suggested_alias_name", "")
    candidate_core = normalized_core_name(candidate_name)
    alias_core = normalized_core_name(alias_name)

    score += SOURCE_SCORE.get(source, 0)
    if is_valid_identifier(row.get("candidate_cik")):
        score += 20
    if is_valid_identifier(row.get("candidate_gvkey")):
        score += 10
    score += MATCH_RULE_SCORE.get(rule_base, 0)
    if parent_prefix_is_weak(row):
        score -= 40
        if len(first_two_informative_tokens(alias_name)) >= 2:
            score -= 80

    if candidate_core and alias_core and candidate_core == alias_core:
        score += 80
    elif candidate_core and alias_core and candidate_core.startswith(alias_core + " "):
        score += 45
    elif has_second_informative_token_mismatch(candidate_name, alias_name):
        score -= 80

    score += suffix_group_score(candidate_name)

    if legal_form_normalized_key(candidate_name) == legal_form_normalized_key(alias_name):
        score += 20
    if candidate_looks_parent_legal_entity(candidate_name):
        score += 20
    if has_us_style_source_or_cik(row):
        score += 20

    if has_geographic_continuation(candidate_name):
        score -= 25
    if has_business_unit_continuation(candidate_name):
        score -= 15

    candidate_len = len(name_tokens(candidate_name))
    alias_len = len(name_tokens(alias_name))
    if candidate_len >= alias_len + 2 and not continuation_is_only_legal_or_parent_suffix(candidate_name, alias_name):
        score -= 15

    return score


def add_candidate_ranking(review):
    review = review.copy()
    review["candidate_rank_score"] = review.apply(score_candidate, axis=1)
    review["candidate_rank"] = ""
    review["recommended_candidate"] = False

    matched_mask = review["candidate_match_rule"] != "no_candidate"
    if not matched_mask.any():
        return review

    sort_cols = [
        "record_id",
        "candidate_rank_score",
        "candidate_source",
        "candidate_match_rule",
        "candidate_bridge_name",
    ]
    ranked = review[matched_mask].sort_values(
        by=sort_cols,
        ascending=[True, False, True, True, True],
    ).copy()
    ranked["candidate_rank"] = ranked.groupby("record_id").cumcount() + 1
    review.loc[ranked.index, "candidate_rank"] = ranked["candidate_rank"]

    for record_id, group in ranked.groupby("record_id", dropna=False):
        group = group.sort_values("candidate_rank")
        top = group.iloc[0]
        second_score = group.iloc[1]["candidate_rank_score"] if len(group) > 1 else None
        margin_ok = len(group) == 1 or top["candidate_rank_score"] >= second_score + 30
        has_identifier = is_valid_identifier(top["candidate_cik"]) or is_valid_identifier(top["candidate_gvkey"])
        rule_base = match_rule_base(top["candidate_match_rule"])
        exact_or_legal = rule_base in {"exact_standardized_match", "legal_form_normalization"}
        strong_parent_prefix = rule_base == "parent_prefix_recovery" and parent_prefix_is_strong(top)
        eligible_rule = exact_or_legal or strong_parent_prefix

        if has_identifier and margin_ok and eligible_rule:
            review.loc[top.name, "recommended_candidate"] = True

    return review


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
                "candidate_rank_score": 0,
                "candidate_rank": "",
                "recommended_candidate": False,
                "n_candidates": 0,
            }
            rows.append(blank_review_fields(row))
            continue

        for candidate in candidates:
            row = {**base, **candidate, "n_candidates": n_candidates}
            rows.append(blank_review_fields(row))

    review = pd.DataFrame(rows)
    review = add_candidate_ranking(review)
    review = review[OUTPUT_COLUMNS]
    review["_frequency_sort"] = pd.to_numeric(review["frequency"], errors="coerce").fillna(0)
    review["_n_candidates_sort"] = pd.to_numeric(review["n_candidates"], errors="coerce").fillna(0)
    review["_rank_sort"] = pd.to_numeric(review["candidate_rank"], errors="coerce").fillna(999999)
    review = review.sort_values(
        by=["_frequency_sort", "recommended_candidate", "_n_candidates_sort", "_rank_sort"],
        ascending=[False, False, True, True],
    ).drop(columns=["_frequency_sort", "_n_candidates_sort", "_rank_sort"])
    return review


def build_summary(review):
    matched = review[review["candidate_match_rule"] != "no_candidate"].copy()
    if matched.empty:
        return pd.DataFrame(columns=["match_rule", "aliases", "records", "total_frequency", "unique_candidates", "recommended_candidates"])

    summary = (
        matched.groupby("candidate_match_rule", dropna=False)
        .agg(
            aliases=("suggested_alias_name", "nunique"),
            records=("record_id", "nunique"),
            total_frequency=("frequency", lambda x: pd.to_numeric(x, errors="coerce").fillna(0).sum()),
            unique_candidates=("candidate_bridge_name", "nunique"),
            recommended_candidates=("recommended_candidate", "sum"),
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
            has_recommended_candidate=("recommended_candidate", "max"),
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
    recommended_aliases = int(per_alias["has_recommended_candidate"].sum())
    recommended_frequency = pd.to_numeric(
        per_alias.loc[per_alias["has_recommended_candidate"], "frequency"],
        errors="coerce",
    ).fillna(0).sum()
    recommended = review[review["recommended_candidate"]].copy()
    recommended_weak_parent_prefix = int(recommended.apply(parent_prefix_is_weak, axis=1).sum()) if not recommended.empty else 0

    print("Step 8.5 alias candidate generation completed")
    print(f"Step 7 records processed: {len(aliases)}")
    print(f"Records with unique candidate: {aliases_with_unique}")
    print(f"Records with multiple candidates: {aliases_with_multiple}")
    print(f"Records with no candidate: {aliases_with_none}")
    print(f"Total recoverable frequency represented by unique candidates: {unique_freq:g}")
    print(f"Aliases with recommended candidate: {recommended_aliases}")
    print(f"Number of recommended candidates: {len(recommended)}")
    print(f"Frequency covered by recommended candidates: {recommended_frequency:g}")
    print("Recommended candidates by source:")
    if recommended.empty:
        print("(none)")
    else:
        print(recommended["candidate_source"].value_counts(dropna=False).to_string())
    print("Recommended candidates by match rule:")
    if recommended.empty:
        print("(none)")
    else:
        print(recommended["candidate_match_rule"].apply(match_rule_base).value_counts(dropna=False).to_string())
    print(f"Recommended candidates using weak parent-prefix recovery: {recommended_weak_parent_prefix}")
    print("llm_decision counts in candidate input:")
    print(aliases["llm_decision"].fillna("").replace("", "(missing)").value_counts(dropna=False).to_string())


def compute_normalization_diagnostics(aliases):
    diagnostics = NORMALIZATION_DIAGNOSTICS.copy()
    diagnostics = {key: 0 for key in diagnostics}

    for value in aliases["suggested_alias_name"].fillna(""):
        raw = str(value)
        accent_normalized = normalize_unicode_accents(raw)
        punctuation_normalized = normalize_punctuation_separators(accent_normalized)
        suffix_normalized = normalize_company_suffix_phrases(punctuation_normalized)

        if accent_normalized != raw:
            diagnostics["aliases_accent_normalized"] += 1
        if punctuation_normalized != accent_normalized.strip():
            diagnostics["aliases_punctuation_hyphen_normalized"] += 1
        if suffix_normalized != punctuation_normalized:
            diagnostics["aliases_company_suffix_normalized"] += 1

    return diagnostics


def print_normalization_diagnostics(diagnostics):
    print("Normalization diagnostics")
    print(f"Aliases affected by accent normalization: {diagnostics['aliases_accent_normalized']}")
    print(f"Aliases affected by company-suffix normalization: {diagnostics['aliases_company_suffix_normalized']}")
    print(f"Aliases affected by punctuation/hyphen normalization: {diagnostics['aliases_punctuation_hyphen_normalized']}")


def print_target_alias_candidate_checks(lookups):
    target_aliases = [
        "GENERAL ELECTRIC",
        "ABC",
        "GENZYME",
        "WAL MART",
        "WAL-MART",
        "NESTLE",
        "NESTLÉ",
        "ELI LILLY",
        "GLAXOSMITHKLINE",
    ]
    print("Target alias candidate checks")
    for alias in target_aliases:
        candidates = find_candidates(alias, lookups)
        if not candidates:
            print(f"{alias}: NO_CANDIDATE (0)")
            continue
        base = {
            "record_id": f"diagnostic_{alias}",
            "suggested_alias_name": alias,
            "candidate_match_rule": "",
            "candidate_cik": "",
            "candidate_gvkey": "",
            "candidate_source": "",
            "candidate_bridge_name": "",
        }
        diagnostic_rows = pd.DataFrame([{**base, **candidate} for candidate in candidates])
        diagnostic_rows = add_candidate_ranking(diagnostic_rows)
        top = diagnostic_rows.sort_values("candidate_rank").iloc[0]
        print(
            f"{alias}: FOUND ({len(candidates)}) | "
            f"top={top['candidate_bridge_name']} | "
            f"source={top['candidate_source']} | "
            f"rule={top['candidate_match_rule']} | "
            f"score={top['candidate_rank_score']}"
        )


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
    normalization_diagnostics = compute_normalization_diagnostics(aliases)

    bridge = prepare_bridge(config)
    lookups = build_bridge_lookups(bridge)
    print_normalization_diagnostics(normalization_diagnostics)
    print_target_alias_candidate_checks(lookups)
    review = build_candidate_review(aliases, lookups)
    summary = build_summary(review)
    top100 = review.drop_duplicates(subset=["suggested_alias_name"], keep="first").head(100)

    output_path = safe_to_csv(review, OUTPUT_FILE, index=False)
    all_output_path = safe_to_csv(review, ALL_OUTPUT_FILE, index=False)
    summary_path = safe_to_csv(summary, SUMMARY_FILE, index=False)
    top100_path = safe_to_csv(top100, TOP100_FILE, index=False)

    report_counts(review, aliases)
    print(f"Main output: {output_path}")
    print(f"All residual output: {all_output_path}")
    print(f"Summary output: {summary_path}")
    print(f"Top 100 output: {top100_path}")


if __name__ == "__main__":
    main()
