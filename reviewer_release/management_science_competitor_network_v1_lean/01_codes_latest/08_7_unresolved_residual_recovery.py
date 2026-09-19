from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd


PROJECT = Path(r"C:\Users\mnasiri\Documents\GitHub\CompetitorNetworkV2")
FINAL_DIR = PROJECT / "data" / "results" / "final"

FINAL_STATUS_LONG = FINAL_DIR / "final_competitor_mentions_long_with_status_rev1.csv"
YEAR_BRIDGE = PROJECT / "company_alias_bridge_year_specific.csv"
IDENTIFIER_BRIDGE = PROJECT / "company_alias_bridge_identifier_level.csv"
IDENTIFIER_PANEL = PROJECT / "company_identifier_year_panel.csv"
REPRISK = PROJECT / "reprisk11072026.csv"
CIQ_COMMON = PROJECT / "ciq_common.csv"
TRUCOST = PROJECT / "trucost_com.csv"
AUDITORS = PROJECT / "auditorcompanies.csv"
BANKS = PROJECT / "Bank-CRSP-Linking-Table.csv"
ACTUALS = PROJECT / "actuals.csv"

OUT_DIR = FINAL_DIR / "step87_unresolved_recovery"
OUT_CANDIDATES = OUT_DIR / "step87_unresolved_recovery_candidates.csv"
OUT_BEST = OUT_DIR / "step87_unresolved_recovery_best_candidate.csv"
OUT_REVIEW = OUT_DIR / "step87_unresolved_recovery_review.xlsx"
OUT_SUMMARY = OUT_DIR / "step87_unresolved_recovery_summary.csv"
OUT_SOURCE_RULE = OUT_DIR / "step87_unresolved_recovery_source_rule_summary.csv"
OUT_REASON = OUT_DIR / "step87_unresolved_reason_summary.csv"
OUT_SAMPLE = OUT_DIR / "step87_unresolved_recovery_sample100.xlsx"

CHUNKSIZE = 500_000
UNRESOLVED_STATUSES = {"unresolved_no_safe_candidate", "unresolved_unclear"}
RUN_CIQ_COMMON_SCAN = False
RUN_TRUCOST_SCAN = True


STANDARDIZATION_MAP = {
    "COMPANY": "CO", "CORPORATION": "CORP", "INCORPORATED": "INC", "LIMITED": "LTD",
    "HOLDING": "HLDG", "HOLDINGS": "HLDG", "HLDGS": "HLDG", "GROUP": "GRP", "GROUPE": "GRP",
    "TECHNOLOGY": "TECH", "TECHNOLOGIES": "TECH", "SYSTEM": "SYS", "SYSTEMS": "SYS",
    "SERVICE": "SERV", "SERVICES": "SERV", "SOLUTION": "SOLUT", "SOLUTIONS": "SOLUT",
    "INTERNATIONAL": "INTL", "MANUFACTURING": "MFG", "MANUFACTURER": "MFG",
    "MANUFACTURERS": "MFG", "INDUSTRIES": "IND", "INDUSTRY": "IND", "INDUSTRIAL": "IND",
    "PHARMACEUTICALS": "PHARM", "PHARMACEUTICAL": "PHARM", "PHARMA": "PHARM",
    "ELECTRONICS": "ELECTRONIC", "ELECTRO": "ELECTRONIC", "ELEC": "ELECTRONIC",
    "COMMUNICATIONS": "COMM", "COMMUNICATION": "COMM", "HEALTHCARE": "HLTHCR",
    "HEALTH": "HLTH",
}

LEGAL_SUFFIXES = {
    "INC", "CORP", "CO", "LTD", "LLC", "PLC", "NV", "SA", "AG", "BV", "GMBH",
    "LP", "LLP", "KGAA", "OY", "OYJ", "SAS", "SRL", "SARL", "SPA", "PTE",
    "PVT", "SL", "SAU", "AB", "AS", "ASA", "BVBA", "KK", "LTDA", "PTY", "BHD",
    "SDN", "PJSC", "JSC", "OAO", "ZAO", "AO", "THE",
}

GENERIC_TERMS = {
    "PROVIDERS", "PROVIDER", "COMPETITORS", "COMPETITOR", "COMPANIES", "COMPANY",
    "MANUFACTURERS", "MANUFACTURER", "SUPPLIERS", "SUPPLIER", "DISTRIBUTORS",
    "DISTRIBUTOR", "BANKS", "BANK", "INSURERS", "INSURANCE", "WIRELESS",
    "PHARMACEUTICAL", "PHARMACEUTICALS", "FINANCIAL", "INSTITUTIONS", "INSTITUTION",
    "OTHERS", "OTHER", "MAJOR", "SMALLER", "LOCAL", "REGIONAL", "NATIONAL",
    "COMMERCIAL", "PRIVATE", "RETAILERS", "RETAILER", "LENDERS", "LENDER",
    "HOSPITALS", "HOSPITAL", "AGENCIES", "FUNDS", "FUND", "TRUSTS", "TRUST",
    "PRODUCTS", "SERVICES", "SYSTEMS", "SOLUTIONS", "INDUSTRIES", "TECHNOLOGIES",
    "GLOBAL", "INTERNATIONAL", "CAPITAL", "INVESTMENT", "INVESTMENTS",
}


def clean_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "<na>"}:
        return ""
    return text


def normalize_unicode(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def normalize_name(value) -> str:
    text = normalize_unicode(clean_text(value)).upper()
    text = re.sub(r"\bAND\s+COMPANY\b", " CO ", text)
    text = re.sub(r"\bAND\s+CO\b", " CO ", text)
    text = re.sub(r"&\s*COMPANY\b", " CO ", text)
    text = re.sub(r"&\s*CO\b", " CO ", text)
    text = text.replace("&", " AND ")
    text = re.sub(r"[\[\]\(\)\{\},.;:'\"`]", " ", text)
    text = re.sub(r"[-/\\]+", " ", text)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    tokens = [STANDARDIZATION_MAP.get(tok, tok) for tok in text.split()]
    return " ".join(tokens)


def normalize_name_series(series: pd.Series) -> pd.Series:
    out = series.fillna("").astype(str).str.strip()
    out = out.mask(out.str.lower().isin({"nan", "none", "null", "<na>"}), "")
    out = out.str.normalize("NFKD").str.encode("ascii", errors="ignore").str.decode("ascii")
    out = out.str.upper()
    out = out.str.replace(r"\bAND\s+COMPANY\b", " CO ", regex=True)
    out = out.str.replace(r"\bAND\s+CO\b", " CO ", regex=True)
    out = out.str.replace(r"&\s*COMPANY\b", " CO ", regex=True)
    out = out.str.replace(r"&\s*CO\b", " CO ", regex=True)
    out = out.str.replace("&", " AND ", regex=False)
    out = out.str.replace(r"[\[\]\(\)\{\},.;:'\"`]", " ", regex=True)
    out = out.str.replace(r"[-/\\]+", " ", regex=True)
    out = out.str.replace(r"[^A-Z0-9]+", " ", regex=True)
    out = out.str.replace(r"\s+", " ", regex=True).str.strip()
    for src, dst in STANDARDIZATION_MAP.items():
        out = out.str.replace(rf"\b{re.escape(src)}\b", dst, regex=True)
    out = out.str.replace(r"\s+", " ", regex=True).str.strip()
    return out


def rough_name_series(series: pd.Series) -> pd.Series:
    out = series.fillna("").astype(str).str.strip()
    out = out.mask(out.str.lower().isin({"nan", "none", "null", "<na>"}), "")
    out = out.str.normalize("NFKD").str.encode("ascii", errors="ignore").str.decode("ascii")
    out = out.str.upper()
    out = out.str.replace(r"\bAND\s+COMPANY\b", " CO ", regex=True)
    out = out.str.replace(r"\bAND\s+CO\b", " CO ", regex=True)
    out = out.str.replace(r"&\s*COMPANY\b", " CO ", regex=True)
    out = out.str.replace(r"&\s*CO\b", " CO ", regex=True)
    out = out.str.replace("&", " AND ", regex=False)
    out = out.str.replace(r"[^A-Z0-9]+", " ", regex=True)
    return out.str.replace(r"\s+", " ", regex=True).str.strip()


def rough_canonical_series(series: pd.Series) -> pd.Series:
    out = rough_name_series(series)
    for suffix in LEGAL_SUFFIXES:
        out = out.str.replace(rf"\s+{re.escape(suffix)}$", "", regex=True)
    return out.str.strip()


def first_token_series(series: pd.Series) -> pd.Series:
    out = series.fillna("").astype(str).str.strip()
    out = out.mask(out.str.lower().isin({"nan", "none", "null", "<na>"}), "")
    out = out.str.normalize("NFKD").str.encode("ascii", errors="ignore").str.decode("ascii")
    out = out.str.upper().str.extract(r"([A-Z0-9]+)", expand=False).fillna("")
    return out


def first_token(value: str) -> str:
    match = re.search(r"[A-Z0-9]+", normalize_unicode(clean_text(value)).upper())
    return match.group(0) if match else ""


def canonical_name(value) -> str:
    tokens = normalize_name(value).split()
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def canonical_name_series(series: pd.Series) -> pd.Series:
    out = normalize_name_series(series)
    previous = None
    while previous is None or not out.equals(previous):
        previous = out.copy()
        for suffix in LEGAL_SUFFIXES:
            out = out.str.replace(rf"\s+{re.escape(suffix)}$", "", regex=True)
        out = out.str.strip()
    return out


def valid_id(value) -> bool:
    text = clean_text(value)
    if text == "" or text.lower() in {"-1", "-1.0", "-99999", "nan", "none", "null"}:
        return False
    num = pd.to_numeric(text, errors="coerce")
    if not pd.isna(num) and num in {-1, -99999}:
        return False
    return True


def normalize_gvkey(value) -> str:
    if not valid_id(value):
        return ""
    num = pd.to_numeric(value, errors="coerce")
    if not pd.isna(num):
        return str(int(num))
    return clean_text(value)


def normalize_cik(value) -> str:
    if not valid_id(value):
        return ""
    num = pd.to_numeric(value, errors="coerce")
    if not pd.isna(num):
        return str(int(num))
    return clean_text(value)


def parse_years(value) -> set[int]:
    years = set()
    for token in re.split(r"[^0-9]+", clean_text(value)):
        if len(token) == 4:
            try:
                years.add(int(token))
            except ValueError:
                pass
    return years


def compact_values(series: pd.Series, limit: int = 30) -> str:
    values = sorted({clean_text(x) for x in series if clean_text(x)})
    return "|".join(values[:limit])


def compact_years(series: pd.Series, limit: int = 40) -> str:
    values = sorted(set(pd.to_numeric(series, errors="coerce").dropna().astype(int)))
    return "|".join(map(str, values[:limit]))


def is_generic_like_name(value) -> bool:
    tokens = normalize_name(value).split()
    if not tokens:
        return True
    if len(tokens) <= 2 and all(tok in GENERIC_TERMS or tok in LEGAL_SUFFIXES for tok in tokens):
        return True
    if len(tokens) == 1 and tokens[0] in GENERIC_TERMS:
        return True
    return False


def validation_sets() -> tuple[set[tuple[str, int]], set[tuple[str, int]]]:
    panel = pd.read_csv(IDENTIFIER_PANEL, low_memory=False)
    panel["gvkey_norm"] = panel["gvkey"].map(normalize_gvkey)
    panel["cik_norm"] = panel["cik"].map(normalize_cik)
    panel["fyear_num"] = pd.to_numeric(panel["fyear"], errors="coerce")
    panel = panel[panel["fyear_num"].notna()].copy()
    gv = set(zip(panel.loc[panel["gvkey_norm"].ne(""), "gvkey_norm"], panel.loc[panel["gvkey_norm"].ne(""), "fyear_num"].astype(int)))
    ck = set(zip(panel.loc[panel["cik_norm"].ne(""), "cik_norm"], panel.loc[panel["cik_norm"].ne(""), "fyear_num"].astype(int)))
    return gv, ck


def identifier_valid_for_years(gvkey: str, cik: str, years: set[int], gv_set: set[tuple[str, int]], cik_set: set[tuple[str, int]]) -> bool:
    if not years:
        return bool(gvkey or cik)
    if gvkey and any((gvkey, year) in gv_set for year in years):
        return True
    if cik and any((cik, year) in cik_set for year in years):
        return True
    return False


def load_unresolved_aliases() -> pd.DataFrame:
    usecols = [
        "final_status", "competitor_name", "competitor_name_standardized", "final_competitor_name_standardized",
        "sic_file", "fyear", "filename", "llm_classification", "llm_decision", "llm_confidence",
        "llm_reason", "suggested_alias_name", "suggested_alias_scope", "suggested_alias_reason",
        "generic_score_raw", "generic_score_standardized", "is_likely_generic_category",
    ]
    parts = []
    for chunk_no, chunk in enumerate(pd.read_csv(FINAL_STATUS_LONG, usecols=lambda c: c in usecols, chunksize=CHUNKSIZE, low_memory=False), start=1):
        chunk = chunk[chunk["final_status"].isin(UNRESOLVED_STATUSES)].copy()
        if not chunk.empty:
            parts.append(chunk)
        print(f"Loaded final-status chunk {chunk_no}; unresolved rows accumulated: {sum(len(p) for p in parts):,}", flush=True)
    if not parts:
        raise RuntimeError("No unresolved rows found.")
    df = pd.concat(parts, ignore_index=True)
    df["alias_base"] = df["suggested_alias_name"].map(clean_text)
    df.loc[df["alias_base"].eq(""), "alias_base"] = df.loc[df["alias_base"].eq(""), "competitor_name_standardized"].map(clean_text)
    df.loc[df["alias_base"].eq(""), "alias_base"] = df.loc[df["alias_base"].eq(""), "competitor_name"].map(clean_text)
    df["alias_exact_key"] = df["alias_base"].map(normalize_name)
    df["alias_canonical_key"] = df["alias_base"].map(canonical_name)
    df["record_key"] = df["alias_exact_key"]
    grouped = (
        df.groupby("record_key", dropna=False)
        .agg(
            competitor_name=("competitor_name", lambda s: compact_values(s, 10)),
            competitor_name_standardized=("competitor_name_standardized", lambda s: compact_values(s, 10)),
            suggested_alias_name=("suggested_alias_name", lambda s: compact_values(s, 10)),
            suggested_alias_scope=("suggested_alias_scope", lambda s: compact_values(s, 5)),
            llm_classification=("llm_classification", lambda s: compact_values(s, 5)),
            llm_decision=("llm_decision", lambda s: compact_values(s, 5)),
            llm_confidence=("llm_confidence", "max"),
            llm_reason=("llm_reason", lambda s: compact_values(s, 5)),
            final_status_original=("final_status", lambda s: compact_values(s, 5)),
            generic_score_raw=("generic_score_raw", "max"),
            generic_score_standardized=("generic_score_standardized", "max"),
            is_likely_generic_category=("is_likely_generic_category", lambda s: compact_values(s, 3)),
            frequency=("competitor_name", "size"),
            years=("fyear", compact_years),
            sic_files=("sic_file", lambda s: compact_values(s, 20)),
            example_filename=("filename", lambda s: clean_text(s.dropna().iloc[0]) if len(s.dropna()) else ""),
        )
        .reset_index()
    )
    grouped["alias_exact_key"] = grouped["record_key"]
    grouped["alias_canonical_key"] = grouped["alias_exact_key"].map(canonical_name)
    grouped["residual_year_set"] = grouped["years"].map(parse_years)
    grouped["candidate_input_name"] = grouped["suggested_alias_name"].map(clean_text)
    grouped.loc[grouped["candidate_input_name"].eq(""), "candidate_input_name"] = grouped.loc[
        grouped["candidate_input_name"].eq(""), "competitor_name_standardized"
    ].map(clean_text)
    grouped.loc[grouped["candidate_input_name"].eq(""), "candidate_input_name"] = grouped.loc[
        grouped["candidate_input_name"].eq(""), "competitor_name"
    ].map(clean_text)
    grouped["alias_rough_exact_key"] = rough_name_series(grouped["candidate_input_name"])
    grouped["alias_rough_canonical_key"] = rough_canonical_series(grouped["candidate_input_name"])
    grouped["alias_first_token"] = grouped["candidate_input_name"].map(first_token)
    grouped = grouped[grouped["alias_exact_key"].ne("")].copy()
    grouped["record_id"] = [f"step87_unresolved_{i}" for i in range(1, len(grouped) + 1)]
    return grouped


def candidate_record(alias_row, source_row, source: str, match_rule: str, identifier_basis: str, rank_score: int, in_year: bool | str) -> dict:
    gvkey = normalize_gvkey(source_row.get("gvkey", ""))
    cik = normalize_cik(source_row.get("cik", ""))
    isin = clean_text(source_row.get("isin", "")) or clean_text(source_row.get("primary_isin", ""))
    candidate_name = (
        clean_text(source_row.get("conm", ""))
        or clean_text(source_row.get("companyname", ""))
        or clean_text(source_row.get("company_name", ""))
        or clean_text(source_row.get("auditor_name", ""))
        or clean_text(source_row.get("name", ""))
        or clean_text(source_row.get("CNAME", ""))
        or clean_text(source_row.get("name_raw", ""))
        or clean_text(source_row.get("name_std", ""))
    )
    if candidate_name.replace(".", "", 1).isdigit():
        candidate_name = clean_text(source_row.get("name_raw", "")) or clean_text(source_row.get("company_name", ""))
    if gvkey or cik:
        resolution = "recovered_public_identifier"
    elif isin or source in {"CIQ_COMMON", "REPRISK", "AUDITOR_COMPANY", "BANK_LIST", "IBES_ACTUALS", "TRUCOST"}:
        resolution = "verified_company_no_public_identifier"
        gvkey = "-99999"
        cik = "-99999"
    else:
        resolution = "manual_review_candidate"
    return {
        "record_id": alias_row.get("record_id", ""),
        "record_key": alias_row.get("record_key", ""),
        "competitor_name": alias_row.get("competitor_name", ""),
        "competitor_name_standardized": alias_row.get("competitor_name_standardized", ""),
        "suggested_alias_name": alias_row.get("suggested_alias_name", ""),
        "candidate_input_name": alias_row.get("candidate_input_name", ""),
        "llm_classification": alias_row.get("llm_classification", ""),
        "llm_decision": alias_row.get("llm_decision", ""),
        "llm_confidence": alias_row.get("llm_confidence", ""),
        "final_status_original": alias_row.get("final_status_original", ""),
        "frequency": alias_row.get("frequency", 0),
        "years": alias_row.get("years", ""),
        "sic_files": alias_row.get("sic_files", ""),
        "example_filename": alias_row.get("example_filename", ""),
        "alias_exact_key": alias_row.get("alias_exact_key", ""),
        "alias_canonical_key": alias_row.get("alias_canonical_key", ""),
        "candidate_name": candidate_name,
        "candidate_conm": clean_text(source_row.get("conm", "")) or candidate_name,
        "candidate_bridge_name": clean_text(source_row.get("name_std", "")) or normalize_name(candidate_name),
        "candidate_original_name": clean_text(source_row.get("name_raw", "")) or candidate_name,
        "candidate_gvkey": gvkey,
        "candidate_cik": cik,
        "candidate_isin": isin,
        "candidate_companyid": clean_text(source_row.get("companyid", "")),
        "candidate_permco": clean_text(source_row.get("permco", "")),
        "candidate_ticker": clean_text(source_row.get("ticker", "")) or clean_text(source_row.get("TICKER", "")),
        "candidate_source": source,
        "candidate_match_rule": match_rule,
        "candidate_identifier_basis": identifier_basis,
        "candidate_in_residual_year": in_year,
        "candidate_matching_priority": clean_text(source_row.get("matching_priority", "")),
        "candidate_extension_type": clean_text(source_row.get("extension_type", "")),
        "candidate_sic": clean_text(source_row.get("sic", "")),
        "candidate_rank_score": rank_score,
        "step87_resolution_suggestion": resolution,
    }


def add_year_bridge_candidates(aliases: pd.DataFrame, candidates: list[dict]) -> None:
    exact_keys = {x for x in (set(aliases["alias_exact_key"]) | set(aliases["alias_canonical_key"])) if clean_text(x)}
    alias_by_exact: dict[str, list[pd.Series]] = {}
    alias_by_canon: dict[str, list[pd.Series]] = {}
    for _, row in aliases.iterrows():
        alias_by_exact.setdefault(row["alias_exact_key"], []).append(row)
        alias_by_canon.setdefault(row["alias_canonical_key"], []).append(row)

    usecols = ["name_raw", "name_std", "fyear", "gvkey", "cik", "conm", "source", "alias_type", "extension_type", "matching_priority", "tic", "sic"]
    for chunk in pd.read_csv(YEAR_BRIDGE, usecols=lambda c: c in usecols, chunksize=CHUNKSIZE, low_memory=False):
        chunk["exact_key"] = normalize_name_series(chunk["name_std"])
        chunk["canonical_key"] = canonical_name_series(chunk["name_std"])
        chunk["fyear_num"] = pd.to_numeric(chunk["fyear"], errors="coerce")
        matched = chunk[chunk["exact_key"].isin(exact_keys) | chunk["canonical_key"].isin(exact_keys)].copy()
        for _, br in matched.iterrows():
            year = br.get("fyear_num")
            for alias_row in alias_by_exact.get(br["exact_key"], []):
                in_year = not pd.isna(year) and int(year) in alias_row["residual_year_set"]
                candidates.append(candidate_record(alias_row, br, clean_text(br.get("source")) or "YEAR_BRIDGE", "exact_year_specific" if in_year else "exact_other_year", "GVKEY_CIK_YEAR_BRIDGE", 100 if in_year else 80, in_year))
            for alias_row in alias_by_canon.get(br["canonical_key"], []):
                in_year = not pd.isna(year) and int(year) in alias_row["residual_year_set"]
                candidates.append(candidate_record(alias_row, br, clean_text(br.get("source")) or "YEAR_BRIDGE", "legal_year_specific" if in_year else "legal_other_year", "GVKEY_CIK_YEAR_BRIDGE", 90 if in_year else 70, in_year))


def add_identifier_bridge_candidates(aliases: pd.DataFrame, candidates: list[dict], gv_set: set[tuple[str, int]], cik_set: set[tuple[str, int]]) -> None:
    exact_keys = {x for x in (set(aliases["alias_exact_key"]) | set(aliases["alias_canonical_key"])) if clean_text(x)}
    alias_by_exact = {}
    alias_by_canon = {}
    for _, row in aliases.iterrows():
        alias_by_exact.setdefault(row["alias_exact_key"], []).append(row)
        alias_by_canon.setdefault(row["alias_canonical_key"], []).append(row)

    usecols = ["name_raw", "name_std", "gvkey", "cik", "source", "alias_type", "extension_type", "matching_priority", "tic"]
    for chunk in pd.read_csv(IDENTIFIER_BRIDGE, usecols=lambda c: c in usecols, chunksize=CHUNKSIZE, low_memory=False):
        chunk["exact_key"] = normalize_name_series(chunk["name_std"])
        chunk["canonical_key"] = canonical_name_series(chunk["name_std"])
        matched = chunk[chunk["exact_key"].isin(exact_keys) | chunk["canonical_key"].isin(exact_keys)].copy()
        for _, br in matched.iterrows():
            gvkey = normalize_gvkey(br.get("gvkey"))
            cik = normalize_cik(br.get("cik"))
            for alias_row in alias_by_exact.get(br["exact_key"], []):
                if identifier_valid_for_years(gvkey, cik, alias_row["residual_year_set"], gv_set, cik_set):
                    candidates.append(candidate_record(alias_row, br, "WRDS_LOOKUP", "identifier_exact_validated", "WRDS_IDENTIFIER_YEAR_VALIDATED", 65, True))
            for alias_row in alias_by_canon.get(br["canonical_key"], []):
                if identifier_valid_for_years(gvkey, cik, alias_row["residual_year_set"], gv_set, cik_set):
                    candidates.append(candidate_record(alias_row, br, "WRDS_LOOKUP", "identifier_legal_validated", "WRDS_IDENTIFIER_YEAR_VALIDATED", 60, True))


def add_simple_external_candidates(aliases: pd.DataFrame, candidates: list[dict], path: Path, source: str, name_col: str, usecols: list[str], id_basis: str, base_score: int) -> None:
    if not path.exists():
        return
    exact_keys = {x for x in (set(aliases["alias_rough_exact_key"]) | set(aliases["alias_rough_canonical_key"])) if clean_text(x)}
    first_tokens = {x for x in set(aliases["alias_first_token"]) if clean_text(x)}
    alias_by_exact = {}
    alias_by_canon = {}
    for _, row in aliases.iterrows():
        alias_by_exact.setdefault(row["alias_rough_exact_key"], []).append(row)
        alias_by_canon.setdefault(row["alias_rough_canonical_key"], []).append(row)

    for chunk_no, chunk in enumerate(pd.read_csv(path, usecols=lambda c: c in usecols, chunksize=CHUNKSIZE, low_memory=False), start=1):
        if name_col not in chunk.columns:
            continue
        chunk["_first_token"] = first_token_series(chunk[name_col])
        chunk = chunk[chunk["_first_token"].isin(first_tokens)].copy()
        if chunk.empty:
            if chunk_no % 10 == 0:
                print(f"Scanned {source} chunk {chunk_no}; no first-token candidates", flush=True)
            continue
        chunk["exact_key"] = rough_name_series(chunk[name_col])
        chunk["canonical_key"] = rough_canonical_series(chunk[name_col])
        matched = chunk[chunk["exact_key"].isin(exact_keys) | chunk["canonical_key"].isin(exact_keys)].copy()
        if chunk_no % 10 == 0:
            print(f"Scanned {source} chunk {chunk_no}; matched rows so far source-local not accumulated", flush=True)
        for _, br in matched.iterrows():
            for alias_row in alias_by_exact.get(br["exact_key"], []):
                candidates.append(candidate_record(alias_row, br, source, f"{source.lower()}_exact_name", id_basis, base_score, "not_year_specific"))
            for alias_row in alias_by_canon.get(br["canonical_key"], []):
                candidates.append(candidate_record(alias_row, br, source, f"{source.lower()}_legal_name", id_basis, base_score - 5, "not_year_specific"))


def add_trucost_candidates(aliases: pd.DataFrame, candidates: list[dict]) -> None:
    add_simple_external_candidates(
        aliases,
        candidates,
        TRUCOST,
        "TRUCOST",
        "companyname",
        ["institutionid", "companyid", "gvkey", "ticker", "companyname", "yearfounded"],
        "TRUCOST_GVKEY_OR_NAME",
        72,
    )


def add_recovery_candidates(aliases: pd.DataFrame) -> pd.DataFrame:
    candidates: list[dict] = []
    gv_set, cik_set = validation_sets()
    add_year_bridge_candidates(aliases, candidates)
    print(f"After year bridge: {len(candidates):,} candidates")
    add_identifier_bridge_candidates(aliases, candidates, gv_set, cik_set)
    print(f"After identifier bridge: {len(candidates):,} candidates")
    if RUN_TRUCOST_SCAN:
        add_trucost_candidates(aliases, candidates)
        print(f"After Trucost: {len(candidates):,} candidates")
    else:
        print("Skipped Trucost scan; set RUN_TRUCOST_SCAN=True to include it.", flush=True)
    if RUN_CIQ_COMMON_SCAN:
        add_simple_external_candidates(
            aliases, candidates, CIQ_COMMON, "CIQ_COMMON", "companyname",
            ["companyid", "isin", "companyname", "startdate", "enddate"],
            "CIQ_ISIN_NAME_ONLY", 55
        )
        print(f"After CIQ common: {len(candidates):,} candidates")
    else:
        print("Skipped CIQ common scan by default; set RUN_CIQ_COMMON_SCAN=True for a dedicated large-source pass.", flush=True)
    add_simple_external_candidates(
        aliases, candidates, REPRISK, "REPRISK", "company_name",
        ["primary_isin", "reprisk_id", "company_name", "headquarters_country", "sectors", "url", "isins"],
        "REPRISK_ISIN_NAME_ONLY", 54
    )
    print(f"After RepRisk: {len(candidates):,} candidates")
    add_simple_external_candidates(
        aliases, candidates, AUDITORS, "AUDITOR_COMPANY", "auditor_name",
        ["auditor_key", "auditor_name"],
        "AUDITOR_NAME_ONLY", 52
    )
    print(f"After auditor companies: {len(candidates):,} candidates")
    add_simple_external_candidates(
        aliases, candidates, BANKS, "BANK_LIST", "name",
        ["rssd9001", "permco", "name", "dt_start", "dt_end"],
        "BANK_PERMCO_NAME_ONLY", 51
    )
    print(f"After bank list: {len(candidates):,} candidates")
    add_simple_external_candidates(
        aliases, candidates, ACTUALS, "IBES_ACTUALS", "CNAME",
        ["TICKER", "CUSIP", "OFTIC", "CNAME", "MEASURE", "PDICITY", "ANNDATS"],
        "IBES_CUSIP_TICKER_NAME_ONLY", 50
    )
    print(f"After IBES actuals: {len(candidates):,} candidates")
    if not candidates:
        return pd.DataFrame()
    cand = pd.DataFrame(candidates).drop_duplicates()
    cand["candidate_has_public_identifier"] = cand["candidate_gvkey"].map(valid_id) | cand["candidate_cik"].map(valid_id)
    cand["candidate_is_verified_no_public_id"] = cand["candidate_gvkey"].astype(str).eq("-99999") & cand["candidate_cik"].astype(str).eq("-99999")
    cand["candidate_is_generic_like"] = cand["candidate_name"].map(is_generic_like_name)
    cand.loc[cand["candidate_is_generic_like"], "candidate_rank_score"] = cand.loc[cand["candidate_is_generic_like"], "candidate_rank_score"] - 30
    cand = cand.sort_values(
        ["record_id", "candidate_has_public_identifier", "candidate_rank_score", "candidate_source", "candidate_name"],
        ascending=[True, False, False, True, True],
    )
    cand["candidate_rank"] = cand.groupby("record_id").cumcount() + 1
    return cand


def apply_resolution_reasons(aliases: pd.DataFrame, cand: pd.DataFrame) -> pd.DataFrame:
    if cand.empty:
        best = aliases.copy()
        best["step87_resolution_suggestion"] = "no_external_evidence"
        best["step87_unresolved_reason"] = "no deterministic candidate in bridge or external sources"
        return best

    best = cand[cand["candidate_rank"].eq(1)].copy()
    id_counts = (
        cand.assign(public_id_key=cand["candidate_gvkey"].where(cand["candidate_gvkey"].map(valid_id), cand["candidate_cik"]))
        .groupby("record_id")
        .agg(
            n_candidates=("candidate_name", "size"),
            n_distinct_public_ids=("public_id_key", lambda s: len({clean_text(x) for x in s if valid_id(x)})),
            n_distinct_candidate_names=("candidate_name", lambda s: len({normalize_name(x) for x in s if clean_text(x)})),
            candidate_sources_all=("candidate_source", compact_values),
            candidate_rules_all=("candidate_match_rule", compact_values),
        )
        .reset_index()
    )
    best = best.merge(id_counts, on="record_id", how="left")
    ambiguous = best["n_distinct_public_ids"].fillna(0).astype(int).gt(1)
    best.loc[ambiguous, "step87_resolution_suggestion"] = "manual_review_candidate"
    best["step87_unresolved_reason"] = ""
    best.loc[best["step87_resolution_suggestion"].eq("manual_review_candidate"), "step87_unresolved_reason"] = "multiple plausible identifier-backed candidates"
    best.loc[best["step87_resolution_suggestion"].eq("recovered_public_identifier"), "step87_unresolved_reason"] = "deterministic identifier-backed candidate found"
    best.loc[best["step87_resolution_suggestion"].eq("verified_company_no_public_identifier"), "step87_unresolved_reason"] = "credible external company-name evidence but no public identifier"

    represented = set(best["record_id"])
    missing = aliases[~aliases["record_id"].isin(represented)].copy()
    if not missing.empty:
        missing["step87_resolution_suggestion"] = "no_external_evidence"
        missing["step87_unresolved_reason"] = "no deterministic candidate in bridge or external sources"
        best = pd.concat([best, missing], ignore_index=True, sort=False)
    return best


def write_review_file(best: pd.DataFrame) -> None:
    review_cols = [
        "step87_resolution_suggestion", "step87_unresolved_reason", "frequency",
        "competitor_name", "competitor_name_standardized", "suggested_alias_name",
        "candidate_name", "candidate_conm", "candidate_original_name", "candidate_source",
        "candidate_match_rule", "candidate_identifier_basis", "candidate_gvkey", "candidate_cik",
        "candidate_isin", "candidate_companyid", "candidate_ticker", "candidate_rank_score",
        "n_candidates", "n_distinct_public_ids", "candidate_sources_all", "years", "sic_files",
        "llm_classification", "llm_decision", "llm_confidence", "final_status_original",
        "example_filename",
    ]
    cols = [c for c in review_cols if c in best.columns]
    review = best[cols].copy()
    review["manual_decision"] = ""
    review["approved_name"] = ""
    review["approved_gvkey"] = ""
    review["approved_cik"] = ""
    review["reviewer_notes"] = ""
    review = review.sort_values(["step87_resolution_suggestion", "frequency"], ascending=[True, False])
    review.to_excel(OUT_REVIEW, index=False)

    sample = review.sample(n=min(100, len(review)), random_state=42).copy()
    sample.to_excel(OUT_SAMPLE, index=False)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    aliases = load_unresolved_aliases()
    print(f"Unresolved unique aliases for Step 8.7: {len(aliases):,}")
    print(f"Unresolved mention frequency represented: {aliases['frequency'].sum():,}")

    cand = add_recovery_candidates(aliases)
    if cand.empty:
        cand = pd.DataFrame()
        cand.to_csv(OUT_CANDIDATES, index=False)
    else:
        cand.to_csv(OUT_CANDIDATES, index=False)

    best = apply_resolution_reasons(aliases, cand)
    best.to_csv(OUT_BEST, index=False)

    summary = (
        best.groupby("step87_resolution_suggestion", dropna=False)
        .agg(aliases=("record_id", "size"), frequency_sum=("frequency", "sum"))
        .reset_index()
        .sort_values("frequency_sum", ascending=False)
    )
    summary.to_csv(OUT_SUMMARY, index=False)

    if not cand.empty:
        source_rule = (
            cand.groupby(["step87_resolution_suggestion", "candidate_source", "candidate_match_rule"], dropna=False)
            .agg(aliases=("record_id", "nunique"), candidates=("record_id", "size"), frequency_sum=("frequency", "sum"))
            .reset_index()
            .sort_values("frequency_sum", ascending=False)
        )
        source_rule.to_csv(OUT_SOURCE_RULE, index=False)
    else:
        pd.DataFrame().to_csv(OUT_SOURCE_RULE, index=False)

    reason = (
        best.groupby(["step87_resolution_suggestion", "step87_unresolved_reason"], dropna=False)
        .agg(aliases=("record_id", "size"), frequency_sum=("frequency", "sum"))
        .reset_index()
        .sort_values("frequency_sum", ascending=False)
    )
    reason.to_csv(OUT_REASON, index=False)
    write_review_file(best)

    print("Step 8.7 summary:")
    print(summary.to_string(index=False))
    print(f"Wrote: {OUT_CANDIDATES}")
    print(f"Wrote: {OUT_BEST}")
    print(f"Wrote: {OUT_REVIEW}")


if __name__ == "__main__":
    main()
