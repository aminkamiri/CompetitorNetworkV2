import os
from pathlib import Path
import re
import yaml
import pandas as pd

class CompetitorsParagraphExtractor:
    def __init__(self, input_dir, output_dir, results_dir, extracted_sub, competitor_words_file, token_separators_file, overwrite=True):
        """
        Initialize the competitors paragraph extractor.
        
        Args:
            input_dir: Directory containing text files
            output_dir: Directory to store extracted competitors paragraphs
            results_dir: Directory to store results CSVs
            extracted_sub: Subdirectory for extracted paragraphs results
            competitor_words_file: Path to file containing competitor words
            token_separators_file: Path to file containing token separators
            overwrite: Whether to overwrite existing extracted files
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.results_dir = Path(results_dir)
        self.extracted_sub = extracted_sub
        self.overwrite = overwrite
        
        # Load competitor words
        self.competitor_words = open(competitor_words_file).read().split()
        
        # Load token separators
        with open(token_separators_file, encoding='utf-8') as fh:
            self.token_separators = fh.read()
    
    def return_tokens(self, s):
        """
        Return a set of tokens from the string.
        
        Args:
            s: Input string
            
        Returns:
            Set of words
        """
        words = re.sub(f"[{self.token_separators}]", " ", s).split()
        return set(words)
    
    def find_paragraphs_with_words(self, text, words, paragraph_separator):
        """
        Find paragraphs containing specified words.
        
        Args:
            text: The text to search
            words: List of words to search for
            paragraph_separator: Separator for paragraphs
            
        Returns:
            List of paragraphs containing the words
        """
        paragraphs = text.split(paragraph_separator)
        result = []
        for paragraph in paragraphs:
            paragraph = paragraph.replace('\n', ' ')
            word_set = self.return_tokens(paragraph.lower())
            if any(word.lower() in word_set for word in words):
                result.append(paragraph)
        return result
    
    def extract_competitors_paragraphs(self, txt):
        """
        Extract paragraphs containing competitor-related words.
        
        Args:
            txt: The full text
            
        Returns:
            Extracted paragraphs joined by .\n\n
        """
        paragraphs_with_words = self.find_paragraphs_with_words(txt, self.competitor_words, '\n\n')
        txt = ".\n\n".join(paragraphs_with_words)
        return txt
    
    def process_sic_code(self, sic_code):
        """
        Process all text files for a given SIC code.
        
        Args:
            sic_code: SIC code to process
        """
        input_sic_dir = self.input_dir / str(sic_code)
        output_sic_dir = self.output_dir / str(sic_code)
        
        if not input_sic_dir.exists():
            print(f"No files found for SIC code {sic_code}")
            return
        
        output_sic_dir.mkdir(parents=True, exist_ok=True)
        
        txt_files = list(input_sic_dir.glob('*.txt'))
        print(f"Processing {len(txt_files)} files for SIC code {sic_code}...")
        
        results = []
        
        for txt_file in txt_files:
            print(f"Extracting competitors paragraphs from {txt_file.name}...")
            
            # Save extracted paragraphs
            output_filename = txt_file.stem + '.txt'
            output_filepath = output_sic_dir / output_filename
            
            if not self.overwrite and output_filepath.exists():
                print(f"Skipping {txt_file.name}, extracted file already exists.")
                # Still collect sizes if possible
                with open(txt_file, 'r', encoding='utf-8') as f:
                    txt = f.read()
                txt_file_size = len(txt)
                if output_filepath.exists():
                    with open(output_filepath, 'r', encoding='utf-8') as f:
                        extracted = f.read()
                    extracted_file_size = len(extracted)
                else:
                    extracted_file_size = 0
                results.append({
                    'txt_file': txt_file.name,
                    'txt_file_size': txt_file_size,
                    'extracted_file_size': extracted_file_size
                })
                continue
            
            with open(txt_file, 'r', encoding='utf-8') as f:
                txt = f.read()
            
            txt_file_size = len(txt)
            # Clean the text
            txt = txt.replace('Inc.\n', 'Inc. ').replace('Table of Contents', '').replace('Corp.\n', 'Corp. ')
            
            competitors_paragraphs = self.extract_competitors_paragraphs(txt)
            
            with open(output_filepath, 'w', encoding='utf-8') as f:
                f.write(competitors_paragraphs)
            extracted_file_size = len(competitors_paragraphs)
            
            results.append({
                'txt_file': txt_file.name,
                'txt_file_size': txt_file_size,
                'extracted_file_size': extracted_file_size
            })
            
        print(f"Completed processing SIC code {sic_code}")
        
        # Save the DataFrame to CSV
        results_df = pd.DataFrame(results)
        results_path = self.results_dir / self.extracted_sub
        results_path.mkdir(parents=True, exist_ok=True)
        csv_file = results_path / f"{sic_code}.csv"
        results_df.to_csv(csv_file, index=False)
        print(f"Saved results to {csv_file}")

def main():
    # Load configuration from YAML file
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    INPUT_CSV = config['input_csv']
    sic_codes_str = config['sic_codes']
    FILINGS_TEXT = str(Path(config['filings_dir']) / config['text_sub'])
    FILINGS_EXTRACTED = str(Path(config['filings_dir']) / config['extracted_paragraphs_sub'])
    RESULTS_DIR = config['results_dir']
    EXTRACTED_SUB = config['extracted_paragraphs_sub']
    competitor_words_file = config['extraction_words_file']
    token_separators_file = config['token_separators_file']
    overwrite_extracted_files = config.get('overwrite_extracted_files', True)
    
    # Parse SIC codes
    if sic_codes_str == '*':
        df = pd.read_csv(INPUT_CSV)
        SIC_CODES = df['sic'].dropna().unique().tolist()
        SIC_CODES = [int(sic) for sic in SIC_CODES]  # Ensure integers
    else:
        SIC_CODES = [int(x.strip()) for x in sic_codes_str.split(',')]
    
    # Initialize extractor
    extractor = CompetitorsParagraphExtractor(input_dir=FILINGS_TEXT, output_dir=FILINGS_EXTRACTED, results_dir=RESULTS_DIR, extracted_sub=EXTRACTED_SUB, competitor_words_file=competitor_words_file, token_separators_file=token_separators_file, overwrite=overwrite_extracted_files)
    
    # Process each SIC code
    for sic_code in SIC_CODES:
        print(f"\n{'='*80}")
        print(f"Processing SIC code: {sic_code}")
        print(f"{'='*80}")
        extractor.process_sic_code(sic_code)
    
    print("\n" + "="*80)
    print("Competitors paragraphs extraction complete!")
    print("Saved to: filings/extracted_competitors_paragraphs/{sic}/")
    print("="*80)

if __name__ == "__main__":
    main()

