# SEC Filings Downloader and Text Extractor

This project provides tools to download SEC filings and extract text content from them.

## Features

- Download SEC filings (10-K, 20-F) for specified SIC codes
- Extract plain text and Markdown from HTML filings
- Configurable via YAML file
- Clean extracted text by removing page numbers and table of contents

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

## Configuration

Edit `config.yaml` to set:
- SIC codes to process
- Input/output directories
- Email for SEC API
- Other parameters

## Requirements

- Python 3.8+
- Google Chrome
- pandas
- requests
- selenium
- html2text
- PyYAML

## License

[Add license information]