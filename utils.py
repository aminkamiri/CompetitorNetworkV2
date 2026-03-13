# ### A function that removes comma and dot from company names and UPPERCASE them so that matching would be easier
import re

suffixes = {
            'INCORPORATED', 'INC', 'CORPORATION', 'CORP', 'COMPANY', 'CO',
            'LIMITED', 'LTD', 'LLC', 'PLC', 'NV', 'SA', 'AG', 'BV', 'GMBH', 'KGAA',
            'OY', 'OYJ', 'SAS', 'SRL', 'SARL', 'SPA', 'PTE', 'PVT', 'SL', 'SAU',
            'SPRL', 'KS', 'AB', 'AS', 'APS', 'ASA', 'BVBA', 'KK', 'LLP', 'LTDA',
            'RT', 'ZRT', 'KFT', 'KG', 'PTY', 'BHD', 'SDN', 'OO',
            'PJSC', 'JSC', 'OAO', 'ZAO', 'AO', ''
        }

def get_uniform_format_company_name(x, strip_suffixes=False):
    text = re.sub(r'\([^)]*\)', '', x) # remove rounded brackets and what is inside
    text = text.upper().replace(',','').replace('.','').replace('-',' ').strip().replace('-PRO FORMA','')
    if strip_suffixes and text:
        
        words = text.split()
        while words and words[-1] in suffixes:
            words.pop()
        text = ' '.join(words)
    return text

# def get_uniform_format_company_name(x):
#     return x.upper().replace(',','').replace('.','').replace('-',' ')
