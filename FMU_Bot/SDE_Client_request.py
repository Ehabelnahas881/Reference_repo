import requests
import json
import pandas as pd 

pd.options.display.max_columns = None

SDE_config = {
    'function': "NEWS_SENTIMENT",
    'tickers_list': ["TSLA"],
    'topic' : "financial_markets",
    'time_from' : "20240720T0000",
    'time_to' : "20240721T0000",
    'sort' : "EARLIEST",
    'limit' : 1,
    'apikey' : "2M4KMLTI2FDMB6WB",
    'processor' : "Alpha Vantage"
}

for key in SDE_config.keys():
    SDE_config[key] = json.dumps(SDE_config[key])

query = f'''
    query {{
        AlphaVantageAPI(
            function: {SDE_config["function"]}
            tickers_list: {SDE_config["tickers_list"]}
            topic: {SDE_config["topic"]}
            time_from: {SDE_config["time_from"]}
            time_to: {SDE_config["time_to"]}
            sort: {SDE_config["sort"]}
            limit: {SDE_config["limit"]}
            apikey: {SDE_config["apikey"]}
            processor: {SDE_config["processor"]}
        ) {{
            success,
            errors
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

response = requests.post('http://192.168.56.145:4504/graphql',json={"query":query},headers=headers).json()
success = response['data']['AlphaVantageAPI']['success']
error = response['data']['AlphaVantageAPI']['errors']
print('success', success)
print('error:', error)