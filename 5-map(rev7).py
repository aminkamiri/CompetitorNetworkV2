# 5-Map-Competitor-Names.py

import yaml
from pathlib import Path
import pandas as pd
import re

from utils import get_uniform_format_company_name


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


STANDARDIZATION_NORMALIZATION_COUNTERS = {
    "total_standardization_calls": 0,
    "legal_form_spacing_normalized_names": 0,
    "descriptor_harmonized_names": 0,
}


def normalize_legal_form_spacing(x):
    original = x

    for spaced, collapsed in LEGAL_FORM_SPACING_PATTERNS:
        pattern = r"\b" + r"\s+".join(spaced.split()) + r"\b"
        x = re.sub(pattern, collapsed, x)

    return x, x != original


def fix_encoding_artifacts(x):
    if pd.isna(x):
        return ""

    x = str(x)

    replacements = {
        "‚Äôs": "'s",
        "‚Äô": "'",
        "‚Äú": '"',
        "‚Äù": '"',
        "‚Äì": "-",
        "¬Æ": "",
        "™": "",
        "®": "",
        "TM": "",
        "√â": "E",
        "√ñ": "O",
        "√Ö": "A",
        "√ò": "O",
        "√Ü": "A",
    }

    for old, new in replacements.items():
        x = x.replace(old, new)

    return x.strip()


def recover_parent_or_owner_name(x):
    x = fix_encoding_artifacts(x)

    m = re.search(r"\(\s*owned by\s+([^()]+)\s*\)\s*$", x, flags=re.I)
    if m:
        return m.group(1).strip(" .;,)")

    m = re.search(r"^(.+?)['’]s\s+.+$", x)
    if m:
        parent = m.group(1).strip(" .;,")
        if len(parent) > 2:
            return parent

    m = re.search(
        r"(?:,\s*)?(?:a\s+)?(?:division|unit|subsidiary|business|brand)\s+of\s+(.+)$",
        x,
        flags=re.I
    )
    if m:
        parent = m.group(1).strip(" .;,)")
        parent = re.split(r",|\(|;", parent)[0].strip()

        if len(parent) > 2:
            return parent

    return x


def standardize_name_for_mapping(x, allow_parent_recovery=True):
    if pd.isna(x):
        return ""

    STANDARDIZATION_NORMALIZATION_COUNTERS["total_standardization_calls"] += 1

    x = fix_encoding_artifacts(x)

    if allow_parent_recovery:
        x = recover_parent_or_owner_name(x)

    x = get_uniform_format_company_name(x)

    x, legal_form_spacing_changed = normalize_legal_form_spacing(x)

    x = x.replace("-OLD", "")
    x = x.replace("-NEW", "")
    x = x.replace("-PRO FORMA", "")
    x = x.replace("PRO FORMA", "")

    x = re.sub(r"\bCL [A-Z]\b", "", x)
    x = re.sub(r"\bTHE\b", "", x)

    parts = x.split()
    mapped_parts = [STANDARDIZATION_MAP.get(p, p) for p in parts]
    descriptor_harmonized = any(original != mapped for original, mapped in zip(parts, mapped_parts))

    if legal_form_spacing_changed:
        STANDARDIZATION_NORMALIZATION_COUNTERS["legal_form_spacing_normalized_names"] += 1

    if descriptor_harmonized:
        STANDARDIZATION_NORMALIZATION_COUNTERS["descriptor_harmonized_names"] += 1

    x = " ".join(mapped_parts)
    x = re.sub(r"\s+", " ", x).strip()

    return x


def remove_suffixes_one_word_if_safe(name):
    parts = str(name).split()

    while len(parts) > 1 and parts[-1] in REMOVABLE_SUFFIXES:
        parts = parts[:-1]

    cleaned = " ".join(parts).strip()

    if cleaned == name:
        return None

    if len(cleaned) < 4:
        return None

    if cleaned.replace(",", "").isdigit():
        return None

    if len(str(name).split()) > 1 and len(cleaned.split()) == 1:
        return None

    return cleaned


def starts_with_capital(s):
    s = str(s).strip()

    if not s:
        return False

    if s[0].isupper():
        return True

    if re.match(r"^\d+[A-Za-z]", s):
        return True

    return False


def clean_identifier_value(x):
    if pd.isna(x):
        return None

    x = str(x).strip()

    if x == "" or x.lower() in {"nan", "none"}:
        return None

    x = re.sub(r"\.0$", "", x)

    return x


def output_identifier_value(x):
    cleaned = clean_identifier_value(x)
    return cleaned if cleaned is not None else -1


def identity_identifier_value(x):
    cleaned = clean_identifier_value(x)
    return cleaned if cleaned is not None else -1


RECOVERY_DIAGNOSTIC_KEYS = [
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
]


def empty_recovery_diagnostics():
    return {key: "" for key in RECOVERY_DIAGNOSTIC_KEYS}


def join_recovery_candidate_values(values):
    cleaned_values = [
        str(v).strip()
        for v in values
        if str(v).strip() and str(v).strip().lower() not in {"nan", "none"}
    ]
    return ";".join(sorted(set(cleaned_values)))


SAFE_GLOBAL_PARENT_CONTINUATION_TERMS = (
    set(STANDARDIZATION_MAP.keys()) |
    set(STANDARDIZATION_MAP.values()) |
    REMOVABLE_SUFFIXES |
    {
        "COMPUTER",
        "COMPUTERS",
        "ELECTRIC",
        "ELECTRICAL",
        "NORDIC",
        "HEAVY",
        "CORP",
        "INC",
        "CO",
        "LTD",
        "PLC",
        "AG",
        "SA",
        "NV",
        "BV",
        "LLC",
        "LP",
        "GMBH",
        "SPA",
        "PTE",
        "PTY",
        "BHD",
        "AB",
        "AS",
        "SAS",
        "SARL",
        "SRL",
    }
)


def get_continuation_terms(parent_name, recovered_prefix):
    parent_parts = str(parent_name).strip().split()
    prefix_parts = str(recovered_prefix).strip().split()

    if not prefix_parts:
        return parent_parts

    if parent_parts[:len(prefix_parts)] == prefix_parts:
        return parent_parts[len(prefix_parts):]

    return parent_parts


def get_unsafe_global_parent_continuation_terms(parent_name, recovered_prefix):
    continuation_terms = get_continuation_terms(parent_name, recovered_prefix)
    unsafe_terms = [
        term for term in continuation_terms
        if term not in SAFE_GLOBAL_PARENT_CONTINUATION_TERMS
    ]

    return continuation_terms, unsafe_terms


def clean_bridge_name_value(x, fallback=""):
    if pd.isna(x):
        return fallback

    x = str(x).strip()

    if x == "" or x.lower() in {"nan", "none"}:
        return fallback

    return x


def add_candidate(candidates, raw_candidate, method, allow_parent_recovery=True):
    name_std = standardize_name_for_mapping(
        raw_candidate,
        allow_parent_recovery=allow_parent_recovery
    )

    if name_std:
        candidates.append({
            "name": name_std,
            "method": method
        })

    name_clean = remove_suffixes_one_word_if_safe(name_std)

    if name_clean:
        candidates.append({
            "name": name_clean,
            "method": f"{method}_suffix_cleaned"
        })


def bracket_raw_variants(raw_name):
    x = fix_encoding_artifacts(str(raw_name)).strip()

    m = re.match(r"^(.+?)\s*\(([^()]+)\)\s*$", x)

    if not m:
        return []

    outside = m.group(1).strip(" .;,")
    inside = m.group(2).strip(" .;,")

    variants = []

    if outside:
        variants.append((outside, "outside_parentheses"))

    if inside:
        variants.append((inside, "inside_parentheses"))

    return variants


def multiple_raw_variants(raw_name):
    x = fix_encoding_artifacts(str(raw_name)).strip()
    variants = []

    if "/" in x:
        parts = [p.strip(" .;,") for p in re.split(r"\s*/\s*", x) if p.strip(" .;,")]

        if len(parts) >= 2:
            for i, p in enumerate(parts):
                variants.append((p, f"slash_part_{i + 1}"))

    m = re.match(r"^(.+?)\s+and\s+(?:its\s+|their\s+)?affiliates?$", x, flags=re.I)
    if m:
        variants.append((m.group(1).strip(" .;,"), "remove_and_affiliates"))

    m = re.match(r"^(.+?)\s+and\s+(.+?)\s+affiliates?$", x, flags=re.I)
    if m:
        left = m.group(1).strip(" .;,")
        right = m.group(2).strip(" .;,")

        if left.lower() == right.lower():
            variants.append((left, "remove_repeated_and_affiliates"))

    if re.search(r"\s+and\s+", x, flags=re.I) and "affiliate" not in x.lower():
        parts = [p.strip(" .;,") for p in re.split(r"\s+and\s+", x, flags=re.I) if p.strip(" .;,")]

        if len(parts) == 2:
            variants.append((parts[0], "and_part_1"))
            variants.append((parts[1], "and_part_2"))

    return variants


def candidate_name_variants(raw_name):
    candidates = []

    add_candidate(
        candidates,
        raw_name,
        method="full_raw",
        allow_parent_recovery=False
    )

    for raw_variant, method in bracket_raw_variants(raw_name):
        add_candidate(
            candidates,
            raw_variant,
            method=method,
            allow_parent_recovery=False
        )

    add_candidate(
        candidates,
        raw_name,
        method="parent_or_owner_recovery",
        allow_parent_recovery=True
    )

    for raw_variant, method in multiple_raw_variants(raw_name):
        add_candidate(
            candidates,
            raw_variant,
            method=method,
            allow_parent_recovery=False
        )

    seen = set()
    unique_candidates = []

    for c in candidates:
        if c["name"] not in seen:
            unique_candidates.append(c)
            seen.add(c["name"])

    return unique_candidates


def extract_fyear_from_filename(x):
    if pd.isna(x):
        return None

    x = str(x)
    match = re.search(r"_(\d{8})\.txt$", x)

    if match:
        return int(match.group(1)[:4])

    return None


def prepare_bridge(df_bridge, mapped_dir):
    df_bridge = df_bridge.dropna(subset=["name_std", "fyear"]).copy()
    df_bridge["fyear"] = df_bridge["fyear"].astype(int)

    if "name_original" not in df_bridge.columns:
        df_bridge["name_original"] = df_bridge["name_std"]

    df_bridge["name_std"] = df_bridge["name_std"].apply(
        lambda x: standardize_name_for_mapping(x, allow_parent_recovery=True)
    )

    df_bridge["name_std_one_word"] = df_bridge["name_std"].apply(remove_suffixes_one_word_if_safe)

    bridge_aliases = df_bridge.copy()
    bridge_aliases["name_std"] = bridge_aliases["name_std_one_word"]
    bridge_aliases = bridge_aliases.dropna(subset=["name_std"])

    df_bridge = pd.concat([df_bridge, bridge_aliases], ignore_index=True)

    df_bridge["has_cik"] = df_bridge["cik"].apply(clean_identifier_value).notna()
    df_bridge["has_gvkey"] = df_bridge["gvkey"].apply(clean_identifier_value).notna()

    source_priority = {
        "DISCERN": 1,
        "CCM_COMPUSTAT_EXTENSION": 2,
        "COMPUSTAT_GLOBAL": 3,
    }

    df_bridge["source_priority"] = df_bridge["source"].map(source_priority).fillna(9)

    df_bridge = df_bridge.sort_values(
        by=["name_std", "fyear", "source_priority", "has_cik", "has_gvkey"],
        ascending=[True, True, True, False, False],
    )

    dups = df_bridge[df_bridge.duplicated(subset=["name_std", "fyear"], keep=False)].copy()

    if len(dups) > 0:
        dups["identity_pair"] = (
            dups["cik"].apply(output_identifier_value).astype(str)
            + "_"
            + dups["gvkey"].apply(output_identifier_value).astype(str)
        )

        dup_summary = (
            dups.groupby(["name_std", "fyear"], dropna=False)
            .agg(
                n_rows=("name_std", "count"),
                n_sources=("source", "nunique"),
                n_identity_pairs=("identity_pair", "nunique"),
                sources=("source", lambda x: "|".join(sorted(set(map(str, x))))),
                identity_pairs=("identity_pair", lambda x: "|".join(sorted(set(map(str, x))))),
                names_original=("name_original", lambda x: "|".join(sorted(set(map(str, x)))))
            )
            .reset_index()
        )

        dup_summary.to_csv(mapped_dir / "duplicate_name_year_bridge_conflicts_summary.csv", index=False)

    dups.to_csv(mapped_dir / "duplicate_name_year_bridge_rows.csv", index=False)

    df_bridge = df_bridge.drop_duplicates(subset=["name_std", "fyear"], keep="first")

    return df_bridge


def build_yearly_bridge_lookup(df_bridge):
    lookup = {}

    for _, row in df_bridge.iterrows():
        name = str(row["name_std"]).strip()
        fyear = int(row["fyear"])

        key = (name, fyear)

        if key not in lookup:
            bridge_original_name = clean_bridge_name_value(row.get("name_original"), fallback=name)

            lookup[key] = {
                "gvkey": clean_identifier_value(row["gvkey"]),
                "cik": clean_identifier_value(row["cik"]),
                "source": clean_identifier_value(row["source"]),
                "matched_parent_name": name,
                "matched_bridge_name": name,
                "matched_bridge_original_name": bridge_original_name,
            }

    return lookup


def extract_parent_prefixes(name_std, max_tokens=3):
    parts = str(name_std).strip().split()

    prefixes = []

    for n in range(min(max_tokens, len(parts)), 0, -1):
        prefixes.append(" ".join(parts[:n]))

    return prefixes


def build_parent_token_lookup(df_bridge):
    lookup = {}

    for _, row in df_bridge.iterrows():
        name_std = str(row["name_std"]).strip()
        fyear = int(row["fyear"])

        prefixes = extract_parent_prefixes(name_std, max_tokens=3)

        for token in prefixes:
            if not token:
                continue

            key = (token, fyear)

            bridge_original_name = clean_bridge_name_value(row.get("name_original"), fallback=name_std)

            entry = {
                "parent_name": name_std,
                "bridge_original_name": bridge_original_name,
                "gvkey": clean_identifier_value(row["gvkey"]),
                "cik": clean_identifier_value(row["cik"]),
                "source": clean_identifier_value(row["source"]),
            }

            lookup.setdefault(key, [])

            if entry not in lookup[key]:
                lookup[key].append(entry)

    return lookup


def select_candidates_by_source_priority(candidates):
    discern = [
        c for c in candidates
        if str(c["source"]).upper() == "DISCERN"
    ]

    if discern:
        return discern, "DISCERN_PRIORITY"

    ccm = [
        c for c in candidates
        if str(c["source"]).upper() == "CCM_COMPUSTAT_EXTENSION"
    ]

    if ccm:
        return ccm, "CCM_PRIORITY"

    return candidates, "ALL_SOURCES"


def try_parent_token_recovery(name_variant, fyear, parent_token_lookup, global_parent_recovery_blocked_cases=None):
    prefixes = extract_parent_prefixes(name_variant, max_tokens=3)

    for token in prefixes:
        key = (token, int(fyear))
        candidates_all = parent_token_lookup.get(key, [])

        if not candidates_all:
            continue

        candidates_for_identity, priority_rule = select_candidates_by_source_priority(candidates_all)

        identity_pairs_all = set(
            (
                identity_identifier_value(c["cik"]),
                identity_identifier_value(c["gvkey"])
            )
            for c in candidates_all
        )

        identity_pairs = set(
            (
                identity_identifier_value(c["cik"]),
                identity_identifier_value(c["gvkey"])
            )
            for c in candidates_for_identity
        )

        if len(identity_pairs) != 1:
            continue

        candidates_sorted = sorted(
            candidates_for_identity,
            key=lambda c: (
                clean_identifier_value(c["cik"]) is not None,
                clean_identifier_value(c["gvkey"]) is not None,
                len(str(c["parent_name"]))
            ),
            reverse=True
        )

        candidate = candidates_sorted[0]

        continuation_terms = []
        unsafe_continuation_terms = []
        global_parent_recovery_safety_rule = ""

        if priority_rule == "ALL_SOURCES" and str(candidate["source"]).upper() == "COMPUSTAT_GLOBAL":
            continuation_terms, unsafe_continuation_terms = get_unsafe_global_parent_continuation_terms(
                candidate["parent_name"],
                token
            )

            if unsafe_continuation_terms:
                if global_parent_recovery_blocked_cases is not None:
                    global_parent_recovery_blocked_cases.append({
                        "attempted_name_variant": name_variant,
                        "recovered_parent_prefix": token,
                        "matched_bridge_name": candidate["parent_name"],
                        "matched_bridge_original_name": candidate["bridge_original_name"],
                        "continuation_terms": ";".join(continuation_terms),
                        "unsafe_continuation_terms": ";".join(unsafe_continuation_terms),
                        "source": candidate["source"],
                        "fyear": int(fyear),
                        "reason": "unsafe_global_parent_continuation",
                    })

                continue

            global_parent_recovery_safety_rule = "global_parent_recovery_safe_continuation"

        recovery_diagnostics = {
            "recovered_parent_prefix": token,
            "recovered_parent_prefix_n_tokens": len(str(token).split()),
            "recovery_priority_rule": priority_rule,
            "recovery_n_candidates_all": len(candidates_all),
            "recovery_n_candidates_priority": len(candidates_for_identity),
            "recovery_n_unique_identity_pairs_all": len(identity_pairs_all),
            "recovery_n_unique_identity_pairs_priority": len(identity_pairs),
            "recovery_candidate_parent_names_all": join_recovery_candidate_values(c["parent_name"] for c in candidates_all),
            "recovery_candidate_parent_names_priority": join_recovery_candidate_values(c["parent_name"] for c in candidates_for_identity),
            "recovery_candidate_original_names_all": join_recovery_candidate_values(c["bridge_original_name"] for c in candidates_all),
            "recovery_candidate_original_names_priority": join_recovery_candidate_values(c["bridge_original_name"] for c in candidates_for_identity),
            "recovery_candidate_sources_all": join_recovery_candidate_values(c["source"] for c in candidates_all),
            "recovery_candidate_sources_priority": join_recovery_candidate_values(c["source"] for c in candidates_for_identity),
            "recovery_candidate_ciks_all": join_recovery_candidate_values(output_identifier_value(c["cik"]) for c in candidates_all),
            "recovery_candidate_gvkeys_all": join_recovery_candidate_values(output_identifier_value(c["gvkey"]) for c in candidates_all),
            "recovery_candidate_ciks_priority": join_recovery_candidate_values(output_identifier_value(c["cik"]) for c in candidates_for_identity),
            "recovery_candidate_gvkeys_priority": join_recovery_candidate_values(output_identifier_value(c["gvkey"]) for c in candidates_for_identity),
            "global_parent_recovery_continuation_terms": ";".join(continuation_terms),
            "global_parent_recovery_unsafe_continuation_terms": ";".join(unsafe_continuation_terms),
            "global_parent_recovery_safety_rule": global_parent_recovery_safety_rule,
        }

        return {
            "gvkey": candidate["gvkey"],
            "cik": candidate["cik"],
            "source": f"parent_token_recovery_{priority_rule}_{candidate['source']}",
            "matched_standardized_name": candidate["parent_name"],
            "matched_bridge_name": candidate["parent_name"],
            "matched_bridge_original_name": candidate["bridge_original_name"],
            "parent_token": token,
            "recovery_rule": f"parent_prefix_recovery_{priority_rule}",
            "recovery_diagnostics": recovery_diagnostics,
        }

    return None


def append_recovery_diagnostics(recovery_diagnostic_lists, diagnostics=None):
    if diagnostics is None:
        diagnostics = empty_recovery_diagnostics()

    for key in RECOVERY_DIAGNOSTIC_KEYS:
        recovery_diagnostic_lists[key].append(diagnostics.get(key, ""))


def recovery_diagnostic_outputs(recovery_diagnostic_lists):
    return [
        "|".join(map(str, recovery_diagnostic_lists[key]))
        for key in RECOVERY_DIAGNOSTIC_KEYS
    ]


def match_competitor_list_yearly(x, fyear, bridge_lookup, parent_token_lookup, global_parent_recovery_blocked_cases=None):
    if pd.isna(x) or str(x).strip() == "":
        return "", "", "", "", "", "", "", *[""] * len(RECOVERY_DIAGNOSTIC_KEYS)

    if pd.isna(fyear):
        ciks = []
        gvkeys = []
        sources = []
        standardized_names = []
        match_methods = []
        matched_bridge_names = []
        matched_bridge_original_names = []
        recovery_diagnostic_lists = {key: [] for key in RECOVERY_DIAGNOSTIC_KEYS}

        for raw_name in str(x).split("|"):
            raw_name = raw_name.strip()

            if not raw_name:
                continue

            candidates = candidate_name_variants(raw_name)

            ciks.append(-1)
            gvkeys.append(-1)
            sources.append("unmatched")
            standardized_names.append(
                candidates[0]["name"] if candidates else standardize_name_for_mapping(raw_name, allow_parent_recovery=False)
            )
            match_methods.append("unmatched_missing_fyear")
            matched_bridge_names.append("")
            matched_bridge_original_names.append("")
            append_recovery_diagnostics(recovery_diagnostic_lists)

        return (
            "|".join(map(str, standardized_names)),
            "|".join(map(str, ciks)),
            "|".join(map(str, gvkeys)),
            "|".join(map(str, sources)),
            "|".join(map(str, match_methods)),
            "|".join(map(str, matched_bridge_names)),
            "|".join(map(str, matched_bridge_original_names)),
            *recovery_diagnostic_outputs(recovery_diagnostic_lists),
        )

    ciks = []
    gvkeys = []
    sources = []
    standardized_names = []
    match_methods = []
    matched_bridge_names = []
    matched_bridge_original_names = []
    recovery_diagnostic_lists = {key: [] for key in RECOVERY_DIAGNOSTIC_KEYS}

    fyear = int(fyear)

    for raw_name in str(x).split("|"):
        raw_name = raw_name.strip()

        if not raw_name:
            ciks.append(-1)
            gvkeys.append(-1)
            sources.append("unmatched")
            standardized_names.append("")
            match_methods.append("unmatched_empty")
            matched_bridge_names.append("")
            matched_bridge_original_names.append("")
            append_recovery_diagnostics(recovery_diagnostic_lists)
            continue

        candidates = candidate_name_variants(raw_name)

        if not starts_with_capital(raw_name):
            ciks.append(-1)
            gvkeys.append(-1)
            sources.append("unmatched")
            standardized_names.append(
                candidates[0]["name"] if candidates else standardize_name_for_mapping(raw_name, allow_parent_recovery=False)
            )
            match_methods.append("unmatched_invalid_or_lowercase")
            matched_bridge_names.append("")
            matched_bridge_original_names.append("")
            append_recovery_diagnostics(recovery_diagnostic_lists)
            continue

        matched = None
        matched_standardized_name = ""
        matched_method = "unmatched"
        matched_bridge_name = ""
        matched_bridge_original_name = ""
        recovery_diagnostics_for_match = empty_recovery_diagnostics()

        for candidate in candidates:
            name_variant = candidate["name"]
            method = candidate["method"]

            key = (name_variant, fyear)

            if key in bridge_lookup:
                matched = bridge_lookup[key]
                matched_standardized_name = name_variant
                matched_bridge_name = matched["matched_bridge_name"]
                matched_bridge_original_name = matched["matched_bridge_original_name"]
                matched_method = f"exact_{method}"
                break

        if matched is None:
            for candidate in candidates:
                name_variant = candidate["name"]
                method = candidate["method"]

                recovered = try_parent_token_recovery(
                    name_variant,
                    fyear,
                    parent_token_lookup,
                    global_parent_recovery_blocked_cases
                )

                if recovered is not None:
                    matched = {
                        "cik": recovered["cik"],
                        "gvkey": recovered["gvkey"],
                        "source": recovered["source"],
                    }

                    matched_standardized_name = recovered["matched_standardized_name"]
                    matched_bridge_name = recovered["matched_bridge_name"]
                    matched_bridge_original_name = recovered["matched_bridge_original_name"]
                    recovery_diagnostics_for_match = recovered["recovery_diagnostics"]
                    matched_method = f"{recovered['recovery_rule']}_{method}"
                    break

        if matched:
            ciks.append(output_identifier_value(matched["cik"]))
            gvkeys.append(output_identifier_value(matched["gvkey"]))
            sources.append(matched["source"] if matched["source"] is not None else "matched_bridge")
            standardized_names.append(matched_standardized_name)
            match_methods.append(matched_method)
            matched_bridge_names.append(matched_bridge_name)
            matched_bridge_original_names.append(matched_bridge_original_name)
            append_recovery_diagnostics(recovery_diagnostic_lists, recovery_diagnostics_for_match)
        else:
            ciks.append(-1)
            gvkeys.append(-1)
            sources.append("unmatched")
            standardized_names.append(
                candidates[0]["name"] if candidates else standardize_name_for_mapping(raw_name, allow_parent_recovery=False)
            )
            match_methods.append("unmatched_after_all_candidates")
            matched_bridge_names.append("")
            matched_bridge_original_names.append("")
            append_recovery_diagnostics(recovery_diagnostic_lists)

    return (
        "|".join(map(str, standardized_names)),
        "|".join(map(str, ciks)),
        "|".join(map(str, gvkeys)),
        "|".join(map(str, sources)),
        "|".join(map(str, match_methods)),
        "|".join(map(str, matched_bridge_names)),
        "|".join(map(str, matched_bridge_original_names)),
        *recovery_diagnostic_outputs(recovery_diagnostic_lists),
    )

def build_competitor_diagnostics(df, mapped_dir, sic_code):
    all_competitors = set()

    for competitors in df["competitors"]:
        if pd.notna(competitors):
            all_competitors.update(str(competitors).split("|"))

    all_competitors.discard("")

    df_diag = pd.DataFrame({"company_name_in_text": sorted(all_competitors)})

    df_diag["company_name_std"] = df_diag["company_name_in_text"].apply(
        lambda x: standardize_name_for_mapping(x, allow_parent_recovery=False)
    )
    df_diag["company_name_parent_recovered"] = df_diag["company_name_in_text"].apply(
        lambda x: standardize_name_for_mapping(x, allow_parent_recovery=True)
    )
    df_diag["company_name_clean"] = df_diag["company_name_std"].apply(remove_suffixes_one_word_if_safe)
    df_diag["parent_prefixes"] = df_diag["company_name_std"].apply(
        lambda x: "|".join(extract_parent_prefixes(x, max_tokens=3))
    )

    df_diag.to_csv(
        mapped_dir / f"{sic_code}_competitor_name_diagnostics.csv",
        index=False
    )


def build_parent_token_diagnostics(parent_token_lookup, mapped_dir):
    rows = []

    for (token, fyear), candidates_all in parent_token_lookup.items():

        candidates_priority, priority_rule = select_candidates_by_source_priority(candidates_all)

        identity_pairs_all = set(
            (
                identity_identifier_value(c["cik"]),
                identity_identifier_value(c["gvkey"])
            )
            for c in candidates_all
        )

        identity_pairs_priority = set(
            (
                identity_identifier_value(c["cik"]),
                identity_identifier_value(c["gvkey"])
            )
            for c in candidates_priority
        )

        rows.append({
            "parent_token": token,
            "fyear": fyear,
            "n_candidates_all": len(candidates_all),
            "n_unique_identity_pairs_all": len(identity_pairs_all),
            "is_safe_all_sources": len(identity_pairs_all) == 1,
            "priority_rule": priority_rule,
            "n_candidates_priority": len(candidates_priority),
            "n_unique_identity_pairs_priority": len(identity_pairs_priority),
            "is_safe_recovery_token_priority": len(identity_pairs_priority) == 1,
            "candidate_parent_names_all": "|".join(sorted(set(str(c["parent_name"]) for c in candidates_all))),
            "candidate_parent_names_priority": "|".join(sorted(set(str(c["parent_name"]) for c in candidates_priority))),
            "candidate_original_names_all": "|".join(sorted(set(str(c["bridge_original_name"]) for c in candidates_all))),
            "candidate_original_names_priority": "|".join(sorted(set(str(c["bridge_original_name"]) for c in candidates_priority))),
            "candidate_sources_all": "|".join(sorted(set(str(c["source"]) for c in candidates_all))),
            "candidate_sources_priority": "|".join(sorted(set(str(c["source"]) for c in candidates_priority))),
            "candidate_ciks_all": "|".join(sorted(set(str(output_identifier_value(c["cik"])) for c in candidates_all))),
            "candidate_gvkeys_all": "|".join(sorted(set(str(output_identifier_value(c["gvkey"])) for c in candidates_all))),
            "candidate_ciks_priority": "|".join(sorted(set(str(output_identifier_value(c["cik"])) for c in candidates_priority))),
            "candidate_gvkeys_priority": "|".join(sorted(set(str(output_identifier_value(c["gvkey"])) for c in candidates_priority))),
        })

    df_diag = pd.DataFrame(rows)

    df_diag.to_csv(
        mapped_dir / "parent_token_recovery_diagnostics.csv",
        index=False
    )

    return df_diag


def main():
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    RESULTS_DIR = Path(config["results_dir"])
    MAP_SUB = Path(config["map_sub"])
    LLM_SUB = Path(config["llm_sub"])
    DICT_DIR = Path(config["dict_dir"])

    mapped_dir = RESULTS_DIR / MAP_SUB
    mapped_dir.mkdir(parents=True, exist_ok=True)

    llm_dir = RESULTS_DIR / LLM_SUB
    bridge_file = DICT_DIR / config["mapping_bridge_file"]

    df_bridge = pd.read_csv(bridge_file)

    print("Bridge file:", bridge_file)
    print("Bridge columns:", df_bridge.columns.tolist())
    print("Bridge rows:", len(df_bridge))

    df_bridge = prepare_bridge(df_bridge, mapped_dir)

    bridge_lookup = build_yearly_bridge_lookup(df_bridge)
    parent_token_lookup = build_parent_token_lookup(df_bridge)

    print("Number of year-specific bridge mappings:", len(bridge_lookup))
    print("Number of year-specific parent-prefix mappings:", len(parent_token_lookup))

    parent_token_diag = build_parent_token_diagnostics(parent_token_lookup, mapped_dir)

    print("\nParent-prefix diagnostics:")
    print(parent_token_diag["is_safe_recovery_token_priority"].value_counts(dropna=False))

    overall_summary = []
    global_parent_recovery_blocked_cases = []

    for csv_path in sorted(llm_dir.glob("*.csv")):
        sic_code = csv_path.stem
        print(f"\nProcessing {sic_code} -> {csv_path}")

        df = pd.read_csv(csv_path)

        if "competitors" not in df.columns:
            print(f"Skipping {csv_path}; no competitors column found.")
            continue

        if "filename" not in df.columns:
            print("Available columns:", df.columns.tolist())
            raise ValueError(
                "No 'filename' column found. Please rename the filing filename column to 'filename' or update the code."
            )

        df["fyear"] = df["filename"].apply(extract_fyear_from_filename)

        build_competitor_diagnostics(df, mapped_dir, sic_code)

        df[
            [
                "competitors_standardized",
                "competitors_ciks",
                "competitors_gvkeys",
                "competitors_match_sources",
                "competitors_match_methods",
                "competitors_matched_bridge_names",
                "competitors_matched_bridge_original_names",
                "competitors_recovered_parent_prefixes",
                "competitors_recovered_parent_prefix_n_tokens",
                "competitors_recovery_priority_rules",
                "competitors_recovery_n_candidates_all",
                "competitors_recovery_n_candidates_priority",
                "competitors_recovery_n_unique_identity_pairs_all",
                "competitors_recovery_n_unique_identity_pairs_priority",
                "competitors_recovery_candidate_parent_names_all",
                "competitors_recovery_candidate_parent_names_priority",
                "competitors_recovery_candidate_original_names_all",
                "competitors_recovery_candidate_original_names_priority",
                "competitors_recovery_candidate_sources_all",
                "competitors_recovery_candidate_sources_priority",
                "competitors_recovery_candidate_ciks_all",
                "competitors_recovery_candidate_gvkeys_all",
                "competitors_recovery_candidate_ciks_priority",
                "competitors_recovery_candidate_gvkeys_priority",
                "competitors_global_parent_recovery_continuation_terms",
                "competitors_global_parent_recovery_unsafe_continuation_terms",
                "competitors_global_parent_recovery_safety_rules",
            ]
        ] = df.apply(
            lambda row: match_competitor_list_yearly(
                row["competitors"],
                row["fyear"],
                bridge_lookup,
                parent_token_lookup,
                global_parent_recovery_blocked_cases,
            ),
            axis=1,
            result_type="expand"
        )

        n_rows = len(df)
        n_with_competitors = df["competitors"].notna().sum()

        all_sources = []
        for s in df["competitors_match_sources"].dropna():
            all_sources.extend(str(s).split("|"))

        all_methods = []
        for m in df["competitors_match_methods"].dropna():
            all_methods.extend(str(m).split("|"))

        n_unmatched = sum(1 for s in all_sources if s == "unmatched")
        n_parent_recovered = sum(1 for s in all_sources if str(s).startswith("parent_token_recovery_"))
        n_total_mentions = len(all_sources)

        match_rate = 1 - (n_unmatched / n_total_mentions) if n_total_mentions > 0 else None

        overall_summary.append({
            "sic_code": sic_code,
            "n_rows": n_rows,
            "n_rows_with_competitors": n_with_competitors,
            "n_competitor_mentions": n_total_mentions,
            "n_unmatched_mentions": n_unmatched,
            "n_parent_token_recovered_mentions": n_parent_recovered,
            "match_rate": match_rate,
            "n_exact_full_raw": sum(1 for m in all_methods if m == "exact_full_raw"),
            "n_exact_outside_parentheses": sum(1 for m in all_methods if m == "exact_outside_parentheses"),
            "n_exact_inside_parentheses": sum(1 for m in all_methods if m == "exact_inside_parentheses"),
            "n_parent_prefix_recovered_by_method": sum(
                1 for m in all_methods if str(m).startswith("parent_prefix_recovery_")
            ),
        })

        output_file = mapped_dir / f"{sic_code}.xlsx"
        df.to_excel(output_file, index=False)

        print(f"Saved: {output_file}")
        print(
            f"Mentions: {n_total_mentions} | "
            f"Unmatched: {n_unmatched} | "
            f"Parent-prefix recovered: {n_parent_recovered} | "
            f"Match rate: {match_rate}"
        )

    if global_parent_recovery_blocked_cases:
        df_global_blocked = pd.DataFrame(global_parent_recovery_blocked_cases).drop_duplicates()
    else:
        df_global_blocked = pd.DataFrame(
            columns=[
                "attempted_name_variant",
                "recovered_parent_prefix",
                "matched_bridge_name",
                "matched_bridge_original_name",
                "continuation_terms",
                "unsafe_continuation_terms",
                "source",
                "fyear",
                "reason",
            ]
        )

    df_global_blocked.to_csv(
        mapped_dir / "global_parent_recovery_blocked_cases.csv",
        index=False
    )

    pd.DataFrame(
        [
            {
                "metric": metric,
                "value": value,
            }
            for metric, value in STANDARDIZATION_NORMALIZATION_COUNTERS.items()
        ]
    ).to_csv(
        mapped_dir / "standardization_normalization_diagnostics.csv",
        index=False
    )

    if overall_summary:
        df_summary = pd.DataFrame(overall_summary)
        df_summary.to_csv(mapped_dir / "mapping_summary_by_sic.csv", index=False)

        print("\nOverall mapping summary:")
        print(df_summary)

    print("\nMapping complete.")


if __name__ == "__main__":
    main()