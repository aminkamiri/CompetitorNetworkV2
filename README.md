# SEC Filing Competitor Extraction Pipeline

This project provides a four-stage pipeline for downloading SEC filings, extracting
their text, selecting competition-related passages, and identifying named
competitors with an OpenAI model.

## Features

- Download SEC filings (10-K and 20-F) for specified SIC codes
- Extract plain text from HTML filings with headless Chrome
- Select focused snippets around competition-related keywords
- Extract competitor company names with a configurable OpenAI model
- Organize filings and results by SIC code
- Record processing metadata, logs, and errors in CSV and log files
- Configure the pipeline through `config.yaml`

## Pipeline Scripts

### 1. `1-SECFilingsDownloader.py`

Reads companies and their CIK/SIC values from the configured input CSV. For each
selected SIC code, it queries the SEC submissions API for current and historical
10-K and 20-F filings, then downloads each filing's primary HTML document. It
respects the SEC request rate, retries a 503 response once, and supports either
overwriting or reusing downloaded files.

Downloaded HTML files are grouped into SIC-specific directories. The script also
writes per-SIC filing metadata CSVs, issue CSVs for failed API requests or
downloads, a session log, and individual SIC logs. Existing metadata and issue
files are merged and deduplicated on subsequent runs.

### 2. `2-SECFilingTextExtractor.py`

Processes the downloaded HTML files by SIC code and loads each local filing in
headless Chrome through Selenium. It extracts the rendered text from the filing's
`document` element, falling back to the HTML body when necessary, and saves one
UTF-8 `.txt` file per filing. If the browser session fails, it restarts Chrome and
retries up to three times.

The script displays local and overall progress, can skip existing text files when
overwriting is disabled, and records extraction failures in a per-SIC issue CSV.
The class also contains an HTML-to-Markdown helper, but the main pipeline currently
uses the plain-text extraction method.

### 3. `3-SECFilingParagraphExtractor.py`

Reads each filing's extracted text and searches its paragraphs for whole-word,
case-insensitive matches from the configured competition-keyword file. Around
each match it keeps up to 100 characters before and 1,000 characters after the
term, merges overlapping ranges, and adds ellipses where context was trimmed.
The resulting competition-focused snippets are saved as `.txt` files in
SIC-specific directories.

For each SIC code, the script also writes a CSV containing the source and
extracted character counts, the number of double line breaks, and the extracted
text's percentage of the original filing. A text-cleaning helper is available in
the class, although it is not invoked by the current extraction path.

### 4. `4-SECFilingLLMCompetitorExtractor.py`

Sends the competition-focused text from step 3 to the configured OpenAI chat
model through LangChain. Text that exceeds the configured token limit is divided
into chunks. The model returns structured competitor company names, which are
deduplicated, sorted, joined with `|`, and saved with the source filename in a
per-SIC results CSV.

The script retries rate-limit failures up to three times with increasing waits,
saves after every processed file so work can be resumed, skips completed files
unless overwrite mode is enabled, records failures in issue CSVs, and reports
processing time, call counts, and estimated completion time.

### 5. `5-map(rev7).py`

Maps the competitor names extracted in step 4 to company identifiers. It applies
encoding repairs, company-name standardization, legal-form normalization, safe
suffix removal, and multiple name variants before matching each name against the
configured year-specific company alias bridge. When direct matching fails, it
also performs guarded parent-prefix recovery and records all candidate and safety
diagnostics.

The script writes one mapped Excel workbook per SIC code, including aligned
competitor names, CIKs, GVKEYs, match sources, match methods, and bridge names. It
also creates duplicate-bridge reports, parent-recovery diagnostics, per-SIC
competitor diagnostics, and an overall mapping summary.

### 6. `6-merge-descriptives(rev7).py`

Combines the SIC-level mapped workbooks from step 5 into project-wide wide and
long datasets. It parses focal CIKs and filing years from filenames, aligns each
competitor mention with its identifier and matching metadata, excludes 20-F
records from the principal outputs, and audits alignment and bridge problems.

It produces mention- and focal-year-level descriptive tables by year and SIC,
match-source and match-method diagnostics, missing-name frequency reports, and
review samples. Its full residual-name review becomes the input to step 7; a
separate high-frequency pilot file is also generated.

### 7. `7-LLM-Residual-Classification(rev4).py`

Uses the configured OpenAI model to classify competitor names that remain
unmatched after deterministic mapping. In batches, it assigns an entity class,
one of three decisions (`accept_for_manual_alias_bridge`, `drop`, or
`manual_review`), a confidence score and rationale, and—where appropriate—a
suggested alias name and scope. Responses are schema-constrained, normalized,
checked for missing records, and saved incrementally so an interrupted run can
resume.

Outputs include the complete classified residual file, issue and summary files,
decision-specific review files, and validation samples. Command-line and
`config.yaml` options control the model, batch size, record limit, delay, and
overwrite behavior.

### 8. `8-Final-Integration-And-Validation(rev3).py`

Integrates the mapped long dataset from step 6 with step 7 classifications and
the optional manual alias bridge. It preserves existing step-5 identifiers,
applies approved manual aliases to unresolved mentions, labels LLM-dropped and
still-unresolved records, and assigns a traceable final match stage and
resolution to every mention.

It writes the integrated long-form competitor file, a final mapping summary,
unmatched and dropped residual files, manual-review queues, alias candidates, and
validation samples with blank reviewer-note columns.

### 8.5. `8.5-Alias-Candidate-Generation(rev10).py`

Generates and ranks deterministic company candidates for residual aliases from
step 7. It searches year-specific and identifier-level bridges using exact,
legal-form, suffix-stripped, approved-abbreviation, ticker, other-year, and
parent-prefix rules. Candidate identifiers are checked against the
company-identifier/year panel, and source quality, match rule, ambiguity, year
support, and name characteristics contribute to conservative review tiers.

The script writes full and review-focused candidate tables, summaries, top-100
samples, acceptance-tier scenario audits, and comparisons with earlier candidate
runs. These files support human decisions rather than silently treating every
candidate as an accepted match.

### 8.6. `8.6-PreStep7-Generic-Rescue.py`

Re-examines names previously treated as generic phrases before step 7 and tries
to rescue company-like cases. It searches the year and identifier bridges plus
RepRisk and Capital IQ reference data, validates public identifiers for the
relevant years, ranks the evidence, and keeps a best candidate for each alias.

It produces candidate and best-match CSVs, source/rule summaries, and a review
sample. The filename reflects the population being rescued; it remains listed
here in numeric pipeline order.

### 8.7. `8.7-Unresolved-Residual-Recovery.py`

Builds another deterministic recovery pass for aliases that remain unresolved in
the status-enriched final mention data. It aggregates occurrences and years,
normalizes exact and canonical name keys, and searches year-specific and
identifier bridges along with external company sources. Candidates are ranked
with year validity and source evidence, then assigned suggested resolution
reasons.

Outputs include all candidates, the best candidate per residual, resolution and
source/rule summaries, and Excel review files for manual inspection.

### 8.7b. `8.7b-Refine-Unresolved-Recovery-Candidates.py`

Refines the main step-8.7 candidate set. It adds SIC support, checks overlap with
step-8.5 decisions, measures candidate ambiguity and score gaps, and applies more
conservative status rules to determine which recoveries are strong enough to
propose and which still require review.

It saves refined all-candidate and best-candidate CSVs, a review queue, and
summary tables by status and source/rule.

### 8.7c. `8.7c-CIQ-Common-Unresolved-Recovery.py`

Targets residual names not settled by the main step-8.7 pass and searches the
Capital IQ common-company data using exact, canonical, and constrained name
keys. It checks date overlap with the residual years and attaches GVKEYs through
the Capital IQ crosswalk when available.

The resulting candidate and best-candidate files distinguish Capital IQ matches
that can upgrade to a public identifier from those that provide supporting
external evidence only, with corresponding summary tables.

### 8.8. `8.8-Consolidate-Unresolved-Recovery.py`

Consolidates the refined step-8.7 results, Capital IQ recovery results, and
audited no-evidence patterns into one residual-recovery master table. It assigns
proposed actions and reasons while retaining provenance, identifiers, match
rules, and review context from the contributing stages.

It writes the consolidated master file, a manual-review queue, overall and
source-level summaries, and a focused file of the highest-frequency names that
still have no external evidence.

### 8.8b. `8.8b-Partial-External-Evidence.py`

Adds a final evidence pass for step-8.8 records that have plausible external
names but incomplete public identifiers. It searches Capital IQ/GVKEY, RepRisk,
and IBES data using exact, canonical, possessive, and safe-prefix matching, ranks
the resulting evidence, and incorporates the best result into revised master and
review files.

Outputs include all partial-evidence candidates, best candidates, updated CSV
and Excel review artifacts, and a summary of the evidence found.

### 9. `9-Final-Aggregation-And-Export(rev3).py`

Applies reviewed step-8 recovery decisions to the status-enriched mention data
and creates the final deliverables. It recovers focal GVKEYs from identifier
panels and bridge files, preserves an internal audit trail, standardizes missing
identifiers, separates identified from unresolved mentions, and aggregates
identified mentions into clean focal-company/competitor/year network edges.

The script exports an internal audit dataset, clean all-status and identified-only
mention files, the identified competitor-edge file, status and unique-name
summaries, rule-extension and validation-error reports, unresolved exclusions,
human-rejected or corrected aliases, and a focal-GVKEY recovery audit.

### 9 audit. `9-Final-Status-Audit-And-Validation.py`

Creates the status-enriched input used by the final step-9 export. It processes
the final mention data in chunks, joins step-7 classifications, distinguishes
identified, dropped, pre-step-7 generic, and unresolved records, and records the
combination of final status, match stage, and resolution.

It writes the status-enriched long file, mention- and unique-name summaries,
stage and step-7 decision summaries, a unique-name review frame, and stratified
validation samples. Run this audit before the step-9 aggregation script when its
status output needs to be regenerated.

## Installation

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Install Chrome browser (required for text extraction)

## Usage

1. Configure `config.yaml` with your settings
2. Run the downloader:
   ```bash
   python 1-SECFilingsDownloader.py
   ```
3. Run the text extractor:
   ```bash
   python 2-SECFilingTextExtractor.py
   ```
4. Extract competition-related passages:
   ```bash
   python 3-SECFilingParagraphExtractor.py
   ```
5. Extract competitor names with the configured OpenAI model:
   ```bash
   python 4-SECFilingLLMCompetitorExtractor.py
   ```

## Configuration

Edit `config.yaml` to set:
- SIC codes to process
- Input/output directories
- Email for SEC API
- SEC User-Agent company name
- Filing, results, issues, and log directories
- Competition keywords and token separators
- OpenAI API key file, model, prompt, and maximum chunk size
- Overwrite behavior for each pipeline stage
- Other parameters

## Requirements

- Python 3.8+
- Google Chrome
- pandas
- requests
- selenium
- html2text
- PyYAML
- LangChain OpenAI integration
- Pydantic
- tiktoken

## License

[Add license information]
