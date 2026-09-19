import yaml
from pathlib import Path
import pandas as pd
import re
import openpyxl

from utils import get_uniform_format_company_name


STANDARDIZATION_MAP = {
    "HOLDINGS": "HLDG",
    "HOLDING": "HLDG",
    "HLDGS": "HLDG",
    "HLDNG": "HLDG",
    "HOLD": "HLDG",
    "GROUP": "GRP",
    "GROUPE": "GRP",

    "INCORPORATED": "INC",
    "CORPORATION": "CORP",
    "COMPANY": "CO",
    "LIMITED": "LTD",

    "TECHNOLOGIES": "TECH",
    "TECHNOLOGY": "TECH",
    "TECHNOLOGIE": "TECH",
    "TECHNOLGIES": "TECH",
    "TECHNLGY": "TECH",
    "TECHNO": "TECH",
    "TEK": "TECH",

    "RESEARCH": "RES",
    "SERVICES": "SERV",
    "SERVICE": "SERV",
    "SOLUTIONS": "SOLUT",
    "SOLUTION": "SOLUT",
    "SYSTEMS": "SYS",
    "SYSTEM": "SYS",

    "INTERNATIONAL": "INTL",
    "MANUFACTURING": "MFG",
    "MANUFACTURER": "MFG",
    "MANUFACTURERS": "MFG",

    "LABORATORIES": "LAB",
    "LABORATORY": "LAB",
    "LABORATOIRES": "LAB",
    "LABS": "LAB",

    "INDUSTRIES": "IND",
    "INDUSTRY": "IND",

    "PHARMACEUTICALS": "PHARM",
    "PHARMACEUTICAL": "PHARM",
    "PHARMA": "PHARM",
    "PHARMS": "PHARM",
    "BIOPHARMACEUTICALS": "BIOPHARM",
    "BIOPHARMACEUTICAL": "BIOPHARM",
    "BIOTECHNOLOGIES": "BIOTECH",
    "BIOTECHNOLOGY": "BIOTECH",
    "BIOLOGICS": "BIOLOGIC",
    "BIOLOGICAL": "BIOLOGIC",
    "BIOLOGY": "BIOLOGIC",
    "BIOSCIENCES": "BIOSCI",
    "BIOSCIENCE": "BIOSCI",
    "GENOMICS": "GENOMIC",
    "DIAGNOSTICS": "DIAGNOSTIC",

    "HEALTHCARE": "HLTHCR",
    "HEALTH": "HLTH",
    "MEDICAL": "MED",
    "MEDICINE": "MED",
    "MEDICINES": "MED",
    "CHEMICALS": "CHEM",
    "CHEMICAL": "CHEM",

    "THERAPEUTICS": "THER",
    "THERAPEUTIC": "THER",
    "THERAPIES": "THER",

    "SEMICONDUCTORS": "SEMICOND",
    "SEMICONDUCTOR": "SEMICOND",
    "SEMICON": "SEMICOND",
    "ELECTRONICS": "ELECTRONIC",
    "ELECTRO": "ELECTRONIC",
    "ELEC": "ELECTRONIC",
    "MICROELECTRONICS": "MICROELECTRONIC",
    "COMMUNICATIONS": "COMM",
    "COMMUNICATION": "COMM",
    "TELECOMMUNICATIONS": "TELECOM",
    "TELECOMM": "TELECOM",

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
    "SDN", "PJSC", "JSC", "OAO", "ZAO", "AO", "HLDG", "GRP"
}


def standardize_name_for_mapping(x):
    if pd.isna(x):
        return ""

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


def remove_suffixes_if_safe(name):
    parts = name.split()

    while len(parts) > 2 and parts[-1] in REMOVABLE_SUFFIXES:
        parts = parts[:-1]

    cleaned = " ".join(parts).strip()

    if cleaned == name:
        return None

    if len(cleaned.split()) < 2:
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


def build_mapping_dict(df_map, name_col, id_col):
    mapping = {}

    for idx, row in df_map.iterrows():
        name = row[name_col]
        value = clean_identifier_value(row[id_col])

        if pd.isna(name) or value is None:
            continue

        mapping[str(name).strip()] = value

    return mapping


def candidate_name_variants(raw_name):
    """
    Return possible standardized versions of the extracted competitor name.
    We first try the full standardized version, then the suffix-cleaned version.
    """
    variants = []

    name_std = standardize_name_for_mapping(raw_name)

    if name_std:
        variants.append(name_std)

    name_clean = remove_suffixes_if_safe(name_std)

    if name_clean:
        variants.append(name_clean)

    # remove duplicates while preserving order
    seen = set()
    variants_unique = []

    for v in variants:
        if v not in seen:
            variants_unique.append(v)
            seen.add(v)

    return variants_unique


def replace_with_mapping(x, dict_maps):
    if pd.isna(x):
        return ""

    values = []

    for raw_name in str(x).split("|"):
        raw_name = raw_name.strip()

        if not raw_name:
            values.append(-1)
            continue

        if not starts_with_capital(raw_name):
            values.append(-1)
            continue

        matched_value = -1

        for name_variant in candidate_name_variants(raw_name):
            if name_variant in dict_maps:
                matched_value = dict_maps[name_variant]
                break

        values.append(matched_value)

    return "|".join(map(str, values))


def main():
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    RESULTS_DIR = Path(config["results_dir"])
    MAP_SUB = Path(config["map_sub"])
    OUTPUT_DIR = RESULTS_DIR / MAP_SUB
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    LLM_DIR = RESULTS_DIR / Path(config["llm_sub"])

    CIK_COLUMN = config["cik_column"]
    COMPANY_NAME_COLUMN = config["company_name_column"]
    GVKEY_COLUMN = config["gvkey_column"]

    DICT_DIR = Path(config["dict_dir"])
    dict_map_file = DICT_DIR / "company_name_to_cik_mapping.csv"

    df_map = pd.read_csv(dict_map_file, index_col=0)

    print("Mapping file:", dict_map_file)
    print("Mapping columns:", df_map.columns.tolist())
    print("Mapping rows:", len(df_map))
    print(df_map.head())

    dict_maps_cik = build_mapping_dict(df_map, COMPANY_NAME_COLUMN, CIK_COLUMN)
    dict_maps_gvkey = build_mapping_dict(df_map, COMPANY_NAME_COLUMN, GVKEY_COLUMN)

    print("Number of CIK mappings:", len(dict_maps_cik))
    print("Number of GVKEY mappings:", len(dict_maps_gvkey))

    mapped_dir = RESULTS_DIR / MAP_SUB
    mapped_dir.mkdir(parents=True, exist_ok=True)

    for csv_path in sorted(LLM_DIR.glob("*.csv")):
        sic_code = csv_path.stem
        print(f"Processing {sic_code} -> {csv_path}")

        df = pd.read_csv(csv_path)

        if "competitors" not in df.columns:
            print(f"Skipping {csv_path}; no competitors column found.")
            continue

        # Optional diagnostics: competitor standardization list
        all_competitors = set()

        for competitors in df["competitors"]:
            try:
                if pd.notna(competitors):
                    all_competitors.update(str(competitors).split("|"))
            except Exception:
                print("parse error for", competitors)

        all_competitors.discard("")

        df_all_competitors = pd.DataFrame(
            {"company_name_in_text": sorted(all_competitors)}
        )

        df_all_competitors["company_name_std"] = df_all_competitors[
            "company_name_in_text"
        ].apply(standardize_name_for_mapping)

        df_all_competitors["company_name_clean"] = df_all_competitors[
            "company_name_std"
        ].apply(remove_suffixes_if_safe)

        df_all_competitors.to_csv(
            mapped_dir / f"{sic_code}_competitor_name_diagnostics.csv",
            index=False
        )

        df["competitors_ciks"] = df["competitors"].apply(
            lambda x: replace_with_mapping(x, dict_maps_cik)
        )

        df["competitors_gvkeys"] = df["competitors"].apply(
            lambda x: replace_with_mapping(x, dict_maps_gvkey)
        )

        print(df.head())

        df.to_excel(mapped_dir / f"{sic_code}.xlsx", index=False)


if __name__ == "__main__":
    main()