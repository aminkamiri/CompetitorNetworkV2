import os
from pathlib import Path
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import html2text
import yaml
import pandas as pd

class SECFilingTextExtractor:
    def __init__(self, input_dir, output_dir, overwrite=True):
        """
        Initialize the text extractor.
        
        Args:
            input_dir: Directory containing HTML files
            output_dir: Directory to store extracted text files
            overwrite: Whether to overwrite existing text files
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.overwrite = overwrite
        
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
        self.driver.get(file_path)
        
        # Try to get text from document element, fall back to body
        try:
            full_text = self.driver.find_element(By.XPATH, "//document").text
        except:
            full_text = self.driver.find_element(By.XPATH, "html/body").text
        
        return full_text
    
    
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
    
    
    def process_sic_code(self, sic_code):
        """
        Process all HTML files for a given SIC code.
        
        Args:
            sic_code: SIC code to process
        """
        input_sic_dir = self.input_dir / str(sic_code)
        output_sic_dir = self.output_dir / str(sic_code)
        
        if not input_sic_dir.exists():
            print(f"No files found for SIC code {sic_code}")
            return
        
        # Create output directory
        output_sic_dir.mkdir(parents=True, exist_ok=True)
                
        html_files = list(input_sic_dir.glob('*.html'))
        print(f"Processing {len(html_files)} files for SIC code {sic_code}...")
        
        for html_file in html_files:
            print(f"Extracting text from {html_file.name}...")
            
            # Save full text
            text_filename = html_file.stem + '.txt'
            text_filepath = output_sic_dir / text_filename
            
            if not self.overwrite and text_filepath.exists():
                print(f"Skipping {html_file.name}, text file already exists.")
                continue
            
            print(f"Processing {html_file.name}...")
            
            # Extract full text
            text = self.extract_text_from_html(html_file)
            
            with open(text_filepath, 'w', encoding='utf-8') as f:
                f.write(text)
            
            
        print(f"Completed processing SIC code {sic_code}")

def main():
    # Load configuration from YAML file
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
        INPUT_CSV = config['input_csv']
        sic_codes_str = config['sic_codes']
        FILINGS_DOWNLOADS = str(Path(config['filings_dir']) / config['download_sub'])
        FILINGS_TEXT = str(Path(config['filings_dir']) / config['text_sub'])
        overwrite_text_files = config.get('overwrite_text_files', True)
    
    # Parse SIC codes
    if sic_codes_str == '*':
        df = pd.read_csv(INPUT_CSV)
        SIC_CODES = df['sic'].dropna().unique().tolist()
        SIC_CODES = [int(sic) for sic in SIC_CODES]  # Ensure integers
    else:
        SIC_CODES = [int(x.strip()) for x in sic_codes_str.split(',')]
    
    # Initialize extractor
    extractor = SECFilingTextExtractor(input_dir=FILINGS_DOWNLOADS, output_dir=FILINGS_TEXT, overwrite=overwrite_text_files)
    
    # Process each SIC code
    for sic_code in SIC_CODES:
        print(f"\n{'='*80}")
        print(f"Processing SIC code: {sic_code}")
        print(f"{'='*80}")
        extractor.process_sic_code(sic_code)
    
    print("\n" + "="*80)
    print("Text extraction complete!")
    print("Full text saved to: filings/text/{sic}/")
    print("Markdown saved to: filings/text/{sic}/")
    print("Competition paragraphs saved to: filings/extracted/{sic}/")
    print("="*80)

if __name__ == "__main__":
    main()