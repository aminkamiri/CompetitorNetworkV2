# 7-LLM-Residual-Classification(rev1).py

from datetime import datetime
from pathlib import Path
import argparse
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
MAIN_OUTPUT_FILE = STEP7_DIR / "step7_llm_residual_classified.csv"
ISSUES_FILE = STEP7_DIR / "step7_issues.csv"

DEFAULT_MODEL = "gpt-5.5"
DEFAULT_BATCH_SIZE = 25
DEFAULT_MAX_RECORDS = 200

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

CLASSIFICATION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "record_id": {"type": "string"},
                    "competitor_name": {"type": "string"},
                    "llm_classification": {"type": "string", "enum": sorted(VALID_CLASSES)},
                    "llm_decision": {"type": "string", "enum": sorted(VALID_DECISIONS)},
                    "llm_confidence": {"type": "number"},
                    "llm_reason": {"type": "string"},
                },
                "required": [
                    "record_id",
                    "competitor_name",
                    "llm_classification",
                    "llm_decision",
                    "llm_confidence",
                    "llm_reason",
                ],
            },
        }
    },
    "required": ["classifications"],
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


def read_config():
    config_path = Path("config.yaml")
    if config_path.exists():
        with open(config_path, "r") as f:
            return yaml.safe_load(f) or {}
    return {}


def read_openai_api_key(config):
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]

    key_file = config.get("openai_key_file")
    if key_file and Path(key_file).exists():
        return Path(key_file).read_text().strip()

    raise RuntimeError("No OpenAI API key found. Set OPENAI_API_KEY or config.yaml openai_key_file.")


def parse_max_records(value):
    if value is None:
        return None

    value_text = str(value).strip().lower()
    if value_text in {"", "none", "null"}:
        return None

    return int(value)


def parse_args():
    config = read_config()
    parser = argparse.ArgumentParser(description="Classify residual unmatched competitor-name extractions.")
    parser.add_argument("--model", default=config.get("step7_model", DEFAULT_MODEL))
    parser.add_argument("--batch-size", type=int, default=int(config.get("step7_batch_size", DEFAULT_BATCH_SIZE)))
    parser.add_argument(
        "--max-records",
        type=parse_max_records,
        default=parse_max_records(config.get("step7_max_records", DEFAULT_MAX_RECORDS)),
        help="Pilot cap after sorting by frequency descending. Use 0 or none for full file.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        default=bool(config.get("step7_overwrite", False)),
        help="Reprocess records even if they already exist in the main output.",
    )
    parser.add_argument("--sleep-seconds", type=float, default=float(config.get("step7_sleep_seconds", 0)))
    return parser.parse_args(), config


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


def normalize_result(item, input_row=None, reason_override=None):
    input_row = input_row or {}
    classification = str(item.get("llm_classification", "unclear")).strip()
    decision = str(item.get("llm_decision", "manual_review")).strip()

    if classification not in VALID_CLASSES:
        classification = "unclear"
    if decision not in VALID_DECISIONS:
        decision = "manual_review"

    confidence = item.get("llm_confidence", 0)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0

    confidence = max(0, min(1, confidence))

    return {
        **input_row,
        "record_id": str(item.get("record_id", input_row.get("record_id", ""))).strip(),
        "competitor_name": str(item.get("competitor_name", input_row.get("competitor_name", ""))).strip(),
        "llm_classification": classification,
        "llm_decision": decision,
        "llm_confidence": confidence,
        "llm_reason": reason_override if reason_override is not None else str(item.get("llm_reason", "")).strip(),
        "llm_model": input_row.get("llm_model", ""),
        "processed_at": datetime.now().isoformat(timespec="seconds"),
    }


def missing_result_for_row(row):
    row_dict = row.to_dict()
    return normalize_result(
        {
            "record_id": row_dict.get("record_id", ""),
            "competitor_name": row_dict.get("competitor_name", ""),
            "llm_classification": "unclear",
            "llm_decision": "manual_review",
            "llm_confidence": 0,
            "llm_reason": "Missing from model output",
        },
        input_row=row_dict,
    )


def build_batch_prompt(batch):
    records = []
    for row in batch.to_dict(orient="records"):
        records.append({
            "record_id": str(row.get("record_id", "")),
            "competitor_name": str(row.get("competitor_name", "")),
            "competitor_name_standardized": str(row.get("competitor_name_standardized", "")),
            "frequency": row.get("frequency", ""),
            "sic_files": str(row.get("sic_files", "")),
            "years": str(row.get("years", "")),
            "generic_score_raw": row.get("generic_score_raw", ""),
            "generic_score_standardized": row.get("generic_score_standardized", ""),
        })

    return {
        "task": "Classify residual unmatched competitor-name extractions for audit review.",
        "hard_rules": [
            "Never assign CIK, GVKEY, PERMNO, or any firm identifier.",
            "Do not decide firm identity.",
            "Do not map to parent firms.",
            "Do not invent identifiers.",
            "Return exactly one classification per record_id.",
        ],
        "allowed_classifications": sorted(VALID_CLASSES),
        "allowed_decisions": sorted(VALID_DECISIONS),
        "decision_rules": {
            "accept_for_manual_alias_bridge": "Only if the residual appears to be a specific identifiable organization-like name that could later be mapped through a manual alias bridge.",
            "drop": "Use for generic phrases, product categories, pure products/brands, technical terms, artifacts, people, and social handles.",
            "manual_review": "Use for multiple entities or uncertain cases.",
        },
        "records": records,
    }


def response_text(response):
    if hasattr(response, "output_text"):
        return response.output_text
    return str(response)


def call_model_for_batch(client, model, batch):
    prompt = build_batch_prompt(batch)
    response = client.responses.create(
        model=model,
        input=json.dumps(prompt, ensure_ascii=True),
        text={
            "format": {
                "type": "json_schema",
                "name": "step7_residual_classification_batch",
                "schema": CLASSIFICATION_SCHEMA,
                "strict": True,
            }
        },
    )
    parsed = extract_json_object(response_text(response))
    return parsed.get("classifications", [])


def load_existing_output(overwrite):
    if overwrite or not MAIN_OUTPUT_FILE.exists():
        return pd.DataFrame()

    existing = pd.read_csv(MAIN_OUTPUT_FILE)
    if "record_id" not in existing.columns:
        return pd.DataFrame()

    return existing.drop_duplicates(subset=["record_id"], keep="last")


def save_outputs(result, issues):
    if result.empty:
        result = pd.DataFrame(columns=[
            "record_id",
            "competitor_name",
            "competitor_name_standardized",
            "frequency",
            "llm_classification",
            "llm_decision",
            "llm_confidence",
            "llm_reason",
            "llm_model",
            "processed_at",
        ])

    result = result.drop_duplicates(subset=["record_id"], keep="last")
    safe_to_csv(result, MAIN_OUTPUT_FILE, index=False)

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

    issues_df = pd.DataFrame(issues)
    safe_to_csv(issues_df, ISSUES_FILE, index=False)

    sample_specs = [
        ("accept_for_manual_alias_bridge", "accepted_for_manual_alias_bridge_sample.csv"),
        ("drop", "dropped_cases_sample.csv"),
        ("manual_review", "manual_review_cases_sample.csv"),
    ]
    for decision, filename in sample_specs:
        sample = result[result["llm_decision"] == decision].copy()
        if sample.empty:
            sample = pd.DataFrame(columns=list(result.columns))
        else:
            sample = sample.sample(n=min(100, len(sample)), random_state=42)
        sample["manual_validation"] = ""
        sample["notes"] = ""
        safe_to_csv(sample, VALIDATION_DIR / filename, index=False)

    return result, summary


def main():
    args, config = parse_args()

    if args.batch_size <= 0:
        raise ValueError("batch_size must be positive.")

    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Missing Step 7 input: {INPUT_FILE}")

    df = pd.read_csv(INPUT_FILE)
    input_rows = len(df)

    df["frequency"] = pd.to_numeric(df["frequency"], errors="coerce").fillna(0)
    df = df.sort_values("frequency", ascending=False).reset_index(drop=True)

    if args.max_records not in {None, 0}:
        df = df.head(args.max_records).copy()

    existing = load_existing_output(args.overwrite)
    already_processed = set(existing["record_id"].astype(str)) if not existing.empty else set()

    to_process = df[~df["record_id"].astype(str).isin(already_processed)].copy()

    print("Step 7 residual classification")
    print("Input rows:", input_rows)
    print("Already processed rows:", len(already_processed))
    print("Rows sent to API:", len(to_process))
    print("Model:", args.model)
    print("Batch size:", args.batch_size)
    print("Max records:", args.max_records)

    result = existing.copy()
    issues = []

    if not to_process.empty:
        from openai import OpenAI
        client = OpenAI(api_key=read_openai_api_key(config))

        for start in range(0, len(to_process), args.batch_size):
            batch = to_process.iloc[start:start + args.batch_size].copy()
            batch_ids = set(batch["record_id"].astype(str))
            input_rows_by_id = {
                str(row["record_id"]): {**row, "llm_model": args.model}
                for row in batch.to_dict(orient="records")
            }

            try:
                raw_items = call_model_for_batch(client, args.model, batch)
            except Exception as exc:
                raw_items = []
                issues.append({
                    "issue_type": "batch_api_error",
                    "record_id": "",
                    "details": str(exc),
                    "batch_start": start,
                    "batch_size": len(batch),
                })

            normalized = []
            seen_output_ids = set()
            for item in raw_items:
                record_id = str(item.get("record_id", "")).strip()
                if record_id not in batch_ids:
                    issues.append({
                        "issue_type": "unexpected_record_id",
                        "record_id": record_id,
                        "details": "Model returned record_id not present in batch.",
                        "batch_start": start,
                        "batch_size": len(batch),
                    })
                    continue

                seen_output_ids.add(record_id)
                normalized.append(normalize_result(item, input_rows_by_id[record_id]))

            missing_ids = sorted(batch_ids - seen_output_ids)
            for record_id in missing_ids:
                normalized.append(missing_result_for_row(pd.Series(input_rows_by_id[record_id])))
                issues.append({
                    "issue_type": "missing_model_output",
                    "record_id": record_id,
                    "details": "Missing from model output",
                    "batch_start": start,
                    "batch_size": len(batch),
                })

            if normalized:
                batch_result = pd.DataFrame(normalized)
                result = pd.concat([result, batch_result], ignore_index=True)
                result = result.drop_duplicates(subset=["record_id"], keep="last")

            result, _ = save_outputs(result, issues)
            print(f"Processed batch {start // args.batch_size + 1}: {len(result)} total classified rows saved.")

            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)

    result, summary = save_outputs(result, issues)

    print("\nFinal decision counts:")
    if result.empty:
        print("(no rows)")
    else:
        print(result["llm_decision"].value_counts(dropna=False))
    print("Outputs saved in:", STEP7_DIR)


if __name__ == "__main__":
    main()
