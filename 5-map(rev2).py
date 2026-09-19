# 5-Map-Competitor-Names.py

import yaml
from pathlib import Path
import pandas as pd
import re

from utils import get_uniform_format_company_name


STANDARDIZATION_MAP = {
    "HOLDINGS": "HLDG", "HOLDING": "HLDG", "HLDGS": "HLDG", "HLDNG": "HLDG", "HOLD": "HLDG",
    "GROUP": "GRP", "GROUPE": "GRP",

    "INCORPORATED": "INC", "CORPORATION": "CORP", "COMPANY": "CO", "LIMITED": "LTD",

    "TECHNOLOGIES": "TECH", "TECHNOLOGY": "TECH", "TECHNOLOGIE": "TECH",
    "TECHNOLGIES": "TECH", "TECHNLGY": "TECH", "TECHNO": "TECH", "TEK": "TECH",

    "RESEARCH": "RES",
    "SERVICES": "SERV", "SERVICE": "SERV",
    "SOLUTIONS": "SOLUT", "SOLUTION": "SOLUT",
    "SYSTEMS": "SYS", "SYSTEM": "SYS",

    "INTERNATIONAL": "INTL",
    "MANUFACTURING": "MFG", "MANUFACTURER": "MFG", "MANUFACTURERS": "MFG",

    "LABORATORIES": "LAB", "LABORATORY": "LAB", "LABORATOIRES": "LAB", "LABS": "LAB",

    "INDUSTRIES": "IND", "INDUSTRY": "IND",

    "PHARMACEUTICALS": "PHARM", "PHARMACEUTICAL": "PHARM", "PHARMA": "PHARM", "PHARMS": "PHARM",
    "BIOPHARMACEUTICALS": "BIOPHARM", "BIOPHARMACEUTICAL": "BIOPHARM",
    "BIOTECHNOLOGIES": "BIOTECH", "BIOTECHNOLOGY": "BIOTECH",
    "BIOLOGICS": "BIOLOGIC", "BIOLOGICAL": "BIOLOGIC", "BIOLOGY": "BIOLOGIC",
    "BIOSCIENCES": "BIOSCI", "BIOSCIENCE": "BIOSCI",
    "GENOMICS": "GENOMIC",
    "DIAGNOSTICS": "DIAGNOSTIC",

    "HEALTHCARE": "HLTHCR", "HEALTH": "HLTH",
    "MEDICAL": "MED", "MEDICINE": "MED", "MEDICINES": "MED",
    "CHEMICALS": "CHEM", "CHEMICAL": "CHEM",

    "THERAPEUTICS": "THER", "THERAPEUTIC": "THER", "THERAPIES": "THER",

    "SEMICONDUCTORS": "SEMICOND", "SEMICONDUCTOR": "SEMICOND", "SEMICON": "SEMICOND",
    "ELECTRONICS": "ELECTRONIC", "ELECTRO": "ELECTRONIC", "ELEC": "ELECTRONIC",
    "MICROELECTRONICS": "MICROELECTRONIC",

    "COMMUNICATIONS": "COMM", "COMMUNICATION": "COMM",
    "TELECOMMUNICATIONS": "TELECOM", "TELECOMM": "TELECOM",

    "ENGINEERING": "ENG",
    "DEVELOPMENT": "DEV",
    "GLOBAL": "GLOB",
    "WORLDWIDE": "WORLD",
    "ENTERPRISES": "ENTERPRISE",
    "COMPONENTS": "COMPONENT",
    "DEVICES": "DEVICE",
    "CONSUMERS": "CONSUMER",
    "FRANCHISES": "FRANCHISE",
}


REMOVABLE_SUFFIXES = {
    "INC", "CORP", "CO", "LTD", "LLC", "PLC", "NV", "SA", "AG", "BV",
    "GMBH", "LP", "LLP", "KGAA", "OY", "OYJ", "SAS", "SRL", "SARL",
    "SPA", "PTE", "PVT", "SL", "SAU", "SPRL", "KS", "AB", "AS", "APS",
    "ASA", "BVBA", "KK", "LTDA", "RT", "ZRT", "KFT", "KG", "PTY", "BHD",
    "SDN", "PJSC", "JSC", "OAO", "ZAO", "AO", "HLDG", "GRP", "IND"
}


def fix_encoding_artifacts(x):
    if pd.isna(x):
        return ""

    x = str(x)

    replacements = {
        "‚Äôs": "'s",
        "‚Äô": "'",
        "‚Äú": '"',
        "‚Äù": '"',
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
    """
    Recover firm/parent names from product or brand expressions before matching.

    Examples:
    Zytiga (Janssen) -> Janssen
    ZomactonTM (Ferring Pharmaceuticals) -> Ferring Pharmaceuticals
    Johnson & Johnson's DURAGESIC -> Johnson & Johnson
    INS INSoft Division, a unit of Lucent Technologies -> Lucent Technologies
    Mallards (owned by Tyson) -> Tyson
    """

    x = fix_encoding_artifacts(x)

    # Product (owned by Parent)
    m = re.search(r"\(\s*owned by\s+([^()]+)\s*\)\s*$", x, flags=re.I)
    if m:
        return m.group(1).strip(" .;,)")

    # Product (Parent)
    m = re.search(r"\(([^()]+)\)\s*$", x)
    if m:
        parent = m.group(1).strip(" .;,)")

        bad_parent_terms = {
            "usa", "us", "u.s.", "canada", "uk", "eu", "generic",
            "formerly", "d/b/a", "also known as", "new", "old"
        }

        if len(parent) > 2 and parent.lower() not in bad_parent_terms:
            return parent

    # Parent's Product
    m = re.search(r"^(.+?)['’]s\s+.+$", x)
    if m:
        parent = m.group(1).strip(" .;,")
        if len(parent) > 2:
            return parent

    # Division/unit/subsidiary/business/brand of Parent
    m = re.search(
        r"\b(?:a\s+)?(?:unit|division|subsidiary|business|brand)\s+of\s+(.+)$",
        x,
        flags=re.I
    )
    if m:
        parent = m.group(1).strip(" .;,)")

        # Remove trailing explanatory clauses
        parent = re.split(r",|\(|;", parent)[0].strip()

        if len(parent) > 2:
            return parent

    return x


def standardize_name_for_mapping(x):
    if pd.isna(x):
        return ""

    # New: recover parent/owner first, then normalize
    x = recover_parent_or_owner_name(x)

    x = get_uniform_format_company_name(x)

    x = x.replace("-OLD", "")
    x = x.replace("-NEW", "")
    x = x.replace("-PRO FORMA", "")
    x = x.replace("PRO FORMA", "")

    x = re.sub(r"\bCL [A-Z]\b", "", x)
    x = re.sub(r"\bTHE\b", "", x)

    parts = x.split()
    parts = [STANDARDIZATION_MAP.get(p, p) for p in parts]

    x = " ".join(parts)
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

    return cleaned


def starts_with_capital(s):
    s = str(s).strip()
    return s[0].isupper() if s else False


def clean_identifier_value(x):
    if pd.isna(x):
        return None

    x = str(x).strip()

    if x == "" or x.lower() in {"nan", "none"}:
        return None

    x = re.sub(r"\.0$", "", x)

    return x


def candidate_name_variants(raw_name):
    variants = []

    name_std = standardize_name_for_mapping(raw_name)

    if name_std:
        variants.append(name_std)

    name_one_word = remove_suffixes_one_word_if_safe(name_std)

    if name_one_word:
        variants.append(name_one_word)

    # Remove duplicates while preserving order
    seen = set()
    variants_unique = []

    for v in variants:
        if v not in seen:
            variants_unique.append(v)
            seen.add(v)

    return variants_unique


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

    # Keep original bridge name for diagnostics if possible
    if "name_original" not in df_bridge.columns:
        df_bridge["name_original"] = df_bridge["name_std"]

    # Apply exact same standardization to bridge side
    df_bridge["name_std"] = df_bridge["name_std"].apply(standardize_name_for_mapping)

    # Create conservative suffix-cleaned alias
    df_bridge["name_std_one_word"] = df_bridge["name_std"].apply(remove_suffixes_one_word_if_safe)

    bridge_aliases = df_bridge.copy()
    bridge_aliases["name_std"] = bridge_aliases["name_std_one_word"]
    bridge_aliases = bridge_aliases.dropna(subset=["name_std"])

    df_bridge = pd.concat([df_bridge, bridge_aliases], ignore_index=True)

    df_bridge["has_cik"] = df_bridge["cik"].notna() & (df_bridge["cik"].astype(str).str.strip() != "")
    df_bridge["has_gvkey"] = df_bridge["gvkey"].notna() & (df_bridge["gvkey"].astype(str).str.strip() != "")

    source_priority = {
        "DISCERN": 1,
        "CCM_COMPUSTAT_EXTENSION": 2,
        "COMPUSTAT_GLOBAL": 3,
    }

    df_bridge["source_priority"] = df_bridge["source"].map(source_priority).fillna(9)

    df_bridge = df_bridge.sort_values(
        by=["name_std", "fyear", "has_cik", "has_gvkey", "source_priority"],
        ascending=[True, True, False, False, True],
    )

    dups = df_bridge[df_bridge.duplicated(subset=["name_std", "fyear"], keep=False)]
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
            lookup[key] = {
                "gvkey": clean_identifier_value(row["gvkey"]),
                "cik": clean_identifier_value(row["cik"]),
                "source": clean_identifier_value(row["source"]),
            }

    return lookup


def match_competitor_list_yearly(x, fyear, bridge_lookup):
    if pd.isna(x) or pd.isna(fyear):
        return "", "", "", ""

    ciks = []
    gvkeys = []
    sources = []
    standardized_names = []

    fyear = int(fyear)

    for raw_name in str(x).split("|"):
        raw_name = raw_name.strip()

        if not raw_name or not starts_with_capital(raw_name):
            ciks.append(-1)
            gvkeys.append(-1)
            sources.append("unmatched")
            standardized_names.append("")
            continue

        matched = None
        matched_standardized_name = ""

        variants = candidate_name_variants(raw_name)

        for name_variant in variants:
            key = (name_variant, fyear)

            if key in bridge_lookup:
                matched = bridge_lookup[key]
                matched_standardized_name = name_variant
                break

        if matched:
            ciks.append(matched["cik"] if matched["cik"] is not None else "")
            gvkeys.append(matched["gvkey"] if matched["gvkey"] is not None else "")
            sources.append(matched["source"] if matched["source"] is not None else "matched_bridge")
            standardized_names.append(matched_standardized_name)
        else:
            ciks.append(-1)
            gvkeys.append(-1)
            sources.append("unmatched")
            standardized_names.append(variants[0] if variants else "")

    return (
        "|".join(map(str, standardized_names)),
        "|".join(map(str, ciks)),
        "|".join(map(str, gvkeys)),
        "|".join(map(str, sources)),
    )


def build_competitor_diagnostics(df, mapped_dir, sic_code):
    all_competitors = set()

    for competitors in df["competitors"]:
        if pd.notna(competitors):
            all_competitors.update(str(competitors).split("|"))

    all_competitors.discard("")

    df_diag = pd.DataFrame({"company_name_in_text": sorted(all_competitors)})

    df_diag["recovered_or_cleaned_name"] = df_diag["company_name_in_text"].apply(recover_parent_or_owner_name)

    df_diag["company_name_std"] = df_diag["company_name_in_text"].apply(standardize_name_for_mapping)

    df_diag["company_name_clean"] = df_diag["company_name_std"].apply(remove_suffixes_one_word_if_safe)

    df_diag.to_csv(
        mapped_dir / f"{sic_code}_competitor_name_diagnostics.csv",
        index=False
    )


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
    print(df_bridge.head())

    df_bridge = prepare_bridge(df_bridge, mapped_dir)
    bridge_lookup = build_yearly_bridge_lookup(df_bridge)

    print("Number of year-specific bridge mappings:", len(bridge_lookup))

    overall_summary = []

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
            ]
        ] = df.apply(
            lambda row: match_competitor_list_yearly(
                row["competitors"],
                row["fyear"],
                bridge_lookup
            ),
            axis=1,
            result_type="expand"
        )
        print(
            df[
                [
                    "filename",
                    "fyear",
                    "competitors",
                    "competitors_standardized",
                    "competitors_ciks",
                    "competitors_gvkeys",
                    "competitors_match_sources",
                ]
            ].head(10)
        )
        # Diagnostics for match quality
        n_rows = len(df)
        n_with_competitors = df["competitors"].notna().sum()

        all_sources = []
        for s in df["competitors_match_sources"].dropna():
            all_sources.extend(str(s).split("|"))

        n_unmatched = sum(1 for s in all_sources if s == "unmatched")
        n_total_mentions = len(all_sources)
        match_rate = 1 - (n_unmatched / n_total_mentions) if n_total_mentions > 0 else None

        overall_summary.append({
            "sic_code": sic_code,
            "n_rows": n_rows,
            "n_rows_with_competitors": n_with_competitors,
            "n_competitor_mentions": n_total_mentions,
            "n_unmatched_mentions": n_unmatched,
            "match_rate": match_rate,
        })

        output_file = mapped_dir / f"{sic_code}.xlsx"
        df.to_excel(output_file, index=False)

        print(f"Saved: {output_file}")
        print(f"Mentions: {n_total_mentions} | Unmatched: {n_unmatched} | Match rate: {match_rate}")

    if overall_summary:
        df_summary = pd.DataFrame(overall_summary)
        df_summary.to_csv(mapped_dir / "mapping_summary_by_sic.csv", index=False)

        print("\nOverall mapping summary:")
        print(df_summary)

    print("\nMapping complete.")


if __name__ == "__main__":
    main()