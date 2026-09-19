from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd


PROJECT = Path(r"C:\Users\mnasiri\Documents\GitHub\CompetitorNetworkV2")

UNIFIED_MISSING = PROJECT / "data" / "results" / "descriptives" / "missing_review" / "unified_missing_name_review.csv"
YEAR_BRIDGE = PROJECT / "company_alias_bridge_year_specific.csv"
IDENTIFIER_BRIDGE = PROJECT / "company_alias_bridge_identifier_level.csv"
IDENTIFIER_PANEL = PROJECT / "company_identifier_year_panel.csv"
REPRISK = PROJECT / "reprisk11072026.csv"
CAPITAL_IQ = PROJECT / "capital_iq_master.csv"

OUT_DIR = PROJECT / "data" / "results" / "final" / "step86_pre_step7_generic_rescue"
OUT_CANDIDATES = OUT_DIR / "pre_step7_generic_rescue_candidates.csv"
OUT_BEST = OUT_DIR / "pre_step7_generic_rescue_best_candidate.csv"
OUT_SUMMARY = OUT_DIR / "pre_step7_generic_rescue_summary.csv"
OUT_SAMPLE = OUT_DIR / "pre_step7_generic_rescue_review_sample100.xlsx"

CHUNKSIZE = 500_000
RUN_CAPITAL_IQ_SCAN = False


STANDARDIZATION_MAP = {
    "COMPANY": "CO", "CORPORATION": "CORP", "INCORPORATED": "INC", "LIMITED": "LTD",
    "HOLDING": "HLDG", "HOLDINGS": "HLDG", "HLDGS": "HLDG", "GROUP": "GRP", "GROUPE": "GRP",
    "TECHNOLOGY": "TECH", "TECHNOLOGIES": "TECH", "SYSTEM": "SYS", "SYSTEMS": "SYS",
    "SERVICE": "SERV", "SERVICES": "SERV", "SOLUTION": "SOLUT", "SOLUTIONS": "SOLUT",
    "INTERNATIONAL": "INTL", "MANUFACTURING": "MFG", "INDUSTRIES": "IND",
    "INDUSTRY": "IND", "INDUSTRIAL": "IND", "PHARMACEUTICALS": "PHARM",
    "PHARMACEUTICAL": "PHARM", "PHARMA": "PHARM", "ELECTRONICS": "ELECTRONIC",
    "ELECTRO": "ELECTRONIC", "ELEC": "ELECTRONIC", "COMMUNICATIONS": "COMM",
    "COMMUNICATION": "COMM", "HEALTHCARE": "HLTHCR", "HEALTH": "HLTH",
}

LEGAL_SUFFIXES = {
    "INC", "CORP", "CO", "LTD", "LLC", "PLC", "NV", "SA", "AG", "BV", "GMBH",
    "LP", "LLP", "KGAA", "OY", "OYJ", "SAS", "SRL", "SARL", "SPA", "PTE",
    "PVT", "SL", "SAU", "AB", "AS", "ASA", "BVBA", "KK", "LTDA", "PTY", "BHD",
    "SDN", "PJSC", "JSC", "OAO", "ZAO", "AO",
}

GENERIC_CATEGORY_TERMS = {
    "PROVIDERS", "PROVIDER", "COMPETITORS", "COMPETITOR", "COMPANIES", "COMPANY",
    "MANUFACTURERS", "MANUFACTURER", "SUPPLIERS", "SUPPLIER", "DISTRIBUTORS",
    "DISTRIBUTOR", "BANKS", "INSURERS", "INSURANCE", "WIRELESS", "PHARMACEUTICAL",
    "PHARMACEUTICALS", "FINANCIAL", "INSTITUTIONS", "OTHERS", "OTHER", "MAJOR",
    "SMALLER", "LOCAL", "REGIONAL", "NATIONAL", "COMMERCIAL", "PRIVATE",
    "RETAILERS", "RETAILER", "LENDERS", "LENDER", "HOSPITALS", "AGENCIES",
    "FUNDS", "FUND", "TRUSTS", "TRUST",
}

PLURAL_CATEGORY_ENDINGS = {
    "PROVIDERS", "SUPPLIERS", "COMPETITORS", "COMPANIES", "BANKS",
    "INSTITUTIONS", "RETAILERS", "LENDERS", "HOSPITALS", "AGENCIES",
    "MANUFACTURERS", "DISTRIBUTORS", "INSURERS", "FUNDS", "TRUSTS",
}

PROPER_COMPANY_SIGNALS = {
    "INC", "CORP", "CO", "LTD", "LLC", "PLC", "NV", "SA", "AG", "BV", "GMBH",
    "LP", "LLP", "BANK", "BANCORP", "MORTGAGE", "SYSTEMS", "SYS", "SOLUTIONS",
    "SOLUT", "PRODUCTS", "SERVICES", "HEALTH", "HLTH", "HOSPITAL", "TECHNOLOGIES",
    "TECH", "COMPUTER", "COMPUTERS", "COMMERCIAL", "LIFE",
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


def canonical_name(value) -> str:
    tokens = normalize_name(value).split()
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def parse_years(value) -> set[int]:
    text = clean_text(value)
    years = set()
    for token in re.split(r"[^0-9]+", text):
        if len(token) == 4:
            try:
                years.add(int(token))
            except ValueError:
                pass
    return years


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


def is_likely_category_phrase(name: str) -> bool:
    tokens = normalize_name(name).split()
    if not tokens:
        return True
    if len(tokens) <= 2 and all(tok in GENERIC_CATEGORY_TERMS for tok in tokens):
        return True
    if tokens[-1] in PLURAL_CATEGORY_ENDINGS:
        return True
    return False


def is_lowercase_generic_category_phrase(name: str) -> bool:
    raw = clean_text(name)
    if not raw:
        return False
    first_alpha = next((ch for ch in raw if ch.isalpha()), "")
    if first_alpha and not first_alpha.islower():
        return False
    tokens = normalize_name(raw).split()
    if not tokens:
        return False
    return tokens[-1] in PLURAL_CATEGORY_ENDINGS or all(tok in GENERIC_CATEGORY_TERMS for tok in tokens)


def has_proper_company_signal(name: str) -> bool:
    tokens = set(normalize_name(name).split())
    distinctive = [tok for tok in tokens if tok not in GENERIC_CATEGORY_TERMS and tok not in LEGAL_SUFFIXES]
    return bool(tokens & PROPER_COMPANY_SIGNALS) and len(distinctive) >= 1


def load_generic_drops() -> pd.DataFrame:
    df = pd.read_csv(UNIFIED_MISSING, low_memory=False)
    action_col = "suggested_action" if "suggested_action" in df.columns else "recommended_action"
    generic = df[
        df[action_col].fillna("").astype(str).eq("review_remove_generic")
        | df.get("is_likely_generic_category", False).astype(str).str.lower().eq("true")
    ].copy()
    generic["alias_exact_key"] = generic["competitor_name_standardized"].map(normalize_name)
    generic.loc[generic["alias_exact_key"].eq(""), "alias_exact_key"] = generic.loc[
        generic["alias_exact_key"].eq(""), "competitor_name"
    ].map(normalize_name)
    generic["alias_canonical_key"] = generic["alias_exact_key"].map(canonical_name)
    generic["residual_year_set"] = generic["years"].map(parse_years)
    generic["is_likely_category_phrase_86"] = generic["competitor_name"].map(is_likely_category_phrase)
    generic["is_lowercase_generic_category_phrase_86"] = generic["competitor_name"].map(is_lowercase_generic_category_phrase)
    generic["has_proper_company_signal_86"] = generic["competitor_name"].map(has_proper_company_signal)
    generic = generic[generic["alias_exact_key"] != ""].copy()
    if "record_id" not in generic.columns:
        generic["record_id"] = [f"pre_step7_generic_{i}" for i in range(1, len(generic) + 1)]
    return generic


def validation_sets() -> tuple[set[tuple[str, int]], set[tuple[str, int]]]:
    panel = pd.read_csv(IDENTIFIER_PANEL, low_memory=False)
    panel["gvkey_norm"] = panel["gvkey"].map(normalize_gvkey)
    panel["cik_norm"] = panel["cik"].map(normalize_cik)
    panel["fyear"] = pd.to_numeric(panel["fyear"], errors="coerce").astype("Int64")
    gv = set(zip(panel.loc[panel["gvkey_norm"].ne(""), "gvkey_norm"], panel.loc[panel["gvkey_norm"].ne(""), "fyear"].astype(int)))
    ck = set(zip(panel.loc[panel["cik_norm"].ne(""), "cik_norm"], panel.loc[panel["cik_norm"].ne(""), "fyear"].astype(int)))
    return gv, ck


def candidate_record(alias_row, bridge_row, source: str, match_rule: str, identifier_basis: str, candidate_in_year: bool) -> dict:
    gvkey = normalize_gvkey(bridge_row.get("gvkey", ""))
    cik = normalize_cik(bridge_row.get("cik", ""))
    company_name = clean_text(bridge_row.get("conm", "")) or clean_text(bridge_row.get("name_raw", "")) or clean_text(bridge_row.get("company_name", ""))
    if not company_name or company_name.replace(".", "", 1).isdigit():
        company_name = clean_text(bridge_row.get("name_std", "")) or clean_text(bridge_row.get("name_raw", ""))
    if gvkey or cik:
        rescue_status = "rescue_identifier_backed_exact"
    elif identifier_basis in {"REPRISK_NAME_ONLY", "CAPITAL_IQ_NAME_ONLY"}:
        rescue_status = "rescue_verified_company_no_public_id"
    else:
        rescue_status = "not_rescued_no_usable_identifier"
    return {
        "record_id": alias_row.get("record_id", ""),
        "competitor_name": alias_row.get("competitor_name", ""),
        "competitor_name_standardized": alias_row.get("competitor_name_standardized", ""),
        "frequency": alias_row.get("frequency", ""),
        "years": alias_row.get("years", ""),
        "alias_exact_key": alias_row.get("alias_exact_key", ""),
        "alias_canonical_key": alias_row.get("alias_canonical_key", ""),
        "candidate_name": company_name,
        "candidate_bridge_name": clean_text(bridge_row.get("name_std", "")) or normalize_name(company_name),
        "candidate_original_name": clean_text(bridge_row.get("name_raw", "")) or clean_text(bridge_row.get("company_name", "")) or company_name,
        "candidate_gvkey": gvkey if gvkey else ("-99999" if rescue_status == "rescue_verified_company_no_public_id" else ""),
        "candidate_cik": cik if cik else ("-99999" if rescue_status == "rescue_verified_company_no_public_id" else ""),
        "candidate_source": source,
        "candidate_match_rule": match_rule,
        "candidate_identifier_basis": identifier_basis,
        "candidate_in_residual_year": candidate_in_year,
        "rescue_status": rescue_status,
        "is_likely_category_phrase_86": alias_row.get("is_likely_category_phrase_86", ""),
        "is_lowercase_generic_category_phrase_86": alias_row.get("is_lowercase_generic_category_phrase_86", ""),
        "has_proper_company_signal_86": alias_row.get("has_proper_company_signal_86", ""),
    }


def add_year_bridge_candidates(aliases: pd.DataFrame, candidates: list[dict]) -> None:
    exact_keys = set(aliases["alias_exact_key"]) | set(aliases["alias_canonical_key"])
    alias_by_exact = {}
    alias_by_canon = {}
    for _, row in aliases.iterrows():
        alias_by_exact.setdefault(row["alias_exact_key"], []).append(row)
        alias_by_canon.setdefault(row["alias_canonical_key"], []).append(row)

    usecols = ["name_raw", "name_std", "fyear", "gvkey", "cik", "conm", "source", "alias_type", "extension_type", "matching_priority"]
    for chunk in pd.read_csv(YEAR_BRIDGE, usecols=lambda c: c in usecols, chunksize=CHUNKSIZE, low_memory=False):
        chunk["exact_key"] = chunk["name_std"].map(normalize_name)
        chunk["canonical_key"] = chunk["name_std"].map(canonical_name)
        chunk["fyear_num"] = pd.to_numeric(chunk["fyear"], errors="coerce")
        matched = chunk[chunk["exact_key"].isin(exact_keys) | chunk["canonical_key"].isin(exact_keys)].copy()
        for _, br in matched.iterrows():
            br_year = int(br["fyear_num"]) if not pd.isna(br["fyear_num"]) else None
            for alias_row in alias_by_exact.get(br["exact_key"], []):
                if br_year is not None and br_year in alias_row["residual_year_set"]:
                    candidates.append(candidate_record(alias_row, br, clean_text(br.get("source")) or "YEAR_SPECIFIC_BRIDGE", "exact_year_specific", "GVKEY_CIK", True))
            for alias_row in alias_by_canon.get(br["canonical_key"], []):
                if br_year is not None and br_year in alias_row["residual_year_set"] and br["canonical_key"] != br["exact_key"]:
                    candidates.append(candidate_record(alias_row, br, clean_text(br.get("source")) or "YEAR_SPECIFIC_BRIDGE", "legal_year_specific", "GVKEY_CIK", True))


def add_identifier_bridge_candidates(aliases: pd.DataFrame, candidates: list[dict], valid_gv: set[tuple[str, int]], valid_ck: set[tuple[str, int]]) -> None:
    exact_keys = set(aliases["alias_exact_key"]) | set(aliases["alias_canonical_key"])
    alias_by_exact = {}
    alias_by_canon = {}
    for _, row in aliases.iterrows():
        alias_by_exact.setdefault(row["alias_exact_key"], []).append(row)
        alias_by_canon.setdefault(row["alias_canonical_key"], []).append(row)
    bridge = pd.read_csv(IDENTIFIER_BRIDGE, low_memory=False)
    bridge["exact_key"] = bridge["name_std"].map(normalize_name)
    bridge["canonical_key"] = bridge["name_std"].map(canonical_name)
    bridge = bridge[bridge["exact_key"].isin(exact_keys) | bridge["canonical_key"].isin(exact_keys)].copy()
    for _, br in bridge.iterrows():
        gv = normalize_gvkey(br.get("gvkey", ""))
        ck = normalize_cik(br.get("cik", ""))
        for key, rule, alias_map in [
            (br["exact_key"], "identifier_exact_validated", alias_by_exact),
            (br["canonical_key"], "identifier_legal_validated", alias_by_canon),
        ]:
            for alias_row in alias_map.get(key, []):
                years = alias_row["residual_year_set"]
                valid = any((gv and (gv, y) in valid_gv) or (ck and (ck, y) in valid_ck) for y in years)
                if valid:
                    candidates.append(candidate_record(alias_row, br, clean_text(br.get("source")) or "IDENTIFIER_LEVEL_BRIDGE", rule, "GVKEY_CIK_VALIDATED", True))


def add_reprisk_candidates(aliases: pd.DataFrame, candidates: list[dict]) -> None:
    keys = set(aliases["alias_exact_key"]) | set(aliases["alias_canonical_key"])
    alias_by_exact = {}
    alias_by_canon = {}
    for _, row in aliases.iterrows():
        alias_by_exact.setdefault(row["alias_exact_key"], []).append(row)
        alias_by_canon.setdefault(row["alias_canonical_key"], []).append(row)
    rep = pd.read_csv(REPRISK, usecols=["primary_isin", "reprisk_id", "company_name", "headquarters_country", "sectors"], low_memory=False)
    rep["exact_key"] = rep["company_name"].map(normalize_name)
    rep["canonical_key"] = rep["company_name"].map(canonical_name)
    rep = rep[rep["exact_key"].isin(keys) | rep["canonical_key"].isin(keys)].copy()
    for _, br in rep.iterrows():
        row_dict = {
            "name_std": br["exact_key"],
            "name_raw": br["company_name"],
            "company_name": br["company_name"],
            "gvkey": "",
            "cik": "",
        }
        for alias_row in alias_by_exact.get(br["exact_key"], []):
            rec = candidate_record(alias_row, row_dict, "REPRISK", "reprisk_exact_name", "REPRISK_NAME_ONLY", False)
            rec["candidate_reprisk_id"] = clean_text(br.get("reprisk_id"))
            rec["candidate_isin"] = clean_text(br.get("primary_isin"))
            candidates.append(rec)
        for alias_row in alias_by_canon.get(br["canonical_key"], []):
            rec = candidate_record(alias_row, row_dict, "REPRISK", "reprisk_legal_name", "REPRISK_NAME_ONLY", False)
            rec["candidate_reprisk_id"] = clean_text(br.get("reprisk_id"))
            rec["candidate_isin"] = clean_text(br.get("primary_isin"))
            candidates.append(rec)


def add_capital_iq_candidates(aliases: pd.DataFrame, candidates: list[dict]) -> None:
    keys = set(aliases["alias_exact_key"]) | set(aliases["alias_canonical_key"])
    ticker_keys = {k for k in aliases["alias_exact_key"] if re.fullmatch(r"[A-Z0-9.]{1,6}", k)}
    alias_by_exact = {}
    alias_by_canon = {}
    for _, row in aliases.iterrows():
        alias_by_exact.setdefault(row["alias_exact_key"], []).append(row)
        alias_by_canon.setdefault(row["alias_canonical_key"], []).append(row)

    company_to_gvkey = {}
    company_to_name = {}
    usecols = ["symboltypecat", "companyid", "companyname", "symbolvalue", "startdate", "enddate", "activeflag"]
    for chunk in pd.read_csv(CAPITAL_IQ, usecols=lambda c: c in usecols, chunksize=CHUNKSIZE, low_memory=False):
        gv = chunk[chunk["symboltypecat"].fillna("").astype(str).str.lower().eq("gvkey")].copy()
        for _, row in gv.iterrows():
            companyid = clean_text(row.get("companyid"))
            gvkey = normalize_gvkey(row.get("symbolvalue"))
            if companyid and gvkey:
                company_to_gvkey.setdefault(companyid, set()).add(gvkey)
                company_to_name.setdefault(companyid, clean_text(row.get("companyname")))

    for chunk in pd.read_csv(CAPITAL_IQ, usecols=lambda c: c in usecols, chunksize=CHUNKSIZE, low_memory=False):
        chunk["symboltypecat_l"] = chunk["symboltypecat"].fillna("").astype(str).str.lower()
        names = chunk[chunk["companyname"].notna()].copy()
        names["exact_key"] = names["companyname"].map(normalize_name)
        names["canonical_key"] = names["companyname"].map(canonical_name)
        names = names[names["exact_key"].isin(keys) | names["canonical_key"].isin(keys)].copy()
        for _, br in names.iterrows():
            companyid = clean_text(br.get("companyid"))
            gvkeys = sorted(company_to_gvkey.get(companyid, set()))
            row_dict = {"name_std": br["exact_key"], "name_raw": br["companyname"], "company_name": br["companyname"], "gvkey": gvkeys[0] if len(gvkeys) == 1 else "", "cik": ""}
            basis = "CAPITAL_IQ_GVKEY" if len(gvkeys) == 1 else "CAPITAL_IQ_NAME_ONLY"
            for alias_row in alias_by_exact.get(br["exact_key"], []):
                candidates.append(candidate_record(alias_row, row_dict, "CAPITAL_IQ", "capital_iq_exact_company_name", basis, False))
            for alias_row in alias_by_canon.get(br["canonical_key"], []):
                candidates.append(candidate_record(alias_row, row_dict, "CAPITAL_IQ", "capital_iq_legal_company_name", basis, False))
        tick = chunk[chunk["symboltypecat_l"].eq("ticker")].copy()
        tick["ticker_key"] = tick["symbolvalue"].map(normalize_name)
        tick = tick[tick["ticker_key"].isin(ticker_keys)].copy()
        for _, br in tick.iterrows():
            companyid = clean_text(br.get("companyid"))
            gvkeys = sorted(company_to_gvkey.get(companyid, set()))
            if len(gvkeys) != 1:
                continue
            for alias_row in alias_by_exact.get(br["ticker_key"], []):
                row_dict = {"name_std": normalize_name(company_to_name.get(companyid, "")), "name_raw": company_to_name.get(companyid, ""), "company_name": company_to_name.get(companyid, ""), "gvkey": gvkeys[0], "cik": ""}
                candidates.append(candidate_record(alias_row, row_dict, "CAPITAL_IQ", "capital_iq_exact_ticker", "CAPITAL_IQ_TICKER_GVKEY", False))


def rank_candidates(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return candidates
    source_score = {"DISCERN": 50, "COMPUSTAT_US": 45, "COMPUSTAT_GLOBAL": 35, "CAPITAL_IQ": 25, "REPRISK": 20, "WRDS_LOOKUP": 10}
    rule_score = {
        "exact_year_specific": 80, "legal_year_specific": 70,
        "identifier_exact_validated": 55, "identifier_legal_validated": 45,
        "capital_iq_exact_company_name": 40, "capital_iq_legal_company_name": 35,
        "capital_iq_exact_ticker": 35, "reprisk_exact_name": 30, "reprisk_legal_name": 25,
    }
    candidates["rank_score"] = (
        candidates["candidate_source"].map(source_score).fillna(0)
        + candidates["candidate_match_rule"].map(rule_score).fillna(0)
        + candidates["candidate_gvkey"].map(lambda x: 20 if valid_id(x) else 0)
        + candidates["candidate_cik"].map(lambda x: 10 if valid_id(x) else 0)
    )
    candidates = candidates.sort_values(["record_id", "rank_score"], ascending=[True, False])
    candidates["candidate_rank"] = candidates.groupby("record_id").cumcount() + 1
    return candidates


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    aliases = load_generic_drops()
    candidates = []
    valid_gv, valid_ck = validation_sets()
    print(f"Pre-Step 7 generic-drop aliases: {len(aliases):,}")

    add_year_bridge_candidates(aliases, candidates)
    print(f"After year bridge candidates: {len(candidates):,}")
    add_identifier_bridge_candidates(aliases, candidates, valid_gv, valid_ck)
    print(f"After identifier bridge candidates: {len(candidates):,}")
    add_reprisk_candidates(aliases, candidates)
    print(f"After RepRisk candidates: {len(candidates):,}")
    if RUN_CAPITAL_IQ_SCAN:
        add_capital_iq_candidates(aliases, candidates)
        print(f"After Capital IQ candidates: {len(candidates):,}")
    else:
        print("Skipped Capital IQ full scan by default; set RUN_CAPITAL_IQ_SCAN=True to include it.")

    cand = pd.DataFrame(candidates)
    if cand.empty:
        cand = pd.DataFrame(columns=["record_id", "competitor_name", "rescue_status"])
    cand = cand.drop_duplicates()
    cand = rank_candidates(cand)
    cand.to_csv(OUT_CANDIDATES, index=False)

    best = cand.sort_values(["record_id", "candidate_rank"]).drop_duplicates("record_id", keep="first")
    aliases_out = aliases.merge(best, on=["record_id", "competitor_name", "competitor_name_standardized", "frequency", "years", "alias_exact_key", "alias_canonical_key", "is_likely_category_phrase_86", "is_lowercase_generic_category_phrase_86", "has_proper_company_signal_86"], how="left", suffixes=("", "_candidate"))
    aliases_out["rescue_status"] = aliases_out["rescue_status"].fillna("not_rescued_no_evidence")
    generic_mask = (
        aliases_out["is_likely_category_phrase_86"].fillna(False).astype(bool)
        | aliases_out["is_lowercase_generic_category_phrase_86"].fillna(False).astype(bool)
    )
    aliases_out.loc[generic_mask, "rescue_status"] = "not_rescued_generic_category"
    candidate_clear_cols = [
        col for col in aliases_out.columns
        if col.startswith("candidate_") or col in {"rank_score"}
    ]
    aliases_out.loc[generic_mask, candidate_clear_cols] = pd.NA
    aliases_out.to_csv(OUT_BEST, index=False)

    summary = (
        aliases_out.groupby(["rescue_status"], dropna=False)
        .agg(
            aliases=("record_id", "size"),
            frequency_sum=("frequency", lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum()),
            unique_names=("competitor_name", "nunique"),
        )
        .reset_index()
        .sort_values("aliases", ascending=False)
    )
    source_summary = (
        aliases_out.groupby(["rescue_status", "candidate_source", "candidate_match_rule"], dropna=False)
        .agg(aliases=("record_id", "size"))
        .reset_index()
    )
    summary.to_csv(OUT_SUMMARY, index=False)
    source_summary.to_csv(OUT_DIR / "pre_step7_generic_rescue_source_rule_summary.csv", index=False)

    sample_pool = aliases_out[aliases_out["rescue_status"].str.startswith("rescue_")].copy()
    if sample_pool.empty:
        sample_pool = aliases_out.copy()
    sample = sample_pool.sample(n=min(100, len(sample_pool)), random_state=42).copy()
    sample["manual_validation"] = ""
    sample["notes"] = ""
    sample.to_excel(OUT_SAMPLE, index=False)

    print(f"Wrote: {OUT_CANDIDATES}")
    print(f"Wrote: {OUT_BEST}")
    print(f"Wrote: {OUT_SUMMARY}")
    print(f"Wrote: {OUT_SAMPLE}")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
