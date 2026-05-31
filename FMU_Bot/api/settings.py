import pathlib
from pathlib import Path

#define paths
ROOT = Path('/kns-dta-data-kubernetes-namespace-tst-tst-kct/FMU-Financial_Market_Updater.Bot-API_2.0/FMU_Bot')
GRAPHQL_SCHEMA = ROOT / 'schema.graphql'

#server
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 4574

HEADERS = {
            'Accept-Encoding': 'gzip, deflate, br',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Connection': 'keep-alive',
            'DNT': '1'
        }