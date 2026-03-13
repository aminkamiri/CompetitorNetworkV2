import os
from pathlib import Path
import re
import time
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
        Finds paragraphs containing specified words and returns clean, 
        non-redundant snippets.
        """
        # 1. Clean the word list: unique words, lowercased, escaped for Regex
        unique_words = sorted(list(set(w.lower() for w in words)), key=len, reverse=True)
        if not unique_words:
            return []

        # 2. Build a regex pattern with word boundaries \b to avoid sub-word matches
        # Example: r'\b(competitors|competitor|compete|rival)\b'
        pattern = re.compile(r'\b(' + '|'.join(map(re.escape, unique_words)) + r')\b', re.IGNORECASE)
        
        paragraphs = text.split(paragraph_separator)
        result = []

        for paragraph in paragraphs:
            if not paragraph.strip():
                continue
                
            # Find all match positions in one pass
            matches = list(pattern.finditer(paragraph))
            if not matches:
                continue

            # 3. Calculate snippet boundaries and merge overlaps
            intervals = []
            for m in matches:
                start = max(m.start() - 100, 0)
                end = min(m.end() + 1000, len(paragraph))
                intervals.append([start, end])

            # Merge overlapping intervals (classic interval merging algorithm)
            merged = []
            if intervals:
                intervals.sort()
                curr_start, curr_end = intervals[0]
                for next_start, next_end in intervals[1:]:
                    if next_start <= curr_end:  # Overlap found
                        curr_end = max(curr_end, next_end)
                    else:
                        merged.append((curr_start, curr_end))
                        curr_start, curr_end = next_start, next_end
                merged.append((curr_start, curr_end))

            # 4. Extract snippets and add ellipses
            for start, end in merged:
                snippet = paragraph[start:end]
                if start > 0:
                    snippet = "..." + snippet.lstrip()
                if end < len(paragraph):
                    snippet = snippet.rstrip() + "..."
                result.append(snippet)

        return result

    # def find_paragraphs_with_words(self, text, words, paragraph_separator):
    #     """
    #     Find paragraphs containing specified words.
        
    #     Args:
    #         text: The text to search
    #         words: List of words to search for
    #         paragraph_separator: Separator for paragraphs
            
    #     Returns:
    #         List of snippets from paragraphs containing the words. Each
    #         snippet includes up to 100 characters before each matching
    #         word and up to 500 characters after it (ellipses added if the
    #         paragraph is trimmed).
    #     """
    #     paragraphs = text.split(paragraph_separator)
    #     result = []
    #     for paragraph in paragraphs:
    #         # paragraph = paragraph.replace('\n', ' ')
    #         word_set = self.return_tokens(paragraph.lower())
    #         if any(word.lower() in word_set for word in words):
    #             # paragraph contains at least one of the words; instead of
    #             # returning the entire paragraph we build snippets around all
    #             # occurrences.  the requirement is to include up to 100
    #             # chars before the match and 500 chars after the match.
                
    #             low_par = paragraph.lower()
    #             snippets_in_para = []
                
    #             for word in words:
    #                 w = word.lower()
    #                 # Find all occurrences of the word
    #                 start_idx = 0
    #                 while True:
    #                     idx = low_par.find(w, start_idx)
    #                     if idx == -1:
    #                         break
                        
    #                     # compute snippet boundaries
    #                     snippet_start = max(idx - 100, 0)
    #                     snippet_end = min(idx + len(w) + 1000, len(paragraph))
    #                     snippet = paragraph[snippet_start:snippet_end]
                        
    #                     # add ellipses when truncated to indicate context
    #                     if snippet_start > 0:
    #                         snippet = "..." + snippet
    #                     if snippet_end < len(paragraph):
    #                         snippet = snippet + "..."
                        
    #                     snippets_in_para.append(snippet)
    #                     start_idx = idx + 1
                
    #             result.extend(snippets_in_para)
    #     return result
    
    def extract_competitors_paragraphs(self, txt):
        """
        Extract paragraphs containing competitor-related words.
        
        Args:
            txt: The full text
            
        Returns:
            Extracted paragraphs joined by .\n\n
        """
        # if txt.count('\n\n') < 30:
        #     paragraph_separator = '\n'
        # else:
        #     paragraph_separator = '\n\n'
        paragraph_separator = '\n\n'
        # txt_clean = self.clean_text(txt)
        txt_clean = txt
        paragraphs_with_words = self.find_paragraphs_with_words(txt_clean, self.competitor_words, paragraph_separator)
        par = ".\n\n".join(paragraphs_with_words)
        # if len(par)/len(txt) > 0.9:
        #     print("Warning: Extracted paragraphs are more than 90% of the original text. This might indicate an issue with the extraction process.")

        return par
    
    def clean_text(self, text):
        """
        Clean text by removing unwanted lines using regex.
        
        Args:
            text: The extracted text to clean
            
        Returns:
            Cleaned text
        """

        text = text.replace('Inc.\n', 'Inc. ').replace('Corp.\n', 'Corp. ')#.replace('Table of Contents', '')
        
        # 1. Remove "Table of Contents" lines (handles optional 's', case insensitive)
        text = re.sub(r'^\s*table of content[s]?\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)

        # 2. Remove lines containing only numbers or "Page X"
        text = re.sub(r'^\s*(page[-\s]*\d+[-\d]*|\d+)\s*$', '', text, flags=re.IGNORECASE | re.MULTILINE)

        # 3. Clean up resulting empty lines (optional but recommended)
        text = re.sub(r'\n\s*\n', '\n', text)
                
        return text

    def process_sic_code(self, sic_code, global_start_index=0, global_total_files=0, global_start_time=None):
        """
        Process all text files for a given SIC code.
        
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
        
        output_sic_dir.mkdir(parents=True, exist_ok=True)
        
        txt_files = list(input_sic_dir.glob('*.txt'))
        local_total = len(txt_files)
        print(f"Processing {len(txt_files)} files for SIC code {sic_code}...")
        
        results = []
        
        for i, txt_file in enumerate(txt_files):
            file_start_time = time.time()
            global_current = global_start_index + i + 1
            files_left = global_total_files - global_current
            
            elapsed_total = time.time() - global_start_time if global_start_time else 0
            elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed_total))
            
            progress_info = f"[SIC: {i+1}/{local_total}] [Global: {global_current}/{global_total_files} | Left: {files_left}] [Elapsed: {elapsed_str}]"
            print(f"{progress_info} Extracting competitors paragraphs from {txt_file.name}..." + " " * 20, end='\r')
            
            # Save extracted paragraphs
            output_filename = txt_file.stem + '.txt'
            output_filepath = output_sic_dir / output_filename
            
            if not self.overwrite and output_filepath.exists():
                # print(f"  > Skipping {txt_file.name}, extracted file already exists.")
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
            
            competitors_paragraphs = self.extract_competitors_paragraphs(txt)
            # if len(competitors_paragraphs)/len(txt) > 0.9:
            #     print("Warning: Extracted paragraphs are more than 90% of the original text. This might indicate an issue with the extraction process.")

            with open(output_filepath, 'w', encoding='utf-8') as f:
                f.write(competitors_paragraphs)
            extracted_file_size = len(competitors_paragraphs)
            
            results.append({
                'txt_file': txt_file.name,
                'txt_file_size': txt_file_size,
                'extracted_file_size': extracted_file_size,
                'double_enter_count': txt.count('\n\n')
            })
            
            file_duration = time.time() - file_start_time
            # print(f"  > Completed {txt_file.name} in {file_duration:.2f}s")
            
        print(f"\nCompleted processing SIC code {sic_code}")
        
        # Save the DataFrame to CSV
        results_df = pd.DataFrame(results)
        results_df['prc'] = results_df['extracted_file_size'] / results_df['txt_file_size'] * 100
        results_path = self.results_dir / self.extracted_sub
        results_path.mkdir(parents=True, exist_ok=True)
        csv_file = results_path / f"{sic_code}.csv"
        results_df.to_csv(csv_file, index=False)
        print(f"Saved results to {csv_file}")
        return local_total

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
    
    # Calculate total files to process
    print("Calculating total files...")
    total_files = 0
    for sic_code in SIC_CODES:
        sic_dir = Path(FILINGS_TEXT) / str(sic_code)
        if sic_dir.exists():
            total_files += len(list(sic_dir.glob('*.txt')))
    
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
    print("Competitors paragraphs extraction complete!")
    print("Saved to: filings/extracted_competitors_paragraphs/{sic}/")
    print("="*80)

if __name__ == "__main__":
    main()
