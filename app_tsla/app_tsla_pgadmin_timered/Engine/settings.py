import os
from pathlib import Path

# Automatically find the path to schema.graphql in the current folder
BASE_DIR = Path(__file__).resolve().parent
GRAPHQL_SCHEMA = str(BASE_DIR / "schema.graphql")

# IDE server settings
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 3989

# Database settings (Using your AWS RDS credentials)
DATABASE_HOST = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
DATABASE_PORT = 5432
USER = 'ehab.elnahas'
PASSWORD = 'test'
DBNAME = 'dyDATA_new'

# Scraping settings
FLUSH_THRESHOLD = 5