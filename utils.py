# ### A function that removes comma and dot from company names and UPPERCASE them so that matching would be easier
import re
def get_uniform_format_company_name(x):
    text = re.sub(r'\([^)]*\)', '', x) # remove rounded brackets and what is inside
    return text.upper().replace(',','').replace('.','').replace('-',' ').strip().replace('-PRO FORMA','')

# def get_uniform_format_company_name(x):
#     return x.upper().replace(',','').replace('.','').replace('-',' ')
