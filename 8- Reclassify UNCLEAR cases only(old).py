# 8-Reclassify-Manual-Review-Names.py

import os
import json
import time
from pathlib import Path
from datetime import timedelta

import yaml
import pandas as pd
from openai import OpenAI


class Step8ManualReviewReclassifier:
    def __init__(
        self,
        input_csv,
        output_csv,
        issues_csv,
        model_name="gpt-4.1-nano",
        batch_size=100,
        overwrite=False,
    ):
        self.input_csv = Path(input_csv)
        self.output_csv = Path(output_csv)
        self.issues_csv = Path(issues_csv)

        self.output_csv.parent.mkdir(parents=True, exist_ok=True)
        self.issues_csv.parent.mkdir(parents=True, exist_ok=True)

        self.model_name = model_name
        self.batch_size = batch_size
        self.overwrite = overwrite

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY not found. In PowerShell run: "
                "$env:OPENAI_API_KEY='sk-proj-your-real-key'"
            )

        self.client = OpenAI(api_key=api_key)

        self.total_api_calls = 0
        self.total_records_processed = 0
        self.total_processing_time = 0

    def format_time(self, seconds):
        return str(timedelta(seconds=int(seconds)))

    def build_schema(self):
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "validations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "record_id": {"type": "integer"},
                            "raw_name": {"type": "string"},
                            "step8_entity_type": {
                                "type": "string",
                                "enum": [
                                    "company",
                                    "subsidiary",
                                    "division_or_business_unit",
                                    "multiple_entities",
                                    "brand_or_product",
                                    "generic_phrase",
                                    "person",
                                    "social_handle",
                                    "domain_or_website",
                                    "government_or_public_institution",
                                    "association_or_nonprofit",
                                    "technical_term",
                                    "artifact",
                                    "unclear",
                                ],
                            },
                            "step8_decision": {
                                "type": "string",
                                "enum": ["accept", "drop", "manual_review"],
                            },
                            "step8_standardized_name": {
                                "type": ["string", "null"]
                            },
                            "step8_confidence": {"type": "number"},
                            "step8_reason": {"type": "string"},
                        },
                        "required": [
                            "record_id",
                            "raw_name",
                            "step8_entity_type",
                            "step8_decision",
                            "step8_standardized_name",
                            "step8_confidence",
                            "step8_reason",
                        ],
                    },
                }
            },
            "required": ["validations"],
        }

    def build_prompt(self, batch_records):
        records_text = json.dumps(batch_records, ensure_ascii=False, indent=2)

        return f"""
You are reclassifying extracted competitor-name strings from SEC 10-K competition sections.

These records were previously assigned to manual_review. Your task is to resolve as many as possible, but with stricter rules.

For each record, classify whether raw_name refers to a real company-like organization that should be kept for later matching to CIK/GVKEY/PERMNO.

Use the following decisions:

accept:
Use this only if raw_name likely refers to a company, legal entity, subsidiary, division, business unit, association, nonprofit, government/public institution, or company-name variant that could reasonably be mapped to an organization or parent firm.

drop:
Use this if raw_name is a generic phrase, industry category, product category, customer type, supplier type, technology term, product, brand, service line, named commercial offering, social media handle, artifact, or non-organization phrase.

manual_review:
Use this only if it remains genuinely ambiguous after applying these rules, or if it contains multiple entities that should be split manually.

Important classification rules:
- Do NOT accept pure brands, products, service lines, or named commercial offerings.
- Examples to drop: "AT&T TV", "AT&T U-verse", "AT&T TV NOW", "Abbott Libre".
- Accept subsidiaries, divisions, and business units if they are organization-like.
- Examples to accept: "Abbott Molecular", "Abbott Vascular", "Abbott Nutrition", "ADVA Optical Networking SE".
- If the name contains multiple entities separated by "/", "&", "and", commas, or merger/partnership style references, use manual_review and entity_type = multiple_entities.
- Legal suffixes such as Inc, Corp, Ltd, LLC, GmbH, S.A., SE, BV, NV, PLC, AG strongly indicate accept.
- Corrupted encoding such as "‚Äì" or "‚Äô" should be mentally corrected before classification.
- Preserve the original record_id exactly.
- Return exactly one output for every input record.
- Do not invent identifiers.
- If accepted, provide a cleaned step8_standardized_name.
- If dropped or still manual_review, step8_standardized_name should be null unless there is an obvious cleaned organization name.

Records:
{records_text}
""".strip()

    def validate_batch_with_api(self, batch_records):
        response = self.client.responses.create(
            model=self.model_name,
            input=[
                {
                    "role": "system",
                    "content": "You are a precise research assistant cleaning company-name extraction data.",
                },
                {
                    "role": "user",
                    "content": self.build_prompt(batch_records),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "step8_manual_review_reclassification",
                    "schema": self.build_schema(),
                    "strict": True,
                }
            },
            temperature=0,
        )

        self.total_api_calls += 1
        parsed = json.loads(response.output_text)
        return parsed["validations"]

    def save_issue(self, batch_id, error, batch_records):
        issue_row = {
            "batch_id": batch_id,
            "error": str(error),
            "batch_records": json.dumps(batch_records, ensure_ascii=False),
        }

        if self.issues_csv.exists():
            issues = pd.read_csv(self.issues_csv)
            issues = pd.concat([issues, pd.DataFrame([issue_row])], ignore_index=True)
        else:
            issues = pd.DataFrame([issue_row])

        issues.to_csv(self.issues_csv, index=False)

    def load_existing_step8_results(self):
        if self.overwrite and self.output_csv.exists():
            self.output_csv.unlink()

        if self.output_csv.exists():
            df = pd.read_csv(self.output_csv)
            if "step8_processed" in df.columns:
                done = df[df["step8_processed"] == True]
                return set(done["record_id"].astype(int))
        return set()

    def process(self):
        if not self.input_csv.exists():
            raise FileNotFoundError(f"Input file not found: {self.input_csv}")

        df = pd.read_csv(self.input_csv)

        required_cols = [
            "record_id",
            "raw_name",
            "sic_context",
            "year_context",
            "frequency",
            "decision",
            "standardized_name",
            "entity_type",
            "confidence",
            "reason",
            "source",
        ]

        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Required column missing from Step 7 file: {col}")

        original_n = len(df)

        manual_df = df[df["decision"] == "manual_review"].copy()
        print("\n" + "=" * 80)
        print("STEP 8: RECLASSIFY STEP 7 MANUAL REVIEW CASES")
        print(f"Input Step 7 master records: {original_n}")
        print(f"Step 7 manual_review records to inspect: {len(manual_df)}")
        print(f"Model: {self.model_name}")
        print(f"Batch size: {self.batch_size}")
        print("=" * 80 + "\n")

        if len(manual_df) == 0:
            df["final_decision"] = df["decision"]
            df["final_standardized_name"] = df["standardized_name"]
            df["final_entity_type"] = df["entity_type"]
            df["final_confidence"] = df["confidence"]
            df["final_reason"] = df["reason"]
            df["step8_processed"] = False
            df.to_csv(self.output_csv, index=False)
            print("No manual_review records found. Final file saved unchanged.")
            return

        processed_ids = self.load_existing_step8_results()

        rows_to_api = manual_df[
            ~manual_df["record_id"].astype(int).isin(processed_ids)
        ].copy()

        total = len(rows_to_api)
        print(f"Already Step 8 processed: {len(processed_ids)}")
        print(f"Remaining to send to API: {total}\n")

        step8_results = []

        start_time = time.time()

        for batch_start in range(0, total, self.batch_size):
            batch_id = batch_start // self.batch_size + 1
            batch = rows_to_api.iloc[batch_start: batch_start + self.batch_size]

            batch_records = [
                {
                    "record_id": int(r["record_id"]),
                    "raw_name": str(r["raw_name"]),
                    "sic_context": str(r["sic_context"]),
                    "year_context": str(r["year_context"]),
                    "frequency": int(r["frequency"]) if not pd.isna(r["frequency"]) else 1,
                    "step7_entity_type": str(r["entity_type"]),
                    "step7_confidence": float(r["confidence"]) if not pd.isna(r["confidence"]) else 0.0,
                    "step7_reason": str(r["reason"]),
                }
                for _, r in batch.iterrows()
            ]

            print(f"[Batch {batch_id}] Processing {len(batch_records)} records...")

            batch_start_time = time.time()
            max_retries = 3

            for attempt in range(max_retries):
                try:
                    validations = self.validate_batch_with_api(batch_records)

                    validation_by_id = {
                        int(v["record_id"]): v for v in validations
                    }

                    for r in batch_records:
                        v = validation_by_id.get(int(r["record_id"]))

                        if v is None:
                            v = {
                                "record_id": r["record_id"],
                                "raw_name": r["raw_name"],
                                "step8_entity_type": "unclear",
                                "step8_decision": "manual_review",
                                "step8_standardized_name": None,
                                "step8_confidence": 0.0,
                                "step8_reason": "Missing from model output",
                            }

                        step8_results.append(v)

                    elapsed = time.time() - batch_start_time
                    self.total_records_processed += len(batch_records)
                    self.total_processing_time += elapsed

                    avg_time = self.total_processing_time / max(self.total_records_processed, 1)
                    remaining = total - (batch_start + len(batch_records))
                    eta = avg_time * remaining

                    print(
                        f"  ✓ Done in {elapsed:.2f}s | "
                        f"API calls: {self.total_api_calls} | "
                        f"Processed: {self.total_records_processed}/{total} | "
                        f"ETA: {self.format_time(eta)}"
                    )

                    break

                except Exception as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 15
                        print(f"  Error: {e}")
                        print(f"  Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        print(f"  ✗ Failed batch {batch_id}: {e}")
                        self.save_issue(batch_id, e, batch_records)

            time.sleep(1)

        if step8_results:
            step8_df = pd.DataFrame(step8_results)

            step8_df = step8_df.drop_duplicates(
                subset=["record_id"],
                keep="last",
            )

            step8_df["step8_processed"] = True

            df = df.merge(
                step8_df[
                    [
                        "record_id",
                        "step8_entity_type",
                        "step8_decision",
                        "step8_standardized_name",
                        "step8_confidence",
                        "step8_reason",
                        "step8_processed",
                    ]
                ],
                on="record_id",
                how="left",
                validate="one_to_one",
            )
        else:
            df["step8_entity_type"] = pd.NA
            df["step8_decision"] = pd.NA
            df["step8_standardized_name"] = pd.NA
            df["step8_confidence"] = pd.NA
            df["step8_reason"] = pd.NA
            df["step8_processed"] = False

        # Create final integrated columns
        df["final_decision"] = df["decision"]
        df["final_standardized_name"] = df["standardized_name"]
        df["final_entity_type"] = df["entity_type"]
        df["final_confidence"] = df["confidence"]
        df["final_reason"] = df["reason"]

        mask = df["step8_decision"].notna()

        df.loc[mask, "final_decision"] = df.loc[mask, "step8_decision"]
        df.loc[mask, "final_entity_type"] = df.loc[mask, "step8_entity_type"]
        df.loc[mask, "final_confidence"] = df.loc[mask, "step8_confidence"]
        df.loc[mask, "final_reason"] = df.loc[mask, "step8_reason"]

        # Only replace standardized name if Step 8 provides one
        mask_std = mask & df["step8_standardized_name"].notna()
        df.loc[mask_std, "final_standardized_name"] = df.loc[
            mask_std,
            "step8_standardized_name",
        ]

        # Safety check: row count must not change
        if len(df) != original_n:
            raise RuntimeError(
                f"Row-count changed from {original_n} to {len(df)}. "
                "This should never happen."
            )

        df.to_csv(self.output_csv, index=False)

        print("\n" + "=" * 80)
        print("STEP 8 COMPLETE")
        print(f"Output: {self.output_csv}")
        print(f"Final rows: {len(df)}")
        print("\nOriginal Step 7 decision distribution:")
        print(df["decision"].value_counts(dropna=False))
        print("\nFinal decision distribution:")
        print(df["final_decision"].value_counts(dropna=False))
        print("=" * 80 + "\n")

        self.create_final_splits(df)

    def create_final_splits(self, df):
        output_dir = self.output_csv.parent

        accepted = df[df["final_decision"] == "accept"].copy()
        dropped = df[df["final_decision"] == "drop"].copy()
        manual = df[df["final_decision"] == "manual_review"].copy()

        accepted.to_csv(output_dir / "step8_final_accepted_company_names.csv", index=False)
        dropped.to_csv(output_dir / "step8_final_dropped_non_company_names.csv", index=False)
        manual.to_csv(output_dir / "step8_final_manual_review_company_names.csv", index=False)

        print("Final Step 8 split files created:")
        print(f"  Accepted: {len(accepted)}")
        print(f"  Dropped: {len(dropped)}")
        print(f"  Manual review: {len(manual)}")


def main():
    with open("config_step8.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    reclassifier = Step8ManualReviewReclassifier(
        input_csv=config["input_csv"],
        output_csv=config["output_csv"],
        issues_csv=config["issues_csv"],
        model_name=config.get("llm_model_name", "gpt-4.1-nano"),
        batch_size=config.get("batch_size", 100),
        overwrite=config.get("overwrite", False),
    )

    reclassifier.process()


if __name__ == "__main__":
    main()