# 7-LLM-Residual-Classification.py

from datetime import datetime
from pathlib import Path
import json
import os
import re
import time

import pandas as pd
import yaml


RESULTS_DIR = Path("data/results")
OUT_DIR = RESULTS_DIR / "descriptives"
REVIEW_DIR = OUT_DIR / "missing_review"
STEP7_DIR = OUT_DIR / "step7_residual_classification"
VALIDATION_DIR = STEP7_DIR / "validation_samples"
STEP7_DIR.mkdir(parents=True, exist_ok=True)
VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

INPUT_FILE = REVIEW_DIR / "unmatched_review_for_step7.csv"
MODEL = "gpt-4.1-mini"

VALID_CLASSES = {
    "company",
    "subsidiary_or_business_unit",
    "brand_or_product",
    "generic_phrase",
    "multiple_entities",
    "government_or_public_institution",
    "association_or_nonprofit",
    "person",
    "technical_term",
    "artifact",
    "unclear",
}

VALID_DECISIONS = {
    "accept_for_manual_alias_bridge",
    "drop",
    "manual_review",
}


def safe_to_csv(df, path, index=False):
    path = Path(path)
    try:
        df.to_csv(path, index=index)
        return path
    except PermissionError:
        fallback = path.with_name(f"{path.stem}_{datetime.now():%Y%m%d_%H%M%S}{path.suffix}")
        df.to_csv(fallback, index=index)
        print(f"Permission denied writing {path}; wrote {fallback} instead.")
        return fallback


def read_openai_api_key():
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]

    config_path = Path("config.yaml")
    if config_path.exists():
        with open(config_path, "r") as f:
            config = yaml.safe_load(f) or {}
        key_file = config.get("openai_key_file")
        if key_file and Path(key_file).exists():
            return Path(key_file).read_text().strip()

    raise RuntimeError("No OpenAI API key found. Set OPENAI_API_KEY or config.yaml openai_key_file.")


def extract_json_object(text):
    text = str(text).strip()
    text = re.sub(r"^```(?:json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def normalize_response(obj):
    classification = str(obj.get("classification", "unclear")).strip()
    decision = str(obj.get("decision", "manual_review")).strip()

    if classification not in VALID_CLASSES:
        classification = "unclear"
    if decision not in VALID_DECISIONS:
        decision = "manual_review"

    return {
        "llm_classification": classification,
        "llm_decision": decision,
        "llm_confidence": str(obj.get("confidence", "")).strip(),
        "llm_reason": str(obj.get("reason", "")).strip(),
    }


def classify_one(client, row):
    prompt = {
        "task": "Classify one residual unmatched competitor-name extraction for audit review.",
        "hard_rules": [
            "Never assign CIK, GVKEY, PERMNO, or any firm identifier.",
            "Do not decide firm identity.",
            "Only classify the textual residual name.",
            "Return JSON only."
        ],
        "allowed_classifications": sorted(VALID_CLASSES),
        "allowed_decisions": sorted(VALID_DECISIONS),
        "decision_guidance": {
            "accept_for_manual_alias_bridge": "Use only when the residual appears to be a specific identifiable firm or business unit that could plausibly be manually aliased later.",
            "drop": "Use for generic phrases, artifacts, technical terms, people, or clearly non-firm cases.",
            "manual_review": "Use when entity type or usefulness is ambiguous."
        },
        "record": {
            "record_id": row.get("record_id", ""),
            "competitor_name": row.get("competitor_name", ""),
            "competitor_name_standardized": row.get("competitor_name_standardized", ""),
            "frequency": row.get("frequency", ""),
            "sic_files": row.get("sic_files", ""),
            "years": row.get("years", ""),
            "generic_score_raw": row.get("generic_score_raw", ""),
            "generic_score_standardized": row.get("generic_score_standardized", ""),
        },
        "required_json_keys": ["classification", "decision", "confidence", "reason"],
    }

    response = client.responses.create(
        model=MODEL,
        input=json.dumps(prompt, ensure_ascii=True),
        temperature=0,
    )

    text = response.output_text
    return normalize_response(extract_json_object(text))


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing Step 7 input: {INPUT_FILE}")

    df = pd.read_csv(INPUT_FILE)

    if df.empty:
        result = df.copy()
        for col in ["llm_classification", "llm_decision", "llm_confidence", "llm_reason"]:
            result[col] = ""
    else:
        from openai import OpenAI
        client = OpenAI(api_key=read_openai_api_key())

        rows = []
        for i, row in df.iterrows():
            row_dict = row.to_dict()
            try:
                classified = classify_one(client, row_dict)
            except Exception as exc:
                classified = {
                    "llm_classification": "unclear",
                    "llm_decision": "manual_review",
                    "llm_confidence": "",
                    "llm_reason": f"LLM_ERROR: {exc}",
                }

            rows.append({**row_dict, **classified})

            if (i + 1) % 25 == 0:
                print(f"Classified {i + 1} / {len(df)}")
                time.sleep(1)

        result = pd.DataFrame(rows)

    safe_to_csv(result, STEP7_DIR / "step7_llm_residual_classified.csv", index=False)
    safe_to_csv(
        result[result["llm_decision"] == "accept_for_manual_alias_bridge"].copy(),
        STEP7_DIR / "step7_accept_for_manual_alias_bridge.csv",
        index=False,
    )
    safe_to_csv(
        result[result["llm_decision"] == "drop"].copy(),
        STEP7_DIR / "step7_dropped_cases.csv",
        index=False,
    )
    safe_to_csv(
        result[result["llm_decision"] == "manual_review"].copy(),
        STEP7_DIR / "step7_manual_review_cases.csv",
        index=False,
    )

    summary = (
        result.groupby(["llm_classification", "llm_decision"], dropna=False)
        .agg(records=("record_id", "count"), total_frequency=("frequency", "sum"))
        .reset_index()
        if not result.empty
        else pd.DataFrame(columns=["llm_classification", "llm_decision", "records", "total_frequency"])
    )
    safe_to_csv(summary, STEP7_DIR / "step7_summary.csv", index=False)

    for col in ["llm_classification", "llm_decision"]:
        for value, sample in result.groupby(col, dropna=False):
            if sample.empty:
                continue
            safe_name = re.sub(r"[^A-Za-z0-9_]+", "_", str(value)).strip("_").lower() or "blank"
            sample = sample.sample(n=min(100, len(sample)), random_state=42)
            safe_to_csv(sample, VALIDATION_DIR / f"step7_sample_{col}_{safe_name}.csv", index=False)

    print("Step 7 completed. Outputs saved in:", STEP7_DIR)


if __name__ == "__main__":
    main()
