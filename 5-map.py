import yaml
from pathlib import Path
import pandas as pd
import openpyxl
from utils import get_uniform_format_company_name

# # Retrieving competitors' ciks
with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)

SIC_CODE = None
INPUT_CSV = config['input_csv']
RESULTS_DIR = Path(config['results_dir'])
MAP_SUB = Path(config['map_sub'])
OUTPUT_DIR = RESULTS_DIR / MAP_SUB
# Create output directory
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

LLM_SUB = config['llm_sub']
# directory containing LLM outputs (many SIC files)
LLM_DIR = Path(RESULTS_DIR) / Path(LLM_SUB)
CIK_COLUMN = config['cik_column']
COMPANY_NAME_COLUMN = config['company_name_column']


DICT_DIR = Path(config['dict_dir']) 
dict_map_file= str(DICT_DIR) + '/company_name_to_cik_mapping.csv'
df_map=pd.read_csv(dict_map_file, index_col=0)
print("mapping dictionary: \n", df_map.head())
print("to load the dictionary faster, use it on dictionary producing file later ")
dict_maps={}
for idx,row in df_map.iterrows():
    dict_maps[row[COMPANY_NAME_COLUMN]]=row[CIK_COLUMN]
print(dict_maps)

# If a company name does not start with an UPPERCASE letter, then it must be a mistake by GPT3.5 returning an industry or something
def starts_with_capital(s):
    return s[0].isupper() if s else False

def replace_with_cik(x):
    if pd.isna(x):
        return ''
    ciks=[]
    
    for name in x.split('|'):
        if starts_with_capital(name):
            try:
                name=get_uniform_format_company_name(name)
            except:
                print(x)
            if name in dict_maps:
                ciks.append(dict_maps[name])
            else:
                ciks.append(-1)
        else:
            # Competitor name doesn't start with capital (likely a typo/industry term)
            # Add -1 to maintain 1-to-1 mapping with competitors
            ciks.append(-1)
    return "|".join(map(str, ciks))

# Process all CSV files in the LLM output directory
for csv_path in sorted(LLM_DIR.glob('*.csv')):
    sic_code = csv_path.stem
    print(f"Processing {sic_code} -> {csv_path}")
    df = pd.read_csv(csv_path)  # keep first column as column (do not set index_col=0)
    # build set of all competitors found in this file
    all_competitors = set()
    for competitors in df.get('competitors', pd.Series(dtype=object)):
        try:
            if pd.notna(competitors):
                all_competitors.update(competitors.split('|'))
        except Exception:
            print('parse error for', competitors)
    if "" in all_competitors:
        all_competitors.discard('')
    df_all_competitors=pd.DataFrame({'company_name_in_text':list(all_competitors)})
    print(df_all_competitors.head())
    df_all_competitors['company_name']=df_all_competitors['company_name_in_text'].apply(lambda x: get_uniform_format_company_name(x))
    print(df_all_competitors)

    # create competitors_ciks column
    df['competitors_ciks']=df['competitors'].apply(lambda x: replace_with_cik(x))

    print(df.head())
    mapped_dir = Path('data/results/mapped')
    mapped_dir.mkdir(parents=True, exist_ok=True)
    df.to_excel(mapped_dir / f'{sic_code}.xlsx', index=False)



