# 8.5-Alias-Candidate-Generation(rev9).py

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
COMPARISON_SUMMARY_FILE = FINAL_DIR / "candidate_alias_review_rev6_vs_rev7_summary.csv"
COMPARISON_RECOVERED_TOP100_FILE = FINAL_DIR / "candidate_alias_review_rev6_vs_rev7_recovered_top100.csv"
COMPARISON_SOURCE_FILE = FINAL_DIR / "candidate_alias_review_rev6_vs_rev7_source_comparison.csv"
COMPARISON_MATCH_RULE_FILE = FINAL_DIR / "candidate_alias_review_rev6_vs_rev7_match_rule_comparison.csv"
COMPARISON_VALIDATION_FILE = FINAL_DIR / "candidate_alias_review_rev6_vs_rev7_validation_examples.csv"
COMPARISON_RECOVERED_BREAKDOWN_FILE = FINAL_DIR / "candidate_alias_review_rev6_vs_rev7_recovered_breakdown.csv"
TIER_AUDIT_FILE = FINAL_DIR / "candidate_acceptance_tier_audit.csv"
TIER_SCENARIO_SUMMARY_FILE = FINAL_DIR / "candidate_acceptance_tier_scenario_summary.csv"
TIER_AUTO_BY_RULE_FILE = FINAL_DIR / "candidate_acceptance_tier_auto_accept_by_match_rule.csv"
TIER_AUTO_BY_SOURCE_FILE = FINAL_DIR / "candidate_acceptance_tier_auto_accept_by_source.csv"
TIER_VALIDATION_FILE = FINAL_DIR / "candidate_acceptance_tier_validation_examples.csv"
REV6_NO_CANDIDATE_AUDIT_FILE = FINAL_DIR / "no_candidate_audit" / "no_candidate_full_annotated_audit.csv"

YEAR_SPECIFIC_BRIDGE_FILE = Path("data/dict/company_alias_bridge_year_specific.csv")
IDENTIFIER_LEVEL_BRIDGE_FILE = Path("data/dict/company_alias_bridge_identifier_level.csv")
IDENTIFIER_YEAR_PANEL_FILE = Path("data/dict/company_identifier_year_panel.csv")

SOURCE_PRIORITY = {
    "DISCERN": 1,
    "COMPUSTAT_US": 2,
    "CCM_COMPUSTAT_EXTENSION": 2,
    "NON_DISCERN_US_COMPUSTAT": 2,
    "COMPUSTAT_GLOBAL": 3,
    "SEC_HEADER": 4,
    "SEC_FILING_HEADER": 4,
    "WRDS_LOOKUP": 5,
    "WRDS_NAME_LOOKUP": 5,
    "WRDS": 5,
}

SOURCE_SCORE = {
    "DISCERN": 45,
    "COMPUSTAT_US": 35,
    "CCM_COMPUSTAT_EXTENSION": 35,
    "NON_DISCERN_US_COMPUSTAT": 35,
    "COMPUSTAT_GLOBAL": 20,
    "SEC_HEADER": 10,
    "SEC_FILING_HEADER": 10,
    "WRDS_LOOKUP": 0,
    "WRDS_NAME_LOOKUP": 0,
    "WRDS": 0,
}

MATCH_RULE_SCORE = {
    "exact_standardized_match": 50,
    "legal_form_normalization": 40,
    "suffix_stripped_match": 30,
    "exact_other_year": 35,
    "legal_other_year": 25,
    "approved_abbreviation_bridge_match": 22,
    "ticker_year_match": 18,
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
    "LILLY ELI AND CO": "ELI LILLY",
    "LILLY ELI CO": "ELI LILLY",
    "ELI LILLY AND COMPANY": "ELI LILLY",
    "ELI LILLY COMPANY": "ELI LILLY",
    "ELI LILLY & COMPANY": "ELI LILLY",
    "WAL MART STORES": "WAL MART",
    "WALMART STORES": "WAL MART",
    "WALMART": "WAL MART",
    "EXXONMOBIL": "EXXON MOBIL",
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


APPROVED_ABBREVIATION_ALIASES = {
    "3M": {"search_names": ["3M", "MINNESOTA MINING AND MANUFACTURING"], "confidence": "high"},
    "ABB": {"search_names": ["ABB", "ASEA BROWN BOVERI"], "confidence": "high"},
    "AMD": {"search_names": ["AMD", "ADVANCED MICRO DEVICES"], "confidence": "high"},
    "ARM": {"search_names": ["ARM", "ARM HOLDINGS"], "confidence": "medium"},
    "ASML": {"search_names": ["ASML", "ASML HOLDING"], "confidence": "high"},
    "AT&T": {"search_names": ["AT&T", "ATT", "AMERICAN TELEPHONE AND TELEGRAPH"], "confidence": "high"},
    "BAE": {"search_names": ["BAE", "BAE SYSTEMS"], "confidence": "high"},
    "BASF": {"search_names": ["BASF"], "confidence": "high"},
    "BMW": {"search_names": ["BMW", "BAYERISCHE MOTOREN WERKE"], "confidence": "high"},
    "BP": {"search_names": ["BP"], "confidence": "high"},
    "BT": {"search_names": ["BT", "BT GROUP"], "confidence": "medium"},
    "CBS": {"search_names": ["CBS"], "confidence": "medium"},
    "CVS": {"search_names": ["CVS", "CVS HEALTH"], "confidence": "high"},
    "DHL": {"search_names": ["DHL", "DHL GROUP"], "confidence": "medium"},
    "DXC": {"search_names": ["DXC", "DXC TECHNOLOGY"], "confidence": "high"},
    "EMC": {"search_names": ["EMC", "EMC CORPORATION"], "confidence": "high"},
    "ESPN": {"search_names": ["ESPN"], "confidence": "medium"},
    "EY": {"search_names": ["EY", "ERNST AND YOUNG", "ERNST YOUNG"], "confidence": "medium"},
    "F5": {"search_names": ["F5"], "confidence": "medium"},
    "GE": {"search_names": ["GE", "GENERAL ELECTRIC"], "confidence": "high"},
    "GM": {"search_names": ["GM", "GENERAL MOTORS"], "confidence": "high"},
    "H&M": {"search_names": ["H&M", "HENNES AND MAURITZ", "HENNES MAURITZ"], "confidence": "medium"},
    "HP": {"search_names": ["HP", "HP INC", "HEWLETT PACKARD"], "confidence": "high"},
    "HPE": {"search_names": ["HPE", "HEWLETT PACKARD ENTERPRISE"], "confidence": "high"},
    "HSBC": {"search_names": ["HSBC", "HSBC HOLDINGS"], "confidence": "high"},
    "IBM": {"search_names": ["IBM", "INTERNATIONAL BUSINESS MACHINES", "INTL BUSINESS MACHINES"], "confidence": "high"},
    "ING": {"search_names": ["ING", "ING GROUP"], "confidence": "high"},
    "KFC": {"search_names": ["KFC", "KENTUCKY FRIED CHICKEN"], "confidence": "medium"},
    "KKR": {"search_names": ["KKR", "KKR AND CO"], "confidence": "high"},
    "LG": {"search_names": ["LG", "LG ELECTRONICS"], "confidence": "high"},
    "LVMH": {"search_names": ["LVMH", "MOET HENNESSY LOUIS VUITTON"], "confidence": "high"},
    "MGM": {"search_names": ["MGM"], "confidence": "medium"},
    "NCR": {"search_names": ["NCR", "NCR CORPORATION"], "confidence": "high"},
    "NXP": {"search_names": ["NXP", "NXP SEMICONDUCTORS"], "confidence": "high"},
    "P&G": {"search_names": ["P&G", "PROCTER AND GAMBLE", "PROCTER GAMBLE"], "confidence": "high"},
    "PG&E": {"search_names": ["PG&E", "PACIFIC GAS AND ELECTRIC"], "confidence": "high"},
    "PWC": {"search_names": ["PWC", "PRICEWATERHOUSECOOPERS", "PRICE WATERHOUSE COOPERS"], "confidence": "medium"},
    "RBS": {"search_names": ["RBS", "ROYAL BANK OF SCOTLAND"], "confidence": "medium"},
    "SAP": {"search_names": ["SAP"], "confidence": "high"},
    "SAS": {"search_names": ["SAS", "SAS INSTITUTE"], "confidence": "low"},
    "SK": {"search_names": ["SK", "SK GROUP"], "confidence": "low"},
    "TDK": {"search_names": ["TDK", "TDK CORPORATION"], "confidence": "high"},
    "TNT": {"search_names": ["TNT", "TNT EXPRESS"], "confidence": "medium"},
    "TSMC": {"search_names": ["TSMC", "TAIWAN SEMICONDUCTOR MANUFACTURING"], "confidence": "high"},
    "UBS": {"search_names": ["UBS", "UBS GROUP"], "confidence": "high"},
    "UPS": {"search_names": ["UPS", "UNITED PARCEL SERVICE"], "confidence": "high"},
    "USPS": {"search_names": ["USPS", "UNITED STATES POSTAL SERVICE"], "confidence": "low"},
    "VMWARE": {"search_names": ["VMWARE"], "confidence": "high"},
    "YKK": {"search_names": ["YKK", "YKK CORPORATION"], "confidence": "medium"},
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
    "candidate_lookup_stage",
    "candidate_valid_fyears",
    "candidate_year_min",
    "candidate_year_max",
    "candidate_years_available",
    "residual_years_requested",
    "candidate_year_distance_min",
    "candidate_in_residual_year",
    "candidate_tic",
    "candidate_ticker_match_type",
    "approved_abbreviation_alias",
    "approved_abbreviation_search_name",
    "approved_abbreviation_confidence",
    "candidate_matching_priority",
    "candidate_alias_type",
    "candidate_extension_type",
    "candidate_in_identifier_year_panel",
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
    for col in ["conm", "id_name", "name_original", "name_std"]:
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


def resolve_project_file(path):
    path = Path(path)
    if path.exists():
        return path
    root_fallback = Path(path.name)
    if root_fallback.exists():
        return root_fallback
    raise FileNotFoundError(f"Missing required Step 8.5 input file: {path}")


def first_column(df, candidates, required=True):
    lower_lookup = {str(col).lower(): col for col in df.columns}
    for candidate in candidates:
        if candidate in df.columns:
            return candidate
        lower = candidate.lower()
        if lower in lower_lookup:
            return lower_lookup[lower]
    if required:
        raise ValueError(f"Missing required column. Tried: {candidates}. Available: {df.columns.tolist()}")
    return None


def normalize_year_value(value):
    cleaned = clean_identifier_value(value)
    if cleaned == "":
        return None
    numeric = pd.to_numeric(cleaned, errors="coerce")
    if pd.isna(numeric):
        return None
    return int(numeric)


def parse_years(value):
    if pd.isna(value):
        return []
    years = []
    for match in re.findall(r"\b(?:19|20)\d{2}\b", str(value)):
        year = int(match)
        if year not in years:
            years.append(year)
    return years


def standardize_bridge_frame(df, stage):
    name_col = first_column(df, ["name_std", "alias_std", "alias_name_std", "company_name_std"])
    gvkey_col = first_column(df, ["gvkey", "GVKEY"], required=False)
    cik_col = first_column(df, ["cik", "CIK"], required=False)
    source_col = first_column(df, ["source", "alias_source", "match_source"], required=False)
    tic_col = first_column(df, ["tic", "ticker", "TIC", "TICKER"], required=False)
    priority_col = first_column(df, ["matching_priority", "source_priority"], required=False)
    alias_type_col = first_column(df, ["alias_type"], required=False)
    extension_type_col = first_column(df, ["extension_type"], required=False)

    df = df.dropna(subset=[name_col]).copy()
    df["candidate_bridge_name"] = df[name_col].apply(standardize_name_for_mapping)
    df["candidate_bridge_original_name"] = df.apply(best_company_name_from_bridge_row, axis=1)
    df["candidate_conm"] = df.apply(
        lambda row: clean_conm_value(row.get("conm"), fallback=best_company_name_from_bridge_row(row)),
        axis=1,
    )
    df["candidate_cik"] = df[cik_col].apply(output_identifier_value) if cik_col else -1
    df["candidate_gvkey"] = df[gvkey_col].apply(output_identifier_value) if gvkey_col else -1
    df["candidate_tic"] = df[tic_col].apply(clean_name_value) if tic_col else ""
    df["ticker_key"] = df["candidate_tic"].apply(standardize_name_for_mapping)
    if source_col:
        df["candidate_source"] = df[source_col].apply(clean_name_value)
    else:
        df["candidate_source"] = "WRDS_LOOKUP" if stage == "identifier_level_validated_fallback" else "UNKNOWN"
    df["candidate_lookup_stage"] = stage
    mapped_priority = df["candidate_source"].str.upper().map(SOURCE_PRIORITY).fillna(9)
    if priority_col:
        df["candidate_matching_priority"] = pd.to_numeric(df[priority_col], errors="coerce").fillna(mapped_priority)
    else:
        df["candidate_matching_priority"] = mapped_priority
    df["source_priority"] = df["candidate_matching_priority"]
    df["candidate_alias_type"] = df[alias_type_col].apply(clean_name_value) if alias_type_col else ""
    df["candidate_extension_type"] = df[extension_type_col].apply(clean_name_value) if extension_type_col else ""
    df["candidate_in_identifier_year_panel"] = False
    df["exact_key"] = df["candidate_bridge_name"]
    df["legal_key"] = df["candidate_bridge_name"].apply(legal_form_normalized_key)
    df["suffix_key"] = df["candidate_bridge_name"].apply(strip_suffixes)
    return df


def prepare_year_specific_bridge():
    bridge_file = resolve_project_file(YEAR_SPECIFIC_BRIDGE_FILE)
    bridge = pd.read_csv(bridge_file, low_memory=False)
    year_col = first_column(bridge, ["fyear", "fiscal_year", "year"])
    bridge = standardize_bridge_frame(bridge, "year_specific_primary")
    bridge["fyear"] = pd.read_csv(bridge_file, usecols=[year_col], low_memory=False)[year_col].apply(normalize_year_value)
    bridge = bridge.dropna(subset=["candidate_bridge_name", "fyear"]).copy()
    bridge["fyear"] = bridge["fyear"].astype(int)
    identity_cols = [
        "candidate_bridge_name", "candidate_bridge_original_name", "candidate_conm",
        "candidate_cik", "candidate_gvkey", "candidate_source", "candidate_lookup_stage",
        "source_priority", "candidate_matching_priority", "candidate_alias_type",
        "candidate_extension_type", "candidate_in_identifier_year_panel", "candidate_tic", "ticker_key",
        "exact_key", "legal_key", "suffix_key", "fyear",
    ]
    bridge = bridge[identity_cols].drop_duplicates()
    return bridge


def prepare_identifier_level_bridge():
    bridge_file = resolve_project_file(IDENTIFIER_LEVEL_BRIDGE_FILE)
    bridge = pd.read_csv(bridge_file, low_memory=False)
    bridge = standardize_bridge_frame(bridge, "identifier_level_validated_fallback")
    bridge["candidate_source"] = bridge["candidate_source"].replace("", "WRDS_LOOKUP")
    identity_cols = [
        "candidate_bridge_name", "candidate_bridge_original_name", "candidate_conm",
        "candidate_cik", "candidate_gvkey", "candidate_source", "candidate_lookup_stage",
        "source_priority", "candidate_matching_priority", "candidate_alias_type",
        "candidate_extension_type", "candidate_in_identifier_year_panel", "candidate_tic", "ticker_key",
        "exact_key", "legal_key", "suffix_key",
    ]
    bridge = bridge[identity_cols].drop_duplicates()
    return bridge


def prepare_identifier_year_panel():
    panel_file = resolve_project_file(IDENTIFIER_YEAR_PANEL_FILE)
    panel = pd.read_csv(panel_file, low_memory=False)
    year_col = first_column(panel, ["fyear", "fiscal_year", "year"])
    gvkey_col = first_column(panel, ["gvkey", "GVKEY"], required=False)
    cik_col = first_column(panel, ["cik", "CIK"], required=False)
    panel["fyear_clean"] = panel[year_col].apply(normalize_year_value)
    panel = panel.dropna(subset=["fyear_clean"]).copy()
    panel["fyear_clean"] = panel["fyear_clean"].astype(int)
    gvkey_years = set()
    cik_years = set()
    if gvkey_col:
        gvkey_years = set(
            zip(panel[gvkey_col].apply(clean_identifier_value), panel["fyear_clean"])
        )
        gvkey_years = {(gvkey, year) for gvkey, year in gvkey_years if gvkey}
    if cik_col:
        cik_years = set(
            zip(panel[cik_col].apply(clean_identifier_value), panel["fyear_clean"])
        )
        cik_years = {(cik, year) for cik, year in cik_years if cik}
    return {"gvkey_years": gvkey_years, "cik_years": cik_years}


def bridge_row_to_candidate(row, rule):
    return {
        "candidate_bridge_name": row["candidate_bridge_name"],
        "candidate_bridge_original_name": row["candidate_bridge_original_name"],
        "candidate_conm": row["candidate_conm"],
        "candidate_cik": row["candidate_cik"],
        "candidate_gvkey": row["candidate_gvkey"],
        "candidate_source": row["candidate_source"],
        "candidate_lookup_stage": row.get("candidate_lookup_stage", ""),
        "candidate_valid_fyears": row.get("candidate_valid_fyears", ""),
        "candidate_year_min": row.get("candidate_year_min", ""),
        "candidate_year_max": row.get("candidate_year_max", ""),
        "candidate_years_available": row.get("candidate_years_available", ""),
        "residual_years_requested": row.get("residual_years_requested", ""),
        "candidate_year_distance_min": row.get("candidate_year_distance_min", ""),
        "candidate_in_residual_year": row.get("candidate_in_residual_year", ""),
        "candidate_tic": row.get("candidate_tic", ""),
        "candidate_ticker_match_type": row.get("candidate_ticker_match_type", ""),
        "approved_abbreviation_alias": row.get("approved_abbreviation_alias", ""),
        "approved_abbreviation_search_name": row.get("approved_abbreviation_search_name", ""),
        "approved_abbreviation_confidence": row.get("approved_abbreviation_confidence", ""),
        "candidate_matching_priority": row.get("candidate_matching_priority", row.get("source_priority", 9)),
        "candidate_alias_type": row.get("candidate_alias_type", ""),
        "candidate_extension_type": row.get("candidate_extension_type", ""),
        "candidate_in_identifier_year_panel": row.get("candidate_in_identifier_year_panel", False),
        "candidate_match_rule": rule,
        "source_priority": row.get("source_priority", 9),
    }


def add_candidates_from_key(candidates, lookup, key_value, rule):
    if not key_value:
        return
    matches = lookup.get(key_value, [])
    for row in matches:
        candidates.append(bridge_row_to_candidate(row, rule))


def format_years(years):
    return ";".join(map(str, sorted({int(y) for y in years if pd.notna(y)})))


def min_year_distance(candidate_years, residual_years):
    candidate_years = sorted({int(y) for y in candidate_years if pd.notna(y)})
    residual_years = sorted({int(y) for y in residual_years if pd.notna(y)})
    if not candidate_years or not residual_years:
        return ""
    return min(abs(candidate_year - residual_year) for candidate_year in candidate_years for residual_year in residual_years)


def apply_year_audit_fields(candidate, candidate_years, residual_years, in_residual_year):
    candidate_years = sorted({int(y) for y in candidate_years if pd.notna(y)})
    residual_years = sorted({int(y) for y in residual_years if pd.notna(y)})
    candidate["candidate_year_min"] = min(candidate_years) if candidate_years else ""
    candidate["candidate_year_max"] = max(candidate_years) if candidate_years else ""
    candidate["candidate_years_available"] = format_years(candidate_years)
    candidate["residual_years_requested"] = format_years(residual_years)
    candidate["candidate_year_distance_min"] = 0 if in_residual_year else min_year_distance(candidate_years, residual_years)
    candidate["candidate_in_residual_year"] = bool(in_residual_year)
    return candidate


def add_year_specific_candidates_from_key(candidates, lookup, key_value, years, rule):
    if not key_value or not years:
        return
    grouped = {}
    for year in years:
        matches = lookup.get((key_value, year), [])
        for row in matches:
            row_identity = (
                row.get("candidate_bridge_name"),
                row.get("candidate_cik"),
                row.get("candidate_gvkey"),
                row.get("candidate_source"),
                row.get("candidate_lookup_stage"),
                row.get("candidate_matching_priority"),
                rule,
            )
            if row_identity not in grouped:
                grouped[row_identity] = {"row": row, "years": set()}
            grouped[row_identity]["years"].add(year)
    for item in grouped.values():
        candidate = bridge_row_to_candidate(item["row"], rule)
        candidate["candidate_valid_fyears"] = format_years(item["years"])
        candidates.append(apply_year_audit_fields(candidate, item["years"], years, True))


def add_other_year_candidates_from_key(candidates, lookup, key_value, residual_years, rule):
    if not key_value or not residual_years:
        return
    residual_years = set(residual_years)
    for row in lookup.get(key_value, []):
        available_years = set(row.get("_available_years", set()))
        if not available_years or available_years.intersection(residual_years):
            continue
        candidate = bridge_row_to_candidate(row, rule)
        candidate["candidate_valid_fyears"] = ""
        candidates.append(apply_year_audit_fields(candidate, available_years, residual_years, False))


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


def add_year_specific_parent_prefix_candidates(candidates, parent_prefix_lookup, alias_std, years):
    if not years:
        return
    seen_rows = set()
    for token in extract_parent_prefixes(alias_std, max_tokens=3):
        if not token:
            continue
        for year in years:
            matches = parent_prefix_lookup.get((token, year), [])
            for row in matches:
                if not global_parent_recovery_is_safe(row, token):
                    continue
                rule = f"parent_prefix_recovery:{token}"
                row_identity = (
                    row.get("candidate_bridge_name"),
                    row.get("candidate_cik"),
                    row.get("candidate_gvkey"),
                    row.get("candidate_source"),
                    row.get("candidate_lookup_stage"),
                    rule,
                )
                if row_identity in seen_rows:
                    continue
                candidate = bridge_row_to_candidate(row, rule)
                candidate["candidate_valid_fyears"] = str(year)
                candidates.append(candidate)
                seen_rows.add(row_identity)


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
        if current is None or (candidate["_rule_order"], candidate.get("source_priority", 9)) < (
            current["_rule_order"],
            current.get("source_priority", 9),
        ):
            output[identity] = candidate

    deduped = list(output.values())
    deduped.sort(
        key=lambda c: (
            c["_rule_order"],
            c.get("source_priority", 9),
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


def build_year_lookup(bridge, key_col):
    lookup = {}
    for _, row in bridge.iterrows():
        key = row.get(key_col, "")
        year = row.get("fyear")
        if not key or pd.isna(year):
            continue
        lookup.setdefault((key, int(year)), []).append(row)
    return lookup


def build_parent_prefix_lookup(bridge):
    lookup = {}
    for _, row in bridge.iterrows():
        name = row.get("candidate_bridge_name", "")
        for token in extract_parent_prefixes(name, max_tokens=3):
            if token and token != name:
                lookup.setdefault(token, []).append(row)
    return lookup


def build_year_parent_prefix_lookup(bridge):
    lookup = {}
    for _, row in bridge.iterrows():
        name = row.get("candidate_bridge_name", "")
        year = row.get("fyear")
        if pd.isna(year):
            continue
        for token in extract_parent_prefixes(name, max_tokens=3):
            if token and token != name:
                lookup.setdefault((token, int(year)), []).append(row)
    return lookup




def approved_abbreviation_entry(alias_name):
    alias_std = standardize_name_for_mapping(alias_name)
    alias_compact = alias_std.replace(" ", "")
    for raw_alias, entry in APPROVED_ABBREVIATION_ALIASES.items():
        raw_std = standardize_name_for_mapping(raw_alias)
        if alias_std == raw_std or alias_compact == raw_std.replace(" ", ""):
            return raw_alias, entry
    return "", None


def approved_abbreviation_search_keys(alias_name):
    raw_alias, entry = approved_abbreviation_entry(alias_name)
    if not entry:
        return []
    keys = []
    for search_name in entry.get("search_names", []):
        key = standardize_name_for_mapping(search_name)
        if key and key not in keys:
            keys.append(key)
        legal_key = legal_form_normalized_key(search_name)
        if legal_key and legal_key not in keys:
            keys.append(legal_key)
    return keys


def apply_abbreviation_audit(candidate, raw_alias, search_name, confidence, match_type):
    candidate["candidate_ticker_match_type"] = match_type
    candidate["approved_abbreviation_alias"] = raw_alias
    candidate["approved_abbreviation_search_name"] = search_name
    candidate["approved_abbreviation_confidence"] = confidence
    return candidate


def add_ticker_year_candidates(candidates, lookup, alias_std, years):
    if not alias_std or not years:
        return
    ticker_candidates = []
    add_year_specific_candidates_from_key(ticker_candidates, lookup, alias_std, years, "ticker_year_match")
    for candidate in ticker_candidates:
        candidate["candidate_ticker_match_type"] = "exact_tic_year"
        candidates.append(candidate)


def add_approved_abbreviation_candidates(candidates, lookups, alias_name, years):
    raw_alias, entry = approved_abbreviation_entry(alias_name)
    if not entry or not years:
        return
    confidence = entry.get("confidence", "")
    seen = set()
    for search_name in entry.get("search_names", []):
        search_std = standardize_name_for_mapping(search_name)
        legal_key = legal_form_normalized_key(search_name)
        candidate_batch = []
        add_year_specific_candidates_from_key(candidate_batch, lookups["exact"], search_std, years, "approved_abbreviation_bridge_match")
        add_year_specific_candidates_from_key(candidate_batch, lookups["legal"], legal_key, years, "approved_abbreviation_bridge_match")
        add_year_specific_candidates_from_key(candidate_batch, lookups["ticker"], search_std, years, "approved_abbreviation_bridge_match")
        for candidate in candidate_batch:
            identity = candidate_identity(candidate) + (candidate.get("candidate_match_rule"), search_name)
            if identity in seen:
                continue
            seen.add(identity)
            candidates.append(apply_abbreviation_audit(candidate, raw_alias, search_name, confidence, "approved_abbreviation_year"))

def bridge_identity_for_year_aggregation(row, key):
    return (
        key,
        row.get("candidate_bridge_name"),
        row.get("candidate_bridge_original_name"),
        row.get("candidate_conm"),
        row.get("candidate_cik"),
        row.get("candidate_gvkey"),
        row.get("candidate_source"),
        row.get("candidate_lookup_stage"),
        row.get("candidate_matching_priority"),
        row.get("candidate_alias_type"),
        row.get("candidate_extension_type"),
        row.get("candidate_tic"),
    )


def build_other_year_lookup(bridge, key_col):
    grouped = {}
    for _, row in bridge.iterrows():
        key = row.get(key_col, "")
        year = row.get("fyear")
        if not key or pd.isna(year):
            continue
        rowd = row.to_dict()
        identity = bridge_identity_for_year_aggregation(rowd, key)
        if identity not in grouped:
            grouped[identity] = {"row": rowd, "years": set()}
        grouped[identity]["years"].add(int(year))

    lookup = {}
    for identity, item in grouped.items():
        rowd = dict(item["row"])
        years = sorted(item["years"])
        rowd["_available_years"] = set(years)
        rowd["candidate_year_min"] = min(years)
        rowd["candidate_year_max"] = max(years)
        rowd["candidate_years_available"] = format_years(years)
        key = identity[0]
        lookup.setdefault(key, []).append(rowd)
    return lookup


def build_identifier_bridge_lookups(bridge):
    return {
        "exact": build_lookup(bridge, "exact_key"),
        "legal": build_lookup(bridge, "legal_key"),
        "suffix": build_lookup(bridge, "suffix_key"),
    }


def build_year_specific_bridge_lookups(bridge):
    return {
        "exact": build_year_lookup(bridge, "exact_key"),
        "legal": build_year_lookup(bridge, "legal_key"),
        "suffix": build_year_lookup(bridge, "suffix_key"),
        "ticker": build_year_lookup(bridge, "ticker_key"),
        "other_exact": build_other_year_lookup(bridge, "exact_key"),
        "other_legal": build_other_year_lookup(bridge, "legal_key"),
        "other_suffix": build_other_year_lookup(bridge, "suffix_key"),
    }


def candidate_valid_years(candidate, years, validation_panel):
    valid_years = []
    gvkey = clean_identifier_value(candidate.get("candidate_gvkey"))
    cik = clean_identifier_value(candidate.get("candidate_cik"))
    for year in years:
        if gvkey and (gvkey, year) in validation_panel["gvkey_years"]:
            valid_years.append(year)
            continue
        if cik and (cik, year) in validation_panel["cik_years"]:
            valid_years.append(year)
    return sorted(set(valid_years))


def annotate_identifier_year_panel_presence(candidates, years, validation_panel):
    annotated = []
    for candidate in candidates:
        candidate = dict(candidate)
        valid_years = candidate_valid_years(candidate, years, validation_panel)
        if valid_years:
            candidate["candidate_in_identifier_year_panel"] = True
            candidate["candidate_valid_fyears"] = ";".join(map(str, valid_years))
        else:
            candidate["candidate_in_identifier_year_panel"] = False
        annotated.append(candidate)
    return annotated


def validate_identifier_level_candidates(candidates, years, validation_panel):
    if not years:
        return []
    validated = []
    for candidate in candidates:
        valid_years = candidate_valid_years(candidate, years, validation_panel)
        if not valid_years:
            continue
        candidate = dict(candidate)
        candidate["candidate_valid_fyears"] = format_years(valid_years)
        candidate["candidate_lookup_stage"] = "identifier_level_validated_fallback"
        candidate["candidate_in_identifier_year_panel"] = True
        candidate = apply_year_audit_fields(candidate, valid_years, years, True)
        candidate["source_priority"] = candidate.get("source_priority", SOURCE_PRIORITY.get(str(candidate.get("candidate_source", "")).upper(), 9))
        validated.append(candidate)
    return validated


def find_candidates(alias_name, lookups, years, validation_panel):
    alias_std = standardize_name_for_mapping(alias_name)
    legal_key = legal_form_normalized_key(alias_name)
    suffix_key = strip_suffixes(alias_std)

    exact_year_candidates = []
    add_year_specific_candidates_from_key(
        exact_year_candidates,
        lookups["year_specific"]["exact"],
        alias_std,
        years,
        "exact_standardized_match",
    )
    exact_year_candidates = dedupe_candidates(exact_year_candidates)
    if exact_year_candidates:
        return annotate_identifier_year_panel_presence(exact_year_candidates, years, validation_panel)

    relaxed_year_candidates = []
    add_year_specific_candidates_from_key(
        relaxed_year_candidates,
        lookups["year_specific"]["legal"],
        legal_key,
        years,
        "legal_form_normalization",
    )
    add_year_specific_candidates_from_key(
        relaxed_year_candidates,
        lookups["year_specific"]["suffix"],
        suffix_key,
        years,
        "suffix_stripped_match",
    )
    relaxed_year_candidates = dedupe_candidates(relaxed_year_candidates)
    if relaxed_year_candidates:
        return annotate_identifier_year_panel_presence(relaxed_year_candidates, years, validation_panel)

    exact_other_year_candidates = []
    add_other_year_candidates_from_key(
        exact_other_year_candidates,
        lookups["year_specific"]["other_exact"],
        alias_std,
        years,
        "exact_other_year",
    )
    exact_other_year_candidates = dedupe_candidates(exact_other_year_candidates)
    if exact_other_year_candidates:
        return annotate_identifier_year_panel_presence(exact_other_year_candidates, years, validation_panel)

    legal_other_year_candidates = []
    add_other_year_candidates_from_key(
        legal_other_year_candidates,
        lookups["year_specific"]["other_legal"],
        legal_key,
        years,
        "legal_other_year",
    )
    add_other_year_candidates_from_key(
        legal_other_year_candidates,
        lookups["year_specific"]["other_suffix"],
        suffix_key,
        years,
        "legal_other_year",
    )
    legal_other_year_candidates = dedupe_candidates(legal_other_year_candidates)
    if legal_other_year_candidates:
        return annotate_identifier_year_panel_presence(legal_other_year_candidates, years, validation_panel)

    abbreviation_ticker_candidates = []
    add_approved_abbreviation_candidates(abbreviation_ticker_candidates, lookups["year_specific"], alias_name, years)
    add_ticker_year_candidates(abbreviation_ticker_candidates, lookups["year_specific"]["ticker"], alias_std, years)
    abbreviation_ticker_candidates = dedupe_candidates(abbreviation_ticker_candidates)
    if abbreviation_ticker_candidates:
        return annotate_identifier_year_panel_presence(abbreviation_ticker_candidates, years, validation_panel)

    identifier_candidates = []
    add_candidates_from_key(identifier_candidates, lookups["identifier_level"]["exact"], alias_std, "exact_standardized_match")
    add_candidates_from_key(identifier_candidates, lookups["identifier_level"]["legal"], legal_key, "legal_form_normalization")
    add_candidates_from_key(identifier_candidates, lookups["identifier_level"]["suffix"], suffix_key, "suffix_stripped_match")
    identifier_candidates = dedupe_candidates(identifier_candidates)
    identifier_candidates = validate_identifier_level_candidates(identifier_candidates, years, validation_panel)
    return dedupe_candidates(identifier_candidates)


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

    priority = pd.to_numeric(row.get("candidate_matching_priority", row.get("source_priority", 9)), errors="coerce")
    priority = 9 if pd.isna(priority) else float(priority)
    score += SOURCE_SCORE.get(source, 0)
    score += max(0, 60 - (priority * 10))
    has_cik = is_valid_identifier(row.get("candidate_cik"))
    has_gvkey = is_valid_identifier(row.get("candidate_gvkey"))
    if has_cik:
        score += 20
    if has_gvkey:
        score += 10
    if has_cik and has_gvkey:
        score += 10
    if bool(row.get("candidate_in_identifier_year_panel")):
        score += 5
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

    review["_rule_sort"] = review["candidate_match_rule"].apply(lambda value: {"exact_standardized_match": 1, "legal_form_normalization": 2, "suffix_stripped_match": 2, "exact_other_year": 3, "legal_other_year": 4, "approved_abbreviation_bridge_match": 5, "ticker_year_match": 6, "parent_prefix_recovery": 7}.get(match_rule_base(value), 9))
    review["_priority_sort"] = pd.to_numeric(review.get("candidate_matching_priority"), errors="coerce").fillna(9)
    review["_id_count_sort"] = review.apply(lambda row: int(is_valid_identifier(row.get("candidate_cik"))) + int(is_valid_identifier(row.get("candidate_gvkey"))), axis=1)
    review["_panel_sort"] = review["candidate_in_identifier_year_panel"].astype(bool).astype(int)
    sort_cols = [
        "record_id",
        "_rule_sort",
        "_priority_sort",
        "_id_count_sort",
        "_panel_sort",
        "candidate_rank_score",
        "candidate_source",
        "candidate_bridge_name",
    ]
    ranked = review[matched_mask].sort_values(
        by=sort_cols,
        ascending=[True, True, True, False, False, False, True, True],
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
        exact_or_legal = rule_base in {"exact_standardized_match", "legal_form_normalization", "exact_other_year", "legal_other_year"}
        strong_parent_prefix = rule_base == "parent_prefix_recovery" and parent_prefix_is_strong(top)
        eligible_rule = exact_or_legal or strong_parent_prefix

        if has_identifier and margin_ok and eligible_rule:
            review.loc[top.name, "recommended_candidate"] = True

    review = review.drop(columns=["_rule_sort", "_priority_sort", "_id_count_sort", "_panel_sort"], errors="ignore")
    return review


def build_candidate_review(aliases, lookups, validation_panel):
    rows = []
    for _, alias_row in aliases.iterrows():
        alias_name = clean_name_value(alias_row.get("suggested_alias_name"))
        base = base_alias_fields(alias_row)
        years = parse_years(alias_row.get("years"))
        candidates = find_candidates(alias_name, lookups, years, validation_panel) if alias_name else []
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
                "candidate_lookup_stage": "",
                "candidate_valid_fyears": "",
                "candidate_year_min": "",
                "candidate_year_max": "",
                "candidate_years_available": "",
                "residual_years_requested": format_years(years),
                "candidate_year_distance_min": "",
                "candidate_in_residual_year": False,
                "candidate_tic": "",
                "candidate_ticker_match_type": "",
                "approved_abbreviation_alias": "",
                "approved_abbreviation_search_name": "",
                "approved_abbreviation_confidence": "",
                "candidate_matching_priority": "",
                "candidate_alias_type": "",
                "candidate_extension_type": "",
                "candidate_in_identifier_year_panel": False,
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

    per_alias_stage = (
        review.groupby("record_id", dropna=False)
        .agg(
            n_candidates=("n_candidates", "max"),
            frequency=("frequency", "first"),
            has_exact_year=("candidate_match_rule", lambda x: any(x == "exact_standardized_match")),
            has_relaxed_year=("candidate_match_rule", lambda x: any(x.isin(["legal_form_normalization", "suffix_stripped_match"]))),
            has_identifier_fallback=("candidate_lookup_stage", lambda x: any(x == "identifier_level_validated_fallback")),
        )
        .reset_index()
    )
    exact_year_aliases = int(((per_alias_stage["n_candidates"] > 0) & per_alias_stage["has_exact_year"] & ~per_alias_stage["has_identifier_fallback"]).sum())
    relaxed_year_aliases = int(((per_alias_stage["n_candidates"] > 0) & ~per_alias_stage["has_exact_year"] & per_alias_stage["has_relaxed_year"] & ~per_alias_stage["has_identifier_fallback"]).sum())
    fallback_aliases = int(((per_alias_stage["n_candidates"] > 0) & per_alias_stage["has_identifier_fallback"]).sum())
    no_candidate_aliases = int((per_alias_stage["n_candidates"] == 0).sum())

    print("Step 8.5 alias candidate generation completed")
    print(f"Residual aliases processed: {len(aliases)}")
    print(f"Aliases with exact year-specific candidates: {exact_year_aliases}")
    print(f"Aliases with relaxed/legal-suffix year-specific candidates: {relaxed_year_aliases}")
    print(f"Aliases with identifier-level fallback candidates: {fallback_aliases}")
    print(f"Aliases with no candidates: {no_candidate_aliases}")
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
    matched = review[review["candidate_match_rule"] != "no_candidate"].copy()
    print("Candidate counts by source:")
    print(matched["candidate_source"].fillna("(missing)").replace("", "(missing)").value_counts(dropna=False).to_string() if not matched.empty else "(none)")
    print("Candidate counts by matching_priority:")
    priority_counts = pd.to_numeric(matched["candidate_matching_priority"], errors="coerce").fillna(999).astype(int).value_counts().sort_index() if not matched.empty else pd.Series(dtype=int)
    print(priority_counts.to_string() if not priority_counts.empty else "(none)")
    print("Candidate counts by extension_type:")
    print(matched["candidate_extension_type"].fillna("(missing)").replace("", "(missing)").value_counts(dropna=False).to_string() if not matched.empty else "(none)")
    print("Top no-candidate aliases by frequency:")
    no_candidate = review[review["candidate_match_rule"] == "no_candidate"].copy()
    if no_candidate.empty:
        print("(none)")
    else:
        no_candidate["_freq"] = pd.to_numeric(no_candidate["frequency"], errors="coerce").fillna(0)
        print(no_candidate.sort_values("_freq", ascending=False)[["suggested_alias_name", "frequency", "years"]].head(20).to_string(index=False))
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


def validation_panel_years(validation_panel):
    years = {year for _, year in validation_panel["gvkey_years"]}
    years.update({year for _, year in validation_panel["cik_years"]})
    return sorted(years)


def print_target_alias_candidate_checks(lookups, validation_panel):
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
    diagnostic_years = validation_panel_years(validation_panel)
    for alias in target_aliases:
        candidates = find_candidates(alias, lookups, diagnostic_years, validation_panel)
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




def candidate_status_frame(review):
    if review is None or review.empty:
        return pd.DataFrame(columns=["record_id", "status", "suggested_alias_name", "normalized_alias", "frequency", "years"])
    df = review.copy()
    if "suggested_alias_name" in df.columns:
        df["normalized_alias"] = df["suggested_alias_name"].apply(standardize_name_for_mapping)
    else:
        df["normalized_alias"] = ""
    if "candidate_rank" in df.columns:
        df["_rank"] = pd.to_numeric(df["candidate_rank"], errors="coerce").fillna(999999)
    else:
        df["_rank"] = 999999
    df["_is_match"] = df["candidate_match_rule"].ne("no_candidate")
    df["_recommended"] = df.get("recommended_candidate", False).astype(str).str.lower().eq("true")
    df["_sort_match"] = (~df["_is_match"]).astype(int)
    df["_sort_recommended"] = (~df["_recommended"]).astype(int)
    ordered = df.sort_values(["record_id", "_sort_match", "_sort_recommended", "_rank"])
    first = ordered.groupby("record_id", dropna=False).head(1).copy()
    first["status"] = first["candidate_match_rule"].where(first["_is_match"], "no_candidate")
    return first


def matched_candidate_rows(review):
    if review is None or review.empty:
        return pd.DataFrame()
    return review[review["candidate_match_rule"].ne("no_candidate")].copy()


def value_count_comparison(rev6, rev7, col, out_col):
    a = matched_candidate_rows(rev6)
    b = matched_candidate_rows(rev7)
    left = a[col].fillna("(missing)").replace("", "(missing)").value_counts(dropna=False).rename("rev6_candidates") if not a.empty else pd.Series(dtype=int, name="rev6_candidates")
    right = b[col].fillna("(missing)").replace("", "(missing)").value_counts(dropna=False).rename("rev7_candidates") if not b.empty else pd.Series(dtype=int, name="rev7_candidates")
    comp = pd.concat([left, right], axis=1).fillna(0).astype(int).reset_index().rename(columns={"index": out_col})
    if out_col not in comp.columns:
        comp = comp.rename(columns={comp.columns[0]: out_col})
    comp["difference"] = comp["rev7_candidates"] - comp["rev6_candidates"]
    return comp.sort_values(["rev7_candidates", "difference"], ascending=False)


def rule_count_comparison(rev6, rev7):
    a = matched_candidate_rows(rev6)
    b = matched_candidate_rows(rev7)
    left = a["candidate_match_rule"].fillna("(missing)").replace("", "(missing)").value_counts(dropna=False).rename("rev6_candidates") if not a.empty else pd.Series(dtype=int, name="rev6_candidates")
    right = b["candidate_match_rule"].fillna("(missing)").replace("", "(missing)").value_counts(dropna=False).rename("rev7_candidates") if not b.empty else pd.Series(dtype=int, name="rev7_candidates")
    comp = pd.concat([left, right], axis=1).fillna(0).astype(int).reset_index().rename(columns={"index": "match_rule"})
    if "match_rule" not in comp.columns:
        comp = comp.rename(columns={comp.columns[0]: "match_rule"})
    comp["difference"] = comp["rev7_candidates"] - comp["rev6_candidates"]
    return comp.sort_values(["rev7_candidates", "difference"], ascending=False)


def aliases_by_layer(review):
    per_alias = candidate_status_frame(review)
    return {
        "residual_aliases_processed": int(per_alias["record_id"].nunique()),
        "exact_year_specific_candidates": int(per_alias["status"].eq("exact_standardized_match").sum()),
        "legal_year_specific_candidates": int(per_alias["status"].isin(["legal_form_normalization", "suffix_stripped_match"]).sum()),
        "exact_other_year_candidates": int(per_alias["status"].eq("exact_other_year").sum()),
        "legal_other_year_candidates": int(per_alias["status"].eq("legal_other_year").sum()),
        "identifier_level_fallback_candidates": int(per_alias["status"].ne("no_candidate").sum() if "candidate_lookup_stage" not in per_alias.columns else per_alias["candidate_lookup_stage"].eq("identifier_level_validated_fallback").sum()),
        "no_candidate_count": int(per_alias["status"].eq("no_candidate").sum()),
    }


def create_comparison_outputs(rev6_review, rev7_review):
    if rev6_review is None or rev6_review.empty:
        return None

    rev6_status = candidate_status_frame(rev6_review)
    rev7_status = candidate_status_frame(rev7_review)
    rev6_counts = aliases_by_layer(rev6_review)
    rev7_counts = aliases_by_layer(rev7_review)
    summary_rows = []
    for key in sorted(set(rev6_counts) | set(rev7_counts)):
        summary_rows.append({
            "metric": key,
            "rev6": rev6_counts.get(key, 0),
            "rev7": rev7_counts.get(key, 0),
            "difference": rev7_counts.get(key, 0) - rev6_counts.get(key, 0),
        })
    summary_rows.append({
        "metric": "change_in_no_candidate_count_from_rev6_to_rev7",
        "rev6": rev6_counts.get("no_candidate_count", 0),
        "rev7": rev7_counts.get("no_candidate_count", 0),
        "difference": rev7_counts.get("no_candidate_count", 0) - rev6_counts.get("no_candidate_count", 0),
    })
    summary = pd.DataFrame(summary_rows)

    source_comp = value_count_comparison(rev6_review, rev7_review, "candidate_source", "candidate_source")
    rule_comp = rule_count_comparison(rev6_review, rev7_review)

    recovered_ids = set(rev6_status.loc[rev6_status["status"].eq("no_candidate"), "record_id"]).intersection(
        set(rev7_status.loc[rev7_status["status"].ne("no_candidate"), "record_id"])
    )
    recovered = rev7_review[rev7_review["record_id"].isin(recovered_ids) & rev7_review["candidate_match_rule"].ne("no_candidate")].copy()
    if not recovered.empty:
        recovered["_freq"] = pd.to_numeric(recovered["frequency"], errors="coerce").fillna(0)
        recovered["_rank"] = pd.to_numeric(recovered["candidate_rank"], errors="coerce").fillna(999999)
        recovered_top100 = recovered.sort_values(["_freq", "recommended_candidate", "_rank"], ascending=[False, False, True]).drop_duplicates("record_id").head(100)
        recovered_top100 = recovered_top100.drop(columns=["_freq", "_rank"], errors="ignore")
        recovered_breakdown = (
            recovered.groupby(["candidate_source", "candidate_matching_priority", "candidate_extension_type", "candidate_match_rule"], dropna=False)
            .agg(aliases=("record_id", "nunique"), total_frequency=("frequency", lambda x: pd.to_numeric(x, errors="coerce").fillna(0).sum()))
            .reset_index()
            .sort_values(["aliases", "total_frequency"], ascending=False)
        )
    else:
        recovered_top100 = pd.DataFrame(columns=rev7_review.columns)
        recovered_breakdown = pd.DataFrame(columns=["candidate_source", "candidate_matching_priority", "candidate_extension_type", "candidate_match_rule", "aliases", "total_frequency"])

    validation_examples = build_validation_example_comparison(rev6_review, rev7_review)

    safe_to_csv(summary, COMPARISON_SUMMARY_FILE, index=False)
    safe_to_csv(source_comp, COMPARISON_SOURCE_FILE, index=False)
    safe_to_csv(rule_comp, COMPARISON_MATCH_RULE_FILE, index=False)
    safe_to_csv(recovered_top100, COMPARISON_RECOVERED_TOP100_FILE, index=False)
    safe_to_csv(recovered_breakdown, COMPARISON_RECOVERED_BREAKDOWN_FILE, index=False)
    safe_to_csv(validation_examples, COMPARISON_VALIDATION_FILE, index=False)
    return {
        "summary": summary,
        "source_comp": source_comp,
        "rule_comp": rule_comp,
        "recovered_count": len(recovered_ids),
        "recovered_breakdown": recovered_breakdown,
        "validation_examples": validation_examples,
    }


def select_validation_row(review, alias):
    if review is None or review.empty:
        return None
    target_norm = standardize_name_for_mapping(alias)
    df = review.copy()
    df["_alias_norm"] = df["suggested_alias_name"].apply(standardize_name_for_mapping)
    subset = df[(df["_alias_norm"].eq(target_norm)) | (df["suggested_alias_name"].astype(str).str.upper().eq(alias.upper()))].copy()
    if subset.empty:
        return None
    subset["_freq"] = pd.to_numeric(subset["frequency"], errors="coerce").fillna(0)
    subset["_rank"] = pd.to_numeric(subset["candidate_rank"], errors="coerce").fillna(999999)
    subset["_is_match"] = subset["candidate_match_rule"].ne("no_candidate")
    subset["_recommended"] = subset["recommended_candidate"].astype(str).str.lower().eq("true")
    subset = subset.sort_values(["_freq", "_is_match", "_recommended", "_rank"], ascending=[False, False, False, True])
    return subset.iloc[0]


def row_status(row):
    if row is None:
        return "not_in_residual_input"
    if str(row.get("candidate_match_rule", "")) == "no_candidate":
        return "no_candidate"
    return "candidate_found"


def build_validation_example_comparison(rev6_review, rev7_review):
    examples = [
        "Amazon", "Philips", "IBM", "ExxonMobil", "Exxon Mobil", "Bloomberg",
        "Eli Lilly", "Gemalto", "Home Shopping Network", "Avanir", "Regeneron",
    ]
    rows = []
    for alias in examples:
        rev6_row = select_validation_row(rev6_review, alias)
        rev7_row = select_validation_row(rev7_review, alias)
        row = rev7_row if rev7_row is not None else rev6_row
        rows.append({
            "residual_alias": alias,
            "normalized_alias": standardize_name_for_mapping(alias),
            "residual_fiscal_years": "" if row is None else row.get("years", ""),
            "rev6_status": row_status(rev6_row),
            "rev7_status": row_status(rev7_row),
            "candidate_name": "" if rev7_row is None else rev7_row.get("candidate_bridge_name", ""),
            "candidate_gvkey": "" if rev7_row is None else rev7_row.get("candidate_gvkey", ""),
            "candidate_cik": "" if rev7_row is None else rev7_row.get("candidate_cik", ""),
            "candidate_source": "" if rev7_row is None else rev7_row.get("candidate_source", ""),
            "candidate_matching_priority": "" if rev7_row is None else rev7_row.get("candidate_matching_priority", ""),
            "match_rule": "" if rev7_row is None else rev7_row.get("candidate_match_rule", ""),
            "candidate_year_min": "" if rev7_row is None else rev7_row.get("candidate_year_min", ""),
            "candidate_year_max": "" if rev7_row is None else rev7_row.get("candidate_year_max", ""),
        })
    return pd.DataFrame(rows)




GENERIC_NAME_TOKENS = {
    "HOLDING", "HOLDINGS", "HLDG", "HLDGS", "GROUP", "GRP", "COMPANY", "CO",
    "CORP", "CORPORATION", "INC", "LTD", "PLC", "SA", "NV", "AG", "LP", "LLC",
    "FUND", "TRUST", "INVESTMENT", "INVESTMENTS", "CAPITAL", "INDUSTRIES", "IND",
    "TECHNOLOGIES", "TECH", "INTERNATIONAL", "INTL", "GLOBAL", "SYSTEMS", "SYS",
}
COMP_SUPPORT_SOURCES = {"COMPUSTAT_US", "COMPUSTAT_GLOBAL", "CCM_COMPUSTAT_EXTENSION", "NON_DISCERN_US_COMPUSTAT"}
DISCERN_SUPPORT_SOURCES = {"DISCERN"}
SEC_SUPPORT_SOURCES = {"SEC_HEADER", "SEC_FILING_HEADER"}
STRONG_BRIDGE_SOURCES = COMP_SUPPORT_SOURCES | DISCERN_SUPPORT_SOURCES
SCENARIOS = [
    "conservative_rev7_current",
    "auto_accept_same_year_only",
    "auto_accept_same_year_plus_unique_exact_other_year",
    "auto_accept_same_year_plus_unique_exact_and_legal_other_year",
    "broad_recall_with_manual_flags",
]


def valid_gvkey(value):
    return is_valid_identifier(value)


def distinct_valid_values(series):
    values = set()
    for value in series:
        cleaned = clean_identifier_value(value)
        if cleaned:
            values.add(cleaned)
    return values


def candidate_match_family(row):
    rule = str(row.get("candidate_match_rule", ""))
    lookup_stage = str(row.get("candidate_lookup_stage", ""))
    in_year = str(row.get("candidate_in_residual_year", "")).lower() == "true" or row.get("candidate_in_residual_year") is True
    base = match_rule_base(rule)
    if rule == "no_candidate":
        return "no_candidate"
    if lookup_stage == "identifier_level_validated_fallback":
        return "identifier_fallback"
    if base == "exact_other_year":
        return "exact_other_year"
    if base == "legal_other_year":
        return "legal_other_year"
    if base == "approved_abbreviation_bridge_match":
        return "approved_abbreviation"
    if base == "ticker_year_match":
        return "ticker_year"
    if base == "exact_standardized_match" and in_year:
        return "exact_year_specific"
    if base in {"legal_form_normalization", "suffix_stripped_match"} and in_year:
        return "legal_year_specific"
    return base


def candidate_is_generic_name(value):
    name = standardize_name_for_mapping(value)
    tokens = name_tokens(name)
    if not name:
        return True
    if re.fullmatch(r"\d+(?:\s+\d+)*", name):
        return True
    if len(name.replace(" ", "")) <= 2:
        return True
    if tokens and all(token in GENERIC_NAME_TOKENS for token in tokens):
        return True
    if len(tokens) >= 2:
        generic_count = sum(token in GENERIC_NAME_TOKENS for token in tokens)
        if generic_count / len(tokens) >= 0.8:
            return True
    return False


def top_candidate_per_record(review):
    df = review.copy()
    df["_is_match"] = df["candidate_match_rule"].ne("no_candidate")
    df["_recommended"] = df["recommended_candidate"].astype(str).str.lower().eq("true")
    df["_rank"] = pd.to_numeric(df["candidate_rank"], errors="coerce").fillna(999999)
    df["_freq"] = pd.to_numeric(df["frequency"], errors="coerce").fillna(0)
    return df.sort_values(
        ["record_id", "_is_match", "_recommended", "_rank", "candidate_rank_score"],
        ascending=[True, False, False, True, False],
    ).groupby("record_id", dropna=False).head(1).copy()


def add_reliability_diagnostics(review):
    review = review.copy()
    matched_mask = review["candidate_match_rule"].ne("no_candidate")
    review["match_family"] = review.apply(candidate_match_family, axis=1)
    review["candidate_source_clean"] = review["candidate_source"].fillna("").astype(str).str.upper()
    review["candidate_gvkey_clean"] = review["candidate_gvkey"].apply(clean_identifier_value)
    review["candidate_name_length"] = review["candidate_bridge_name"].fillna("").astype(str).str.len()
    review["candidate_token_count"] = review["candidate_bridge_name"].apply(lambda value: len(name_tokens(value)))
    review["candidate_is_generic_name"] = review["candidate_bridge_name"].apply(candidate_is_generic_name)

    record_year_counts = []
    record_all_counts = []
    record_legal_counts = []
    source_support = []
    for record_id, group in review.groupby("record_id", dropna=False):
        matched = group[group["candidate_match_rule"].ne("no_candidate")].copy()
        in_year = matched[matched["candidate_in_residual_year"].astype(str).str.lower().eq("true")]
        legal = matched[matched["match_family"].isin(["legal_year_specific", "legal_other_year"])]
        record_year_counts.append((record_id, len(distinct_valid_values(in_year["candidate_gvkey"]))))
        record_all_counts.append((record_id, len(distinct_valid_values(matched["candidate_gvkey"]))))
        record_legal_counts.append((record_id, len(distinct_valid_values(legal["candidate_gvkey"]))))

        for gvkey, gv_group in matched.groupby("candidate_gvkey_clean", dropna=False):
            sources = sorted({src for src in gv_group["candidate_source_clean"] if src})
            source_support.append({
                "record_id": record_id,
                "candidate_gvkey_clean": gvkey,
                "candidate_supported_by_sources_count": len(sources),
                "candidate_sources_all": ";".join(sources),
                "candidate_has_compustat_support": any(src in COMP_SUPPORT_SOURCES for src in sources),
                "candidate_has_discern_support": any(src in DISCERN_SUPPORT_SOURCES for src in sources),
                "candidate_has_sec_support": any(src in SEC_SUPPORT_SOURCES for src in sources),
                "candidate_is_sec_only": bool(sources) and all(src in SEC_SUPPORT_SOURCES for src in sources),
            })

    year_df = pd.DataFrame(record_year_counts, columns=["record_id", "n_distinct_gvkeys_alias_year"])
    all_df = pd.DataFrame(record_all_counts, columns=["record_id", "n_distinct_gvkeys_alias_all_years"])
    legal_df = pd.DataFrame(record_legal_counts, columns=["record_id", "n_distinct_gvkeys_legal_all_years"])
    support_df = pd.DataFrame(source_support)
    review = review.merge(year_df, on="record_id", how="left").merge(all_df, on="record_id", how="left").merge(legal_df, on="record_id", how="left")
    if not support_df.empty:
        review = review.merge(support_df, on=["record_id", "candidate_gvkey_clean"], how="left")
    for col in ["candidate_supported_by_sources_count", "n_distinct_gvkeys_alias_year", "n_distinct_gvkeys_alias_all_years", "n_distinct_gvkeys_legal_all_years"]:
        review[col] = pd.to_numeric(review.get(col), errors="coerce").fillna(0).astype(int)
    for col in ["candidate_has_compustat_support", "candidate_has_discern_support", "candidate_has_sec_support", "candidate_is_sec_only"]:
        review[col] = review.get(col, False).fillna(False).astype(bool)
    review["candidate_sources_all"] = review.get("candidate_sources_all", "").fillna("")
    return review


def assign_acceptance_tier(row):
    if row.get("candidate_match_rule") == "no_candidate":
        return "no_candidate"
    family = row.get("match_family", "")
    priority = pd.to_numeric(row.get("candidate_matching_priority"), errors="coerce")
    priority = 999 if pd.isna(priority) else priority
    source = str(row.get("candidate_source", "")).upper()
    has_panel = bool(row.get("candidate_in_identifier_year_panel"))
    distance = pd.to_numeric(row.get("candidate_year_distance_min"), errors="coerce")
    distance = 999999 if pd.isna(distance) else distance
    n_year = int(row.get("n_distinct_gvkeys_alias_year", 0))
    n_all = int(row.get("n_distinct_gvkeys_alias_all_years", 0))
    n_legal = int(row.get("n_distinct_gvkeys_legal_all_years", 0))

    if family == "exact_year_specific":
        if n_year == 1 and has_panel:
            return "Tier A auto_accept"
        return "Tier A manual_review"
    if family == "legal_year_specific":
        if n_year == 1 and priority <= 3 and not bool(row.get("candidate_is_sec_only")):
            return "Tier B auto_accept"
        return "Tier B manual_review"
    if family == "exact_other_year":
        if n_all == 1 and (distance <= 3 or source in STRONG_BRIDGE_SOURCES):
            return "Tier C auto_accept"
        return "Tier C manual_review"
    if family == "legal_other_year":
        if n_legal == 1 and not bool(row.get("candidate_is_sec_only")) and not bool(row.get("candidate_is_generic_name")):
            return "Tier D auto_accept"
        return "Tier D manual_review"
    if family in {"approved_abbreviation", "ticker_year"}:
        confidence = str(row.get("approved_abbreviation_confidence", "")).lower()
        strong_source = source in STRONG_BRIDGE_SOURCES
        if n_year == 1 and has_panel and strong_source and confidence == "high":
            return "Tier TIC auto_accept"
        return "Tier TIC manual_review"
    if family == "identifier_fallback":
        if n_all == 1 and has_panel:
            return "Tier E auto_accept"
        return "Tier E manual_review"
    return "manual_review"


def scenario_status(row, scenario):
    if row.get("candidate_match_rule") == "no_candidate":
        return "no_candidate"
    tier = row.get("acceptance_tier", "")
    family = row.get("match_family", "")
    current_recommended = str(row.get("recommended_candidate", "")).lower() == "true"
    if scenario == "conservative_rev7_current":
        return "auto_accept" if current_recommended else "manual_review"
    if scenario == "auto_accept_same_year_only":
        return "auto_accept" if tier.startswith("Tier A auto") or tier.startswith("Tier B auto") else "manual_review"
    if scenario == "auto_accept_same_year_plus_unique_exact_other_year":
        return "auto_accept" if tier.startswith(("Tier A auto", "Tier B auto", "Tier C auto")) else "manual_review"
    if scenario == "auto_accept_same_year_plus_unique_exact_and_legal_other_year":
        return "auto_accept" if tier.startswith(("Tier A auto", "Tier B auto", "Tier C auto", "Tier D auto")) else "manual_review"
    if scenario == "broad_recall_with_manual_flags":
        return "auto_accept" if tier.startswith(("Tier A auto", "Tier B auto", "Tier C auto", "Tier D auto", "Tier TIC auto", "Tier E auto")) else "manual_review"
    return "manual_review"


def load_rev6_no_candidate_ids(previous_review=None):
    if REV6_NO_CANDIDATE_AUDIT_FILE.exists():
        baseline = pd.read_csv(REV6_NO_CANDIDATE_AUDIT_FILE, usecols=["record_id"], low_memory=False)
        return set(baseline["record_id"].dropna().astype(str))
    prev_status = candidate_status_frame(previous_review) if previous_review is not None else pd.DataFrame(columns=["record_id", "status"])
    return set(prev_status.loc[prev_status["status"].eq("no_candidate"), "record_id"].dropna().astype(str))


def build_scenario_outputs(review, previous_review):
    existing_audit_cols = {"match_family", "acceptance_tier", "n_distinct_gvkeys_alias_year"}
    if existing_audit_cols.issubset(set(review.columns)):
        audit = review.copy()
    else:
        audit = add_reliability_diagnostics(review)
        audit["acceptance_tier"] = audit.apply(assign_acceptance_tier, axis=1)
    top = top_candidate_per_record(audit)

    rev6_no_candidate_ids = load_rev6_no_candidate_ids(previous_review)

    summary_rows = []
    auto_rule_rows = []
    auto_source_rows = []
    for scenario in SCENARIOS:
        scenario_df = top.copy()
        scenario_df["scenario"] = scenario
        scenario_df["scenario_status"] = scenario_df.apply(lambda row: scenario_status(row, scenario), axis=1)
        recovered = scenario_df[scenario_df["record_id"].isin(rev6_no_candidate_ids) & scenario_df["scenario_status"].ne("no_candidate")]
        summary_rows.append({
            "scenario": scenario,
            "total_residual_aliases": len(scenario_df),
            "auto_accept_count": int(scenario_df["scenario_status"].eq("auto_accept").sum()),
            "manual_review_count": int(scenario_df["scenario_status"].eq("manual_review").sum()),
            "no_candidate_count": int(scenario_df["scenario_status"].eq("no_candidate").sum()),
            "recovered_from_rev6_no_candidate": int(recovered["record_id"].nunique()),
        })
        auto = scenario_df[scenario_df["scenario_status"].eq("auto_accept")]
        if not auto.empty:
            by_rule = auto["candidate_match_rule"].value_counts(dropna=False).reset_index()
            by_rule.columns = ["match_rule", "auto_accept_count"]
            by_rule["scenario"] = scenario
            auto_rule_rows.append(by_rule)
            by_source = auto["candidate_source"].fillna("(missing)").replace("", "(missing)").value_counts(dropna=False).reset_index()
            by_source.columns = ["candidate_source", "auto_accept_count"]
            by_source["scenario"] = scenario
            auto_source_rows.append(by_source)
        manual_top = scenario_df[scenario_df["scenario_status"].eq("manual_review")].sort_values("_freq", ascending=False).head(100)
        no_top = scenario_df[scenario_df["scenario_status"].eq("no_candidate")].sort_values("_freq", ascending=False).head(100)
        safe_to_csv(manual_top, FINAL_DIR / f"candidate_acceptance_tier_{scenario}_manual_review_top100.csv", index=False)
        safe_to_csv(no_top, FINAL_DIR / f"candidate_acceptance_tier_{scenario}_no_candidate_top100.csv", index=False)

    summary = pd.DataFrame(summary_rows)
    auto_rule = pd.concat(auto_rule_rows, ignore_index=True) if auto_rule_rows else pd.DataFrame(columns=["match_rule", "auto_accept_count", "scenario"])
    auto_source = pd.concat(auto_source_rows, ignore_index=True) if auto_source_rows else pd.DataFrame(columns=["candidate_source", "auto_accept_count", "scenario"])
    validation = build_tier_validation_examples(top)

    safe_to_csv(audit, TIER_AUDIT_FILE, index=False)
    safe_to_csv(summary, TIER_SCENARIO_SUMMARY_FILE, index=False)
    safe_to_csv(auto_rule, TIER_AUTO_BY_RULE_FILE, index=False)
    safe_to_csv(auto_source, TIER_AUTO_BY_SOURCE_FILE, index=False)
    safe_to_csv(validation, TIER_VALIDATION_FILE, index=False)
    return {"summary": summary, "auto_rule": auto_rule, "auto_source": auto_source, "validation": validation}


def build_tier_validation_examples(top):
    examples = [
        "Amazon", "Philips", "IBM", "ExxonMobil", "Exxon Mobil", "Bloomberg",
        "Eli Lilly", "Gemalto", "Home Shopping Network", "Avanir", "Regeneron",
    ]
    rows = []
    df = top.copy()
    df["_alias_norm"] = df["suggested_alias_name"].apply(standardize_name_for_mapping)
    for alias in examples:
        norm = standardize_name_for_mapping(alias)
        subset = df[(df["_alias_norm"].eq(norm)) | (df["suggested_alias_name"].astype(str).str.upper().eq(alias.upper()))].copy()
        if subset.empty:
            rows.append({"residual_alias": alias, "normalized_alias": norm, "status": "not_in_residual_input"})
            continue
        subset = subset.sort_values("_freq", ascending=False)
        row = subset.iloc[0]
        out = {
            "residual_alias": alias,
            "normalized_alias": norm,
            "residual_fiscal_years": row.get("years", ""),
            "candidate_name": row.get("candidate_bridge_name", ""),
            "candidate_gvkey": row.get("candidate_gvkey", ""),
            "candidate_cik": row.get("candidate_cik", ""),
            "candidate_source": row.get("candidate_source", ""),
            "candidate_tic": row.get("candidate_tic", ""),
            "candidate_ticker_match_type": row.get("candidate_ticker_match_type", ""),
            "approved_abbreviation_alias": row.get("approved_abbreviation_alias", ""),
            "approved_abbreviation_confidence": row.get("approved_abbreviation_confidence", ""),
            "candidate_matching_priority": row.get("candidate_matching_priority", ""),
            "match_rule": row.get("candidate_match_rule", ""),
            "match_family": row.get("match_family", ""),
            "acceptance_tier": row.get("acceptance_tier", ""),
            "candidate_year_min": row.get("candidate_year_min", ""),
            "candidate_year_max": row.get("candidate_year_max", ""),
            "n_distinct_gvkeys_alias_year": row.get("n_distinct_gvkeys_alias_year", ""),
            "n_distinct_gvkeys_alias_all_years": row.get("n_distinct_gvkeys_alias_all_years", ""),
            "n_distinct_gvkeys_legal_all_years": row.get("n_distinct_gvkeys_legal_all_years", ""),
            "candidate_sources_all": row.get("candidate_sources_all", ""),
            "candidate_is_generic_name": row.get("candidate_is_generic_name", ""),
        }
        for scenario in SCENARIOS:
            out[scenario] = scenario_status(row, scenario)
        rows.append(out)
    return pd.DataFrame(rows)


def main():
    FINAL_DIR.mkdir(parents=True, exist_ok=True)
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing Step 7 classified input: {INPUT_FILE}")

    config = load_config()
    previous_review = pd.read_csv(OUTPUT_FILE, low_memory=False) if OUTPUT_FILE.exists() else None
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

    year_specific_bridge = prepare_year_specific_bridge()
    identifier_level_bridge = prepare_identifier_level_bridge()
    validation_panel = prepare_identifier_year_panel()
    lookups = {
        "year_specific": build_year_specific_bridge_lookups(year_specific_bridge),
        "identifier_level": build_identifier_bridge_lookups(identifier_level_bridge),
    }
    print("Bridge architecture inputs")
    print(f"Year-specific bridge rows: {len(year_specific_bridge)}")
    print(f"Identifier-level WRDS bridge rows: {len(identifier_level_bridge)}")
    print(f"Validation panel GVKEY-years: {len(validation_panel['gvkey_years'])}")
    print(f"Validation panel CIK-years: {len(validation_panel['cik_years'])}")
    print_normalization_diagnostics(normalization_diagnostics)
    print_target_alias_candidate_checks(lookups, validation_panel)
    review = build_candidate_review(aliases, lookups, validation_panel)
    summary = build_summary(review)
    top100 = review.drop_duplicates(subset=["suggested_alias_name"], keep="first").head(100)
    comparison = create_comparison_outputs(previous_review, review)
    tier_outputs = build_scenario_outputs(review, previous_review)

    output_path = safe_to_csv(review, OUTPUT_FILE, index=False)
    all_output_path = safe_to_csv(review, ALL_OUTPUT_FILE, index=False)
    summary_path = safe_to_csv(summary, SUMMARY_FILE, index=False)
    top100_path = safe_to_csv(top100, TOP100_FILE, index=False)

    report_counts(review, aliases)
    if comparison:
        print("Rev6 vs rev7 comparison")
        print(comparison["summary"].to_string(index=False))
        print(f"Aliases recovered from rev6 no_candidate: {comparison['recovered_count']}")
    if tier_outputs:
        print("Acceptance tier scenario summary")
        print(tier_outputs["summary"].to_string(index=False))
    print(f"Main output: {output_path}")
    print(f"All residual output: {all_output_path}")
    print(f"Summary output: {summary_path}")
    print(f"Top 100 output: {top100_path}")


if __name__ == "__main__":
    main()
