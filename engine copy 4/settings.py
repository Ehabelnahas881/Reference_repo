import os

# Database settings
USER = 'YFS'
PASSWORD = 'YFSpostgres2025'
DATABASE = 'dyDATA_new'
HOST = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
PORT = 5432

# waitress server settings
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 3987       

USER_AGENT = [
    {"ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36", "impersonate": "chrome120"},
    {"ua": "Mozilla/5.0 (Windows NT 10.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36", "impersonate": "chrome120"}
]

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "Referer": "https://finance.yahoo.com/",
    "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1"
}

# Path to GraphQL schema file
GRAPHQL_SCHEMA = os.path.join(os.path.dirname(__file__), "schema.graphql").replace('/.','')
