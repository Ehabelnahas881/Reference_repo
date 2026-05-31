import requests
import json
import pandas as pd 

pd.options.display.max_columns = None

YFS_config = {
    # 'financial_asset_list' : ['AAPL'],
    'financial_asset_list' : [2, 12, 14, 15, 16, 20, 21, 22, 23, 25],
    'environment_pk': 4,
}

for key in YFS_config.keys():
    YFS_config[key] = json.dumps(YFS_config[key])

query = f'''
    query {{
        YFS_Extractor(
            financial_asset_list: {YFS_config["financial_asset_list"]}
            environment_pk: {YFS_config["environment_pk"]}
        ) {{
            success,
            error,
        }}
    }}
'''

headers = {
        'Accept-Encoding': 'gzip, deflate, br',
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'Connection': 'keep-alive',
        'DNT': '1'
    }

response = requests.post('http://127.0.0.1:3987/graphql', json={"query":query}, headers=headers, timeout=5).json()
print(json.dumps(response, indent=2))