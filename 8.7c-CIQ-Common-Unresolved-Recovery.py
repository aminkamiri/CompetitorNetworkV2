from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd


PROJECT = Path(r"C:\Users\mnasiri\Documents\GitHub\CompetitorNetworkV2")
STEP87_DIR = PROJECT / "data" / "results" / "final" / "step87_unresolved_recovery"
CIQ_COMMON = PROJECT / "ciq_common.csv"

STEP87_REFINED = STEP87_DIR / "step87_unresolved_recovery_best_candidate_refined.csv"
STEP87_ORIGINAL = STEP87_DIR / "step87_unresolved_recovery_best_candidate.csv"
CIQ_GVKEY = PROJECT / "CIQ-gvkey.csv"

OUT_CANDIDATES = STEP87_DIR / "step87c_ciq_common_unresolved_candidates.csv"
OUT_BEST = STEP87_DIR / "step87c_ciq_common_unresolved_best_candidate.csv"
OUT_SUMMARY = STEP87_DIR / "step87c_ciq_common_unresolved_summary.csv"
OUT_SOURCE_RULE = STEP87_DIR / "step87c_ciq_common_unresolved_source_rule_summary.csv"
OUT_GVKEY_SUMMARY = STEP87_DIR / "step87c_ciq_common_gvkey_crosswalk_summary.csv"

CHUNKSIZE = 500_000

LEGAL_SUFFIXES = {
    "INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC",
    "AG", "SA", "SE", "NV", "BV", "GMBH", "LLC", "LP", "LLP", "SPA", "AB",
    "AS", "SARL", "SRL", "THE",
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


def rough_name(value) -> str:
    text = normalize_unicode(clean_text(value)).upper()
    text = re.sub(r"\bAND\s+COMPANY\b", " CO ", text)
    text = re.sub(r"\bAND\s+CO\b", " CO ", text)
    text = re.sub(r"&\s*COMPANY\b", " CO ", text)
    text = re.sub(r"&\s*CO\b", " CO ", text)
    text = text.replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


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


def rough_canonical(value) -> str:
    tokens = rough_name(value).split()
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def rough_canonical_series(series: pd.Series) -> pd.Series:
    out = rough_name_series(series)
    previous = None
    while previous is None or not out.equals(previous):
        previous = out.copy()
        for suffix in LEGAL_SUFFIXES:
            out = out.str.replace(rf"\s+{re.escape(suffix)}$", "", regex=True)
        out = out.str.strip()
    return out


def first_token(value: str) -> str:
    match = re.search(r"[A-Z0-9]+", normalize_unicode(clean_text(value)).upper())
    return match.group(0) if match else ""


def first_token_series(series: pd.Series) -> pd.Series:
    out = series.fillna("").astype(str).str.strip()
    out = out.mask(out.str.lower().isin({"nan", "none", "null", "<na>"}), "")
    out = out.str.normalize("NFKD").str.encode("ascii", errors="ignore").str.decode("ascii")
    out = out.str.upper().str.extract(r"([A-Z0-9]+)", expand=False).fillna("")
    return out


def parse_years(value) -> set[int]:
    years = set()
    for token in re.split(r"[^0-9]+", clean_text(value)):
        if len(token) == 4:
            try:
                years.add(int(token))
            except ValueError:
                pass
    return years


def year_overlap(start, end, years: set[int]) -> str:
    if not years:
        return "unknown_no_residual_years"
    start_dt = pd.to_datetime(start, errors="coerce")
    end_dt = pd.to_datetime(end, errors="coerce")
    start_year = int(start_dt.year) if not pd.isna(start_dt) else None
    end_year = int(end_dt.year) if not pd.isna(end_dt) else 2026
    if start_year is None and end_year is None:
        return "unknown_no_ciq_dates"
    if start_year is None:
        start_year = min(years)
    if any(start_year <= year <= end_year for year in years):
        return "date_overlaps_residual_year"
    return "date_outside_residual_year"


def load_aliases() -> pd.DataFrame:
    refined = pd.read_csv(STEP87_REFINED, low_memory=False)
    original = pd.read_csv(STEP87_ORIGINAL, low_memory=False)
    no_external = original[
        original["step87_resolution_suggestion"].fillna("").astype(str).eq("no_external_evidence")
    ].copy()
    no_external["step87_refined_resolution_suggestion"] = "no_external_evidence"
    no_external = no_external[~no_external["record_id"].isin(set(refined["record_id"]))].copy()
    df = pd.concat([refined, no_external], ignore_index=True, sort=False)
    for col in ["alias_exact_key", "alias_canonical_key", "candidate_input_name", "years"]:
        if col not in df.columns:
            df[col] = ""
    df["ciq_alias_exact_key"] = df["alias_exact_key"].map(rough_name)
    df.loc[df["ciq_alias_exact_key"].eq(""), "ciq_alias_exact_key"] = df.loc[
        df["ciq_alias_exact_key"].eq(""), "candidate_input_name"
    ].map(rough_name)
    df["ciq_alias_canonical_key"] = df["alias_canonical_key"].map(rough_name)
    df.loc[df["ciq_alias_canonical_key"].eq(""), "ciq_alias_canonical_key"] = df.loc[
        df["ciq_alias_canonical_key"].eq(""), "candidate_input_name"
    ].map(rough_canonical)
    df["ciq_alias_first_token"] = df["ciq_alias_exact_key"].map(first_token)
    df["residual_year_set"] = df["years"].map(parse_years)
    return df[df["ciq_alias_exact_key"].ne("")].copy()


def load_ciq_gvkey_crosswalk() -> pd.DataFrame:
    if not CIQ_GVKEY.exists():
        return pd.DataFrame(columns=["companyid_norm", "ciq_crosswalk_gvkey", "ciq_crosswalk_companyname", "ciq_crosswalk_startdate", "ciq_crosswalk_enddate"])
    xw = pd.read_csv(CIQ_GVKEY, low_memory=False)
    xw["companyid_norm"] = pd.to_numeric(xw.get("companyid"), errors="coerce").astype("Int64").astype(str).replace("<NA>", "")
    xw["ciq_crosswalk_gvkey"] = pd.to_numeric(xw.get("gvkey"), errors="coerce").astype("Int64").astype(str).replace("<NA>", "")
    xw = xw[xw["companyid_norm"].ne("") & xw["ciq_crosswalk_gvkey"].ne("")].copy()
    xw = xw.rename(
        columns={
            "companyname": "ciq_crosswalk_companyname",
            "startdate": "ciq_crosswalk_startdate",
            "enddate": "ciq_crosswalk_enddate",
        }
    )
    return xw[
        ["companyid_norm", "ciq_crosswalk_gvkey", "ciq_crosswalk_companyname", "ciq_crosswalk_startdate", "ciq_crosswalk_enddate"]
    ].drop_duplicates()


def attach_ciq_gvkey(candidates: pd.DataFrame) -> pd.DataFrame:
    if candidates.empty:
        return candidates
    xw = load_ciq_gvkey_crosswalk()
    candidates = candidates.copy()
    candidates["companyid_norm"] = pd.to_numeric(candidates["candidate_companyid"], errors="coerce").astype("Int64").astype(str).replace("<NA>", "")
    if xw.empty:
        candidates["ciq_has_gvkey_crosswalk"] = False
        candidates["ciq_crosswalk_gvkey"] = ""
        return candidates
    out = candidates.merge(xw, on="companyid_norm", how="left")
    out["ciq_has_gvkey_crosswalk"] = out["ciq_crosswalk_gvkey"].fillna("").astype(str).ne("")
    out["ciq_gvkey_date_overlap"] = out.apply(
        lambda r: year_overlap(r.get("ciq_crosswalk_startdate", ""), r.get("ciq_crosswalk_enddate", ""), parse_years(r.get("years", ""))),
        axis=1,
    )
    out["ciq_identifier_upgrade_candidate"] = (
        out["ciq_has_gvkey_crosswalk"]
        & out["candidate_date_overlap"].eq("date_overlaps_residual_year")
    )
    return out


def scan_ciq_common(aliases: pd.DataFrame) -> pd.DataFrame:
    alias_by_exact: dict[str, list[pd.Series]] = {}
    alias_by_canon: dict[str, list[pd.Series]] = {}
    for _, row in aliases.iterrows():
        alias_by_exact.setdefault(row["ciq_alias_exact_key"], []).append(row)
        alias_by_canon.setdefault(row["ciq_alias_canonical_key"], []).append(row)
    keys = {k for k in set(alias_by_exact) | set(alias_by_canon) if k}
    first_tokens = {x for x in set(aliases["ciq_alias_first_token"]) if x}

    candidates: list[dict] = []
    usecols = ["companyid", "isin", "companyname", "startdate", "enddate"]
    for chunk_no, chunk in enumerate(
        pd.read_csv(CIQ_COMMON, usecols=lambda c: c in usecols, chunksize=CHUNKSIZE, low_memory=False),
        start=1,
    ):
        chunk["_first_token"] = first_token_series(chunk["companyname"])
        chunk = chunk[chunk["_first_token"].isin(first_tokens)].copy()
        if chunk.empty:
            if chunk_no % 10 == 0:
                print(f"Scanned CIQ_COMMON chunk {chunk_no}; no first-token candidates", flush=True)
            continue
        chunk["exact_key"] = rough_name_series(chunk["companyname"])
        chunk["canonical_key"] = rough_canonical_series(chunk["companyname"])
        matched = chunk[chunk["exact_key"].isin(keys) | chunk["canonical_key"].isin(keys)].copy()
        for _, ciq in matched.iterrows():
            for alias in alias_by_exact.get(ciq["exact_key"], []):
                candidates.append(make_candidate(alias, ciq, "ciq_common_exact_name"))
            for alias in alias_by_canon.get(ciq["canonical_key"], []):
                candidates.append(make_candidate(alias, ciq, "ciq_common_legal_name"))
        if chunk_no % 10 == 0:
            print(f"Scanned CIQ_COMMON chunk {chunk_no}; candidates so far {len(candidates):,}", flush=True)
    if not candidates:
        return pd.DataFrame()
    out = pd.DataFrame(candidates).drop_duplicates(
        ["record_id", "candidate_companyid", "candidate_isin", "candidate_name", "candidate_match_rule"]
    )
    out = attach_ciq_gvkey(out)
    out["candidate_date_overlap_rank"] = out["candidate_date_overlap"].map(
        {"date_overlaps_residual_year": 2, "unknown_no_ciq_dates": 1, "unknown_no_residual_years": 1}
    ).fillna(0)
    out["candidate_match_rank"] = out["candidate_match_rule"].map({"ciq_common_exact_name": 2, "ciq_common_legal_name": 1}).fillna(0)
    out["candidate_gvkey_rank"] = out.get("ciq_identifier_upgrade_candidate", False).astype(int)
    out = out.sort_values(
        ["record_id", "candidate_gvkey_rank", "candidate_date_overlap_rank", "candidate_match_rank", "candidate_name"],
        ascending=[True, False, False, False, True],
    )
    out["ciq_candidate_rank"] = out.groupby("record_id").cumcount() + 1
    return out


def make_candidate(alias: pd.Series, ciq: pd.Series, match_rule: str) -> dict:
    years = alias.get("residual_year_set", set())
    return {
        "record_id": alias.get("record_id", ""),
        "record_key": alias.get("record_key", ""),
        "frequency": alias.get("frequency", ""),
        "years": alias.get("years", ""),
        "competitor_name": alias.get("competitor_name", ""),
        "suggested_alias_name": alias.get("suggested_alias_name", ""),
        "candidate_input_name": alias.get("candidate_input_name", ""),
        "step87_refined_resolution_suggestion": alias.get("step87_refined_resolution_suggestion", ""),
        "step87_resolution_suggestion": alias.get("step87_resolution_suggestion", ""),
        "candidate_name": clean_text(ciq.get("companyname", "")),
        "candidate_companyid": clean_text(ciq.get("companyid", "")),
        "candidate_isin": clean_text(ciq.get("isin", "")).upper().replace(" ", ""),
        "candidate_source": "CIQ_COMMON",
        "candidate_match_rule": match_rule,
        "candidate_identifier_basis": "CIQ_COMMON_ISIN_NAME_ONLY",
        "candidate_ciq_startdate": clean_text(ciq.get("startdate", "")),
        "candidate_ciq_enddate": clean_text(ciq.get("enddate", "")),
        "candidate_date_overlap": year_overlap(ciq.get("startdate", ""), ciq.get("enddate", ""), years),
    }


def main() -> None:
    aliases = load_aliases()
    print(f"Step 8.7c CIQ aliases: {len(aliases):,}", flush=True)
    cand = scan_ciq_common(aliases)
    if cand.empty:
        pd.DataFrame().to_csv(OUT_CANDIDATES, index=False)
        pd.DataFrame().to_csv(OUT_BEST, index=False)
        pd.DataFrame().to_csv(OUT_SUMMARY, index=False)
        print("No CIQ_COMMON candidates found.")
        return
    cand.to_csv(OUT_CANDIDATES, index=False)
    best = cand[cand["ciq_candidate_rank"].eq(1)].copy()
    best.to_csv(OUT_BEST, index=False)
    summary = (
        best.groupby(["step87_refined_resolution_suggestion", "candidate_date_overlap"], dropna=False)
        .agg(aliases=("record_id", "size"), frequency_sum=("frequency", "sum"))
        .reset_index()
        .sort_values("frequency_sum", ascending=False)
    )
    summary.to_csv(OUT_SUMMARY, index=False)
    gvkey_summary = (
        best.groupby(["step87_refined_resolution_suggestion", "candidate_date_overlap", "ciq_has_gvkey_crosswalk", "ciq_identifier_upgrade_candidate"], dropna=False)
        .agg(aliases=("record_id", "size"), frequency_sum=("frequency", "sum"))
        .reset_index()
        .sort_values("frequency_sum", ascending=False)
    )
    gvkey_summary.to_csv(OUT_GVKEY_SUMMARY, index=False)
    source_rule = (
        cand.groupby(["candidate_match_rule", "candidate_date_overlap"], dropna=False)
        .agg(aliases=("record_id", "nunique"), candidates=("record_id", "size"), frequency_sum=("frequency", "sum"))
        .reset_index()
        .sort_values("frequency_sum", ascending=False)
    )
    source_rule.to_csv(OUT_SOURCE_RULE, index=False)
    print("Step 8.7c CIQ_COMMON summary:")
    print(summary.to_string(index=False))
    print(f"Wrote: {OUT_CANDIDATES}")
    print(f"Wrote: {OUT_BEST}")


if __name__ == "__main__":
    main()
