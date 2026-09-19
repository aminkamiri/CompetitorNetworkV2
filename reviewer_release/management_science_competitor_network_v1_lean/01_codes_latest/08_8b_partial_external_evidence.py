from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd


PROJECT = Path(r"C:\Users\mnasiri\Documents\GitHub\CompetitorNetworkV2")
STEP87_DIR = PROJECT / "data" / "results" / "final" / "step87_unresolved_recovery"

STEP88_MASTER = STEP87_DIR / "step88_unresolved_recovery_consolidated_master.csv"
CIQ_GVKEY = PROJECT / "CIQ-gvkey.csv"
REPRISK = PROJECT / "reprisk11072026.csv"
IBES_ACTUALS = PROJECT / "actuals.csv"

OUT_PARTIAL = STEP87_DIR / "step88b_partial_external_evidence_candidates.csv"
OUT_BEST = STEP87_DIR / "step88b_partial_external_evidence_best.csv"
OUT_MASTER = STEP87_DIR / "step88_unresolved_recovery_consolidated_master_with_partial_evidence.csv"
OUT_REVIEW = STEP87_DIR / "step88_unresolved_recovery_manual_review_queue_with_partial_evidence.csv"
OUT_SUMMARY = STEP87_DIR / "step88b_partial_external_evidence_summary.csv"
OUT_XLSX_REVIEW = STEP87_DIR / "step88_unresolved_recovery_manual_review_queue_with_partial_evidence.xlsx"
OUT_XLSX_MASTER = STEP87_DIR / "step88_unresolved_recovery_consolidated_master_with_partial_evidence.xlsx"

CHUNKSIZE = 300_000

LEGAL_SUFFIXES = {
    "INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC",
    "AG", "SA", "SE", "NV", "BV", "GMBH", "LLC", "LP", "LLP", "SPA", "AB",
    "AS", "SARL", "SRL", "THE", "PTE", "PTY", "KG", "KGAA",
}

SAFE_CONTINUATION_TERMS = {
    "TECH", "TECHNOLOGY", "TECHNOLOGIES", "PHARMA", "PHARM", "PHARMACEUTICAL",
    "PHARMACEUTICALS", "HEALTH", "HEALTHCARE", "DIAGNOSTIC", "DIAGNOSTICS",
    "MEDICAL", "THERAPEUTICS", "BIO", "BIOTECH", "BIOTECHNOLOGY", "FINANCE",
    "FINANCIAL", "TRADING", "HOLDING", "HOLDINGS", "HLDG", "GROUP", "GRP",
    "CORP", "CORPORATION", "CO", "COMPANY", "INC", "LTD", "LIMITED", "PLC",
    "AG", "SA", "SE", "NV", "BV", "GMBH", "LLC", "LP", "LLP", "AS", "AB",
    "SYSTEMS", "SYS", "SERVICES", "SOLUTIONS", "INDUSTRIES", "INTERNATIONAL",
    "DEVICES", "RESEARCH", "DEVELOPMENT", "LABORATORIES", "LABS",
}


def clean_text(value) -> str:
    if value is None or pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "<na>"}:
        return ""
    return text


def normalize(value) -> str:
    text = unicodedata.normalize("NFKD", clean_text(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).upper()
    text = text.replace("&", " AND ")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return normalize_possessive_spacing(text)


def normalize_possessive_spacing(text: str) -> str:
    tokens = text.split()
    if len(tokens) == 2 and tokens[-1] == "S" and len(tokens[0]) >= 3:
        return tokens[0] + "S"
    return " ".join(tokens)


def compact(value) -> str:
    return re.sub(r"[^A-Z0-9]+", "", normalize(value))


def canonical(value) -> str:
    tokens = normalize(value).split()
    while tokens and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def first_token(value: str) -> str:
    toks = normalize(value).split()
    return toks[0] if toks else ""


def valid_id(value) -> bool:
    text = clean_text(value)
    if text == "" or text.lower() in {"-1", "-1.0", "-99999", "nan", "none", "null"}:
        return False
    num = pd.to_numeric(text, errors="coerce")
    if not pd.isna(num) and num in {-1, -99999}:
        return False
    return True


def match_type(alias: str, candidate: str) -> tuple[str, int]:
    a = normalize(alias)
    c = normalize(candidate)
    ac = canonical(alias)
    cc = canonical(candidate)
    if not a or not c:
        return "", 0
    if a == c or compact(a) == compact(c):
        return "possessive_or_exact_name", 100
    if ac and (ac == cc or compact(ac) == compact(cc)):
        return "legal_canonical_name", 90
    a_tokens = ac.split() or a.split()
    c_tokens = cc.split() or c.split()
    if not a_tokens or not c_tokens:
        return "", 0
    if c_tokens[: len(a_tokens)] == a_tokens and len(c_tokens) > len(a_tokens):
        continuation = c_tokens[len(a_tokens):]
        if continuation and all(tok in SAFE_CONTINUATION_TERMS for tok in continuation):
            return "alias_prefix_safe_continuation", 75
    if len(a_tokens) >= 2 and a_tokens == c_tokens[: len(a_tokens)]:
        return "multi_token_prefix", 65
    return "", 0


def load_targets() -> pd.DataFrame:
    master = pd.read_csv(STEP88_MASTER, low_memory=False)
    targets = master[
        master["step88_proposed_action"].isin(
            ["remain_unresolved_no_evidence", "remain_unresolved_reason_coded"]
        )
    ].copy()
    targets["evidence_alias_raw"] = targets["suggested_alias_name"].map(clean_text)
    targets.loc[targets["evidence_alias_raw"].eq(""), "evidence_alias_raw"] = targets.loc[
        targets["evidence_alias_raw"].eq(""), "candidate_input_name"
    ].map(clean_text)
    targets.loc[targets["evidence_alias_raw"].eq(""), "evidence_alias_raw"] = targets.loc[
        targets["evidence_alias_raw"].eq(""), "competitor_name"
    ].map(lambda x: clean_text(str(x).split("|")[0]))
    targets["evidence_alias"] = targets["evidence_alias_raw"].map(split_alias_alternatives)
    targets = targets.explode("evidence_alias").reset_index(drop=True).copy()
    targets["evidence_alias"] = targets["evidence_alias"].map(clean_text)
    targets["evidence_first_token"] = targets["evidence_alias"].map(first_token)
    targets = targets[targets["evidence_first_token"].ne("")].copy()
    return targets


def split_alias_alternatives(value) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    parts = [clean_text(part) for part in re.split(r"\s*\|\s*", text)]
    return [part for part in parts if part]


def candidate_record(alias_row: pd.Series, source_row: pd.Series, source: str, name_col: str, basis: str) -> dict | None:
    mt, score = match_type(alias_row.get("evidence_alias", ""), source_row.get(name_col, ""))
    if not mt:
        return None
    gvkey = clean_text(source_row.get("gvkey", "")) or clean_text(source_row.get("ciq_gvkey", ""))
    return {
        "record_id": alias_row.get("record_id", ""),
        "frequency": alias_row.get("frequency", ""),
        "competitor_name": alias_row.get("competitor_name", ""),
        "suggested_alias_name": alias_row.get("suggested_alias_name", ""),
        "evidence_alias": alias_row.get("evidence_alias", ""),
        "previous_step88_action": alias_row.get("step88_proposed_action", ""),
        "partial_candidate_name": clean_text(source_row.get(name_col, "")),
        "partial_candidate_source": source,
        "partial_match_rule": mt,
        "partial_identifier_basis": basis,
        "partial_gvkey": gvkey,
        "partial_cik": clean_text(source_row.get("cik", "")),
        "partial_isin": clean_text(source_row.get("primary_isin", "")) or clean_text(source_row.get("isin", "")),
        "partial_companyid": clean_text(source_row.get("companyid", "")),
        "partial_ticker": clean_text(source_row.get("TICKER", "")) or clean_text(source_row.get("OFTIC", "")),
        "partial_cusip": clean_text(source_row.get("CUSIP", "")),
        "partial_score": score,
    }


def scan_ciq_gvkey(targets: pd.DataFrame, candidates: list[dict]) -> None:
    if not CIQ_GVKEY.exists():
        return
    source = pd.read_csv(CIQ_GVKEY, low_memory=False)
    source["first_token"] = source["companyname"].map(first_token)
    source["gvkey"] = pd.to_numeric(source["gvkey"], errors="coerce").astype("Int64").astype(str).replace("<NA>", "")
    scan_source_frame(targets, source, candidates, "CIQ_GVKEY", "companyname", "CIQ_COMPANYID_GVKEY")


def scan_reps_and_ibes(targets: pd.DataFrame, candidates: list[dict]) -> None:
    if REPRISK.exists():
        for chunk in pd.read_csv(REPRISK, usecols=lambda c: c in ["primary_isin", "reprisk_id", "company_name", "isins"], chunksize=CHUNKSIZE, low_memory=False):
            chunk["first_token"] = chunk["company_name"].map(first_token)
            scan_source_frame(targets, chunk, candidates, "REPRISK_PARTIAL", "company_name", "REPRISK_NAME_ISIN_PARTIAL")
    if IBES_ACTUALS.exists():
        for chunk in pd.read_csv(IBES_ACTUALS, usecols=lambda c: c in ["TICKER", "CUSIP", "OFTIC", "CNAME"], chunksize=CHUNKSIZE, low_memory=False):
            chunk["first_token"] = chunk["CNAME"].map(first_token)
            scan_source_frame(targets, chunk, candidates, "IBES_PARTIAL", "CNAME", "IBES_CUSIP_TICKER_PARTIAL")


def scan_source_frame(targets: pd.DataFrame, source: pd.DataFrame, candidates: list[dict], source_name: str, name_col: str, basis: str) -> None:
    targets = targets.copy()
    targets["evidence_norm"] = targets["evidence_alias"].map(normalize)
    targets["evidence_compact"] = targets["evidence_alias"].map(compact)
    targets["evidence_canonical"] = targets["evidence_alias"].map(canonical)
    targets["evidence_canonical_compact"] = targets["evidence_canonical"].map(lambda x: re.sub(r"[^A-Z0-9]+", "", x))

    def build_map(col: str) -> dict[str, list[int]]:
        out: dict[str, list[int]] = {}
        for idx, value in targets[col].items():
            if value:
                out.setdefault(value, []).append(idx)
        return out

    norm_map = build_map("evidence_norm")
    compact_map = build_map("evidence_compact")
    canon_map = build_map("evidence_canonical")
    canon_compact_map = build_map("evidence_canonical_compact")

    first_tokens = set(targets["evidence_first_token"])
    source = source[source["first_token"].isin(first_tokens)].copy()
    if source.empty:
        return

    for _, source_row in source.iterrows():
        candidate_name = clean_text(source_row.get(name_col, ""))
        c_norm = normalize(candidate_name)
        c_compact = compact(candidate_name)
        c_canon = canonical(candidate_name)
        c_canon_compact = re.sub(r"[^A-Z0-9]+", "", c_canon)
        c_tokens = c_canon.split() or c_norm.split()

        target_indices: set[int] = set()
        for key, mapping in [
            (c_norm, norm_map),
            (c_compact, compact_map),
            (c_canon, canon_map),
            (c_canon_compact, canon_compact_map),
        ]:
            target_indices.update(mapping.get(key, []))

        max_prefix_len = min(6, max(0, len(c_tokens) - 1))
        for prefix_len in range(1, max_prefix_len + 1):
            prefix = " ".join(c_tokens[:prefix_len])
            continuation = c_tokens[prefix_len:]
            if continuation and all(tok in SAFE_CONTINUATION_TERMS for tok in continuation):
                target_indices.update(canon_map.get(prefix, []))
            if prefix_len >= 2:
                target_indices.update(canon_map.get(prefix, []))

        for target_idx in target_indices:
            rec = candidate_record(targets.loc[target_idx], source_row, source_name, name_col, basis)
            if rec is not None:
                candidates.append(rec)


def consolidate_partial(master: pd.DataFrame, best: pd.DataFrame) -> pd.DataFrame:
    out = master.merge(best.add_prefix("partial_"), left_on="record_id", right_on="partial_record_id", how="left")
    has_partial = out["partial_record_id"].notna()
    has_gvkey = out["partial_partial_gvkey"].map(valid_id) if "partial_partial_gvkey" in out.columns else pd.Series(False, index=out.index)
    out["step88b_partial_evidence_found"] = has_partial
    out["step88b_partial_public_identifier_found"] = has_partial & has_gvkey
    out["step88b_revised_action"] = out["step88_proposed_action"]
    out["step88b_revised_bucket"] = out["step88_review_bucket"]
    out["step88b_revised_reason"] = out["step88_reason"]
    idx_public = has_partial & has_gvkey
    out.loc[idx_public, "step88b_revised_action"] = "manual_review_public_candidate_partial_external"
    out.loc[idx_public, "step88b_revised_bucket"] = "manual_review"
    out.loc[idx_public, "step88b_revised_reason"] = "Partial external evidence with GVKEY exists; review before accepting because match was not exact/canonical."
    idx_company = has_partial & ~has_gvkey
    out.loc[idx_company, "step88b_revised_action"] = "external_partial_evidence_needs_review"
    out.loc[idx_company, "step88b_revised_bucket"] = "manual_review"
    out.loc[idx_company, "step88b_revised_reason"] = "Partial external company evidence exists; review before assigning company/no-ID status."
    out.loc[~has_partial & out["step88_proposed_action"].eq("remain_unresolved_no_evidence"), "step88b_revised_action"] = "unresolved_no_accepted_evidence"
    return out


def write_xlsx(csv_path: Path) -> None:
    df = pd.read_csv(csv_path, low_memory=False)
    xlsx_path = csv_path.with_suffix(".xlsx")
    with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="data")
        ws = writer.book["data"]
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for col_cells in ws.columns:
            letter = col_cells[0].column_letter
            values = [str(c.value) if c.value is not None else "" for c in col_cells[:200]]
            ws.column_dimensions[letter].width = min(max([len(v) for v in values] + [8]) + 2, 60)


def main() -> None:
    targets = load_targets()
    print(f"Step 8.8b targets: {len(targets):,}")
    candidates: list[dict] = []
    scan_ciq_gvkey(targets, candidates)
    print(f"After CIQ_GVKEY partial scan: {len(candidates):,}")
    scan_reps_and_ibes(targets, candidates)
    print(f"After RepRisk/IBES partial scan: {len(candidates):,}")
    cand = pd.DataFrame(candidates)
    if cand.empty:
        cand.to_csv(OUT_PARTIAL, index=False)
        return
    cand["partial_has_gvkey"] = cand["partial_gvkey"].map(valid_id)
    cand = cand.drop_duplicates()
    cand = cand.sort_values(["record_id", "partial_has_gvkey", "partial_score", "partial_candidate_source"], ascending=[True, False, False, True])
    cand["partial_rank"] = cand.groupby("record_id").cumcount() + 1
    cand.to_csv(OUT_PARTIAL, index=False)
    best = cand[cand["partial_rank"].eq(1)].copy()
    best.to_csv(OUT_BEST, index=False)

    master = pd.read_csv(STEP88_MASTER, low_memory=False)
    revised = consolidate_partial(master, best)
    revised.to_csv(OUT_MASTER, index=False)
    review = revised[revised["step88b_revised_bucket"].eq("manual_review")].copy()
    review.to_csv(OUT_REVIEW, index=False)

    summary = (
        revised.groupby(["step88b_revised_action", "step88b_revised_bucket"], dropna=False)
        .agg(aliases=("record_id", "size"), frequency_sum=("frequency", "sum"))
        .reset_index()
        .sort_values("frequency_sum", ascending=False)
    )
    summary.to_csv(OUT_SUMMARY, index=False)
    write_xlsx(OUT_REVIEW)
    write_xlsx(OUT_SUMMARY)
    print("Step 8.8b summary:")
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
