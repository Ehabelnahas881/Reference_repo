def resolve_FMU(_,info,dum):
    try:
        # Consolidated imports
        import pandas as pd
        import requests
        import os
        import warnings
        from datetime import date, datetime, timedelta
        from zoneinfo import ZoneInfo
        import psycopg2
        import psycopg2.extras
        from dotenv import load_dotenv

        warnings.filterwarnings("ignore")

        # Consolidated DB creds - prefer .env, fallback hardcoded
        cwd = os.getcwd()
        file_path = os.path.join(cwd, "Credentials.env")
        load_dotenv(file_path)
        hostname = os.getenv("DB_HOST", 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com')
        database = os.getenv("DB_NAME", 'dyDATA_new') 
        username = os.getenv("DB_USER", 'postgres')
        password = os.getenv("DB_PASSWORD", 'Proc2023awsrdspostgresql')
        port_id = int(os.getenv("DB_PORT", 5432))

        this_day = str(date.today())

        # Single conn for all ops
        conn = psycopg2.connect(host=hostname, dbname=database, user=username, password=password, port=port_id)
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        print("Deleting today's already registered data")
        cur.execute('''DELETE FROM "dyTRADE".financial_market_session_time_log WHERE financial_market_session_time_log_utc_date = %s''', (this_day,))
        conn.commit()

        def get_data():
            # Demo data for testing (replace API if key valid)
            data = {'markets': [{'region': 'Europe', 'primary_exchanges': 'LSE,', 'local_open': '09:00', 'local_close': '16:30', 'current_status': 'closed', 'notes': ''}, {'region': 'Asia', 'primary_exchanges': 'TSE', 'local_open': '09:00', 'local_close': '15:00', 'current_status': 'closed', 'notes': ''}]}
            print(data)
            records = data['markets']
            return pd.DataFrame(records)

        cleaned_df = get_data()


        # Get time cols
        time_cols = [col for col in cleaned_df.columns if 'local' in col]
        print("Columns containing time:", time_cols)

        cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].str.strip()

        today = date.today()

        # Parse local times with today
        cleaned_df['local_open'] = pd.to_datetime(cleaned_df['local_open'].apply(lambda x: f"{today} {x}"))
        cleaned_df['local_close'] = pd.to_datetime(cleaned_df['local_close'].apply(lambda x: f"{today} {x}"))

        # Process exchanges to list and explode
        def parse_exchanges(x):
            x = str(x).strip()
            if x.startswith('['):
                # Already list-like
                return eval(x)
            else:
                return x.split(',')

        cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(parse_exchanges)
        cleaned_df = cleaned_df.explode('primary_exchanges', ignore_index=True)
        cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].str.strip()

        # Vectorized market lookup: query all at once
        markets_str = "','".join(cleaned_df['primary_exchanges'].unique())
        query = f'''
        SELECT financial_market_code, financial_market_name, financial_market_alphavantage_name,
               "financial_market_PK", "financial_market_ID", "financial_market_timezone_region_city_PK"
        FROM "dyLEARN".financial_market_list_view 
        WHERE financial_market_code IN ('{markets_str}') 
           OR financial_market_name IN ('{markets_str}')
           OR financial_market_alphavantage_name IN ('{markets_str}')
        '''
        cur.execute(query)
        all_rows = cur.fetchall()
        market_map = {}
        for row in all_rows:
            market_map[row['financial_market_code']] = row
            if row['financial_market_name']:
                market_map[row['financial_market_name']] = row
        # Note: duplicate handling simplistic, take first

        def map_market(market):
            row = market_map.get(market, {})
            return pd.Series({
                'financial_market_PK': row.get('financial_market_PK'),
                'financial_market_ID': row.get('financial_market_ID'),
                'financial_market_timezone_region_city_PK': row.get('financial_market_timezone_region_city_PK')
            })

        market_info = cleaned_df['primary_exchanges'].apply(map_market)
        cleaned_df = pd.concat([cleaned_df, market_info], axis=1)

        missing_markets = cleaned_df[cleaned_df['financial_market_PK'].isna()]['primary_exchanges'].tolist()
        print("Missing market List:", missing_markets)

        # Timezone lookup vectorized
        tz_pks = cleaned_df['financial_market_timezone_region_city_PK'].dropna().unique()
        tz_map = {}
        if len(tz_pks):
        tz_pks_str = "','".join([str(int(pk)) for pk in tz_pks if pd.notna(pk)])
            tz_query = f'''
            SELECT "timezone_region_city_PK", "timezone_region_city_name"
            FROM "dyGEO".timezone_region_city_list
            WHERE "timezone_region_city_PK"::text IN ('{tz_pks_str}')
            '''
            cur.execute(tz_query)
            for row in cur.fetchall():
                tz_map[row['timezone_region_city_PK']] = row['timezone_region_city_name']

        def get_zone(tz_pk):
            if pd.isna(tz_pk):
                return 'UTC'
            return tz_map.get(tz_pk, 'UTC')

        cleaned_df['zone'] = cleaned_df['financial_market_timezone_region_city_PK'].apply(get_zone)

        # Vectorized tz conversion
        def local_to_utc(local_time, zone):
            if pd.isna(local_time):
                return pd.NaT
            local_tz = ZoneInfo(zone)
            dt = local_time.tz_localize(local_tz)
            utc_dt = dt.tz_convert('UTC')
            return utc_dt.tz_localize(None)

        for col in time_cols:
            cleaned_df[col] = cleaned_df.apply(lambda row: local_to_utc(row[col], row['zone']), axis=1)

        print(cleaned_df)

        # Fill notes
        cleaned_df['notes'] = cleaned_df['notes'].fillna('-')

        print(cleaned_df)

        print("\n=== CALCULATED SESSIONS (1=Pre, 2=Regular, 3=Post, 4=Overnight) ===")

        table_name = '"dyTRADE".financial_market_session_time_log'

        # Prepare inserts list for bulk
        inserts = []

        for i in cleaned_df.index:
            if pd.isna(cleaned_df.loc[i, 'financial_market_PK']): 
                print(f"Skipping {cleaned_df.loc[i, 'primary_exchanges']} - No PK")
                continue

            # Optionally skip US
            if cleaned_df.loc[i, 'region'] == 'United States':
                continue

            market_pk = cleaned_df.loc[i, 'financial_market_PK']
            market_name = cleaned_df.loc[i, 'primary_exchanges']
            status_str = "1" if str(cleaned_df.loc[i, 'current_status']).lower() != "closed" else "0"
            notes = cleaned_df.loc[i, 'notes']

            open_time = cleaned_df.loc[i, 'local_open']
            close_time = cleaned_df.loc[i, 'local_close']

            # Session 1: Pre (1.5h before open)
            pre_open = open_time - timedelta(hours=1.5)
            pre_close = open_time
            inserts.append((
                market_pk, 1, this_day, pre_open, pre_close, f"Pre {market_name}", status_str
            ))
            print(f" SESSION 1 PRE - {market_name} PK={market_pk}: {pre_open.strftime('%H:%M')}→{pre_close.strftime('%H:%M')} UTC")

            # Session 2: Regular
            inserts.append((
                market_pk, 2, this_day, open_time, close_time, f"Regular {market_name}", status_str
            ))
            print(f" SESSION 2 REGULAR - {market_name} PK={market_pk}: {open_time.strftime('%H:%M')}→{close_time.strftime('%H:%M')} UTC")

            # Session 3: Post (1h after close)
            post_open = close_time
            post_close = close_time + timedelta(hours=1)
            inserts.append((
                market_pk, 3, this_day, post_open, post_close, f"Post {market_name}", status_str
            ))
            print(f" SESSION 3 POST - {market_name} PK={market_pk}: {post_open.strftime('%H:%M')}→{post_close.strftime('%H:%M')} UTC")

            # Session 4: Overnight (post to next pre)
            overnight_open = post_close
            overnight_close = pre_open + timedelta(days=1)  # Next day pre
            inserts.append((
                market_pk, 4, this_day, overnight_open, overnight_close, f"Overnight {market_name}", status_str
            ))
            print(f" SESSION 4 OVERNIGHT - {market_name} PK={market_pk}: {overnight_open.strftime('%H:%M')}→{overnight_close.strftime('%H:%M')} UTC")

        # Bulk parametrized insert
        if inserts:
            insert_query = f'''
            INSERT INTO {table_name} 
            ("financial_market_session_time_financial_market_PK", 
             "financial_market_session_time_market_session_PK", 
             "financial_market_session_time_log_utc_date", 
             "financial_market_session_time_opening_UTC_time", 
             "financial_market_session_time_closure_UTC_time", 
             "financial_market_session_time_note", 
             "financial_market_session_time_activity_status") 
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            '''
            psycopg2.extras.execute_batch(cur, insert_query, inserts, page_size=100)
            conn.commit()


        print("All 4 SESSIONS inserted for valid markets!")

        cur.close()
        conn.close()

        return {'success': True, 'errors': None}

    except Exception as error:
        print('Error: ', error)
        return {'success': False, 'errors': str(error)}

if __name__ == '__main__':
    resolve_FMU(None, None, None)

