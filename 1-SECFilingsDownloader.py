import pandas as pd
import requests
import time
import os
from pathlib import Path
import re
from datetime import datetime
import logging
import yaml

class SECFilingsDownloader:
    def __init__(self, email, company_name, download_dir, overwrite=True):
        """
        Initialize the SEC filings downloader.
        
        Args:
            email: Your email address for SEC API (required by SEC)
            company_name: Your company name
            download_dir: Directory to store downloaded files
            overwrite: Whether to overwrite existing downloaded files
        """
        self.headers = {
            'User-Agent': f'{company_name}/1.0 ({email})',
            'Accept-Encoding': 'gzip, deflate'
        }
        self.base_url = 'https://data.sec.gov'
        self.download_dir = Path(download_dir) 
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.overwrite = overwrite
        
        # Initialize main logger
        self.main_logger = None
        self.sic_logger = None
        
    def setup_logging(self, log_dir):
        """
        Set up logging to both console and files.
        
        Args:
            log_dir: Directory to store SIC-specific log files
        """
        # Create logs directory
        log_path = Path(log_dir) 
        log_path.mkdir(parents=True, exist_ok=True)
        
        # Create main session log file with timestamp in logs directory
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        main_log_file = log_path / f'sec_downloader_{timestamp}.log'
        
        # Configure main logger
        self.main_logger = logging.getLogger('SEC_Downloader')
        self.main_logger.setLevel(logging.INFO)
        
        # Clear any existing handlers
        self.main_logger.handlers.clear()
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_format)
        
        # Main file handler
        main_file_handler = logging.FileHandler(main_log_file, mode='w')
        main_file_handler.setLevel(logging.INFO)
        file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        main_file_handler.setFormatter(file_format)
        
        self.main_logger.addHandler(console_handler)
        self.main_logger.addHandler(main_file_handler)
        
        self.log_dir = log_path
        
    def setup_sic_logger(self, sic_code):
        """
        Set up logger for a specific SIC code.
        
        Args:
            sic_code: SIC code for the logger
        """
        # Remove existing SIC logger handlers if any
        if self.sic_logger:
            for handler in self.sic_logger.handlers[:]:
                handler.close()
                self.sic_logger.removeHandler(handler)
        
        # Create SIC-specific logger
        sic_log_file = self.log_dir / f'{sic_code}.log'
        
        self.sic_logger = logging.getLogger(f'SIC_{sic_code}')
        self.sic_logger.setLevel(logging.INFO)
        self.sic_logger.handlers.clear()
        
        # SIC file handler (append mode for re-runs)
        sic_file_handler = logging.FileHandler(sic_log_file, mode='a')
        sic_file_handler.setLevel(logging.INFO)
        file_format = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        sic_file_handler.setFormatter(file_format)
        
        self.sic_logger.addHandler(sic_file_handler)
        
    def log(self, message, level='info', sic_only=False):
        """
        Log a message to appropriate loggers.
        
        Args:
            message: Message to log
            level: Log level ('info', 'error', 'warning')
            sic_only: If True, only log to SIC logger, not main logger
        """
        log_func = getattr(logging, level.lower(), logging.info)
        
        if not sic_only and self.main_logger:
            log_func_main = getattr(self.main_logger, level.lower(), self.main_logger.info)
            log_func_main(message)
        
        if self.sic_logger:
            log_func_sic = getattr(self.sic_logger, level.lower(), self.sic_logger.info)
            log_func_sic(message)
        
    def get_company_filings(self, cik, form_types=['10-K', '20-F']):
        """
        Get filing information for a specific CIK.
        
        Args:
            cik: Company's CIK number
            form_types: List of form types to retrieve
            
        Returns:
            Tuple of (filings list, error_info dict or None)
        """
        # Pad CIK with zeros to 10 digits
        cik_padded = str(cik).zfill(10)
        url = f'{self.base_url}/submissions/CIK{cik_padded}.json'
        
        response = None
        try:
            time.sleep(0.1)  # SEC rate limiting: 10 requests per second
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            filings = []
            recent = data.get('filings', {}).get('recent', {})
            
            if not recent:
                return [], None
            
            forms = recent.get('form', [])
            filing_dates = recent.get('filingDate', [])
            report_dates = recent.get('reportDate', [])
            accession_numbers = recent.get('accessionNumber', [])
            primary_documents = recent.get('primaryDocument', [])
            
            for i, form in enumerate(forms):
                if form in form_types:
                    accession = accession_numbers[i].replace('-', '')
                    filing_info = {
                        'cik': cik,
                        'form_type': form,
                        'filing_date': filing_dates[i],
                        'report_date': report_dates[i] if i < len(report_dates) else None,
                        'accession_number': accession_numbers[i],
                        'primary_document': primary_documents[i],
                        'href': f'https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{primary_documents[i]}'
                    }
                    filings.append(filing_info)
            
            return filings, None
            
        except requests.exceptions.RequestException as e:
            error_info = {
                'cik': cik,
                'error_type': 'fetch_filings',
                'error_message': str(e),
                'url': url,
                'status_code': response.status_code if response is not None else None
            }
            self.log(f"Error fetching filings for CIK {cik}: {e}", level='error')
            return [], error_info
    
    def download_filing(self, filing_info, sic_code, retry_on_503=True):
        """
        Download a single filing.
        
        Args:
            filing_info: Dictionary with filing information
            sic_code: SIC code for organizing files
            retry_on_503: Whether to retry once on 503 errors
            
        Returns:
            Tuple of (download result dict or None, error_info dict or None)
        """
        # Create directory for this SIC code
        sic_dir = self.download_dir / str(sic_code)
        sic_dir.mkdir(exist_ok=True)
        
        # Generate filename
        cik = filing_info['cik']
        date = filing_info['filing_date'].replace('-', '')
        form = filing_info['form_type'].replace('-', '')
        filename = f"CIK{cik}_{form}_{date}.html"
        filepath = sic_dir / filename
        
        # Extract file number from accession number
        accession = filing_info['accession_number']
        file_number = accession
        
        # Check if file already exists
        if not self.overwrite and filepath.exists():
            self.log(f"File already exists, skipping: {filename}")
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            result = {
                'cik': cik,
                'downloaded_file_name': filename,
                'doc_name': filing_info['form_type'],
                'filingDate': filing_info['filing_date'],
                'reportDate': filing_info.get('report_date'),
                'file_number': file_number,
                'href': filing_info['href'],
                'downloaded_path': str(filepath),
                'html_char_count': len(content)
            }
            return result, None
        
        response = None
        try:
            time.sleep(0.1)  # SEC rate limiting
            response = requests.get(filing_info['href'], headers=self.headers, timeout=30)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            result = {
                'cik': cik,
                'downloaded_file_name': filename,
                'doc_name': filing_info['form_type'],
                'filingDate': filing_info['filing_date'],
                'reportDate': filing_info.get('report_date'),
                'file_number': file_number,
                'href': filing_info['href'],
                'downloaded_path': str(filepath),
                'html_char_count': len(response.text)
            }
            return result, None
            
        except requests.exceptions.RequestException as e:
            # Check if it's a 503 error and retry is enabled
            if response is not None and response.status_code == 503 and retry_on_503:
                self.log(f"503 error, waiting 1 second and retrying...", level='warning')
                time.sleep(1)
                return self.download_filing(filing_info, sic_code, retry_on_503=False)
            
            error_info = {
                'cik': cik,
                'error_type': 'download_filing',
                'error_message': str(e),
                'url': filing_info['href'],
                'status_code': response.status_code if response is not None else None,
                'form_type': filing_info['form_type'],
                'filing_date': filing_info['filing_date']
            }
            self.log(f"Error downloading {filing_info['href']}: {e}", level='error')
            return None, error_info
    
    def process_sic_code(self, df, sic_code, cik_col='cik', sic_col='sic', output_dir='results', issues_dir='issues'):
        """
        Process all CIKs for a given SIC code.
        
        Args:
            df: DataFrame with CIK and SIC columns
            sic_code: SIC code to process
            cik_col: Name of the CIK column
            sic_col: Name of the SIC column
            output_dir: Directory to store result CSV files
            issues_dir: Directory to store issue CSV files
        """
        # Create output directories
        output_path = Path(output_dir) 
        issues_path = Path(issues_dir) 
        output_path.mkdir(parents=True, exist_ok=True)
        issues_path.mkdir(parents=True, exist_ok=True)
        
        # Filter for specific SIC code
        sic_df = df[df[sic_col] == sic_code].copy()
        
        if sic_df.empty:
            self.log(f"No companies found for SIC code {sic_code}")
            return
        
        original_count = len(sic_df)
        
        # Remove rows with null/NaN CIK values
        sic_df = sic_df.dropna(subset=[cik_col])
        null_removed = original_count - len(sic_df)
        
        if null_removed > 0:
            self.log(f"Removed {null_removed} entries with null/NaN CIK values")
        
        # Convert CIK to integer (in case it's read as float/decimal)
        sic_df[cik_col] = sic_df[cik_col].astype(int)
        
        # Drop duplicates based on CIK
        before_dedup = len(sic_df)
        sic_df = sic_df.drop_duplicates(subset=[cik_col])
        duplicates_removed = before_dedup - len(sic_df)
        
        if duplicates_removed > 0:
            self.log(f"Removed {duplicates_removed} duplicate CIK entries")
        
        self.log(f"Processing SIC code {sic_code} with {len(sic_df)} unique companies...")
        
        results = []
        errors = []
        
        for idx, row in sic_df.iterrows():
            cik = row[cik_col]
            self.log(f"Processing CIK {cik}...")
            if cik != 886328:
                continue
            else:
                print("dddd")
            # Get filings for this CIK
            filings, error = self.get_company_filings(cik)
            
            if error:
                errors.append(error)
                continue
            
            # Download each filing
            for filing in filings:
                download_result, download_error = self.download_filing(filing, sic_code)
                if download_result:
                    results.append(download_result)
                if download_error:
                    errors.append(download_error)
        
        # Save results to CSV
        output_file = output_path / f"{sic_code}.csv"
        
        if results:
            results_df = pd.DataFrame(results)
            
            # Check if CSV already exists
            if output_file.exists():
                self.log(f"Merging with existing {output_file}...")
                existing_df = pd.read_csv(output_file)
                
                # Add html_char_count column if missing
                if 'html_char_count' not in existing_df.columns:
                    self.log("Adding html_char_count column to existing CSV...")
                    existing_df['html_char_count'] = existing_df['downloaded_path'].apply(
                        lambda path: len(open(path, 'r', encoding='utf-8', errors='ignore').read()) if os.path.exists(path) else 0
                    )
                
                # Combine existing and new results
                combined_df = pd.concat([existing_df, results_df], ignore_index=True)
                
                # Remove duplicates based on key columns (cik, doc_name, filingDate)
                combined_df = combined_df.drop_duplicates(
                    subset=['cik', 'doc_name', 'filingDate'], 
                    keep='first'
                )
                
                combined_df.to_csv(output_file, index=False)
                self.log(f"Saved {len(combined_df)} total filings to {output_file} ({len(results)} new)")
            else:
                results_df.to_csv(output_file, index=False)
                self.log(f"Saved {len(results)} filings to {output_file}")
        else:
            # If no new results but file exists, just report
            if output_file.exists():
                existing_df = pd.read_csv(output_file)
                self.log(f"No new filings to download. {output_file} contains {len(existing_df)} existing filings")
            else:
                self.log(f"No filings downloaded for SIC code {sic_code}")
        
        # Save errors to CSV
        error_file = issues_path / f"{sic_code}_issues.csv"
        
        if errors:
            errors_df = pd.DataFrame(errors)
            
            # Check if error CSV already exists
            if error_file.exists():
                self.log(f"Merging with existing {error_file}...")
                existing_errors_df = pd.read_csv(error_file)
                
                # Combine existing and new errors
                combined_errors_df = pd.concat([existing_errors_df, errors_df], ignore_index=True)
                
                # Remove duplicates based on key columns
                combined_errors_df = combined_errors_df.drop_duplicates(
                    subset=['cik', 'error_type', 'url'], 
                    keep='last'  # Keep last occurrence to show most recent error
                )
                
                combined_errors_df.to_csv(error_file, index=False)
                self.log(f"Saved {len(combined_errors_df)} total errors to {error_file} ({len(errors)} new)")
            else:
                errors_df.to_csv(error_file, index=False)
                self.log(f"Saved {len(errors)} errors to {error_file}")
        else:
            # If no new errors but file exists, just report
            if error_file.exists():
                existing_errors_df = pd.read_csv(error_file)
                self.log(f"No new errors. {error_file} contains {len(existing_errors_df)} existing errors")
            else:
                self.log("No errors encountered")

def main():
    # Load configuration from YAML file
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
        INPUT_CSV = config['input_csv']
        sic_codes_str = config['sic_codes']
        EMAIL = config['email']
        COMPANY_NAME = config['company_name']
        DOWNLOAD_DIR = str(Path(config['filings_dir']) / config['download_sub'])
        RESULTS_DIR = str(Path(config['results_dir']) / config['download_sub'])
        ISSUES_DIR = str(Path(config['issues_dir']) / config['download_sub'])
        LOG_DIR = str(Path(config['log_dir']) / config['download_sub']) #config['log_dir']
        CIK_COLUMN = config['cik_column']
        SIC_COLUMN = config['sic_column']
        overwrite_downloaded_files = config.get('overwrite_downloaded_files', True)
    
    # Parse SIC codes
    if sic_codes_str == '*':
        df = pd.read_csv(INPUT_CSV)
        SIC_CODES = df['sic'].dropna().unique().tolist()
        SIC_CODES = [int(sic) for sic in SIC_CODES]  # Ensure integers
    else:
        SIC_CODES = [int(x.strip()) for x in sic_codes_str.split(',')]
    
    # Initialize downloader
    downloader = SECFilingsDownloader(email=EMAIL, company_name=COMPANY_NAME, download_dir=DOWNLOAD_DIR, overwrite=overwrite_downloaded_files)
    
    # Set up logging
    downloader.setup_logging(log_dir=LOG_DIR)
    
    # Load data
    downloader.log(f"Loading data from {INPUT_CSV}...")
    df = pd.read_csv(INPUT_CSV)
    
    # Ensure CIK and SIC columns exist
    if CIK_COLUMN not in df.columns or SIC_COLUMN not in df.columns:
        downloader.log(f"Error: CSV must contain '{CIK_COLUMN}' and '{SIC_COLUMN}' columns", level='error')
        downloader.log(f"Available columns: {list(df.columns)}", level='error')
        return
    
    # Process each SIC code
    downloader.log(f"Processing {len(SIC_CODES)} SIC codes...")
    for i, sic_code in enumerate(SIC_CODES, 1):
        downloader.log(f"\n{'='*80}")
        downloader.log(f"Processing SIC code {i}/{len(SIC_CODES)}: {sic_code}")
        downloader.log(f"{'='*80}")
        
        # Set up SIC-specific logger
        downloader.setup_sic_logger(sic_code)
        
        downloader.process_sic_code(
            df, sic_code, 
            cik_col=CIK_COLUMN, 
            sic_col=SIC_COLUMN,
            output_dir=RESULTS_DIR,
            issues_dir=ISSUES_DIR
        )
    
    downloader.log("\n" + "="*80)
    downloader.log("All downloads complete!")
    downloader.log(f"Results saved to: {RESULTS_DIR}/")
    downloader.log(f"Issues saved to: {ISSUES_DIR}/")
    downloader.log("="*80)

if __name__ == "__main__":
    main()