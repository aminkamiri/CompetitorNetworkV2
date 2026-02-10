# !pip install -U sec-cik-mapper
from collections import Counter
import pandas as pd
import numpy as np
import re
from pathlib import Path
import re
import yaml


from utils import get_uniform_format_company_name
# def get_uniform_format_company_name(x):
#     return x.upper().replace(',','').replace('.','').replace('-',' ')

def filter_counter(counter, threshold):
    filtered_counter = Counter({key: value for key, value in counter.items() if value > threshold})
    return filtered_counter

def replace_word_with_synonym(word, synonyms_set, text):
    replaced_texts = []
    for synonym in synonyms_set:
        replaced_text = re.sub(r'\b' + re.escape(word) + r'\b', synonym, text)
        if synonym=='':
            # replaced_text = re.sub(r'\b' + re.escape(word) + r'\b', synonym, text)
            replaced_text = replaced_text.replace(' '*2, ' ').strip()#.rstrip('-.') #remove - . at the end
        
        if text!=replaced_text:
            replaced_texts.append(replaced_text)
    return replaced_texts

def abbreviate_string(input_string):
    # Split the input string into words
    words = input_string.split()
    
    # Extract the first letter of each word and capitalize it
    abbreviation = ''.join(word[0].upper() for word in words)
    
    return abbreviation

def create_dict(sic_file, col_cik,col_company_name, col_tic, dict_map_file):
    company_name_to_cik={}
    df=pd.read_csv(sic_file, dtype={col_cik: str},index_col=0)
    print(len(df))
    df=df.loc[pd.notna(df[col_cik])]
    df[col_cik] = df[col_cik].str.zfill(10)
    df[col_company_name] = df[col_company_name].apply(lambda x: get_uniform_format_company_name(x))
    # df.head()

    for tup in df.itertuples():
        # edgar_name=tup.edgar_name.strip()
        computesat_name=tup.conm.strip()
        if computesat_name!='':     
            company_name_to_cik[get_uniform_format_company_name(computesat_name)]=tup.cik
    # len(company_name_to_cik),company_name_to_cik

    # /DE/ or /dn at the end, add them without those slashes
    # lst_cik_to_company_name=[]
    company_name_to_cik_addition={}
    check_the_last_characters=9  #must be in in the last 6 characters
    tail_sign=["/", "\\", "\\\\", "////", "-"]
    for company_name,cik in company_name_to_cik.items():
        # company_name_to_cik_addition[company_name]=cik
        
        company_name=company_name.strip()
        #"/"
        try:
            idx=company_name.rfind("/") if company_name[-1]!="/" else company_name[:-1].rfind("/")
        except:
            print(company_name)
        if idx>-1 and idx> len(company_name)-check_the_last_characters:
            company_name_to_cik_addition[company_name[:idx].strip()]=cik
        # "\\\\"
        try:
            idx=company_name.rfind("\\\\") if company_name[-2:]!="\\\\" else company_name[:-2].rfind("\\\\")
        except:
            print(company_name)
            
        if idx>-1 and idx> len(company_name)-check_the_last_characters:
            company_name_to_cik_addition[company_name[:idx].strip()]=cik
        # "\\"
        try:
            idx=company_name.rfind("\\") if company_name[-1]!="\\" else company_name[:-1].rfind("\\")
        except:
            print(company_name)
            
        if idx>-1 and idx> len(company_name)-check_the_last_characters and company_name[-2:]!="\\\\":
            company_name_to_cik_addition[company_name[:idx].strip()]=cik
        # "-"
        try:
            idx=company_name.rfind("-")
        except:
            print(company_name)
            
        if idx>-1 and idx> len(company_name)-check_the_last_characters:
            company_name_to_cik_addition[company_name[:idx].strip()]=cik

    print(len(company_name_to_cik))
    company_name_to_cik.update(company_name_to_cik_addition)
    print(len(company_name_to_cik))

    synonym_groups=[
    # ---Holding/Group
                    {'Holdings','Holding', 'Hldg', 'Hldng','Hold','Hldgs', ''},
                    {'Group', 'Grp', 'Groupe', ''},
                    {'Incorporated','Inc', 'Corporation', 'Corp', 'Co', 'Company', ''},
    
    # --- TECH

                {'Technologies','Technologie','Technolgies','Technology','Technlgy','Tech', 'Tek', 'Techno', ''},

                {'Nanotechnologies', 'Nanotechnology', 'Nano', ''},
                {'Informatics', 'Info', ''},  
                {'Solutions', 'Solution', ''},
                {'Research', 'Res', ''},
                {'Services', 'Service', ''},
                
    # --- COMPONENTS
                {'Component', 'Components', ''},

#     # --- ESSENTIAL / ENTERPRISE
                {'Essential', 'Essentials', ''},
                {'Enterprise', 'Enterprises', ''},
                {'Clinic', 'Clinics', ''},
                
    # --- INTL
                {'International', 'Intl', ''},
                {'Global',  ''},
                {'Worldwide', ''},
    # --- MANUFACTURING
                {'Manufacturing', 'Manufacturer', 'Manufacturers', 'Mfg', ''},
                
    # --- LABS
                {'Lab', 'Labs', 'Laboratory', 'Laboratories', 'Laboratoires', ''},
    # --- INDUSTRY
                {'Industry', 'Industries', 'Ind', ''},

    # --- PHARMA / BIOPHARMA
                {'Pharmaceutical', 'Pharmaceuticals', 'Pharm', 'Pharms', 'Pharma',
                'Pharmasset', ''},
                {'Biopharma', 'Biopharmaceutical', 'Biopharmaceuticals',''}, 
                {'Biotechnology', 'Biotechnologies', 'Biotech', ''},
                {'Biologics', 'Biologic', 'Bio', 'Biology', 'Biological', ''},
                # --- SCI / LIFE SCIENCE
                {'Bioscience', 'Biosciences', 'Bio', ''}, 
                {'Biosystems',''},
                {'Science', 'Sciences', ''}, 
                {'Life', 'Lifesciences', ''},
                {'Neuroscience', 'Neurosciences', ''},
                {'Genomics', 'Genomic', ''},
                {'Oncology', ''}, 
                {'Biotherapeutics', ''},
                
                {'Diagnostics', 'Diagnostic', ''},

                
        # --- CONNECTORS / NOISE
                {'And', '&', ',', ''},
                
                #----------added later
                {'Development', 'Dev', ''},
    # --- SYSTEMS
                {'Microsystem', 'Micro', ''},
                {'Systems', 'System','Sys',''},
                
                
    # --- SEMICONDUCTORS
                {'Semiconductors','Semiconductor', 'Semicon', ''},
                
                {'Photonics', ''},
                {'Silicon', ''},
                {'Engineering','Eng', ''},
                {'Limited','Ltd', ''},
                
#     # --- ELECTRONICS / ELECTRICAL
                {'Electronics','Electronic', 'Electro', 'Elec', ''},
                {'Microelectronics', 'Microelectronic','Micro', ''},
                {'Electromechanical', 'Electromech', ''},

                {'Telecommunications','Telecomm','Telecom','Communication', 'Communications', 'Comm', ''},

                {'Devices', 'Device', ''},
                {'Optoelectronics', 'Optronics', ''},

                {'Lightings', 'Lighting', ''},
                {'-Pro Forma',''},
                {'Pro', ''},
                {'Forma', ''},

                {'SA', ''},  #added because tailing cannot find french limited because lower than 9 repetition
                {'Oncology','Onc', ''},
                {'Health', 'Hlth', ''},
                
    # --- THERAPEUTICS
                {'Therapeutic', 'Therapeutics', 'Ther', 'Therapies',''},
                {'Immunotherapeutics', ''}, 
                {'Nutrition', 'Nutritionals', ''},
                {'Biosciences', 'Bioscience', ''},
    # --- DERMATOLOGY
                 {'Derma', 'Derm', 'Dermatology', 'Dermatologics', ''},

    # --- CONSUMER
                {'Consumer', 'Consumers', ''},

    # --- FRANCHISE
                {'Franchise', 'Franchises', ''},
    # --- CHEM / MED / HEALTH
                {'Chemical', 'Chemicals', 'Chem', ''},
                {'Medicine', 'Medicines', 'Medical', 'Med', 'Medics', ''},
                {'Healthcare', 'Health', 'Hlth', ''},
                {'Care',  ''},
    # --- GENETICS
                {'Gene', 'Genes', 'Genetic', 'Genetics', ''},
                {'Genentech', 'Gentech', 'Epigenetics', ''},
                {'Epigenetics', ''},

                #----------
                {'US', ''},
                {'UK', ''},
                {'I', ''},
                {'II', ''},
                {'III', ''}
                , 
    # --- LEGAL
                {'LLC', ''}, {'PLC', ''}, {'NV', ''}, {'SA', ''}, {'AG', ''}, {'BV', ''}, {'GMBH', ''}, 
                {'KGAA', ''},
                {'OY', ''}, {'OYJ', ''}, {'SAS', ''}, {'SRL', ''}, {'SARL', ''}, {'SPA', ''}, 
                {'PTE', ''}, {'PVT', ''}, {'SL', ''}, {'SAU', ''},
                {'SPRL', ''}, {'KS', ''}, {'AB', ''}, {'AS', ''}, {'APS', ''}, 
                {'ASA', ''}, {'BVBA', ''}, {'KK', ''}, {'LLP', ''}, {'LTDA', ''},
                {'RT', ''}, {'ZRT', ''}, {'KFT', ''}, {'KG', ''}, {'PTY', ''}, {'BHD', ''}, 
                {'SDN', ''}, {'OO', ''},
                {'PJSC', ''}, {'JSC', ''}, {'OAO', ''}, {'ZAO', ''}, {'AO', ''},

            ]


    synonym_groups = [{word.upper() for word in word_set} for word_set in synonym_groups]
    

    for synonym_group in synonym_groups:
        print(synonym_group)
        company_name_to_cik_addition={}
        for company_name,cik in company_name_to_cik.items():
            for synonym in synonym_group-{''}:
                new_names=replace_word_with_synonym(synonym, synonym_group-{synonym}, company_name)
                for new_company_name in new_names:
                    if not (new_company_name in company_name_to_cik):
                        company_name_to_cik_addition[new_company_name]=cik
                                # print(new_company_name)

        print(len(company_name_to_cik))
        print(company_name_to_cik_addition)
        company_name_to_cik.update(company_name_to_cik_addition)
        print(len(company_name_to_cik))
        print("-------------")



    name_tails=[]#set()
    name_tails_examples={}
    company_name_to_cik_addition={}
        
    for company_name,cik in company_name_to_cik.items():
        parts=company_name.split()
        if len(parts)<=1:
            continue
        name_tail= parts[-1]
        name_tails.append(company_name.split()[-1])
        if name_tail not in name_tails_examples:
            name_tails_examples[name_tail]=set()
        name_tails_examples[name_tail].add(company_name)
        if  name_tail.count(".")>=2:
            new_name_tail=name_tail.replace(".","")
            new_company_name=" ".join(parts[:-1]) + " " + new_name_tail
            company_name_to_cik_addition[new_company_name]=cik
            print(f'{company_name}-->{new_company_name}')

    print(len(company_name_to_cik))
    company_name_to_cik.update(company_name_to_cik_addition)
    print(len(company_name_to_cik))

    name_tails_cnt= filter_counter(Counter(name_tails),9)
    # name_tails_cnt

    # company_name
    # company_name_to_cik_addition
    # Counter(name_tails)

    company_name_to_cik_addition={}
    for company_name,cik in company_name_to_cik.items():
        for name_tail,_ in name_tails_cnt.items():
            if company_name.endswith(name_tail):
                company_name_curtailed=company_name.rstrip(name_tail).rstrip().rstrip(',').rstrip()
                #Inc. > Inc and Inc > Inc.
                endswith_dot=name_tail.endswith('.')
                endswith_comm_blank_tail=company_name.endswith(', '+name_tail)

                if endswith_dot and endswith_comm_blank_tail: #', Inc.'
                    company_name_v2_1=company_name[:-1]#', Inc'
                    company_name_v2_2=company_name_curtailed+" "+name_tail#' Inc.'
                    company_name_v2_3=company_name_curtailed+" "+name_tail[:-1]#' Inc'
                    print("",end='')
                elif endswith_dot and (not endswith_comm_blank_tail): #' Inc.'
                    company_name_v2_1=company_name_curtailed+", "+name_tail[:-1]#', Inc'
                    company_name_v2_2=company_name_curtailed+", "+name_tail#', Inc.'
                    company_name_v2_3=company_name[:-1]#' Inc'
                    print("",end='')
                elif (not endswith_dot) and endswith_comm_blank_tail: #', Inc'
                    company_name_v2_1=company_name+"."#', Inc.'
                    company_name_v2_2=company_name_curtailed+" "+name_tail+"."#' Inc.'
                    company_name_v2_3=company_name_curtailed+" "+name_tail#' Inc'
                    print("",end='')
                else: #' Inc'
                    company_name_v2_1=company_name+'.' #' Inc.'
                    company_name_v2_2=company_name_curtailed+", "+name_tail+"."#', Inc.'
                    company_name_v2_3=company_name_curtailed+", "+name_tail#', Inc'
                    print("",end='')

                company_name_to_cik_addition[company_name_v2_1]=cik
                company_name_to_cik_addition[company_name_v2_2]=cik
                company_name_to_cik_addition[company_name_v2_3]=cik

                
                #, Inc. > Inc
                #add curtailed version
                
                if company_name_curtailed in company_name_to_cik:
                    print(f'tried to remove "{name_tail}" from "{company_name} ({cik})" but')
                    print(f"{company_name_curtailed} ({company_name_to_cik[company_name_curtailed]}) already exists in company_name_to_cik and can't de added to it.")
                    print("------------")
                else:
                    company_name_to_cik_addition[company_name_curtailed]=cik

    print(len(company_name_to_cik),'+',len(company_name_to_cik_addition))
    company_name_to_cik.update(company_name_to_cik_addition)
    print(len(company_name_to_cik))

    #add tic from wrds
    company_name_to_cik_addition={}
    df_wrds=pd.read_csv(sic_file)
    df_wrds = df_wrds.replace([np.inf, -np.inf], np.nan)  # Replace infinite values with NaN
    df_wrds = df_wrds.dropna(subset=[col_cik,col_tic])  # Remove rows with NaN in 'cik' column
    df_wrds.cik=df_wrds.cik.astype(int)
    for idx,row in df_wrds.iterrows():
        new_company_name=row[col_tic].split('.')[0]
        cik=row[col_cik]
        if new_company_name in company_name_to_cik:
            print(f'abbreviation exists: {new_company_name} {cik} {company_name_to_cik[new_company_name]}')
        else:
            company_name_to_cik_addition[new_company_name]=cik
    print(len(company_name_to_cik))
    print(len(company_name_to_cik_addition))
    company_name_to_cik.update(company_name_to_cik_addition)
    print(len(company_name_to_cik))

    # #MUST BE THE LAST PHASE
    company_name_to_cik_addition={}
    for company_name,cik, in company_name_to_cik.items():
        new_company_name=abbreviate_string(company_name)
        if new_company_name in company_name_to_cik:
            print(f'abbreviation exists: {new_company_name} {cik} {company_name_to_cik[new_company_name]}')
        else:
            company_name_to_cik_addition[new_company_name]=cik

    print(len(company_name_to_cik))
    print(len(company_name_to_cik_addition))
    company_name_to_cik.update(company_name_to_cik_addition)
    print(len(company_name_to_cik))

    # ## re-introduce original names and ciks

    for idx,row in df.iterrows():
        computesat_name=tup.conm.strip()
        if computesat_name!='':     
            company_name_to_cik[get_uniform_format_company_name(computesat_name)]=row[col_cik]

    # # Store company_name_to_cik dictionary

    df=pd.DataFrame(company_name_to_cik.items(),columns=[col_company_name,col_cik])
    df.sort_values([col_cik,col_company_name]).to_csv(dict_map_file)

    # path='data/cik_list/'
    df=pd.read_csv(sic_file,index_col=0)
    print(len(df))
    df=df.loc[pd.notna(df[col_cik])]
    print(len(df))
    df[col_cik]=df[col_cik].astype(int)
    

    df['cik_retrieved_from_name']=df[col_company_name].apply(lambda x: int(company_name_to_cik[get_uniform_format_company_name(x)]) if get_uniform_format_company_name(x) in company_name_to_cik else None)

    # # The following list must be empty

    df[df[col_cik] !=df.cik_retrieved_from_name]


    df.loc[df[col_cik] !=df.cik_retrieved_from_name,[col_company_name,col_cik]].to_csv('missing_ciks.csv')

def main():
        # Load configuration from YAML file
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    
    INPUT_CSV = config['input_csv']
    COMPANY_NAME_COLUMN = config['company_name_column']
    CIK_COLUMN = config['cik_column']
    TIC_COLUMN = config['tic_column']
    # SIC_COLUMN = config['sic_column']
    
          
    DICT_DIR = Path(config['dict_dir']) 
    # Create output directory
    DICT_DIR.mkdir(parents=True, exist_ok=True)
    dict_map_file= str(DICT_DIR) + '/company_name_to_cik_mapping.csv'

    create_dict(INPUT_CSV,CIK_COLUMN,COMPANY_NAME_COLUMN,TIC_COLUMN, dict_map_file)#cm4['dict_map_file'])

main()