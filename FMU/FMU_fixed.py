def resolve_FMU(_,info,dum):
    try:
        #Importing libraries
        import pandas as pd
        import requests
        import time
        import datetime
        import pytz
        from datetime import datetime, timezone, timedelta
        from zoneinfo import ZoneInfo
        from datetime import date
        import psycopg2
        import psycopg2.extras
        from psycopg2.extensions import AsIs
        import dotenv
        from dotenv import load_dotenv
        import os
        import warnings
        warnings.filterwarnings("ignore")

        # DB config
        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
        database = 'dyDATA_new' 
        username = 'postgres'
        password = 'Proc2023awsrdspostgresql'
        port_id = 5432
        this_day = str(date.today())

        # Delete prior data
        with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                print("Deleting today's already registered data")
                cur.execute(f'''DELETE FROM "dyTRADE".financial_market_session_time_log WHERE "financial_market_session_time_log_utc_date" = '{this_day}' ''')

        def get_alpha_data():
            url = 'https://www.alphavantage.co/query?function=MARKET_STATUS&apikey=2M4KMLTI2FDMB6WB'
            r = requests.get(url)
            data = r.json()
            print(data)
            df = pd.json_normalize(data['markets'])
            df['primary_exchanges'] = df['primary_exchanges'].str.strip()
            return df

        df = get_alpha_data()

        time_cols = ['local_open', 'local_close']
        df[time_cols] = df[time_cols].apply(pd.to_datetime)

        print("Columns containing time:", time_cols)
        print(df['local_open'])

        def correct_date_time(df):
            # Add columns
            df = df.copy()
            df['financial_market_PK'] = None
            df['financial_market_ID'] = None
            df['financial_market_timezone_region_city_PK'] = None
            missing_markets = []

            # Explode exchanges
            df['exchanges'] = df['primary_exchanges'].str.split(', ')
            df = df.explode('exchanges')
            df['primary_exchanges'] = df['exchanges'].str.strip()
            df = df.drop('exchanges', axis=1).reset_index(drop=True)

            for i in df.index:
                market = df.loc[i, 'primary_exchanges']
                print(f"Processing market: {market}")

                # Get market PK from DB
                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        query = f'''SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view 
                        where "financial_market_code"='{market}' or "financial_market_name"='{market}' or "financial_market_alphavantage_name"='{market}'; '''
                        print(query)
                        cur.execute(query)
                        result = cur.fetchall()

                if not result:
                    print(f"No match for {market}, skipping")
                    missing_markets.append(market)
                    df.loc[i, 'notes'] = df.loc[i, 'notes'] or "No market PK match"
                    continue

                row = result[0]
                PK = row['financial_market_PK']
                ID = row['financial_market_ID']
                tz_pk = row['financial_market_timezone_region_city_PK']

                df.loc[i, 'financial_market_PK'] = PK
                df.loc[i, 'financial_market_ID'] = ID
                df.loc[i, 'financial_market_timezone_region_city_PK'] = tz_pk

                if tz_pk is None:
                    missing_markets.append(market)
                    df.loc[i, 'notes'] = "No timezone"
                    continue

                # Get zone
                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        query = f'''SELECT "timezone_region_city_name" from "dyGEO".timezone_region_city_list where "timezone_region_city_PK" = '{tz_pk}'; '''
                        cur.execute(query)
                        result = cur.fetchall()
                        zone = result[0][0] if result else 'UTC'

                print(f"Zone for {market}: {zone}")

                # Convert times to UTC, naive
                local_tz = ZoneInfo(zone)
                utc_tz = ZoneInfo("UTC")
                for col in time_cols:
                    local_str = df.loc[i, col].strftime('%Y-%m-%d %H:%M:%S')
                    dt = pd.to_datetime(local_str).tz_localize(local_tz)
                    dt_utc = dt.tz_convert(utc_tz)
                    df.loc[i, col] = dt_utc.tz_localize(None)

            print(df)
            print("Missing markets:", missing_markets)
            return df

        time_adjusted_df = correct_date_time(df)

        # Prep for insert
        time_adjusted_df.loc[:, 'notes'] = time_adjusted_df['notes'].fillna('-')
        time_adjusted_df.loc[:, 'current_status'] = time_adjusted_df['current_status'].map({'closed': 0, 'open': 1}).fillna(1)

        print(time_adjusted_df)

        # Insert non-US markets with PK
        with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
            with conn.cursor() as cur:
                for i in time_adjusted_df.index:
                    if time_adjusted_df.loc[i, 'region'] == 'United States' or pd.isna(time_adjusted_df.loc[i, 'financial_market_PK']):
                        continue

                    status = time_adjusted_df.loc[i, 'current_status']
                    pk = time_adjusted_df.loc[i, 'financial_market_PK']
                    open_time = time_adjusted_df.loc[i, 'local_open'].strftime('%Y-%m-%d %H:%M:%S')
                    close_time = time_adjusted_df.loc[i, 'local_close'].strftime('%Y-%m-%d %H:%M:%S')
                    note = str(time_adjusted_df.loc[i, 'notes'])

                    query = f'''INSERT INTO "dyTRADE".financial_market_session_time_log (
                        "financial_market_session_time_financial_market_PK",
                        "financial_market_session_time_market_session_PK",
                        "financial_market_session_time_log_utc_date",
                        "financial_market_session_time_opening_UTC_time",
                        "financial_market_session_time_closure_UTC_time",
                        "financial_market_session_time_note",
                        "financial_market_session_time_activity_status"
                    ) VALUES (%s, 2, %s, %s, %s, %s, %s)'''
                    cur.execute(query, (pk, this_day, open_time, close_time, note, status))

                conn.commit()
                print("Inserts completed successfully.")

        # apicalls fallback (simplified, similar logic)
        print("AlphaVantage processing complete. apicalls fallback skipped for now.")

        response = {'success': True, 'errors': None}
        return response

    except Exception as error:
        print('Error: ', error)
        response = {'success': False, 'errors': str(error)}
        return response

if __name__ == '__main__':
    resolve_FMU(None, None, None)
