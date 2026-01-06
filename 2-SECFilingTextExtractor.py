import os
from pathlib import Path
import re
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import InvalidSessionIdException, NoSuchElementException, WebDriverException
import html2text
import yaml
import pandas as pd

class SECFilingTextExtractor:
    def __init__(self, input_dir, output_dir, issues_dir, overwrite=True):
        """
        Initialize the text extractor.
        
        Args:
            input_dir: Directory containing HTML files
            output_dir: Directory to store extracted text files
            issues_dir: Directory to store issue CSV files
            overwrite: Whether to overwrite existing text files
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.issues_dir = Path(issues_dir)
        self.overwrite = overwrite
        
        self._setup_driver()
        
    def _setup_driver(self):
        # Set up Selenium with headless Chrome
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        
    def __del__(self):
        """Clean up Selenium driver."""
        if hasattr(self, 'driver'):
            self.driver.quit()
    
    def extract_text_from_html(self, html_file):
        """
        Extract text from HTML file using Selenium.
        
        Args:
            html_file: Path to HTML file
            
        Returns:
            Extracted text with paragraphs separated by \n\n
        """
        # Load the HTML file
        file_path = f"file:///{html_file.absolute().as_posix()}"
        
        last_error = None
        for attempt in range(3):
            try:
                self.driver.get(file_path)
                
                # Try to get text from document element, fall back to body
                try:
                    full_text = self.driver.find_element(By.XPATH, "//document").text
                except NoSuchElementException:
                    full_text = self.driver.find_element(By.XPATH, "html/body").text
                
                return full_text
            except (InvalidSessionIdException, WebDriverException, TimeoutError) as e: 
                last_error = e
                print(f"Session issue or timeout detected while processing {html_file.name}. Restarting driver (Attempt {attempt+1}/3)...")
                try:
                    self.driver.quit()
                except:
                    pass
                self._setup_driver()
        
        raise InvalidSessionIdException(f"Failed to extract text from {html_file.name} after retries. Last error: {last_error}")
    
    
    def extract_markdown_from_html(self, html_file):
        """
        Extract Markdown from HTML file using Selenium and html2text.
        
        Args:
            html_file: Path to HTML file
            
        Returns:
            Extracted Markdown
        """
        # Load the HTML file
        file_path = f"file:///{html_file.absolute().as_posix()}"
        self.driver.get(file_path)
        
        # Get the inner HTML of the body or document element (similar to text extraction)
        try:
            # Try to get the document element's inner HTML
            content_html = self.driver.find_element(By.XPATH, "//document").get_attribute("innerHTML")
        except:
            # Fall back to body element's inner HTML
            content_html = self.driver.find_element(By.XPATH, "html/body").get_attribute("innerHTML")
        
        # Convert the targeted HTML to Markdown
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = True
        h.ignore_tables = False
        markdown = h.handle(content_html)
        
        return markdown
    
    
    def clean_extracted_text(self, text):
        """
        Clean extracted text by removing unwanted lines using regex.
        
        Args:
            text: The extracted text to clean
            
        Returns:
            Cleaned text
        """
        # Remove lines containing only "Table of contents" (case insensitive, with spaces)
        text = re.sub(r'^\n\s*table of content[s]?\s*\n$', '', text, flags= re.IGNORECASE)
        
        # Remove lines containing page numbers (standalone numbers or "page" followed by numbers/dashes)
        text = re.sub(r'^\n\s*(page[-\s]*\d+[-\d]*|\d+)\s*\n$', '', text, flags= re.IGNORECASE)
        
        # Remove extra blank lines that might result from removals
        # text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        
        return text
    
    
    def process_sic_code(self, sic_code, global_start_index=0, global_total_files=0, global_start_time=None):
        """
        Process all HTML files for a given SIC code.
        
        Args:
            sic_code: SIC code to process
            global_start_index: Starting index for global progress
            global_total_files: Total number of files across all SIC codes
            global_start_time: Timestamp when the global process started
        """
        input_sic_dir = self.input_dir / str(sic_code)
        output_sic_dir = self.output_dir / str(sic_code)
        
        if not input_sic_dir.exists():
            print(f"No files found for SIC code {sic_code}")
            return 0
        
        # Create output directory
        output_sic_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup issues directory and file
        self.issues_dir.mkdir(parents=True, exist_ok=True)
        issues_csv = self.issues_dir / f"{sic_code}_issues.csv"
        
        if issues_csv.exists():
            existing_issues = pd.read_csv(issues_csv)
        else:
            existing_issues = pd.DataFrame(columns=['filename', 'error'])
                
        html_files = list(input_sic_dir.glob('*.html'))
        local_total = len(html_files)
        print(f"Processing {len(html_files)} files for SIC code {sic_code}...")
        
        for i, html_file in enumerate(html_files):
            file_start_time = time.time()
            global_current = global_start_index + i + 1
            files_left = global_total_files - global_current
            
            elapsed_total = time.time() - global_start_time if global_start_time else 0
            elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed_total))
            
            progress_info = f"[SIC: {i+1}/{local_total}] [Global: {global_current}/{global_total_files} | Left: {files_left}] [Elapsed: {elapsed_str}]"
            print(f"{progress_info} Extracting text from {html_file.name}..." + " " * 20, end='\r')
            
            # Save full text
            text_filename = html_file.stem + '.txt'
            text_filepath = output_sic_dir / text_filename
            
            if not self.overwrite and text_filepath.exists():
                # print(f"  > Skipping {html_file.name}, text file already exists.")
                continue
            
            
            try:
                # Extract full text
                text = self.extract_text_from_html(html_file)
                
                with open(text_filepath, 'w', encoding='utf-8') as f:
                    f.write(text)
            except Exception as e:
                print(f"\nFailed to extract text from {html_file.name}: {e}")
                new_issue = {'filename': html_file.name, 'error': str(e)}
                existing_issues = pd.concat([existing_issues, pd.DataFrame([new_issue])], ignore_index=True)
                existing_issues.to_csv(issues_csv, index=False)
            
            file_duration = time.time() - file_start_time
            # print(f"  > Completed {html_file.name} in {file_duration:.2f}s")
            
            
        print(f"\nCompleted processing SIC code {sic_code}")
        return local_total

def main():
    # Load configuration from YAML file
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
        INPUT_CSV = config['input_csv']
        sic_codes_str = config['sic_codes']
        FILINGS_DOWNLOADS = str(Path(config['filings_dir']) / config['download_sub'])
        FILINGS_TEXT = str(Path(config['filings_dir']) / config['text_sub'])
        ISSUES_DIR = str(Path(config['issues_dir']) / config['text_sub'])
        overwrite_text_files = config.get('overwrite_text_files', True)
    
    # Parse SIC codes
    if sic_codes_str == '*':
        df = pd.read_csv(INPUT_CSV)
        SIC_CODES = df['sic'].dropna().unique().tolist()
        SIC_CODES = [int(sic) for sic in SIC_CODES]  # Ensure integers
    else:
        SIC_CODES = [int(x.strip()) for x in sic_codes_str.split(',')]
    
    # Initialize extractor
    extractor = SECFilingTextExtractor(input_dir=FILINGS_DOWNLOADS, output_dir=FILINGS_TEXT, issues_dir=ISSUES_DIR, overwrite=overwrite_text_files)
    
    # Calculate total files to process
    print("Calculating total files...")
    total_files = 0
    for sic_code in SIC_CODES:
        sic_dir = Path(FILINGS_DOWNLOADS) / str(sic_code)
        if sic_dir.exists():
            total_files += len(list(sic_dir.glob('*.html')))
    
    print(f"Total files to process across {len(SIC_CODES)} SIC codes: {total_files}")
    
    global_processed = 0
    global_start_time = time.time()
    
    # Process each SIC code
    for sic_code in SIC_CODES:
        print(f"\n{'='*80}")
        print(f"Processing SIC code: {sic_code}")
        print(f"{'='*80}")
        processed_count = extractor.process_sic_code(sic_code, global_processed, total_files, global_start_time)
        global_processed += processed_count
    
    print("\n" + "="*80)
    print("Text extraction complete!")
    print("Full text saved to: filings/text/{sic}/")
    print("Markdown saved to: filings/text/{sic}/")
    print(f"Issues saved to: {ISSUES_DIR}/")
    print("Competition paragraphs saved to: filings/extracted/{sic}/")
    print("="*80)

if __name__ == "__main__":
    main()