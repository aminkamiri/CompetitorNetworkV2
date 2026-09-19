# 7-Validate-Competitor-Names.py

import os
import re
import json
import time
from pathlib import Path
from datetime import timedelta

import yaml
import pandas as pd
from openai import OpenAI


LEGAL_SUFFIX_PATTERN = (
    r"\b("
    r"inc\.?|incorporated|corp\.?|corporation|co\.?|company|"
    r"llc|l\.l\.c\.|ltd\.?|limited|plc|ag|sa|s\.a\.|"
    r"nv|n\.v\.|bv|b\.v\.|gmbh|kg|ab|as|a/s|oy|"
    r"spa|s\.p\.a\.|srl|s\.r\.l\.|pte\.?\s*ltd\.?|"
    r"kk|k\.k\.|bvba|sarl"
    r")\b"
)


class LLMCompetitorNameValidator:
    def __init__(
        self,
        input_csv,
        results_dir,
        issues_dir,
        model_name="gpt-4.1-nano",
        batch_size=100,
        overwrite=False,
        raw_name_col="competitor_name",
        sic_col="sic_files",
        year_col="years",
        frequency_col="frequency",
    ):
        self.input_csv = Path(input_csv)
        self.results_dir = Path(results_dir) / "step7_llm_validation"
        self.issues_dir = Path(issues_dir) / "step7_llm_validation"

        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.issues_dir.mkdir(parents=True, exist_ok=True)

        self.output_csv = self.results_dir / "validated_competitor_names.csv"
        self.issues_csv = self.issues_dir / "validation_issues.csv"

        self.model_name = model_name
        self.batch_size = batch_size
        self.overwrite = overwrite

        self.raw_name_col = raw_name_col
        self.sic_col = sic_col
        self.year_col = year_col
        self.frequency_col = frequency_col

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

    def normalize_string(self, x):
        if pd.isna(x):
            return ""
        return str(x).strip()

    def fix_encoding_artifacts(self, x):
        x = self.normalize_string(x)

        replacements = {
            "‚Äôs": "'s",
            "‚Äô": "'",
            "‚Äú": '"',
            "‚Äù": '"',
            "¬Æ": "",
            "™": "",
            "®": "",
            "TM": "",
        }

        for old, new in replacements.items():
            x = x.replace(old, new)

        return x.strip()

    def recover_parent_or_owner_name(self, raw_name):
        x = self.fix_encoding_artifacts(raw_name)

        # Product (owned by Parent)
        m = re.search(r"\(\s*owned by\s+([^()]+)\s*\)\s*$", x, flags=re.I)
        if m:
            return m.group(1).strip(" .;,)"), "owned_by_parent"

        # Product (Parent)
        m = re.search(r"\(([^()]+)\)\s*$", x)
        if m:
            parent = m.group(1).strip(" .;,)")

            bad_parent_terms = {
                "usa", "us", "u.s.", "canada", "uk", "eu", "generic",
                "formerly", "d/b/a", "also known as", "new", "old"
            }

            if len(parent) > 2 and parent.lower() not in bad_parent_terms:
                return parent, "parenthetical_parent"

        # Parent's Product
        m = re.search(r"^(.+?)['’]s\s+.+$", x)
        if m:
            parent = m.group(1).strip(" .;,")
            if len(parent) > 2:
                return parent, "possessive_parent"

        # Division/unit/subsidiary/business/brand of Parent
        m = re.search(
            r"\b(?:a\s+)?(?:unit|division|subsidiary|business|brand)\s+of\s+(.+)$",
            x,
            flags=re.I,
        )
        if m:
            parent = m.group(1).strip(" .;,)")
            parent = re.split(r",|\(|;", parent)[0].strip()

            if len(parent) > 2:
                return parent, "unit_of_parent"

        return None, None

    def make_result(
        self,
        row,
        is_company,
        standardized_name,
        entity_type,
        confidence,
        decision,
        reason,
        source,
    ):
        return {
            "record_id": int(row["record_id"]),
            "raw_name": row["raw_name"],
            "sic_context": row["sic_context"],
            "year_context": row["year_context"],
            "frequency": row["frequency"],
            "is_company": bool(is_company),
            "standardized_name": standardized_name,
            "entity_type": entity_type,
            "confidence": float(confidence),
            "decision": decision,
            "reason": reason,
            "source": source,
        }

    def deterministic_filter(self, row):
        name = self.normalize_string(row["raw_name"])
        lower = name.lower().strip()

        if name == "":
            return self.make_result(
                row, False, None, "artifact", 0.99, "drop",
                "Empty string", "deterministic_empty"
            )

        if lower in {"...inc", "...inc.", ".xyz"}:
            return self.make_result(
                row, False, None, "artifact", 0.99, "drop",
                "Parsing artifact", "deterministic_artifact"
            )

        recovered_parent, recovery_type = self.recover_parent_or_owner_name(name)

        if recovered_parent:
            return self.make_result(
                row, True, recovered_parent, "company", 0.88, "accept",
                f"Recovered company/parent name using {recovery_type} pattern",
                "deterministic_parent_recovery"
            )

        if re.search(LEGAL_SUFFIX_PATTERN, lower, flags=re.I):
            return self.make_result(
                row, True, name, "company", 0.92, "accept",
                "Contains clear legal entity suffix",
                "deterministic_legal_suffix"
            )

        if name.startswith("@") and not re.search(
            r"\b(inc|llc|ltd|limited|corp|corporation|company|communications|group)\b",
            lower,
        ):
            return self.make_result(
                row, False, None, "social_handle", 0.95, "drop",
                "Likely social media handle", "deterministic_social_handle"
            )

        if re.match(
            r"^\d+\s+(other\s+)?(companies|company|insurers|insurer|banks|casinos|institutions|financial institutions|competitors|firms|customers|suppliers|operations)\b",
            lower,
        ):
            return self.make_result(
                row, False, None, "generic_phrase", 0.99, "drop",
                "Generic quantified phrase", "deterministic_generic_phrase"
            )

        if re.search(r"\b(nanometer|duv source|technology node)\b", lower):
            return self.make_result(
                row, False, None, "technical_term", 0.95, "drop",
                "Technical descriptor", "deterministic_technical_term"
            )

        return None

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
                            "is_company": {"type": "boolean"},
                            "standardized_name": {"type": ["string", "null"]},
                            "entity_type": {
                                "type": "string",
                                "enum": [
                                    "company",
                                    "subsidiary",
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
                            "confidence": {"type": "number"},
                            "decision": {
                                "type": "string",
                                "enum": ["accept", "drop", "manual_review"],
                            },
                            "reason": {"type": "string"},
                        },
                        "required": [
                            "record_id",
                            "raw_name",
                            "is_company",
                            "standardized_name",
                            "entity_type",
                            "confidence",
                            "decision",
                            "reason",
                        ],
                    },
                }
            },
            "required": ["validations"],
        }

    def build_prompt(self, batch_records):
        records_text = json.dumps(batch_records, ensure_ascii=False, indent=2)

        return f"""
You are validating extracted competitor names from SEC 10-K competition sections.

For each record:
1. Decide whether raw_name is likely a real company or organization name.
2. Provide a STANDARDIZED company/organization name if possible.
3. Do not provide tickers, CIKs, GVKEYs, PERMNOs, CUSIPs, or other identifiers.

Use:
- record_id
- raw_name
- sic_context
- year_context
- frequency

Important:
- Return exactly one output for every input record.
- Preserve the exact record_id.
- Use SIC, years, and frequency only as context.
- If the string is a product/brand only, classify as brand_or_product and usually drop.
- If the string is a generic phrase, classify as generic_phrase and drop.
- If it is a historical company name, keep the historical company name as standardized_name.
- If there is an acquisition, DBA, parenthetical, or ownership note, standardize to the core company/parent name.
- Use manual_review only when truly uncertain.
- Prefer company classification when SIC/year/frequency strongly support firm-name interpretation.

Decision rules:
- accept: likely company/organization, confidence >= 0.85
- manual_review: ambiguous/context-dependent, confidence 0.55 to 0.84
- drop: not company/organization, or confidence < 0.55

Records:
{records_text}
"""

    def validate_batch_with_api(self, batch_records):
        response = self.client.responses.create(
            model=self.model_name,
            input=[
                {
                    "role": "system",
                    "content": "You are a careful research assistant cleaning company-name extraction data.",
                },
                {
                    "role": "user",
                    "content": self.build_prompt(batch_records),
                },
            ],
            text={
                "format": {
                    "type": "json_schema",
                    "name": "competitor_name_validation_batch",
                    "schema": self.build_schema(),
                    "strict": True,
                }
            },
            temperature=0,
        )

        self.total_api_calls += 1
        parsed = json.loads(response.output_text)
        return parsed["validations"]

    def prepare_input_data(self):
        df = pd.read_csv(self.input_csv)

        required_cols = [self.raw_name_col, self.sic_col, self.year_col]
        for col in required_cols:
            if col not in df.columns:
                raise ValueError(f"Required column not found in input file: {col}")

        if self.frequency_col and self.frequency_col not in df.columns:
            self.frequency_col = None

        df[self.raw_name_col] = df[self.raw_name_col].apply(self.normalize_string)

        grouped_cols = [self.raw_name_col, self.sic_col, self.year_col]

        if self.frequency_col:
            grouped = (
                df.groupby(grouped_cols, dropna=False)[self.frequency_col]
                .sum()
                .reset_index()
                .rename(columns={self.frequency_col: "frequency"})
            )
        else:
            grouped = df.groupby(grouped_cols, dropna=False).size().reset_index(name="frequency")

        grouped = grouped.rename(
            columns={
                self.raw_name_col: "raw_name",
                self.sic_col: "sic_context",
                self.year_col: "year_context",
            }
        )

        grouped["record_id"] = range(1, len(grouped) + 1)

        return grouped[
            [
                "record_id",
                "raw_name",
                "sic_context",
                "year_context",
                "frequency",
            ]
        ]

    def load_existing_results(self):
        if self.overwrite and self.output_csv.exists():
            self.output_csv.unlink()

        if self.output_csv.exists():
            return pd.read_csv(self.output_csv)

        return pd.DataFrame()

    def save_results_incrementally(self, new_results):
        new_df = pd.DataFrame(new_results)

        if self.output_csv.exists():
            old_df = pd.read_csv(self.output_csv)
            combined = pd.concat([old_df, new_df], ignore_index=True)
            combined = combined.drop_duplicates(subset=["record_id"], keep="last")
        else:
            combined = new_df

        combined.to_csv(self.output_csv, index=False)

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

    def process(self):
        df = self.prepare_input_data()
        existing = self.load_existing_results()

        if not existing.empty and "record_id" in existing.columns:
            processed_ids = set(existing["record_id"].astype(int))
        else:
            processed_ids = set()

        rows_to_api = []
        prefilter_results = []

        for _, row in df.iterrows():
            if int(row["record_id"]) in processed_ids:
                continue

            row_dict = row.to_dict()
            prefilter = self.deterministic_filter(row_dict)

            if prefilter is not None:
                prefilter_results.append(prefilter)
            else:
                rows_to_api.append(row_dict)

        if prefilter_results:
            self.save_results_incrementally(prefilter_results)

        total = len(rows_to_api)

        print("\n" + "=" * 80)
        print("STEP 7: LLM COMPETITOR NAME VALIDATION")
        print(f"Input records after deduplication: {len(df)}")
        print(f"Already processed: {len(processed_ids)}")
        print(f"Handled by deterministic prefilter: {len(prefilter_results)}")
        print(f"To send to API: {total}")
        print(f"Model: {self.model_name}")
        print(f"Batch size: {self.batch_size}")
        print("=" * 80 + "\n")

        start_time = time.time()

        for batch_start in range(0, total, self.batch_size):
            batch_id = batch_start // self.batch_size + 1
            batch = rows_to_api[batch_start: batch_start + self.batch_size]

            batch_records = [
                {
                    "record_id": int(r["record_id"]),
                    "raw_name": str(r["raw_name"]),
                    "sic_context": str(r["sic_context"]),
                    "year_context": str(r["year_context"]),
                    "frequency": int(r["frequency"]) if not pd.isna(r["frequency"]) else 1,
                }
                for r in batch
            ]

            print(f"[Batch {batch_id}] Processing {len(batch_records)} records...")

            batch_start_time = time.time()
            max_retries = 3

            for attempt in range(max_retries):
                try:
                    validations = self.validate_batch_with_api(batch_records)

                    validation_by_record_id = {
                        int(v["record_id"]): v for v in validations
                    }

                    final_results = []

                    for r in batch_records:
                        v = validation_by_record_id.get(int(r["record_id"]))

                        if v is None:
                            v = {
                                "record_id": r["record_id"],
                                "raw_name": r["raw_name"],
                                "is_company": False,
                                "standardized_name": None,
                                "entity_type": "unclear",
                                "confidence": 0.0,
                                "decision": "manual_review",
                                "reason": "Missing from model output",
                            }

                        final_results.append(
                            {
                                "record_id": r["record_id"],
                                "raw_name": r["raw_name"],
                                "sic_context": r["sic_context"],
                                "year_context": r["year_context"],
                                "frequency": r["frequency"],
                                "is_company": v["is_company"],
                                "standardized_name": v["standardized_name"],
                                "entity_type": v["entity_type"],
                                "confidence": v["confidence"],
                                "decision": v["decision"],
                                "reason": v["reason"],
                                "source": "openai_api",
                            }
                        )

                    self.save_results_incrementally(final_results)

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

        total_time = time.time() - start_time

        print("\n" + "=" * 80)
        print("STEP 7 COMPLETE")
        print(f"Total API calls: {self.total_api_calls}")
        print(f"Total API records processed: {self.total_records_processed}")
        print(f"Total time: {self.format_time(total_time)}")
        print(f"Output: {self.output_csv}")
        print("=" * 80 + "\n")

        self.create_final_splits()

    def create_final_splits(self):
        if not self.output_csv.exists():
            print("No output file found. No split files created.")
            return

        df = pd.read_csv(self.output_csv)

        accepted = df[df["decision"] == "accept"].copy()
        dropped = df[df["decision"] == "drop"].copy()
        manual = df[df["decision"] == "manual_review"].copy()

        accepted.to_csv(self.results_dir / "accepted_company_names.csv", index=False)
        dropped.to_csv(self.results_dir / "dropped_non_company_names.csv", index=False)
        manual.to_csv(self.results_dir / "manual_review_company_names.csv", index=False)

        print("Final split files created:")
        print(f"  Accepted: {len(accepted)}")
        print(f"  Dropped: {len(dropped)}")
        print(f"  Manual review: {len(manual)}")


def main():
    with open("config_step7.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    validator = LLMCompetitorNameValidator(
        input_csv=config["input_csv"],
        results_dir=config["results_dir"],
        issues_dir=config["issues_dir"],
        model_name=config.get("llm_model_name", "gpt-4.1-nano"),
        batch_size=config.get("batch_size", 100),
        overwrite=config.get("overwrite", False),
        raw_name_col=config.get("raw_name_col", "competitor_name"),
        sic_col=config.get("sic_col", "sic_files"),
        year_col=config.get("year_col", "years"),
        frequency_col=config.get("frequency_col", "frequency"),
    )

    validator.process()


if __name__ == "__main__":
    main()