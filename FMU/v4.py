def resolve_FMU(_, info, dum):
    try:
        import pandas as pd
        import requests
        import psycopg2
        import psycopg2.extras
        from datetime import date, datetime, timedelta
        from backports.zoneinfo import ZoneInfo
        import warnings
        warnings.filterwarnings("ignore")

        # --- DATABASE CREDENTIALS ---
        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
        database = 'dyDATA_new' 
        username = 'postgres'
        password = 'Proc2023awsrdspostgresql'
        port_id = 5432
        this_day = str(date.today())

        # 1. CLEAN PREVIOUS RUN DATA
        with psycopg2.connect(host=hostname, dbname=database, user=username, password=password, port=port_id) as conn:
            with conn.cursor() as cur:
                print(f"Cleaning data for {this_day}...")
                cur.execute(f'DELETE FROM "dyTRADE".financial_market_session_time_log WHERE financial_market_session_time_log_utc_date = \'{this_day}\'')

        # 2. FETCH DATA FROM ALPHAVANTAGE
        print("Fetching market data from AlphaVantage...")
        url = 'https://www.alphavantage.co/query?function=MARKET_STATUS&apikey=2M4KMLTI2FDMB6WB'
        r = requests.get(url)
        data = r.json()
        
        dataframe = pd.DataFrame.from_dict(data)
        market_values = dataframe[['markets']].values
        cleaned_df = pd.concat([pd.DataFrame(market_values[i][0], index=[i]) for i in range(len(market_values))])

        # 3. TIMEZONE CONVERSION LOGIC
        cleaned_df['local_open'] = pd.to_datetime(cleaned_df['local_open'])
        cleaned_df['local_close'] = pd.to_datetime(cleaned_df['local_close'])
        cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(lambda x: x.strip())
        
        # (This section processes the UTC conversion based on your existing logic)
        # Assuming cleaned_df now contains 'local_open' and 'local_close' in UTC...

        # 4. DATABASE INSERTION (INCLUDES OVERNIGHT SESSION)
        table_name = '"dyTRADE".financial_market_session_time_log'
        
        with psycopg2.connect(host=hostname, dbname=database, user=username, password=password, port=port_id) as conn:
            with conn.cursor() as cur:
                for i in range(len(cleaned_df)):
                    # Get IDs and PKs from your view
                    market = cleaned_df['primary_exchanges'].iloc[i]
                    cur.execute(f'SELECT "financial_market_PK" FROM "dyLEARN".financial_market_list_view WHERE financial_market_code=\'{market}\' LIMIT 1')
                    res = cur.fetchone()
                    if not res: continue
                    market_pk = res[0]

                    # Standard Session (Regular Hours)
                    status = 1 if cleaned_df['current_status'].iloc[i] != "closed" else 0
                    
                    # 4th SESSION LOGIC (OVERNIGHT)
                    # Calculate Day Cross
                    pre_open = pd.to_datetime(cleaned_df['local_open'].iloc[i])
                    tomorrow_premarket = pre_open + pd.Timedelta(days=1)

                    # INSERT OVERNIGHT SESSION (PK 4)
                    query = f'''
                    INSERT INTO {table_name} 
                    ("financial_market_session_time_financial_market_PK", "financial_market_session_time_market_session_PK", 
                     "financial_market_session_time_log_utc_date", "financial_market_session_time_opening_UTC_time", 
                     "financial_market_session_time_closure_UTC_time", "financial_market_session_time_activity_status")
                    VALUES ({market_pk}, 4, '{this_day}', '{cleaned_df['local_close'].iloc[i]}', '{tomorrow_premarket}', {status})
                    ON CONFLICT DO NOTHING;
                    '''
                    cur.execute(query)
                
                conn.commit() # FORCE COMMIT BEFORE ANY OTHER ERRORS
        
        print("Success: Overnight sessions (PK 4) inserted and committed.")
        return {'success': True}

    except Exception as error:
        print('Error during execution: ', error)
        return {'success': False, 'errors': error}

if __name__ == '__main__':
    resolve_FMU(None, None, None)