import pandas as pd
import numpy as np
import re
import yaml
from pathlib import Path

from utils import get_uniform_format_company_name


# -----------------------------
# Controlled standardization maps
# -----------------------------

STANDARDIZATION_MAP = {
    # Holding / group
    "HOLDINGS": "HLDG",
    "HOLDING": "HLDG",
    "HLDGS": "HLDG",
    "HLDNG": "HLDG",
    "HOLD": "HLDG",
    "GROUP": "GRP",
    "GROUPE": "GRP",

    # Legal / company forms
    "INCORPORATED": "INC",
    "CORPORATION": "CORP",
    "COMPANY": "CO",
    "LIMITED": "LTD",

    # Technology
    "TECHNOLOGIES": "TECH",
    "TECHNOLOGY": "TECH",
    "TECHNOLOGIE": "TECH",
    "TECHNOLGIES": "TECH",
    "TECHNLGY": "TECH",
    "TECHNO": "TECH",
    "TEK": "TECH",

    # Research / service / systems
    "RESEARCH": "RES",
    "SERVICES": "SERV",
    "SERVICE": "SERV",
    "SOLUTIONS": "SOLUT",
    "SOLUTION": "SOLUT",
    "SYSTEMS": "SYS",
    "SYSTEM": "SYS",

    # International / manufacturing
    "INTERNATIONAL": "INTL",
    "MANUFACTURING": "MFG",
    "MANUFACTURER": "MFG",
    "MANUFACTURERS": "MFG",

    # Labs
    "LABORATORIES": "LAB",
    "LABORATORY": "LAB",
    "LABORATOIRES": "LAB",
    "LABS": "LAB",

    # Industry
    "INDUSTRIES": "IND",
    "INDUSTRY": "IND",

    # Pharma / bio
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

    # Medical / healthcare
    "HEALTHCARE": "HLTHCR",
    "HEALTH": "HLTH",
    "MEDICAL": "MED",
    "MEDICINE": "MED",
    "MEDICINES": "MED",
    "CHEMICALS": "CHEM",
    "CHEMICAL": "CHEM",

    # Therapeutics
    "THERAPEUTICS": "THER",
    "THERAPEUTIC": "THER",
    "THERAPIES": "THER",

    # Semiconductors / electronics
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

    # Engineering
    "ENGINEERING": "ENG",

    # Other useful reductions
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
    # Legal suffixes
    "INC", "CORP", "CO", "LTD", "LLC", "PLC", "NV", "SA", "AG", "BV",
    "GMBH", "LP", "LLP", "KGAA", "OY", "OYJ", "SAS", "SRL", "SARL",
    "SPA", "PTE", "PVT", "SL", "SAU", "SPRL", "KS", "AB", "AS", "APS",
    "ASA", "BVBA", "KK", "LTDA", "RT", "ZRT", "KFT", "KG", "PTY", "BHD",
    "SDN", "PJSC", "JSC", "OAO", "ZAO", "AO",

    # Common words that can be safely removed only if name remains informative
    "HLDG", "GRP"
}


RISKY_STANDALONE_NAMES = {
    "TECH", "PHARM", "BIO", "BIOTECH", "MED", "CHEM", "SEMICOND",
    "SYS", "GRP", "HLDG", "HLTH", "HLTHCR", "LAB", "RES", "SERV",
    "SOLUT", "GLOBAL", "INTL", "IND", "CO", "CORP", "INC"
}


def clean_identifier_value(x, zfill_length=None):
    if pd.isna(x):
        return None

    x = str(x).strip()
    x = re.sub(r"\.0$", "", x)

    if x == "" or x.lower() in {"nan", "none"}:
        return None

    if zfill_length is not None:
        x = x.zfill(zfill_length)

    return x


def standardize_name_for_mapping(x):
    if pd.isna(x):
        return ""

    x = get_uniform_format_company_name(x)

    # Remove known Compustat status markers
    x = x.replace("-OLD", "")
    x = x.replace("-NEW", "")
    x = x.replace("-PRO FORMA", "")
    x = x.replace("PRO FORMA", "")

    # Remove share-class markers
    x = re.sub(r"\bCL [A-Z]\b", "", x)

    # Remove standalone THE
    x = re.sub(r"\bTHE\b", "", x)

    # Standardize tokens
    parts = x.split()
    parts = [STANDARDIZATION_MAP.get(p, p) for p in parts]

    x = " ".join(parts)
    x = re.sub(r"\s+", " ", x).strip()

    return x


def is_safe_name_variant(name):
    if not name:
        return False

    name = name.strip()

    if name.startswith(","):
        return False

    if len(name.replace(",", "").split()) < 2:
        return False

    if name.replace(",", "").isdigit():
        return False

    if re.match(r"^\d+[A-Z]?$", name):
        return False

    if name in RISKY_STANDALONE_NAMES:
        return False

    return True


def remove_suffixes_if_safe(name):
    """
    Creates one conservative cleaned version by removing trailing legal/common suffixes.
    It does not create many artificial variants.
    """
    parts = name.split()

    while len(parts) > 2 and parts[-1] in REMOVABLE_SUFFIXES:
        parts = parts[:-1]

    cleaned = " ".join(parts).strip()

    if cleaned == name:
        return None

    if not is_safe_name_variant(cleaned):
        return None

    return cleaned


def abbreviate_string(input_string):
    words = input_string.split()
    return "".join(word[0].upper() for word in words if word)


def add_mapping(name, cik, gvkey, company_name_to_cik, company_name_to_gvkey):
    if not is_safe_name_variant(name):
        return

    if cik is not None:
        company_name_to_cik[name] = cik

    if gvkey is not None:
        company_name_to_gvkey[name] = gvkey


def create_dict(sic_file, col_cik, col_gvkey, col_company_name, col_tic, dict_map_file):
    company_name_to_cik = {}
    company_name_to_gvkey = {}

    df = pd.read_csv(sic_file)

    print("Input file:", sic_file)
    print("Input columns:", df.columns.tolist())
    print("Initial rows:", len(df))

    df = df.loc[pd.notna(df[col_cik]) | pd.notna(df[col_gvkey])].copy()

    print("Rows with CIK or GVKEY:", len(df))

    for idx, row in df.iterrows():
        raw_name = row[col_company_name]

        name_std = standardize_name_for_mapping(raw_name)

        cik = clean_identifier_value(row[col_cik], zfill_length=10)
        gvkey = clean_identifier_value(row[col_gvkey])

        # 1. Add standardized name
        add_mapping(
            name_std,
            cik,
            gvkey,
            company_name_to_cik,
            company_name_to_gvkey
        )

        # 2. Add conservative cleaned name
        name_clean = remove_suffixes_if_safe(name_std)

        if name_clean:
            add_mapping(
                name_clean,
                cik,
                gvkey,
                company_name_to_cik,
                company_name_to_gvkey
            )

    print("After standardized + cleaned names:")
    print("CIK mappings:", len(company_name_to_cik))
    print("GVKEY mappings:", len(company_name_to_gvkey))

    # 3. Add abbreviations only for longer, safer names
    abbreviation_additions_cik = {}
    abbreviation_additions_gvkey = {}

    all_names = set(company_name_to_cik.keys()) | set(company_name_to_gvkey.keys())

    for company_name in all_names:
        if len(company_name.split()) < 3:
            continue

        abbreviation = abbreviate_string(company_name)

        if len(abbreviation) < 2:
            continue

        if re.match(r"^\d+[A-Z]?$", abbreviation):
            continue

        if company_name in company_name_to_cik:
            abbreviation_additions_cik[abbreviation] = company_name_to_cik[company_name]

        if company_name in company_name_to_gvkey:
            abbreviation_additions_gvkey[abbreviation] = company_name_to_gvkey[company_name]

    company_name_to_cik.update(abbreviation_additions_cik)
    company_name_to_gvkey.update(abbreviation_additions_gvkey)

    print("After abbreviation mappings:")
    print("CIK mappings:", len(company_name_to_cik))
    print("GVKEY mappings:", len(company_name_to_gvkey))

    # Export combined dictionary
    df_cik = pd.DataFrame(
        company_name_to_cik.items(),
        columns=[col_company_name, col_cik]
    )

    df_gvkey = pd.DataFrame(
        company_name_to_gvkey.items(),
        columns=[col_company_name, col_gvkey]
    )

    df_out = df_cik.merge(df_gvkey, on=col_company_name, how="outer")
    df_out = df_out.sort_values(col_company_name)

    df_out.to_csv(dict_map_file)

    print("Dictionary saved to:", dict_map_file)
    print("Final dictionary rows:", len(df_out))
    print(df_out.head(20))

    # Diagnostics for suspicious generated names
    suspicious = df_out[
        df_out[col_company_name].astype(str).str.match(r"^\d+[A-Z]?$|^,|^\d+$", na=False)
    ]

    suspicious.to_csv("suspicious_dictionary_names.csv", index=False)

    print("Suspicious dictionary names:", len(suspicious))
    print("Suspicious names saved to: suspicious_dictionary_names.csv")

    # Validation
    validation = df.copy()
    validation["name_std"] = validation[col_company_name].apply(standardize_name_for_mapping)

    validation["cik_clean"] = validation[col_cik].apply(
        lambda x: clean_identifier_value(x, zfill_length=10)
    )

    validation["gvkey_clean"] = validation[col_gvkey].apply(
        lambda x: clean_identifier_value(x)
    )

    validation["cik_retrieved_from_name"] = validation["name_std"].apply(
        lambda x: company_name_to_cik.get(x, None)
    )

    validation["gvkey_retrieved_from_name"] = validation["name_std"].apply(
        lambda x: company_name_to_gvkey.get(x, None)
    )

    missing_cik = validation[
        (validation["cik_clean"].notna()) &
        (validation["cik_clean"] != validation["cik_retrieved_from_name"])
    ]

    missing_gvkey = validation[
        (validation["gvkey_clean"].notna()) &
        (validation["gvkey_clean"] != validation["gvkey_retrieved_from_name"])
    ]

    missing_cik[[col_company_name, col_cik, "name_std", "cik_retrieved_from_name"]].to_csv(
        "missing_ciks.csv",
        index=False
    )

    missing_gvkey[[col_company_name, col_gvkey, "name_std", "gvkey_retrieved_from_name"]].to_csv(
        "missing_gvkeys.csv",
        index=False
    )

    print("Missing CIK checks:", len(missing_cik))
    print("Missing GVKEY checks:", len(missing_gvkey))


def main():
    with open("config.yaml", "r") as f:
        config = yaml.safe_load(f)

    INPUT_CSV = config["input_csv"]
    COMPANY_NAME_COLUMN = config["company_name_column"]
    CIK_COLUMN = config["cik_column"]
    GVKEY_COLUMN = config["gvkey_column"]
    TIC_COLUMN = config["tic_column"]

    DICT_DIR = Path(config["dict_dir"])
    DICT_DIR.mkdir(parents=True, exist_ok=True)

    dict_map_file = DICT_DIR / "company_name_to_cik_mapping.csv"

    create_dict(
        INPUT_CSV,
        CIK_COLUMN,
        GVKEY_COLUMN,
        COMPANY_NAME_COLUMN,
        TIC_COLUMN,
        dict_map_file
    )


if __name__ == "__main__":
    main()