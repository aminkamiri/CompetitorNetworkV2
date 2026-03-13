import os
from pathlib import Path
import yaml
import pandas as pd
from pydantic import BaseModel, Field
from typing import Optional, List
from langchain_openai import ChatOpenAI
from langchain_core.utils.function_calling import convert_to_openai_function
from langchain_core.output_parsers.openai_functions import JsonOutputFunctionsParser, JsonKeyOutputFunctionsParser
from langchain_core.prompts import ChatPromptTemplate
import tiktoken
import time
from datetime import datetime, timedelta

class LLMCompetitorExtractor:
    def __init__(self, input_dir, results_dir, issues_dir, llm_sub, openai_key_file, model_name, max_no_tokens, template, overwrite=True):
        """
        Initialize the LLM competitor extractor.
        
        Args:
            input_dir: Directory containing extracted competitors paragraphs
            results_dir: Directory to store results
            issues_dir: Directory to store issues
            llm_sub: Subdirectory for LLM results
            openai_key_file: Path to OpenAI API key file
            model_name: Name of the LLM model
            max_no_tokens: Maximum number of tokens per chunk
            template: Prompt template for LLM
            overwrite: Whether to overwrite existing results
        """
        self.input_dir = Path(input_dir)
        self.results_dir = Path(results_dir) / llm_sub
        self.issues_dir = Path(issues_dir) / llm_sub
        self.overwrite = overwrite
        self.model_name = model_name
        self.max_no_tokens = max_no_tokens
        self.template = template
        
        # Statistics tracking
        self.total_llm_calls = 0
        self.total_texts_processed = 0
        self.total_processing_time = 0
        
        # Load OpenAI API key
        with open(openai_key_file) as fh:
            OPENAI_API_KEY = fh.read().strip()
        
        # Define the input schema
        class Competitor(BaseModel):
            """Information about a competitor """
            company_name: str = Field(description="the name of the competitor, which may include (Inc, Ltd, Llc, Co, Corporation, etc.)")
        
        class CompetitorsInfo(BaseModel):
            """Information to extract """
            competitors_list: List[Competitor] = Field(description="List of competitors")
        
        paper_extraction_function = [convert_to_openai_function(CompetitorsInfo)]
        
        model = ChatOpenAI(model_name=self.model_name, temperature=0, openai_api_key=OPENAI_API_KEY)
        
        extraction_model = model.bind(
            functions=paper_extraction_function, 
            function_call={"name": "CompetitorsInfo"}
        )
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.template),
            ("human", "{input}")
        ])
        
        self.extraction_chain = prompt | extraction_model | JsonKeyOutputFunctionsParser(key_name="competitors_list")
    
    def count_tokens(self, text):
        """Count the number of tokens in the text."""
        encoding = tiktoken.encoding_for_model(self.model_name)
        tokens = encoding.encode(text)
        return len(tokens)
    
    def divide_text(self, text, n):
        """Divide text into n parts."""
        if n <= 0:
            raise ValueError("The number of divisions must be a positive integer")
        
        text_length = len(text)
        part_length = text_length // n
        result = []
        
        for i in range(0, text_length, part_length):
            result.append(text[i:i + part_length])
        
        if len(result) > n:
            result[-2] += result[-1]
            result.pop()
        
        return result
    
    def split_text_into_chunks(self, text):
        """Split text into chunks within token limit."""
        import math
        div_no = math.ceil(self.count_tokens(text) / self.max_no_tokens)
        return self.divide_text(text, div_no)
    
    def extract_competitors(self, text):
        """Extract competitors from text using LLM."""
        text= text.strip()
        if len(text) == 0:
            return ""
        
        chunks = self.split_text_into_chunks(text)
        set_competitors = set()
        
        for chunk in chunks:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    result = self.extraction_chain.invoke({"input": chunk})
                    self.total_llm_calls += 1
                    for res in result:
                        try:
                            set_competitors.add(res['company_name'])
                        except:
                            print("Not having a company_name", res)
                    break  # Success, exit retry loop
                except Exception as e:
                    if "rate_limit_exceeded" in str(e) and attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 10  # 10, 20, 30 seconds
                        print(f"Rate limit hit, waiting {wait_time} seconds...")
                        time.sleep(wait_time)
                    else:
                        raise  # Re-raise if not rate limit or final attempt
        
        orgs_str = "|".join(sorted(set_competitors))
        return orgs_str
    
    def format_time(self, seconds):
        """Format seconds into human-readable time."""
        return str(timedelta(seconds=int(seconds)))
    
    def process_sic_code(self, sic_code, sic_index, total_sics):
        """
        Process all extracted paragraphs files for a given SIC code.
        
        Args:
            sic_code: SIC code to process
            sic_index: Current index of SIC code being processed (0-based)
            total_sics: Total number of SIC codes to process
        """
        input_sic_dir = self.input_dir / str(sic_code)
        
        if not input_sic_dir.exists():
            print(f"No extracted paragraphs found for SIC code {sic_code}")
            return
        
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.issues_dir.mkdir(parents=True, exist_ok=True)
        
        results_csv = self.results_dir / f"{sic_code}.csv"
        issues_csv = self.issues_dir / f"{sic_code}_issues.csv"
        
        if self.overwrite:
            # Delete existing CSVs to start fresh
            if results_csv.exists():
                results_csv.unlink()
            if issues_csv.exists():
                issues_csv.unlink()
            existing_results = pd.DataFrame(columns=['filename', 'competitors'])
            existing_issues = pd.DataFrame(columns=['filename', 'error'])
            processed_filenames = set()
        else:
            # Load existing results
            if results_csv.exists():
                existing_results = pd.read_csv(results_csv)
            else:
                existing_results = pd.DataFrame(columns=['filename', 'competitors'])
            
            processed_filenames = set(existing_results['filename'])
            
            # Load existing issues
            if issues_csv.exists():
                existing_issues = pd.read_csv(issues_csv)
            else:
                existing_issues = pd.DataFrame(columns=['filename', 'error'])
        
        txt_files = list(input_sic_dir.glob('*.txt'))
        total_files = len(txt_files)
        files_to_process = [f for f in txt_files if f.name not in processed_filenames]
        num_files_to_process = len(files_to_process)
        
        print(f"\n{'='*80}")
        print(f"SIC CODE: {sic_code} [{sic_index + 1}/{total_sics}]")
        print(f"Total files: {total_files} | Already processed: {len(processed_filenames)} | To process: {num_files_to_process}")
        print(f"Remaining SIC codes after this: {total_sics - sic_index - 1}")
        print(f"{'='*80}\n")
        
        if num_files_to_process == 0:
            print(f"All files for SIC code {sic_code} already processed. Skipping...\n")
            return
        
        sic_start_time = time.time()
        
        for file_idx, txt_file in enumerate(files_to_process, 1):
            cik_start_time = time.time()
            
            print(f"[{file_idx}/{num_files_to_process}] Processing: {txt_file.name}")
            
            try:
                with open(txt_file, 'r', encoding='utf-8') as f:
                    txt = f.read()
                
                # Measure LLM extraction time separately
                llm_start_time = time.time()
                competitors = self.extract_competitors(txt)
                llm_time = time.time() - llm_start_time
                
                file_start_time = time.time()
                new_row = {'filename': txt_file.name, 'competitors': competitors}
                existing_results = pd.concat([existing_results, pd.DataFrame([new_row])], ignore_index=True)
                existing_results.to_csv(results_csv, index=False)
                file_time = time.time() - file_start_time

                cik_time = time.time() - cik_start_time
                self.total_processing_time += cik_time
                self.total_texts_processed += 1
                
                avg_time_per_file = self.total_processing_time / self.total_texts_processed
                remaining_files_all = sum(1 for sic_idx in range(sic_index, total_sics) 
                                         for _ in (self.input_dir / str(sic_code)).glob('*.txt') 
                                         if sic_idx == sic_index) + \
                                    sum(len(list((self.input_dir / str(sc)).glob('*.txt'))) 
                                        for sc_idx, sc in enumerate(self.all_sic_codes) 
                                        if sc_idx > sic_index)
                
                eta_seconds = avg_time_per_file * (num_files_to_process - file_idx)
                
                print(f"  ✓  Total time:{cik_time:.2f}s |LLM Time: {llm_time:.2f}s | File Time: {file_time:.2f}s")
                print(f"  📊 Stats: Size: {len(txt)} chars | {self.total_llm_calls} LLM calls | Avg: {avg_time_per_file:.2f}s/file")
                print(f"  ⏱️  ETA for this SIC: {self.format_time(eta_seconds)}")
                print()
                
                # Add small delay to avoid rate limits
                time.sleep(2)
                
            except Exception as ex:
                new_issue = {'filename': txt_file.name, 'error': str(ex)}
                existing_issues = pd.concat([existing_issues, pd.DataFrame([new_issue])], ignore_index=True)
                existing_issues.to_csv(issues_csv, index=False)
                print(f"  ✗ Error: {str(ex)}\n")
        
        sic_time = time.time() - sic_start_time
        print(f"\n{'='*80}")
        print(f"COMPLETED SIC CODE {sic_code} in {self.format_time(sic_time)}")
        print(f"Processed: {num_files_to_process} files | LLM calls: {self.total_llm_calls}")
        print(f"Results saved to: {results_csv}")
        if issues_csv.exists() and len(existing_issues) > 0:
            print(f"Issues saved to: {issues_csv}")
        print(f"{'='*80}\n")

def main():
    # Load configuration from YAML file
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    INPUT_CSV = config['input_csv']
    sic_codes_str = config['sic_codes']
    FILINGS_EXTRACTED = str(Path(config['filings_dir']) / config['extracted_paragraphs_sub'])
    RESULTS_DIR = config['results_dir']
    ISSUES_DIR = config['issues_dir']
    LLM_SUB = config['llm_sub']
    openai_key_file = config['openai_key_file']
    overwrite = config.get('llm_overwrite', True)
    
    # Parse SIC codes
    if sic_codes_str == '*':
        df = pd.read_csv(INPUT_CSV)
        SIC_CODES = df['sic'].dropna().unique().tolist()
        SIC_CODES = [int(sic) for sic in SIC_CODES]
    else:
        SIC_CODES = [int(x.strip()) for x in sic_codes_str.split(',')]
    
    # Initialize extractor
    extractor = LLMCompetitorExtractor(
        input_dir=FILINGS_EXTRACTED, 
        results_dir=RESULTS_DIR, 
        issues_dir=ISSUES_DIR, 
        llm_sub=LLM_SUB, 
        openai_key_file=openai_key_file, 
        model_name=config['llm_model_name'],
        max_no_tokens=config['llm_max_no_tokens'],
        template=config['llm_template'],
        overwrite=overwrite
    )
    
    # Store SIC codes for reference
    extractor.all_sic_codes = SIC_CODES
    
    total_sics = len(SIC_CODES)
    overall_start_time = time.time()
    
    print("\n" + "="*80)
    print("LLM COMPETITOR EXTRACTION - STARTING")
    print(f"Model: {config['llm_model_name']}")
    print(f"Total SIC codes to process: {total_sics}")
    print(f"SIC codes: {SIC_CODES}")
    print("="*80)
    
    # Process each SIC code
    for idx, sic_code in enumerate(SIC_CODES):
        extractor.process_sic_code(sic_code, idx, total_sics)
    
    overall_time = time.time() - overall_start_time
    
    print("\n" + "="*80)
    print("LLM COMPETITOR EXTRACTION - COMPLETE!")
    print("="*80)
    print(f"📊 Total Statistics:")
    print(f"   • Total SIC codes processed: {total_sics}")
    print(f"   • Total texts processed: {extractor.total_texts_processed}")
    print(f"   • Total LLM calls made: {extractor.total_llm_calls}")
    print(f"   • Total time: {extractor.format_time(overall_time)}")
    print(f"   • Average time per text: {extractor.total_processing_time/extractor.total_texts_processed:.2f}s")
    print(f"   • Average LLM calls per text: {extractor.total_llm_calls/extractor.total_texts_processed:.2f}")
    print(f"\n📁 Output:")
    print(f"   • Results: {RESULTS_DIR}/{LLM_SUB}/")
    print(f"   • Issues: {ISSUES_DIR}/{LLM_SUB}/")
    print("="*80 + "\n")

if __name__ == "__main__":
    main()