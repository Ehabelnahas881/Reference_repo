import requests
import pandas as pd
import json 
import sys
 
# CBC_endpoint = 'http://127.0.0.1:4574/graphql'
FMU_endpoint = 'http://127.0.0.1:4574/graphql'
headers = {
            'Accept-Encoding': 'gzip, deflate, br',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Connection': 'keep-alive',
            'DNT': '1'
        }  

financial_market_pks = [6,16,20]          
pks_str = ", ".join(map(str, financial_market_pks))
try:
  query = f"""
    query {{
        resolve_FMU(financial_market_pks: [{pks_str}]) {{
            success
            errors
            
        }}
    }}
"""
  response = requests.post(FMU_endpoint, json={"query": query}, headers=headers).json()
    #   print("here in return test_engine.py we get: ", response)
  print(response['data']['fitFMU']['error'])
  if response['data']['fitFMU']['error'] == "Null":
      print('FMU executed correctly')
  else:
      print("Some error in FMU")
except Exception as error:
    print(error)

