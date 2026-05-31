def resolve_FMU(_,info,dum):
    try:
        #Importing l;ibraries
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

        from datetime import datetime, timezone

        import dotenv
        from dotenv import load_dotenv
        import os

        import warnings
        warnings.filterwarnings("ignore")

        #Delete any previous day
        cwd = os.getcwd()
        file_path = os.path.join(cwd, "Credentials.env")
        load_dotenv(file_path)
        hostname, port_id, database, username, password = (
            os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
        )
        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
        database = 'dyDATA_new' 
        username = 'postgres'
        password = 'Proc2023awsrdspostgresql'
        port_id = 5432
        this_day = str(date.today())
        with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                print("Deleting today's already registered data")
                cur.execute(f'''DELETE FROM "dyTRADE".financial_market_session_time_log WHERE financial_market_session_time_log_utc_date = '{this_day}' ''')

        def get_data():
            # replace the "demo" apikey below with your own key from https://www.alphavantage.co/support/#api-key
            url = 'https://www.alphavantage.co/query?function=MARKET_STATUS&apikey=2M4KMLTI2FDMB6WB'
            r = requests.get(url)
            data = r.json()
            print(data)

            dataframe = pd.DataFrame.from_dict(data)
            market_values = dataframe[['markets']].values


            #Creating thye dataframe
            cleaned_df = pd.DataFrame()
            temp_df = pd.DataFrame()
            for i in range(0,len(market_values),1):
                temp_df = pd.DataFrame(market_values[i][0], index=[i])
                if i == 0:
                    cleaned_df = temp_df
                else:
                    cleaned_df = pd.concat([cleaned_df,temp_df])
            

            return cleaned_df


        dataframe = get_data()
        cleaned_df = dataframe.copy()

        time_cols = list(cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'local')])
        print("Columns containing time:", time_cols)

        cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(lambda x: x.strip())

        def correct_date_time(cleaned_df):
            #Get region data from table
            cwd = os.getcwd()
            file_path = os.path.join(cwd, "Credentials.env")
            load_dotenv(file_path)
            hostname, port_id, database, username, password = (
                os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
            )
            print(hostname, port_id, database, username, password)

            hostname ="database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com" 
            database="dyDATA_new" 
            username='postgres'
            password='Proc2023awsrdspostgresql'
            port_id=5432

            ###################
            # Changing the time only values into datetime
            #this part need to be fixed!!! The fix is not to uncomment the format line, it is just there was future purposes.
            # Parse times with today's date to avoid future year
            today = date.today()
            cleaned_df['local_open'] = pd.to_datetime(cleaned_df['local_open'].apply(lambda x: f"{today} {x}"))
            cleaned_df['local_close'] = pd.to_datetime(cleaned_df['local_close'].apply(lambda x: f"{today} {x}"))
            print(cleaned_df['local_open'])
            # 2. Separate stock markets (FIXING THE SEQUENCE ERROR)
                # Logic to handle lists if already partially processed
            cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(
                lambda x: [item[1:-1] for sublist in x for item in sublist] if isinstance(x, list) else x
            )

                # CRITICAL FIX: Force column to object type so it can hold the list temporarily
            cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].astype(object)   
            for i in range(len(cleaned_df)):
             if cleaned_df['primary_exchanges'][i].find(',') == 0:
                cleaned_df['primary_exchanges'][i] = cleaned_df['primary_exchanges'][i].split(',')
            cleaned_df = cleaned_df.explode(column = 'primary_exchanges', ignore_index=True)
            # Removing whitespaces from starting and ending of the cells
            cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(lambda x: x.strip())

            # FIILING TIME RELATRED COLUMNS IN A LIST
            time_cols = list(cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'local')])

            cleaned_df['financial_market_PK'] = None
            cleaned_df['financial_market_ID'] = None
            cleaned_df['financial_market_timezone_region_city_PK'] = None
            missing_market_list = []
            for i in range(len(cleaned_df)):
                #Adding neccessary columns to the dataframe like PK and ID
                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        market = cleaned_df['primary_exchanges'][i]
                        print(f"now we in: {market}")
                        financial_market_PK= '''"financial_market_PK"'''
                        financial_market_ID= '''"financial_market_ID"'''
                        financial_market_name= '''"financial_market_name"'''
                        financial_market_timezone_region_city_PK = '''"financial_market_timezone_region_city_PK"'''

                        ################################################
                        query=f'''SELECT {financial_market_PK},{financial_market_ID},{financial_market_name},{financial_market_timezone_region_city_PK} 
                        from "dyLEARN".financial_market_list_view 
                        where financial_market_code='{market}' or 
                        financial_market_name='{market}' or 
                        financial_market_alphavantage_name='{market}'; '''
                        print(query)
                        cur.execute(query)
                        result = cur.fetchall()
                        print(result)
                        
                        if not result:
                            print(f"No market data found for: {market}")
                            cleaned_df.loc[i, 'financial_market_PK'] = None
                            cleaned_df.loc[i, 'financial_market_ID'] = None
                            cleaned_df.loc[i, 'financial_market_timezone_region_city_PK'] = None
                            missing_market_list.append(market)
                            if pd.isna(cleaned_df.loc[i, 'notes']):
                                cleaned_df.loc[i, 'notes'] = "Error: Market not found in database"
                            continue
                        
                        # Use first result row
                        row = result[0]
                        PK = row[0]
                        ID = row[1]
                        timezone_region_city_PK = row[3]
                        print(f"PK: {PK}")
                    

                        cleaned_df.loc[i, 'financial_market_PK'] = PK
                        cleaned_df.loc[i, 'financial_market_ID'] = ID
                        cleaned_df.loc[i, 'financial_market_timezone_region_city_PK'] = timezone_region_city_PK
                        
                        if timezone_region_city_PK is None:
                            print(f"Using UTC for {market} (no timezone)")
                            zone = "UTC"
                            cleaned_df.loc[i, 'notes'] = "UTC (no timezone in DB)"
                            continue  # Skip timezone lookup

                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        country_timezone_region_city_name = '''"timezone_region_city_name"'''
                        country_timezone_region_city_PK = '''"timezone_region_city_PK"'''
                        query=f'''SELECT {country_timezone_region_city_name} 
                        from "dyGEO".timezone_region_city_list
                        where {country_timezone_region_city_PK}='{timezone_region_city_PK}'; '''
                        print(query)
                        cur.execute(query)
                        result = cur.fetchall()
                        if not result:
                            print(f"No timezone data for PK: {timezone_region_city_PK}")
                            cleaned_df.loc[i, 'notes'] = "Error: No timezone data"
                            continue
                        print(result[0])
                        country_zone = str(result[0][0])
                        zone = country_zone


                
                
                print("now to convert the timezone")
                # Time correction to UTC
                for col in time_cols:
                    print("LocaL OPEN time:", cleaned_df['local_open'][i], "Market name:", cleaned_df['primary_exchanges'][i])
                    local  = str(cleaned_df[col][i])
                    print ("Got local time: ", local)
                    # Get timezone we're trying to convert from
                    local_tz = ZoneInfo(zone)
                    # UTC timezone
                    utc_tz = ZoneInfo("UTC")

                    #print((local_open))

                    dt = datetime.strptime(local,"%Y-%m-%d %H:%M:%S")
                    dt = dt.replace(tzinfo=local_tz)
                    dt_open_utc = dt.astimezone(utc_tz)
                    dt_open_utc = pd.Timestamp(dt_open_utc).tz_localize(None)
                    cleaned_df.loc[i, col] = dt_open_utc
                    print("Zone: ", zone, "Converted to UTC: ", cleaned_df.loc[i, col])
                    print("UTC time:", cleaned_df.loc[i, 'local_open'], "Market name:", cleaned_df.loc[i, 'primary_exchanges'])

                # #Removing timezones
            # Remove timezone info for entire column (inside loop now handled)
            cleaned_df['local_open'] = pd.to_datetime(cleaned_df['local_open']).dt.tz_localize(None)
            cleaned_df['local_close'] = pd.to_datetime(cleaned_df['local_close']).dt.tz_localize(None)

            print(cleaned_df)

            print("Missing market List:", missing_market_list)

            return (cleaned_df) 
        
        time_adjusted_dataframe = correct_date_time(cleaned_df)

        this_day = str(date.today())

        for i in range(len(time_adjusted_dataframe)):
            if time_adjusted_dataframe['notes'][i] == "":
                time_adjusted_dataframe['notes'][i] = "-"

        print(time_adjusted_dataframe)

        # "financial_market_opening_status_UUID"

        table_name = '''"dyTRADE".financial_market_session_time_log'''

        #Commenting for time till market_PK not ready time_adjusted_dataframe['financial_market_PK'][i],

        cwd = os.getcwd()
        file_path = os.path.join(cwd, "Credentials.env")
        cwd = os.getcwd()
        file_path = os.path.join(cwd, "Credentials.env")
        load_dotenv(file_path)
        hostname, port_id, database, username, password = (
            os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
        )
        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
        database = 'dyDATA_new' 
        username = 'postgres'
        password = 'Proc2023awsrdspostgresql'
        port_id = 5432
        print(hostname, port_id, database, username, password)
        print(hostname, port_id, database, username, password)
        print("\n=== CALCULATED SESSIONS (1=Pre, 2=Regular, 3=Post, 4=Overnight) ===")
        with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                for i in range(len(time_adjusted_dataframe)):
                    if pd.isna(time_adjusted_dataframe.loc[i, 'financial_market_PK']):
                        print(f"Skipping {time_adjusted_dataframe.loc[i, 'primary_exchanges']} - No PK")
                        continue
                    if time_adjusted_dataframe.loc[i, 'region'] == 'United States':
                        continue

                    current_status = time_adjusted_dataframe.loc[i, 'current_status']
                    status_str = "0" if str(current_status) == "closed" else "1"
                    time_adjusted_dataframe.loc[i, 'current_status'] = status_str
                    
                    notes_str = time_adjusted_dataframe.loc[i, 'notes'] or " "
                    ################################################
                    id= '''"financial_market_session_time_ID"'''
                    financial_market_PK= '''"financial_market_session_time_financial_market_PK"'''
                    session_time_log_utc_date= '''"financial_market_session_time_log_utc_date"'''
                    opening_UTC_time= '''"financial_market_session_time_opening_UTC_time"'''
                    closure_UTC_time= '''"financial_market_session_time_closure_UTC_time"'''
                    session_time_note= '''"financial_market_session_time_note"'''
                    market_status= '''"financial_market_session_time_activity_status"'''
                    market_session_PK =  '''"financial_market_session_time_market_session_PK"'''
                    
                    query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{session_time_note},{market_status})
                    VALUES ({time_adjusted_dataframe['financial_market_PK'][i]},{time_adjusted_dataframe['financial_market_PK'][i]},2,'{this_day}','{time_adjusted_dataframe['local_open'][i]}','{time_adjusted_dataframe['local_close'][i]}',
                    '{time_adjusted_dataframe['notes'][i]}',{time_adjusted_dataframe['current_status'][i]})'''
                    market_name = time_adjusted_dataframe.loc[i, 'primary_exchanges']
                    market_pk = time_adjusted_dataframe.loc[i, 'financial_market_PK']
                    
                    # Session 1: Pre-market (1.5h before)
                    pre_open = time_adjusted_dataframe.loc[i, 'local_open'] - pd.Timedelta(hours=1.5)
                    pre_close = time_adjusted_dataframe.loc[i, 'local_open']
                    print(f" SESSION 1 PRE  - {market_name} PK={market_pk}: {pre_open.strftime('%H:%M')}→{pre_close.strftime('%H:%M')} UTC")
                    cur.execute(f'''INSERT INTO {table_name} ("financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status") VALUES ({market_pk},1,'{this_day}','{pre_open}','{pre_close}','Pre {market_name}',{status_str})''')

                    # Session 2: Regular
                    print(f" SESSION 2 REGULAR - {market_name} (PK={market_pk}): {time_adjusted_dataframe.loc[i, 'local_open'].strftime('%H:%M')} → {time_adjusted_dataframe.loc[i, 'local_close'].strftime('%H:%M')} UTC")
                    print(query)
                    cur.execute(query)

                    # Session 3: Post-market (1h after)
                    post_open = time_adjusted_dataframe.loc[i, 'local_close']
                    post_close = time_adjusted_dataframe.loc[i, 'local_close'] + pd.Timedelta(hours=1)
                    print(f" SESSION 3 POST - {market_name} PK={market_pk}: {post_open.strftime('%H:%M')}→{post_close.strftime('%H:%M')} UTC")
                    cur.execute(f'''INSERT INTO {table_name} ("financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status") VALUES ({market_pk},3,'{this_day}','{post_open}','{post_close}','Post {market_name}',{status_str})''')

                    # Session 4: Overnight (to next pre)
                    overnight_open = post_close
                    overnight_close = pre_open + pd.Timedelta(days=1)
                    print(f" SESSION 4 OVERNIGHT - {market_name} PK={market_pk}: {overnight_open.strftime('%H:%M')}→{overnight_close.strftime('%H:%M')} UTC")
                    cur.execute(f'''INSERT INTO {table_name} ("financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status") VALUES ({market_pk},4,'{this_day}','{overnight_open}','{overnight_close}','Overnight {market_name}',{status_str})''')

        print(" ALL 4 SESSIONS (Pre/Regular/Post/Overnight) inserted for all valid markets!")

        def API_failure():
            
            eastern = pytz.timezone('US/Eastern')
            now_eastern = datetime.now(eastern)
            
            preMarketOpeningTime = now_eastern.replace(hour=4,minute=0,second=0,microsecond=0)
            preMarketOpeningTime_str = preMarketOpeningTime.strftime('%b %d, %Y %I:%M %p ET')
            preMarketClosingTime = now_eastern.replace(hour=9,minute=30,second=0,microsecond=0)
            preMarketClosingTime_str = preMarketClosingTime.strftime('%b %d, %Y %I:%M %p ET')
            
            marketOpeningTime = now_eastern.replace(hour=9,minute=30,second=0,microsecond=0)
            marketOpeningTime_str = marketOpeningTime.strftime('%b %d, %Y %I:%M %p ET')
            marketClosingTime = now_eastern.replace(hour=16,minute=0,second=0,microsecond=0)
            marketClosingTime_str = marketClosingTime.strftime('%b %d, %Y %I:%M %p ET')
            
            afterHoursMarketOpeningTime = now_eastern.replace(hour=16,minute=0,second=0,microsecond=0)
            afterHoursMarketOpeningTime_str = afterHoursMarketOpeningTime.strftime('%b %d, %Y %I:%M %p ET')
            afterHoursMarketClosingTime = now_eastern.replace(hour=20,minute=0,second=0,microsecond=0)
            afterHoursMarketClosingTime_str = afterHoursMarketClosingTime.strftime('%b %d, %Y %I:%M %p ET')
            
            if now_eastern < preMarketOpeningTime:
                marketIndicator = 'Market Closed'
                mrktStatus = 'Closed'
                marketCountDown_timestamp = marketOpeningTime - now_eastern
            
                if marketCountDown_timestamp.total_seconds() < 3600:
                    minutes, seconds = divmod(int(marketCountDown_timestamp.total_seconds()), 60)
                    market_countdown = f"Market Opens in {minutes}M {seconds}S"
                    mrktCountDown = f"Opens in {minutes}M {seconds}S"
                else:  # If the remaining time is 1 hour or more
                    hours, remainder = divmod(int(marketCountDown_timestamp.total_seconds()), 3600)
                    minutes, _ = divmod(remainder, 60)
                    market_countdown = f"Market Opens in {hours}H {minutes}M"
                    mrktCountDown = f"Opens in {hours}H {minutes}M"
            
            elif preMarketOpeningTime < now_eastern < preMarketClosingTime:
                marketIndicator = 'Pre Market'
                mrktStatus = 'Pre-Market'
                marketCountDown_timestamp = marketOpeningTime - now_eastern
            
                if marketCountDown_timestamp.total_seconds() < 3600:
                    minutes, seconds = divmod(int(marketCountDown_timestamp.total_seconds()), 60)
                    market_countdown = f"Market Opens in {minutes}M {seconds}S"
                    mrktCountDown = f"Opens in {minutes}M {seconds}S"
                else:  # If the remaining time is 1 hour or more
                    hours, remainder = divmod(int(marketCountDown_timestamp.total_seconds()), 3600)
                    minutes, _ = divmod(remainder, 60)
                    market_countdown = f"Market Opens in {hours}H {minutes}M"
                    mrktCountDown = f"Opens in {hours}H {minutes}M"
            
            elif marketOpeningTime < now_eastern < marketClosingTime:
                marketIndicator = 'Market Open'
                mrktStatus = 'Open'
                marketCountDown_timestamp = marketClosingTime - now_eastern
            
                if marketCountDown_timestamp.total_seconds() < 3600:
                    minutes, seconds = divmod(int(marketCountDown_timestamp.total_seconds()), 60)
                    market_countdown = f"Market Closes in {minutes}M {seconds}S"
                    mrktCountDown = f"Closes in {minutes}M {seconds}S"
                else:  # If the remaining time is 1 hour or more
                    hours, remainder = divmod(int(marketCountDown_timestamp.total_seconds()), 3600)
                    minutes, _ = divmod(remainder, 60)
                    market_countdown = f"Market Closes in {hours}H {minutes}M"
                    mrktCountDown = f"Closes in {hours}H {minutes}M"
            
            elif afterHoursMarketOpeningTime < now_eastern :
                marketIndicator = 'After Hours'
                mrktStatus = 'After-Hours'
                next_marketOpeningTime = marketOpeningTime + timedelta(days=1)
                marketCountDown_timestamp = next_marketOpeningTime - now_eastern
            
                if marketCountDown_timestamp.total_seconds() < 3600:
                    minutes, seconds = divmod(int(marketCountDown_timestamp.total_seconds()), 60)
                    market_countdown = f"Market Opens in {minutes}M {seconds}S"
                    mrktCountDown = f"Opens in {minutes}M {seconds}S"
                else:  # If the remaining time is 1 hour or more
                    hours, remainder = divmod(int(marketCountDown_timestamp.total_seconds()), 3600)
                    minutes, _ = divmod(remainder, 60)
                    market_countdown = f"Market Opens in {hours}H {minutes}M"
                    mrktCountDown = f"Opens in {hours}H {minutes}M"
            
            today = datetime.today()
            day_number = today.weekday()
            
            if day_number == 0:
                isBusinessDay = True
                today_date = today.date()
                previousTradeDate = today_date - timedelta(days=3)
                nextTradeDate = today_date + timedelta(days=1)
                previousTradeDate_str = previousTradeDate.strftime('%b %d, %Y')
                nextTradeDate_str = nextTradeDate.strftime('%b %d, %Y')

            elif day_number == 5:
                isBusinessDay = False
                today_date = today.date()
                previousTradeDate = today_date - timedelta(days=1)
                nextTradeDate = today_date + timedelta(days=2)
                previousTradeDate_str = previousTradeDate.strftime('%b %d, %Y')
                nextTradeDate_str = nextTradeDate.strftime('%b %d, %Y')

            elif day_number == 6:
                isBusinessDay = False
                today_date = today.date()
                previousTradeDate = today_date - timedelta(days=2)
                nextTradeDate = today_date + timedelta(days=1)
                previousTradeDate_str = previousTradeDate.strftime('%b %d, %Y')
                nextTradeDate_str = nextTradeDate.strftime('%b %d, %Y')

            else:
                isBusinessDay = True
                today_date = today.date()
                previousTradeDate = today_date - timedelta(days=1)
                nextTradeDate = today_date + timedelta(days=1)
                previousTradeDate_str = previousTradeDate.strftime('%b %d, %Y')
                nextTradeDate_str = nextTradeDate.strftime('%b %d, %Y')

            expected_response = {'country': 'U.S.', 'marketIndicator': marketIndicator, 'uiMarketIndicator': marketIndicator, 'marketCountDown': market_countdown, 'preMarketOpeningTime': preMarketOpeningTime_str, 'preMarketClosingTime': preMarketClosingTime_str, 'marketOpeningTime': marketOpeningTime_str,
            'marketClosingTime': marketClosingTime_str, 'afterHoursMarketOpeningTime': afterHoursMarketOpeningTime_str, 'afterHoursMarketClosingTime': afterHoursMarketClosingTime_str, 'previousTradeDate': previousTradeDate_str, 'nextTradeDate': nextTradeDate_str, 'isBusinessDay': isBusinessDay,
            'mrktStatus': mrktStatus, 'mrktCountDown': mrktCountDown}

            return expected_response

        ###########################################################
        # apicalls.io fetched dataframe is processed from here on.
        ###########################################################

        def apicalls_get_data():
            global data
            try:
                url = 'https://api.apicalls.io/v2/markets/market-info'
                headers = {
                'Authorization': 'Bearer 539|5d9M5TONvuHKNOVYKwrWKT88fsivCirNPSc9nXXf'
                }

                response = requests.request('GET', url, headers=headers, timeout=10)
                data = response.json()
                print(data)

                if data is None or ('body' not in data):
                    raise ValueError("Invalid API response")
                dict = data['body']
            except Exception as e:
                print(f"APICalls failed ({e}), using fallback")
                dict = API_failure()
            dataframe = pd.DataFrame(list(dict.items()))
            dataframe =  dataframe.transpose()

            return dataframe
        
        dataframe = apicalls_get_data()
        cleaned_df = dataframe.copy()
        
        def apicalls_correct_date_time(cleaned_df):

            # Get region data from table
            cwd = os.getcwd()
            file_path = os.path.join(cwd, "Credentials.env")
            load_dotenv(file_path)
            hostname, port_id, database, username, password = (
                os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
            )
            print(hostname, port_id, database, username, password)

            hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
            database = 'dyDATA_new' 
            username = 'postgres'
            password = 'Proc2023awsrdspostgresql'
            port_id = 5432

            cleaned_df. columns=cleaned_df. iloc[0]
            cleaned_df = (cleaned_df.drop(0))
            cleaned_df.reset_index()
            cleaned_df.loc[0, 'country'] = 'US'


            time_cols = list(cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'Time')])
            date_cols = (list([cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'Date')]]))

            for col in time_cols:
                cleaned_df[col] = pd.to_datetime(cleaned_df[col], format='%Y-%m-%d %H:%M:%S', errors='coerce')
            
            for col in date_cols:
                cleaned_df[col] = cleaned_df[col].apply(lambda x: pd.to_datetime(str(x), format="%b %d, %Y", errors='coerce').strftime("%d.%m.%Y") if pd.notna(pd.to_datetime(str(x), format="%b %d, %Y", errors='coerce')) else x)


            cleaned_df.assign(financial_market_name="")
            cleaned_df.assign(financial_market_PK="")
            print("Printing cleaned df", cleaned_df)
            market_df = pd.DataFrame()
            # Fallback US data - skip detailed processing, return directly
            print("Fallback US market data processed, returning")
            return cleaned_df
                
            try: 
                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                            query=f'''SELECT "PK"
                            from "dyGEO".country_list_view 
                            where alpha_2_code=%s; ''' # Use US
                            cur.execute(query, ('US',))
                            print(query)
                            cur.execute(query)
                            result = cur.fetchall()
                            print("counrty_PK = ", result)
            except:
                    raise Exception('Could not fetch the country PK.')
            finally:
                if conn is not None:
                    conn.close()

            try: 
                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        for pk in result:
                            query=f'''SELECT "timezone_region_city_PK"
                            from "dyGEO".country_timezone_region_city_rel_view 
                            where "country_PK" = {pk[0]}; ''' # The counrty name should be US and not U.S.
                            print(query)
                            cur.execute(query)
                            timezone_region_city_PK_list = cur.fetchall()
                            print("timezone_region_city_PK_list: ", timezone_region_city_PK_list)
            except:
                raise Exception('Could not fetch the timezone region city PK.')
            finally:
                if conn is not None:
                    conn.close()  
            try: 
                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        for tz_PK in range(len(timezone_region_city_PK_list)):
                            query=f''' SELECT "financial_market_PK", financial_market_name
                            from "dyLEARN".financial_market_list 
                            where "financial_market_timezone_region_city_PK" ='{timezone_region_city_PK_list[tz_PK][0]}'; ''' # The counrty name should be US and not U.S.
                            print(query)
                            cur.execute(query)
                            markets = cur.fetchall()
                            num = row
                            for market in markets:
                                financial_market_PK = market[0]
                                financial_market_name = market[1]
                                data_dict = {'financial_market_name': financial_market_name,'financial_market_PK': financial_market_PK,'country':cleaned_df['country'][row], 'marketIndicator':cleaned_df['marketIndicator'][row],
                                            'uiMarketIndicator':cleaned_df['uiMarketIndicator'][row],'marketCountDown':cleaned_df['marketCountDown'][row],
                                            'preMarketOpeningTime':cleaned_df['preMarketOpeningTime'][row], 'preMarketClosingTime':cleaned_df['preMarketClosingTime'][row],
                                            'marketOpeningTime':cleaned_df['marketOpeningTime'][row], 'marketClosingTime':cleaned_df['marketClosingTime'][row],
                                            'afterHoursMarketOpeningTime':cleaned_df['afterHoursMarketOpeningTime'][row], 'afterHoursMarketClosingTime':cleaned_df['afterHoursMarketClosingTime'][row],
                                            'previousTradeDate':cleaned_df['previousTradeDate'][row], 'nextTradeDate':cleaned_df['nextTradeDate'][row],
                                            'isBusinessDay':cleaned_df['isBusinessDay'][row], 'mrktStatus':cleaned_df['mrktStatus'][row], 'mrktCountDown':cleaned_df['mrktCountDown'][row] }
                                temp_df = pd.DataFrame(data_dict, index=[0])
                                num += 1
                                market_df = pd.concat([market_df,temp_df], ignore_index=True)
            except:
                    raise Exception('Could not fetch the market name')
            finally:
                if conn is not None:
                    conn.close()
                
            cleaned_df = pd.concat([cleaned_df, market_df], ignore_index=True)
            print("Concatinated dataframe:", cleaned_df)

            print(market_df)
            return (market_df)
        
        apicalls_time_adjusted_dataframe = apicalls_correct_date_time(cleaned_df)

        from datetime import date
        this_day = str(date.today())

        cwd = os.getcwd()
        file_path = os.path.join(cwd, "Credentials.env")
        load_dotenv(file_path)
        hostname, port_id, database, username, password = (
            os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
        )
        print(hostname, port_id, database, username, password)

        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
        database = 'dyDATA_new' 
        username = 'postgres'
        password = 'Proc2023awsrdspostgresql'
        port_id = 5432

        # "financial_market_opening_status_UUID"

        table_name = '''"dyTRADE".financial_market_session_time_log'''

        #Commenting for time till market_PK not ready apicalls_time_adjusted_dataframe['financial_market_PK'][i],
        ### For the overnight session logic ###
    
        with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                for i in range(len(apicalls_time_adjusted_dataframe)):
                    if apicalls_time_adjusted_dataframe['mrktStatus'][i] == "Open":
                        apicalls_time_adjusted_dataframe['mrktStatus'][i]=1
                    else:
                        apicalls_time_adjusted_dataframe['mrktStatus'][i]=0
                    if apicalls_time_adjusted_dataframe['notes'][i] is None:
                        apicalls_time_adjusted_dataframe['notes'][i] = " "
                    ################################################
                    id= '''"financial_market_session_time_ID"'''
                    financial_market_PK= '''"financial_market_session_time_financial_market_PK"'''
                    session_time_log_utc_date= '''"financial_market_session_time_log_utc_date"'''
                    opening_UTC_time= '''"financial_market_session_time_opening_UTC_time"'''
                    closure_UTC_time= '''"financial_market_session_time_closure_UTC_time"'''
                    session_time_note= '''"financial_market_session_time_note"'''
                    market_status= '''"financial_market_session_time_activity_status"'''
                    market_session_PK =  '''"financial_market_session_time_market_session_PK"'''
                    next_trade_session_date = '''"financial_market_session_next_market_trading_session_date"'''
                    
                    query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                    VALUES ({apicalls_time_adjusted_dataframe['financial_market_PK'][i]},{apicalls_time_adjusted_dataframe['financial_market_PK'][i]},2,'{this_day}','{apicalls_time_adjusted_dataframe['marketOpeningTime'][i]}','{apicalls_time_adjusted_dataframe['marketClosingTime'][i]}'
                    ,{apicalls_time_adjusted_dataframe['mrktStatus'][i]},'{apicalls_time_adjusted_dataframe['nextTradeDate'][i]}')'''
                    print(query)
                    cur.execute(query)
                
                    # Adding the pre Market data
                    query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                    VALUES ({apicalls_time_adjusted_dataframe['financial_market_PK'][i]},{apicalls_time_adjusted_dataframe['financial_market_PK'][i]},1,'{this_day}','{apicalls_time_adjusted_dataframe['preMarketOpeningTime'][i]}','{apicalls_time_adjusted_dataframe['preMarketClosingTime'][i]}'
                    ,{apicalls_time_adjusted_dataframe['mrktStatus'][i]}, '{apicalls_time_adjusted_dataframe['nextTradeDate'][i]}')'''
                    print(query)
                    cur.execute(query)

                    # Adding the values of after Market data
                    query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                    VALUES ({apicalls_time_adjusted_dataframe['financial_market_PK'][i]},{apicalls_time_adjusted_dataframe['financial_market_PK'][i]},3,'{this_day}','{apicalls_time_adjusted_dataframe['afterHoursMarketOpeningTime'][i]}','{apicalls_time_adjusted_dataframe['afterHoursMarketClosingTime'][i]}'
                    ,{apicalls_time_adjusted_dataframe['mrktStatus'][i]}, '{apicalls_time_adjusted_dataframe['nextTradeDate'][i]}')'''
                    print(query)
                    cur.execute(query)
                    ##################################################
                    ######## Adding the overnight session data########
                    ##################################################
                    # Add 1 day to tomorrow's pre-market opening time for overnight closure
                    tomorrow_premarket = apicalls_time_adjusted_dataframe['preMarketOpeningTime'][i] + pd.Timedelta(days=1)

                    query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                    VALUES ({apicalls_time_adjusted_dataframe['financial_market_PK'][i]},{apicalls_time_adjusted_dataframe['financial_market_PK'][i]},4,'{this_day}','{apicalls_time_adjusted_dataframe['afterHoursMarketClosingTime'][i]}','{tomorrow_premarket}'
                    ,{apicalls_time_adjusted_dataframe['mrktStatus'][i]}, '{apicalls_time_adjusted_dataframe['nextTradeDate'][i]}')'''
                    print(query)
                    cur.execute(query)

                    # approach two
                    #query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                    #VALUES ({apicalls_time_adjusted_dataframe['financial_market_PK'][i]},{apicalls_time_adjusted_dataframe['financial_market_PK'][i]},4,'{this_day}','{apicalls_time_adjusted_dataframe['afterHoursMarketClosingTime'][i]}','{apicalls_time_adjusted_dataframe['preMarketOpeningTime'][i]}'
                    #,{apicalls_time_adjusted_dataframe['mrktStatus'][i]}, '{apicalls_time_adjusted_dataframe['nextTradeDate'][i]}')'''          
                    #print(query)
                    #cur.execute(query)

        response = {
            'success':True,
            'errors':None
        }
        return response
        
        
    except Exception as error:
        print('Error: ', error)
        response = {
            'success':False,
            'errors': error
        }
        return response



if __name__=='__main__':
     resolve_FMU(None, None, None)




(.venv) PS C:\Users\ehaba\OneDrive\scraper> & c:\Users\ehaba\OneDrive\scraper\.venv\Scripts\python.exe c:/Users/ehaba/OneDrive/scraper/FMU/F.py
Deleting today's already registered data
{'endpoint': 'Global Market Open & Close Status', 'markets': [{'market_type': 'Equity', 'region': 'United States', 'primary_exchanges': 'NASDAQ, NYSE, AMEX, BATS', 'local_open': '09:30', 'local_close': '16:15', 'current_status': 'closed', 'notes': ''}, {'market_type': 'Equity', 'region': 'Canada', 'primary_exchanges': 'Toronto, Toronto Ventures', 'local_open': '09:30', 'local_close': '16:00', 'current_status': 'closed', 'notes': ''}, {'market_type': 'Equity', 'region': 'United Kingdom', 'primary_exchanges': 'London', 'local_open': '08:00', 'local_close': '16:30', 'current_status': 'closed', 'notes': ''}, {'market_type': 'Equity', 'region': 'Germany', 'primary_exchanges': 'XETRA, Berlin, Frankfurt, Munich, Stuttgart', 'local_open': '08:00', 'local_close': '20:00', 'current_status': 'closed', 'notes': ''}, {'market_type': 'Equity', 'region': 'France', 'primary_exchanges': 'Paris', 'local_open': '09:00', 'local_close': '17:30', 'current_status': 'closed', 'notes': ''}, {'market_type': 'Equity', 'region': 'Spain', 'primary_exchanges': 'Barcelona, Madrid', 'local_open': '09:00', 'local_close': '17:30', 'current_status': 'closed', 'notes': ''}, {'market_type': 'Equity', 'region': 'Portugal', 'primary_exchanges': 'Lisbon', 'local_open': '08:00', 'local_close': '16:30', 'current_status': 'closed', 'notes': ''}, {'market_type': 'Equity', 'region': 'Japan', 'primary_exchanges': 'Tokyo', 'local_open': '09:00', 'local_close': '15:00', 'current_status': 'open', 'notes': 'Noon trading break from 11:30 to 12:30 local time'}, {'market_type': 'Equity', 'region': 'India', 'primary_exchanges': 'NSE, BSE', 'local_open': '09:15', 'local_close': '15:30', 'current_status': 'open', 'notes': ''}, {'market_type': 'Equity', 'region': 'Mainland China', 'primary_exchanges': 'Shanghai, Shenzhen', 'local_open': '09:30', 'local_close': '15:00', 'current_status': 'open', 'notes': 'Noon trading break from 11:30 to 13:00 local time'}, {'market_type': 'Equity', 'region': 'Hong Kong', 'primary_exchanges': 'Hong Kong', 'local_open': '09:30', 'local_close': '16:00', 'current_status': 'open', 'notes': 'Noon trading break from 12:00 to 13:00 local time'}, {'market_type': 'Equity', 'region': 'Brazil', 'primary_exchanges': 'Sao Paolo', 'local_open': '10:00', 'local_close': '17:30', 'current_status': 'closed', 'notes': ''}, {'market_type': 'Equity', 'region': 'Mexico', 'primary_exchanges': 'Mexico', 'local_open': '08:30', 'local_close': '15:00', 'current_status': 'closed', 'notes': ''}, {'market_type': 'Equity', 'region': 'South Africa', 'primary_exchanges': 'Johannesburg', 'local_open': '09:00', 'local_close': '17:00', 'current_status': 'closed', 'notes': ''}, {'market_type': 'Forex', 'region': 'Global', 'primary_exchanges': 'Global', 'local_open': '00:00', 'local_close': '23:59', 'current_status': 'open', 'notes': 'The forex market is open 24 hours a day, EXCEPT between 16:00 EST on Friday and 17:00 EST on Sunday'}, {'market_type': 'Cryptocurrency', 'region': 'Global', 'primary_exchanges': 'Global', 'local_open': '00:00', 'local_close': '23:59', 'current_status': 'open', 'notes': 'The cryptocurrency market is open 24 hours a day'}]}
Columns containing time: ['local_open', 'local_close']
None None None None None
0    2026-04-21 09:30:00
1    2026-04-21 09:30:00
2    2026-04-21 08:00:00
3    2026-04-21 08:00:00
4    2026-04-21 09:00:00
5    2026-04-21 09:00:00
6    2026-04-21 08:00:00
7    2026-04-21 09:00:00
8    2026-04-21 09:15:00
9    2026-04-21 09:30:00
10   2026-04-21 09:30:00
11   2026-04-21 10:00:00
12   2026-04-21 08:30:00
13   2026-04-21 09:00:00
14   2026-04-21 00:00:00
15   2026-04-21 00:00:00
Name: local_open, dtype: datetime64[us]
now we in: NASDAQ, NYSE, AMEX, BATS
SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view
                        where financial_market_code='NASDAQ, NYSE, AMEX, BATS' or
                        financial_market_name='NASDAQ, NYSE, AMEX, BATS' or
                        financial_market_alphavantage_name='NASDAQ, NYSE, AMEX, BATS';
[]
No market data found for: NASDAQ, NYSE, AMEX, BATS
now we in: Toronto, Toronto Ventures
SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view
                        where financial_market_code='Toronto, Toronto Ventures' or
                        financial_market_name='Toronto, Toronto Ventures' or
                        financial_market_alphavantage_name='Toronto, Toronto Ventures';
[]
No market data found for: Toronto, Toronto Ventures
now we in: London
SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view
                        where financial_market_code='London' or
                        financial_market_name='London' or
                        financial_market_alphavantage_name='London';
[[13, None, 'London Stock Exchange', 38]]
PK: 13
SELECT "timezone_region_city_name" 
                        from "dyGEO".timezone_region_city_list
                        where "timezone_region_city_PK"='38';
['Europe/London']
now to convert the timezone
LocaL OPEN time: 2026-04-21 08:00:00 Market name: London
Got local time:  2026-04-21 08:00:00
Zone:  Europe/London Converted to UTC:  2026-04-21 07:00:00
UTC time: 2026-04-21 07:00:00 Market name: London
LocaL OPEN time: 2026-04-21 07:00:00 Market name: London
Got local time:  2026-04-21 16:30:00
Zone:  Europe/London Converted to UTC:  2026-04-21 15:30:00
UTC time: 2026-04-21 07:00:00 Market name: London
now we in: XETRA, Berlin, Frankfurt, Munich, Stuttgart
SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view
                        where financial_market_code='XETRA, Berlin, Frankfurt, Munich, Stuttgart' or
                        financial_market_name='XETRA, Berlin, Frankfurt, Munich, Stuttgart' or
                        financial_market_alphavantage_name='XETRA, Berlin, Frankfurt, Munich, Stuttgart';
[]
No market data found for: XETRA, Berlin, Frankfurt, Munich, Stuttgart
now we in: Paris
SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view
                        where financial_market_code='Paris' or
                        financial_market_name='Paris' or
                        financial_market_alphavantage_name='Paris';
[[24, None, 'NYSE Euronext Paris', 117], [37, 37, 'Paris Stock Market - Euronext', 117]]
PK: 24
SELECT "timezone_region_city_name" 
                        from "dyGEO".timezone_region_city_list
                        where "timezone_region_city_PK"='117';
['Europe/Paris']
now to convert the timezone
LocaL OPEN time: 2026-04-21 09:00:00 Market name: Paris
Got local time:  2026-04-21 09:00:00
Zone:  Europe/Paris Converted to UTC:  2026-04-21 07:00:00
UTC time: 2026-04-21 07:00:00 Market name: Paris
LocaL OPEN time: 2026-04-21 07:00:00 Market name: Paris
Got local time:  2026-04-21 17:30:00
Zone:  Europe/Paris Converted to UTC:  2026-04-21 15:30:00
UTC time: 2026-04-21 07:00:00 Market name: Paris
now we in: Barcelona, Madrid
SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view
                        where financial_market_code='Barcelona, Madrid' or
                        financial_market_name='Barcelona, Madrid' or
                        financial_market_alphavantage_name='Barcelona, Madrid';
[]
No market data found for: Barcelona, Madrid
now we in: Lisbon
SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view
                        where financial_market_code='Lisbon' or
                        financial_market_name='Lisbon' or
                        financial_market_alphavantage_name='Lisbon';
[[23, None, 'NYSE Euronext Lisbon', 116], [48, None, 'Euronext Lisbon Stock Exchange', 116]]
PK: 23
SELECT "timezone_region_city_name" 
                        from "dyGEO".timezone_region_city_list
                        where "timezone_region_city_PK"='116';
['Europe/Lisbon']
now to convert the timezone
LocaL OPEN time: 2026-04-21 08:00:00 Market name: Lisbon
Got local time:  2026-04-21 08:00:00
Zone:  Europe/Lisbon Converted to UTC:  2026-04-21 07:00:00
UTC time: 2026-04-21 07:00:00 Market name: Lisbon
LocaL OPEN time: 2026-04-21 07:00:00 Market name: Lisbon
Got local time:  2026-04-21 16:30:00
Zone:  Europe/Lisbon Converted to UTC:  2026-04-21 15:30:00
UTC time: 2026-04-21 07:00:00 Market name: Lisbon
now we in: Tokyo
SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view
                        where financial_market_code='Tokyo' or
                        financial_market_name='Tokyo' or
                        financial_market_alphavantage_name='Tokyo';
[[30, None, 'Tokyo Stock Exchange', 89]]
PK: 30
SELECT "timezone_region_city_name" 
                        from "dyGEO".timezone_region_city_list
                        where "timezone_region_city_PK"='89';
['Asia/Tokyo']
now to convert the timezone
LocaL OPEN time: 2026-04-21 09:00:00 Market name: Tokyo
Got local time:  2026-04-21 09:00:00
Zone:  Asia/Tokyo Converted to UTC:  2026-04-21 00:00:00
UTC time: 2026-04-21 00:00:00 Market name: Tokyo
LocaL OPEN time: 2026-04-21 00:00:00 Market name: Tokyo
Got local time:  2026-04-21 15:00:00
Zone:  Asia/Tokyo Converted to UTC:  2026-04-21 06:00:00
UTC time: 2026-04-21 00:00:00 Market name: Tokyo
now we in: NSE, BSE
SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view
                        where financial_market_code='NSE, BSE' or
                        financial_market_name='NSE, BSE' or
                        financial_market_alphavantage_name='NSE, BSE';
[]
No market data found for: NSE, BSE
now we in: Shanghai, Shenzhen
SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view
                        where financial_market_code='Shanghai, Shenzhen' or
                        financial_market_name='Shanghai, Shenzhen' or
                        financial_market_alphavantage_name='Shanghai, Shenzhen';
[]
No market data found for: Shanghai, Shenzhen
now we in: Hong Kong
SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view
                        where financial_market_code='Hong Kong' or
                        financial_market_name='Hong Kong' or
                        financial_market_alphavantage_name='Hong Kong';
[[10, None, 'Hong Kong Exchanges', 110]]
PK: 10
SELECT "timezone_region_city_name" 
                        from "dyGEO".timezone_region_city_list
                        where "timezone_region_city_PK"='110';
['Asia/Hong_Kong']
now to convert the timezone
LocaL OPEN time: 2026-04-21 09:30:00 Market name: Hong Kong
Got local time:  2026-04-21 09:30:00
Zone:  Asia/Hong_Kong Converted to UTC:  2026-04-21 01:30:00
UTC time: 2026-04-21 01:30:00 Market name: Hong Kong
LocaL OPEN time: 2026-04-21 01:30:00 Market name: Hong Kong
Got local time:  2026-04-21 16:00:00
Zone:  Asia/Hong_Kong Converted to UTC:  2026-04-21 08:00:00
UTC time: 2026-04-21 01:30:00 Market name: Hong Kong
now we in: Sao Paolo
SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view
                        where financial_market_code='Sao Paolo' or
                        financial_market_name='Sao Paolo' or
                        financial_market_alphavantage_name='Sao Paolo';
[[51, None, 'São Paulo Stock Exchange', 12]]
PK: 51
SELECT "timezone_region_city_name" 
                        from "dyGEO".timezone_region_city_list
                        where "timezone_region_city_PK"='12';
['America/Sao_Paulo']
now to convert the timezone
LocaL OPEN time: 2026-04-21 10:00:00 Market name: Sao Paolo
Got local time:  2026-04-21 10:00:00
Zone:  America/Sao_Paulo Converted to UTC:  2026-04-21 13:00:00
UTC time: 2026-04-21 13:00:00 Market name: Sao Paolo
LocaL OPEN time: 2026-04-21 13:00:00 Market name: Sao Paolo
Got local time:  2026-04-21 17:30:00
Zone:  America/Sao_Paulo Converted to UTC:  2026-04-21 20:30:00
UTC time: 2026-04-21 13:00:00 Market name: Sao Paolo
now we in: Mexico
SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view
                        where financial_market_code='Mexico' or
                        financial_market_name='Mexico' or
                        financial_market_alphavantage_name='Mexico';
[[52, None, 'Mexican Stock Exchange', 21]]
PK: 52
SELECT "timezone_region_city_name" 
                        from "dyGEO".timezone_region_city_list
                        where "timezone_region_city_PK"='21';
['America/Mexico_City']
now to convert the timezone
LocaL OPEN time: 2026-04-21 08:30:00 Market name: Mexico
Got local time:  2026-04-21 08:30:00
Zone:  America/Mexico_City Converted to UTC:  2026-04-21 14:30:00
UTC time: 2026-04-21 14:30:00 Market name: Mexico
LocaL OPEN time: 2026-04-21 14:30:00 Market name: Mexico
Got local time:  2026-04-21 15:00:00
Zone:  America/Mexico_City Converted to UTC:  2026-04-21 21:00:00
UTC time: 2026-04-21 14:30:00 Market name: Mexico
now we in: Johannesburg
SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view
                        where financial_market_code='Johannesburg' or
                        financial_market_name='Johannesburg' or
                        financial_market_alphavantage_name='Johannesburg';
[[53, None, 'Johannesburg Stock Exchange', 112]]
PK: 53
SELECT "timezone_region_city_name" 
                        from "dyGEO".timezone_region_city_list
                        where "timezone_region_city_PK"='112';
['Africa/Johannesburg']
now to convert the timezone
LocaL OPEN time: 2026-04-21 09:00:00 Market name: Johannesburg
Got local time:  2026-04-21 09:00:00
Zone:  Africa/Johannesburg Converted to UTC:  2026-04-21 07:00:00
UTC time: 2026-04-21 07:00:00 Market name: Johannesburg
LocaL OPEN time: 2026-04-21 07:00:00 Market name: Johannesburg
Got local time:  2026-04-21 17:00:00
Zone:  Africa/Johannesburg Converted to UTC:  2026-04-21 15:00:00
UTC time: 2026-04-21 07:00:00 Market name: Johannesburg
now we in: Global
SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view
                        where financial_market_code='Global' or
                        financial_market_name='Global' or
                        financial_market_alphavantage_name='Global';
[[35, None, 'Foreign Exchange', None]]
PK: 35
Using UTC for Global (no timezone)
now we in: Global
SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view
                        where financial_market_code='Global' or
                        financial_market_name='Global' or
                        financial_market_alphavantage_name='Global';
[[35, None, 'Foreign Exchange', None]]
PK: 35
Using UTC for Global (no timezone)
       market_type          region  ... financial_market_ID financial_market_timezone_region_city_PK
0           Equity   United States  ...                None                                     None
1           Equity          Canada  ...                None                                     None
2           Equity  United Kingdom  ...                None                                       38
3           Equity         Germany  ...                None                                     None
4           Equity          France  ...                None                                      117
5           Equity           Spain  ...                None                                     None
6           Equity        Portugal  ...                None                                      116
7           Equity           Japan  ...                None                                       89
8           Equity           India  ...                None                                     None
9           Equity  Mainland China  ...                None                                     None
10          Equity       Hong Kong  ...                None                                      110
11          Equity          Brazil  ...                None                                       12
12          Equity          Mexico  ...                None                                       21
13          Equity    South Africa  ...                None                                      112
14           Forex          Global  ...                None                                     None
15  Cryptocurrency          Global  ...                None                                     None

[16 rows x 10 columns]
Missing market List: ['NASDAQ, NYSE, AMEX, BATS', 'Toronto, Toronto Ventures', 'XETRA, Berlin, Frankfurt, Munich, Stuttgart', 'Barcelona, Madrid', 'NSE, BSE', 'Shanghai, Shenzhen']
       market_type          region  ... financial_market_ID financial_market_timezone_region_city_PK
0           Equity   United States  ...                None                                     None
1           Equity          Canada  ...                None                                     None
2           Equity  United Kingdom  ...                None                                       38
3           Equity         Germany  ...                None                                     None
4           Equity          France  ...                None                                      117
5           Equity           Spain  ...                None                                     None
6           Equity        Portugal  ...                None                                      116
7           Equity           Japan  ...                None                                       89
8           Equity           India  ...                None                                     None
9           Equity  Mainland China  ...                None                                     None
10          Equity       Hong Kong  ...                None                                      110
11          Equity          Brazil  ...                None                                       12
12          Equity          Mexico  ...                None                                       21
13          Equity    South Africa  ...                None                                      112
14           Forex          Global  ...                None                                     None
15  Cryptocurrency          Global  ...                None                                     None

[16 rows x 10 columns]
database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com 5432 dyDATA_new postgres Proc2023awsrdspostgresql
database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com 5432 dyDATA_new postgres Proc2023awsrdspostgresql

=== CALCULATED SESSIONS (1=Pre, 2=Regular, 3=Post, 4=Overnight) ===
Skipping NASDAQ, NYSE, AMEX, BATS - No PK
Skipping Toronto, Toronto Ventures - No PK
 SESSION 1 PRE  - London PK=13: 05:30→07:00 UTC
 SESSION 2 REGULAR - London (PK=13): 07:00 → 15:30 UTC
INSERT INTO "dyTRADE".financial_market_session_time_log ("financial_market_session_time_ID","financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status")
                    VALUES (13,13,2,'2026-04-21','2026-04-21 07:00:00','2026-04-21 15:30:00',
                    '',0)
 SESSION 3 POST - London PK=13: 15:30→16:30 UTC
 SESSION 4 OVERNIGHT - London PK=13: 16:30→05:30 UTC
Skipping XETRA, Berlin, Frankfurt, Munich, Stuttgart - No PK
 SESSION 1 PRE  - Paris PK=24: 05:30→07:00 UTC
 SESSION 2 REGULAR - Paris (PK=24): 07:00 → 15:30 UTC
INSERT INTO "dyTRADE".financial_market_session_time_log ("financial_market_session_time_ID","financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status")
                    VALUES (24,24,2,'2026-04-21','2026-04-21 07:00:00','2026-04-21 15:30:00',
                    '',0)
 SESSION 3 POST - Paris PK=24: 15:30→16:30 UTC
 SESSION 4 OVERNIGHT - Paris PK=24: 16:30→05:30 UTC
Skipping Barcelona, Madrid - No PK
 SESSION 1 PRE  - Lisbon PK=23: 05:30→07:00 UTC
 SESSION 2 REGULAR - Lisbon (PK=23): 07:00 → 15:30 UTC
INSERT INTO "dyTRADE".financial_market_session_time_log ("financial_market_session_time_ID","financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status")
                    VALUES (23,23,2,'2026-04-21','2026-04-21 07:00:00','2026-04-21 15:30:00',
                    '',0)
 SESSION 3 POST - Lisbon PK=23: 15:30→16:30 UTC
 SESSION 4 OVERNIGHT - Lisbon PK=23: 16:30→05:30 UTC
 SESSION 1 PRE  - Tokyo PK=30: 22:30→00:00 UTC
 SESSION 2 REGULAR - Tokyo (PK=30): 00:00 → 06:00 UTC
INSERT INTO "dyTRADE".financial_market_session_time_log ("financial_market_session_time_ID","financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status")
                    VALUES (30,30,2,'2026-04-21','2026-04-21 00:00:00','2026-04-21 06:00:00',
                    'Noon trading break from 11:30 to 12:30 local time',1)
 SESSION 3 POST - Tokyo PK=30: 06:00→07:00 UTC
 SESSION 4 OVERNIGHT - Tokyo PK=30: 07:00→22:30 UTC
Skipping NSE, BSE - No PK
Skipping Shanghai, Shenzhen - No PK
 SESSION 1 PRE  - Hong Kong PK=10: 00:00→01:30 UTC
 SESSION 2 REGULAR - Hong Kong (PK=10): 01:30 → 08:00 UTC
INSERT INTO "dyTRADE".financial_market_session_time_log ("financial_market_session_time_ID","financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status")
                    VALUES (10,10,2,'2026-04-21','2026-04-21 01:30:00','2026-04-21 08:00:00',
                    'Noon trading break from 12:00 to 13:00 local time',1)
 SESSION 3 POST - Hong Kong PK=10: 08:00→09:00 UTC
 SESSION 4 OVERNIGHT - Hong Kong PK=10: 09:00→00:00 UTC
 SESSION 1 PRE  - Sao Paolo PK=51: 11:30→13:00 UTC
 SESSION 2 REGULAR - Sao Paolo (PK=51): 13:00 → 20:30 UTC
INSERT INTO "dyTRADE".financial_market_session_time_log ("financial_market_session_time_ID","financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status")
                    VALUES (51,51,2,'2026-04-21','2026-04-21 13:00:00','2026-04-21 20:30:00',
                    '',0)
 SESSION 3 POST - Sao Paolo PK=51: 20:30→21:30 UTC
 SESSION 4 OVERNIGHT - Sao Paolo PK=51: 21:30→11:30 UTC
 SESSION 1 PRE  - Mexico PK=52: 13:00→14:30 UTC
 SESSION 2 REGULAR - Mexico (PK=52): 14:30 → 21:00 UTC
INSERT INTO "dyTRADE".financial_market_session_time_log ("financial_market_session_time_ID","financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status")
                    VALUES (52,52,2,'2026-04-21','2026-04-21 14:30:00','2026-04-21 21:00:00',
                    '',0)
 SESSION 3 POST - Mexico PK=52: 21:00→22:00 UTC
 SESSION 4 OVERNIGHT - Mexico PK=52: 22:00→13:00 UTC
 SESSION 1 PRE  - Johannesburg PK=53: 05:30→07:00 UTC
 SESSION 2 REGULAR - Johannesburg (PK=53): 07:00 → 15:00 UTC
INSERT INTO "dyTRADE".financial_market_session_time_log ("financial_market_session_time_ID","financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status")
                    VALUES (53,53,2,'2026-04-21','2026-04-21 07:00:00','2026-04-21 15:00:00',
                    '',0)
 SESSION 3 POST - Johannesburg PK=53: 15:00→16:00 UTC
 SESSION 4 OVERNIGHT - Johannesburg PK=53: 16:00→05:30 UTC
 SESSION 1 PRE  - Global PK=35: 22:30→00:00 UTC
 SESSION 2 REGULAR - Global (PK=35): 00:00 → 23:59 UTC
INSERT INTO "dyTRADE".financial_market_session_time_log ("financial_market_session_time_ID","financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status")
                    VALUES (35,35,2,'2026-04-21','2026-04-21 00:00:00','2026-04-21 23:59:00',
                    'UTC (no timezone in DB)',1)
 SESSION 3 POST - Global PK=35: 23:59→00:59 UTC
 SESSION 4 OVERNIGHT - Global PK=35: 00:59→22:30 UTC
 SESSION 1 PRE  - Global PK=35: 22:30→00:00 UTC
 SESSION 2 REGULAR - Global (PK=35): 00:00 → 23:59 UTC
INSERT INTO "dyTRADE".financial_market_session_time_log ("financial_market_session_time_ID","financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status")
                    VALUES (35,35,2,'2026-04-21','2026-04-21 00:00:00','2026-04-21 23:59:00',
                    'UTC (no timezone in DB)',1)
 SESSION 3 POST - Global PK=35: 23:59→00:59 UTC
 SESSION 4 OVERNIGHT - Global PK=35: 00:59→22:30 UTC
 ALL 4 SESSIONS (Pre/Regular/Post/Overnight) inserted for all valid markets!
APICalls failed (HTTPSConnectionPool(host='api.apicalls.io', port=443): Max retries exceeded with url: /v2/markets/market-info (Caused by NameResolutionError("HTTPSConnection(host='api.apicalls.io', port=443): Failed to resolve 'api.apicalls.io' ([Errno 11001] getaddrinfo failed)"))), using fallback
None None None None None
Printing cleaned df 0 country marketIndicator uiMarketIndicator          marketCountDown  ... nextTradeDate isBusinessDay   mrktStatus     mrktCountDown
1    U.S.     After Hours       After Hours  Market Opens in 10H 21M  ...  Apr 22, 2026          True  After-Hours  Opens in 10H 21M      
0      US             NaN               NaN                      NaN  ...           NaN           NaN          NaN               NaN      

[2 rows x 15 columns]
Fallback US market data processed, returning
None None None None None
Error:  'notes'
(.venv) PS C:\Users\ehaba\OneDrive\scraper> 































def resolve_FMU(_,info,dum):
    try:
        #Importing l;ibraries
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

        from datetime import datetime, timezone

        import dotenv
        from dotenv import load_dotenv
        import os

        import warnings
        warnings.filterwarnings("ignore")

        #Delete any previous day
        cwd = os.getcwd()
        file_path = os.path.join(cwd, "Credentials.env")
        load_dotenv(file_path)
        hostname, port_id, database, username, password = (
            os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
        )
        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
        database = 'dyDATA_new' 
        username = 'postgres'
        password = 'Proc2023awsrdspostgresql'
        port_id = 5432
        this_day = str(date.today())
        with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                print("Deleting today's already registered data")
                cur.execute(f'''DELETE FROM "dyTRADE".financial_market_session_time_log WHERE financial_market_session_time_log_utc_date = '{this_day}' ''')

        def get_data():
            # replace the "demo" apikey below with your own key from https://www.alphavantage.co/support/#api-key
            url = 'https://www.alphavantage.co/query?function=MARKET_STATUS&apikey=2M4KMLTI2FDMB6WB'
            r = requests.get(url)
            data = r.json()
            print(data)

            dataframe = pd.DataFrame.from_dict(data)
            market_values = dataframe[['markets']].values


            #Creating thye dataframe
            cleaned_df = pd.DataFrame()
            temp_df = pd.DataFrame()
            for i in range(0,len(market_values),1):
                temp_df = pd.DataFrame(market_values[i][0], index=[i])
                if i == 0:
                    cleaned_df = temp_df
                else:
                    cleaned_df = pd.concat([cleaned_df,temp_df])
            

            return cleaned_df


        dataframe = get_data()
        cleaned_df = dataframe.copy()

        time_cols = list(cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'local')])
        print("Columns containing time:", time_cols)

        cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(lambda x: x.strip())

        def correct_date_time(cleaned_df):
            #Get region data from table
            cwd = os.getcwd()
            file_path = os.path.join(cwd, "Credentials.env")
            load_dotenv(file_path)
            hostname, port_id, database, username, password = (
                os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
            )
            print(hostname, port_id, database, username, password)

            hostname ="database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com" 
            database="dyDATA_new" 
            username='postgres'
            password='Proc2023awsrdspostgresql'
            port_id=5432

            ###################
            # Changing the time only values into datetime
            #this part need to be fixed!!! The fix is not to uncomment the format line, it is just there was future purposes.
            # Parse times with today's date to avoid future year
            today = date.today()
            cleaned_df['local_open'] = pd.to_datetime(cleaned_df['local_open'].apply(lambda x: f"{today} {x}"))
            cleaned_df['local_close'] = pd.to_datetime(cleaned_df['local_close'].apply(lambda x: f"{today} {x}"))
            print(cleaned_df['local_open'])
            # 2. Separate stock markets (FIXING THE SEQUENCE ERROR)
                # Logic to handle lists if already partially processed
            cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(
                lambda x: [item[1:-1] for sublist in x for item in sublist] if isinstance(x, list) else x
            )

                # CRITICAL FIX: Force column to object type so it can hold the list temporarily
            cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].astype(object)   
            for i in range(len(cleaned_df)):
             if cleaned_df['primary_exchanges'][i].find(',') == 0:
                cleaned_df['primary_exchanges'][i] = cleaned_df['primary_exchanges'][i].split(',')
            cleaned_df = cleaned_df.explode(column = 'primary_exchanges', ignore_index=True)
            # Removing whitespaces from starting and ending of the cells
            cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(lambda x: x.strip())

            # FIILING TIME RELATRED COLUMNS IN A LIST
            time_cols = list(cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'local')])

            cleaned_df['financial_market_PK'] = None
            cleaned_df['financial_market_ID'] = None
            cleaned_df['financial_market_timezone_region_city_PK'] = None
            missing_market_list = []
            for i in range(len(cleaned_df)):
                #Adding neccessary columns to the dataframe like PK and ID
                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        market = cleaned_df['primary_exchanges'][i]
                        print(f"now we in: {market}")
                        financial_market_PK= '''"financial_market_PK"'''
                        financial_market_ID= '''"financial_market_ID"'''
                        financial_market_name= '''"financial_market_name"'''
                        financial_market_timezone_region_city_PK = '''"financial_market_timezone_region_city_PK"'''

                        ################################################
                        query=f'''SELECT {financial_market_PK},{financial_market_ID},{financial_market_name},{financial_market_timezone_region_city_PK} 
                        from "dyLEARN".financial_market_list_view 
                        where financial_market_code='{market}' or 
                        financial_market_name='{market}' or 
                        financial_market_alphavantage_name='{market}'; '''
                        print(query)
                        cur.execute(query)
                        result = cur.fetchall()
                        print(result)
                        
                        if not result:
                            print(f"No market data found for: {market}")
                            cleaned_df.loc[i, 'financial_market_PK'] = None
                            cleaned_df.loc[i, 'financial_market_ID'] = None
                            cleaned_df.loc[i, 'financial_market_timezone_region_city_PK'] = None
                            missing_market_list.append(market)
                            if pd.isna(cleaned_df.loc[i, 'notes']):
                                cleaned_df.loc[i, 'notes'] = "Error: Market not found in database"
                            continue
                        
                        # Use first result row
                        row = result[0]
                        PK = row[0]
                        ID = row[1]
                        timezone_region_city_PK = row[3]
                        print(f"PK: {PK}")
                    

                        cleaned_df.loc[i, 'financial_market_PK'] = PK
                        cleaned_df.loc[i, 'financial_market_ID'] = ID
                        cleaned_df.loc[i, 'financial_market_timezone_region_city_PK'] = timezone_region_city_PK
                        
                        if timezone_region_city_PK is None:
                            print(f"Using UTC for {market} (no timezone)")
                            zone = "UTC"
                            cleaned_df.loc[i, 'notes'] = "UTC (no timezone in DB)"
                            continue  # Skip timezone lookup

                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        country_timezone_region_city_name = '''"timezone_region_city_name"'''
                        country_timezone_region_city_PK = '''"timezone_region_city_PK"'''
                        query=f'''SELECT {country_timezone_region_city_name} 
                        from "dyGEO".timezone_region_city_list
                        where {country_timezone_region_city_PK}='{timezone_region_city_PK}'; '''
                        print(query)
                        cur.execute(query)
                        result = cur.fetchall()
                        if not result:
                            print(f"No timezone data for PK: {timezone_region_city_PK}")
                            cleaned_df.loc[i, 'notes'] = "Error: No timezone data"
                            continue
                        print(result[0])
                        country_zone = str(result[0][0])
                        zone = country_zone


                
                
                print("now to convert the timezone")
                # Time correction to UTC
                for col in time_cols:
                    print("LocaL OPEN time:", cleaned_df['local_open'][i], "Market name:", cleaned_df['primary_exchanges'][i])
                    local  = str(cleaned_df[col][i])
                    print ("Got local time: ", local)
                    # Get timezone we're trying to convert from
                    local_tz = ZoneInfo(zone)
                    # UTC timezone
                    utc_tz = ZoneInfo("UTC")

                    #print((local_open))

                    dt = datetime.strptime(local,"%Y-%m-%d %H:%M:%S")
                    dt = dt.replace(tzinfo=local_tz)
                    dt_open_utc = dt.astimezone(utc_tz)
                    dt_open_utc = pd.Timestamp(dt_open_utc).tz_localize(None)
                    cleaned_df.loc[i, col] = dt_open_utc
                    print("Zone: ", zone, "Converted to UTC: ", cleaned_df.loc[i, col])
                    print("UTC time:", cleaned_df.loc[i, 'local_open'], "Market name:", cleaned_df.loc[i, 'primary_exchanges'])

                # #Removing timezones
            # Remove timezone info for entire column (inside loop now handled)
            cleaned_df['local_open'] = pd.to_datetime(cleaned_df['local_open']).dt.tz_localize(None)
            cleaned_df['local_close'] = pd.to_datetime(cleaned_df['local_close']).dt.tz_localize(None)

            print(cleaned_df)

            print("Missing market List:", missing_market_list)

            return (cleaned_df) 
        
        time_adjusted_dataframe = correct_date_time(cleaned_df)

        this_day = str(date.today())

        for i in range(len(time_adjusted_dataframe)):
            if time_adjusted_dataframe['notes'][i] == "":
                time_adjusted_dataframe['notes'][i] = "-"

        print(time_adjusted_dataframe)

        # "financial_market_opening_status_UUID"

        table_name = '''"dyTRADE".financial_market_session_time_log'''

        #Commenting for time till market_PK not ready time_adjusted_dataframe['financial_market_PK'][i],

        cwd = os.getcwd()
        file_path = os.path.join(cwd, "Credentials.env")
        cwd = os.getcwd()
        file_path = os.path.join(cwd, "Credentials.env")
        load_dotenv(file_path)
        hostname, port_id, database, username, password = (
            os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
        )
        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
        database = 'dyDATA_new' 
        username = 'postgres'
        password = 'Proc2023awsrdspostgresql'
        port_id = 5432
        print(hostname, port_id, database, username, password)
        print(hostname, port_id, database, username, password)
        print("\n=== CALCULATED SESSIONS (1=Pre, 2=Regular, 3=Post, 4=Overnight) ===")
        with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                for i in range(len(time_adjusted_dataframe)):
                    if pd.isna(time_adjusted_dataframe.loc[i, 'financial_market_PK']):
                        print(f"Skipping {time_adjusted_dataframe.loc[i, 'primary_exchanges']} - No PK")
                        continue
                    if time_adjusted_dataframe.loc[i, 'region'] == 'United States':
                        continue

                    current_status = time_adjusted_dataframe.loc[i, 'current_status']
                    status_str = "0" if str(current_status) == "closed" else "1"
                    time_adjusted_dataframe.loc[i, 'current_status'] = status_str
                    
                    notes_str = time_adjusted_dataframe.loc[i, 'notes'] or " "
                    ################################################
                    id= '''"financial_market_session_time_ID"'''
                    financial_market_PK= '''"financial_market_session_time_financial_market_PK"'''
                    session_time_log_utc_date= '''"financial_market_session_time_log_utc_date"'''
                    opening_UTC_time= '''"financial_market_session_time_opening_UTC_time"'''
                    closure_UTC_time= '''"financial_market_session_time_closure_UTC_time"'''
                    session_time_note= '''"financial_market_session_time_note"'''
                    market_status= '''"financial_market_session_time_activity_status"'''
                    market_session_PK =  '''"financial_market_session_time_market_session_PK"'''
                    
                    query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{session_time_note},{market_status})
                    VALUES ({time_adjusted_dataframe['financial_market_PK'][i]},{time_adjusted_dataframe['financial_market_PK'][i]},2,'{this_day}','{time_adjusted_dataframe['local_open'][i]}','{time_adjusted_dataframe['local_close'][i]}',
                    '{time_adjusted_dataframe['notes'][i]}',{time_adjusted_dataframe['current_status'][i]})'''
                    market_name = time_adjusted_dataframe.loc[i, 'primary_exchanges']
                    market_pk = time_adjusted_dataframe.loc[i, 'financial_market_PK']
                    
                    # Session 1: Pre-market (1.5h before)
                    pre_open = time_adjusted_dataframe.loc[i, 'local_open'] - pd.Timedelta(hours=1.5)
                    pre_close = time_adjusted_dataframe.loc[i, 'local_open']
                    print(f" SESSION 1 PRE  - {market_name} PK={market_pk}: {pre_open.strftime('%H:%M')}→{pre_close.strftime('%H:%M')} UTC")
                    cur.execute(f'''INSERT INTO {table_name} ("financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status") VALUES ({market_pk},1,'{this_day}','{pre_open}','{pre_close}','Pre {market_name}',{status_str})''')

                    # Session 2: Regular
                    print(f" SESSION 2 REGULAR - {market_name} (PK={market_pk}): {time_adjusted_dataframe.loc[i, 'local_open'].strftime('%H:%M')} → {time_adjusted_dataframe.loc[i, 'local_close'].strftime('%H:%M')} UTC")
                    print(query)
                    cur.execute(query)

                    # Session 3: Post-market (1h after)
                    post_open = time_adjusted_dataframe.loc[i, 'local_close']
                    post_close = time_adjusted_dataframe.loc[i, 'local_close'] + pd.Timedelta(hours=1)
                    print(f" SESSION 3 POST - {market_name} PK={market_pk}: {post_open.strftime('%H:%M')}→{post_close.strftime('%H:%M')} UTC")
                    cur.execute(f'''INSERT INTO {table_name} ("financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status") VALUES ({market_pk},3,'{this_day}','{post_open}','{post_close}','Post {market_name}',{status_str})''')

                    # Session 4: Overnight (to next pre)
                    overnight_open = post_close
                    overnight_close = pre_open + pd.Timedelta(days=1)
                    print(f" SESSION 4 OVERNIGHT - {market_name} PK={market_pk}: {overnight_open.strftime('%H:%M')}→{overnight_close.strftime('%H:%M')} UTC")
                    cur.execute(f'''INSERT INTO {table_name} ("financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status") VALUES ({market_pk},4,'{this_day}','{overnight_open}','{overnight_close}','Overnight {market_name}',{status_str})''')

        print(" ALL 4 SESSIONS (Pre/Regular/Post/Overnight) inserted for all valid markets!")

        def API_failure():
            
            eastern = pytz.timezone('US/Eastern')
            now_eastern = datetime.now(eastern)
            
            preMarketOpeningTime = now_eastern.replace(hour=4,minute=0,second=0,microsecond=0)
            preMarketOpeningTime_str = preMarketOpeningTime.strftime('%b %d, %Y %I:%M %p ET')
            preMarketClosingTime = now_eastern.replace(hour=9,minute=30,second=0,microsecond=0)
            preMarketClosingTime_str = preMarketClosingTime.strftime('%b %d, %Y %I:%M %p ET')
            
            marketOpeningTime = now_eastern.replace(hour=9,minute=30,second=0,microsecond=0)
            marketOpeningTime_str = marketOpeningTime.strftime('%b %d, %Y %I:%M %p ET')
            marketClosingTime = now_eastern.replace(hour=16,minute=0,second=0,microsecond=0)
            marketClosingTime_str = marketClosingTime.strftime('%b %d, %Y %I:%M %p ET')
            
            afterHoursMarketOpeningTime = now_eastern.replace(hour=16,minute=0,second=0,microsecond=0)
            afterHoursMarketOpeningTime_str = afterHoursMarketOpeningTime.strftime('%b %d, %Y %I:%M %p ET')
            afterHoursMarketClosingTime = now_eastern.replace(hour=20,minute=0,second=0,microsecond=0)
            afterHoursMarketClosingTime_str = afterHoursMarketClosingTime.strftime('%b %d, %Y %I:%M %p ET')
            
            if now_eastern < preMarketOpeningTime:
                marketIndicator = 'Market Closed'
                mrktStatus = 'Closed'
                marketCountDown_timestamp = marketOpeningTime - now_eastern
            
                if marketCountDown_timestamp.total_seconds() < 3600:
                    minutes, seconds = divmod(int(marketCountDown_timestamp.total_seconds()), 60)
                    market_countdown = f"Market Opens in {minutes}M {seconds}S"
                    mrktCountDown = f"Opens in {minutes}M {seconds}S"
                else:  # If the remaining time is 1 hour or more
                    hours, remainder = divmod(int(marketCountDown_timestamp.total_seconds()), 3600)
                    minutes, _ = divmod(remainder, 60)
                    market_countdown = f"Market Opens in {hours}H {minutes}M"
                    mrktCountDown = f"Opens in {hours}H {minutes}M"
            
            elif preMarketOpeningTime < now_eastern < preMarketClosingTime:
                marketIndicator = 'Pre Market'
                mrktStatus = 'Pre-Market'
                marketCountDown_timestamp = marketOpeningTime - now_eastern
            
                if marketCountDown_timestamp.total_seconds() < 3600:
                    minutes, seconds = divmod(int(marketCountDown_timestamp.total_seconds()), 60)
                    market_countdown = f"Market Opens in {minutes}M {seconds}S"
                    mrktCountDown = f"Opens in {minutes}M {seconds}S"
                else:  # If the remaining time is 1 hour or more
                    hours, remainder = divmod(int(marketCountDown_timestamp.total_seconds()), 3600)
                    minutes, _ = divmod(remainder, 60)
                    market_countdown = f"Market Opens in {hours}H {minutes}M"
                    mrktCountDown = f"Opens in {hours}H {minutes}M"
            
            elif marketOpeningTime < now_eastern < marketClosingTime:
                marketIndicator = 'Market Open'
                mrktStatus = 'Open'
                marketCountDown_timestamp = marketClosingTime - now_eastern
            
                if marketCountDown_timestamp.total_seconds() < 3600:
                    minutes, seconds = divmod(int(marketCountDown_timestamp.total_seconds()), 60)
                    market_countdown = f"Market Closes in {minutes}M {seconds}S"
                    mrktCountDown = f"Closes in {minutes}M {seconds}S"
                else:  # If the remaining time is 1 hour or more
                    hours, remainder = divmod(int(marketCountDown_timestamp.total_seconds()), 3600)
                    minutes, _ = divmod(remainder, 60)
                    market_countdown = f"Market Closes in {hours}H {minutes}M"
                    mrktCountDown = f"Closes in {hours}H {minutes}M"
            
            elif afterHoursMarketOpeningTime < now_eastern :
                marketIndicator = 'After Hours'
                mrktStatus = 'After-Hours'
                next_marketOpeningTime = marketOpeningTime + timedelta(days=1)
                marketCountDown_timestamp = next_marketOpeningTime - now_eastern
            
                if marketCountDown_timestamp.total_seconds() < 3600:
                    minutes, seconds = divmod(int(marketCountDown_timestamp.total_seconds()), 60)
                    market_countdown = f"Market Opens in {minutes}M {seconds}S"
                    mrktCountDown = f"Opens in {minutes}M {seconds}S"
                else:  # If the remaining time is 1 hour or more
                    hours, remainder = divmod(int(marketCountDown_timestamp.total_seconds()), 3600)
                    minutes, _ = divmod(remainder, 60)
                    market_countdown = f"Market Opens in {hours}H {minutes}M"
                    mrktCountDown = f"Opens in {hours}H {minutes}M"
            
            today = datetime.today()
            day_number = today.weekday()
            
            if day_number == 0:
                isBusinessDay = True
                today_date = today.date()
                previousTradeDate = today_date - timedelta(days=3)
                nextTradeDate = today_date + timedelta(days=1)
                previousTradeDate_str = previousTradeDate.strftime('%b %d, %Y')
                nextTradeDate_str = nextTradeDate.strftime('%b %d, %Y')

            elif day_number == 5:
                isBusinessDay = False
                today_date = today.date()
                previousTradeDate = today_date - timedelta(days=1)
                nextTradeDate = today_date + timedelta(days=2)
                previousTradeDate_str = previousTradeDate.strftime('%b %d, %Y')
                nextTradeDate_str = nextTradeDate.strftime('%b %d, %Y')

            elif day_number == 6:
                isBusinessDay = False
                today_date = today.date()
                previousTradeDate = today_date - timedelta(days=2)
                nextTradeDate = today_date + timedelta(days=1)
                previousTradeDate_str = previousTradeDate.strftime('%b %d, %Y')
                nextTradeDate_str = nextTradeDate.strftime('%b %d, %Y')

            else:
                isBusinessDay = True
                today_date = today.date()
                previousTradeDate = today_date - timedelta(days=1)
                nextTradeDate = today_date + timedelta(days=1)
                previousTradeDate_str = previousTradeDate.strftime('%b %d, %Y')
                nextTradeDate_str = nextTradeDate.strftime('%b %d, %Y')

            expected_response = {'country': 'U.S.', 'marketIndicator': marketIndicator, 'uiMarketIndicator': marketIndicator, 'marketCountDown': market_countdown, 'preMarketOpeningTime': preMarketOpeningTime_str, 'preMarketClosingTime': preMarketClosingTime_str, 'marketOpeningTime': marketOpeningTime_str,
            'marketClosingTime': marketClosingTime_str, 'afterHoursMarketOpeningTime': afterHoursMarketOpeningTime_str, 'afterHoursMarketClosingTime': afterHoursMarketClosingTime_str, 'previousTradeDate': previousTradeDate_str, 'nextTradeDate': nextTradeDate_str, 'isBusinessDay': isBusinessDay,
            'mrktStatus': mrktStatus, 'mrktCountDown': mrktCountDown}

            return expected_response

        ###########################################################
        # apicalls.io fetched dataframe is processed from here on.
        ###########################################################

        def apicalls_get_data():
            global data
            try:
                url = 'https://api.apicalls.io/v2/markets/market-info'
                headers = {
                'Authorization': 'Bearer 539|5d9M5TONvuHKNOVYKwrWKT88fsivCirNPSc9nXXf'
                }

                response = requests.request('GET', url, headers=headers, timeout=10)
                data = response.json()
                print(data)

                if data is None or ('body' not in data):
                    raise ValueError("Invalid API response")
                dict = data['body']
            except Exception as e:
                print(f"APICalls failed ({e}), using fallback")
                dict = API_failure()
            dataframe = pd.DataFrame(list(dict.items()))
            dataframe =  dataframe.transpose()

            return dataframe
        
        dataframe = apicalls_get_data()
        cleaned_df = dataframe.copy()
        
        def apicalls_correct_date_time(cleaned_df):

            # Get region data from table
            cwd = os.getcwd()
            file_path = os.path.join(cwd, "Credentials.env")
            load_dotenv(file_path)
            hostname, port_id, database, username, password = (
                os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
            )
            print(hostname, port_id, database, username, password)

            hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
            database = 'dyDATA_new' 
            username = 'postgres'
            password = 'Proc2023awsrdspostgresql'
            port_id = 5432

            cleaned_df. columns=cleaned_df. iloc[0]
            cleaned_df = (cleaned_df.drop(0))
            cleaned_df.reset_index()
            cleaned_df.loc[0, 'country'] = 'US'


            time_cols = list(cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'Time')])
            date_cols = (list([cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'Date')]]))

            for col in time_cols:
                cleaned_df[col] = pd.to_datetime(cleaned_df[col], format='%Y-%m-%d %H:%M:%S', errors='coerce')
            
            for col in date_cols:
                cleaned_df[col] = cleaned_df[col].apply(lambda x: pd.to_datetime(str(x), format="%b %d, %Y", errors='coerce').strftime("%d.%m.%Y") if pd.notna(pd.to_datetime(str(x), format="%b %d, %Y", errors='coerce')) else x)


            cleaned_df.assign(financial_market_name="")
            cleaned_df.assign(financial_market_PK="")
            print("Printing cleaned df", cleaned_df)
            market_df = pd.DataFrame()
            # Fallback US data - skip detailed processing, return directly
            print("Fallback US market data processed, returning")
            return cleaned_df
                
            try: 
                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                            query=f'''SELECT "PK"
                            from "dyGEO".country_list_view 
                            where alpha_2_code=%s; ''' # Use US
                            cur.execute(query, ('US',))
                            print(query)
                            cur.execute(query)
                            result = cur.fetchall()
                            print("counrty_PK = ", result)
            except:
                    raise Exception('Could not fetch the country PK.')
            finally:
                if conn is not None:
                    conn.close()

            try: 
                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        for pk in result:
                            query=f'''SELECT "timezone_region_city_PK"
                            from "dyGEO".country_timezone_region_city_rel_view 
                            where "country_PK" = {pk[0]}; ''' # The counrty name should be US and not U.S.
                            print(query)
                            cur.execute(query)
                            timezone_region_city_PK_list = cur.fetchall()
                            print("timezone_region_city_PK_list: ", timezone_region_city_PK_list)
            except:
                raise Exception('Could not fetch the timezone region city PK.')
            finally:
                if conn is not None:
                    conn.close()  
            try: 
                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        for tz_PK in range(len(timezone_region_city_PK_list)):
                            query=f''' SELECT "financial_market_PK", financial_market_name
                            from "dyLEARN".financial_market_list 
                            where "financial_market_timezone_region_city_PK" ='{timezone_region_city_PK_list[tz_PK][0]}'; ''' # The counrty name should be US and not U.S.
                            print(query)
                            cur.execute(query)
                            markets = cur.fetchall()
                            num = row
                            for market in markets:
                                financial_market_PK = market[0]
                                financial_market_name = market[1]
                                data_dict = {'financial_market_name': financial_market_name,'financial_market_PK': financial_market_PK,'country':cleaned_df['country'][row], 'marketIndicator':cleaned_df['marketIndicator'][row],
                                            'uiMarketIndicator':cleaned_df['uiMarketIndicator'][row],'marketCountDown':cleaned_df['marketCountDown'][row],
                                            'preMarketOpeningTime':cleaned_df['preMarketOpeningTime'][row], 'preMarketClosingTime':cleaned_df['preMarketClosingTime'][row],
                                            'marketOpeningTime':cleaned_df['marketOpeningTime'][row], 'marketClosingTime':cleaned_df['marketClosingTime'][row],
                                            'afterHoursMarketOpeningTime':cleaned_df['afterHoursMarketOpeningTime'][row], 'afterHoursMarketClosingTime':cleaned_df['afterHoursMarketClosingTime'][row],
                                            'previousTradeDate':cleaned_df['previousTradeDate'][row], 'nextTradeDate':cleaned_df['nextTradeDate'][row],
                                            'isBusinessDay':cleaned_df['isBusinessDay'][row], 'mrktStatus':cleaned_df['mrktStatus'][row], 'mrktCountDown':cleaned_df['mrktCountDown'][row] }
                                temp_df = pd.DataFrame(data_dict, index=[0])
                                num += 1
                                market_df = pd.concat([market_df,temp_df], ignore_index=True)
            except:
                    raise Exception('Could not fetch the market name')
            finally:
                if conn is not None:
                    conn.close()
                
            cleaned_df = pd.concat([cleaned_df, market_df], ignore_index=True)
            print("Concatinated dataframe:", cleaned_df)

            print(market_df)
            return (market_df)
        
        apicalls_time_adjusted_dataframe = apicalls_correct_date_time(cleaned_df)

        from datetime import date
        this_day = str(date.today())

        cwd = os.getcwd()
        file_path = os.path.join(cwd, "Credentials.env")
        load_dotenv(file_path)
        hostname, port_id, database, username, password = (
            os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
        )
        print(hostname, port_id, database, username, password)

        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
        database = 'dyDATA_new' 
        username = 'postgres'
        password = 'Proc2023awsrdspostgresql'
        port_id = 5432

        # "financial_market_opening_status_UUID"

        table_name = '''"dyTRADE".financial_market_session_time_log'''

        #Commenting for time till market_PK not ready apicalls_time_adjusted_dataframe['financial_market_PK'][i],
        ### For the overnight session logic ###
    
        with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                if 'financial_market_PK' not in apicalls_time_adjusted_dataframe.columns:
                    print("Skipping apicalls inserts - no financial_market_PK column")
                else:
                    for i in range(len(apicalls_time_adjusted_dataframe)):
                        if pd.isna(apicalls_time_adjusted_dataframe.loc[i, 'financial_market_PK']):
                            continue
                        if apicalls_time_adjusted_dataframe['mrktStatus'][i] == "Open":
                            apicalls_time_adjusted_dataframe['mrktStatus'][i]=1
                        else:
                            apicalls_time_adjusted_dataframe['mrktStatus'][i]=0
                        if 'notes' not in apicalls_time_adjusted_dataframe.columns:
                            apicalls_time_adjusted_dataframe['notes'] = ' '
                        if apicalls_time_adjusted_dataframe['notes'][i] is None:
                            apicalls_time_adjusted_dataframe['notes'][i] = " "
                        ################################################
                        id= '''"financial_market_session_time_ID"'''
                        financial_market_PK= '''"financial_market_session_time_financial_market_PK"'''
                        session_time_log_utc_date= '''"financial_market_session_time_log_utc_date"'''
                        opening_UTC_time= '''"financial_market_session_time_opening_UTC_time"'''
                        closure_UTC_time= '''"financial_market_session_time_closure_UTC_time"'''
                        session_time_note= '''"financial_market_session_time_note"'''
                        market_status= '''"financial_market_session_time_activity_status"'''
                        market_session_PK =  '''"financial_market_session_time_market_session_PK"'''
                        next_trade_session_date = '''"financial_market_session_next_market_trading_session_date"'''
                        
                        query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                        VALUES (%s,%s,2,'%s','%s','%s',%s,'%s')''', (apicalls_time_adjusted_dataframe['financial_market_PK'][i], apicalls_time_adjusted_dataframe['financial_market_PK'][i], this_day, apicalls_time_adjusted_dataframe['marketOpeningTime'][i], apicalls_time_adjusted_dataframe['marketClosingTime'][i], apicalls_time_adjusted_dataframe['mrktStatus'][i], apicalls_time_adjusted_dataframe['nextTradeDate'][i])
                        print(query)
                        cur.execute(query)
                    
                        # Adding the pre Market data
                        query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                        VALUES (%s,%s,1,'%s','%s','%s',%s, '%s')''', (apicalls_time_adjusted_dataframe['financial_market_PK'][i], apicalls_time_adjusted_dataframe['financial_market_PK'][i], this_day, apicalls_time_adjusted_dataframe['preMarketOpeningTime'][i], apicalls_time_adjusted_dataframe['preMarketClosingTime'][i], apicalls_time_adjusted_dataframe['mrktStatus'][i], apicalls_time_adjusted_dataframe['nextTradeDate'][i])
                        print(query)
                        cur.execute(query)

                        # Adding the values of after Market data
                        query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                        VALUES (%s,%s,3,'%s','%s','%s',%s, '%s')''', (apicalls_time_adjusted_dataframe['financial_market_PK'][i], apicalls_time_adjusted_dataframe['financial_market_PK'][i], this_day, apicalls_time_adjusted_dataframe['afterHoursMarketOpeningTime'][i], apicalls_time_adjusted_dataframe['afterHoursMarketClosingTime'][i], apicalls_time_adjusted_dataframe['mrktStatus'][i], apicalls_time_adjusted_dataframe['nextTradeDate'][i])
                        print(query)
                        cur.execute(query)
                        ##################################################
                        ######## Adding the overnight session data########
                        ##################################################
                        # Add 1 day to tomorrow's pre-market opening time for overnight closure
                        tomorrow_premarket = apicalls_time_adjusted_dataframe['preMarketOpeningTime'][i] + pd.Timedelta(days=1)

                        query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                        VALUES (%s,%s,4,'%s','%s','%s',%s, '%s')''', (apicalls_time_adjusted_dataframe['financial_market_PK'][i], apicalls_time_adjusted_dataframe['financial_market_PK'][i], this_day, apicalls_time_adjusted_dataframe['afterHoursMarketClosingTime'][i], tomorrow_premarket, apicalls_time_adjusted_dataframe['mrktStatus'][i], apicalls_time_adjusted_dataframe['nextTradeDate'][i])
                        print(query)
                        cur.execute(query)

                        # approach two
                        #query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                        #VALUES (%s,%s,4,'%s','%s','%s',%s, '%s')''', (apicalls_time_adjusted_dataframe['financial_market_PK'][i], apicalls_time_adjusted_dataframe['financial_market_PK'][i], this_day, apicalls_time_adjusted_dataframe['afterHoursMarketClosingTime'][i], apicalls_time_adjusted_dataframe['preMarketOpeningTime'][i], apicalls_time_adjusted_dataframe['mrktStatus'][i], apicalls_time_adjusted_dataframe['nextTradeDate'][i])          
                        #print(query)
                        #cur.execute(query)

        response = {
            'success':True,
            'errors':None
        }
        return response
        
        
    except Exception as error:
        print('Error: ', error)
        response = {
            'success':False,
            'errors': error
        }
        return response



if __name__=='__main__':
     resolve_FMU(None, None, None)
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     
     def resolve_FMU(_,info,dum):
    try:
        #Importing l;ibraries
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

        from datetime import datetime, timezone

        import dotenv
        from dotenv import load_dotenv
        import os

        import warnings
        warnings.filterwarnings("ignore")

        #Delete any previous day
        cwd = os.getcwd()
        file_path = os.path.join(cwd, "Credentials.env")
        load_dotenv(file_path)
        hostname, port_id, database, username, password = (
            os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
        )
        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
        database = 'dyDATA_new' 
        username = 'postgres'
        password = 'Proc2023awsrdspostgresql'
        port_id = 5432
        this_day = str(date.today())
        with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                print("Deleting today's already registered data")
                cur.execute(f'''DELETE FROM "dyTRADE".financial_market_session_time_log WHERE financial_market_session_time_log_utc_date = '{this_day}' ''')

        def get_data():
            # replace the "demo" apikey below with your own key from https://www.alphavantage.co/support/#api-key
            url = 'https://www.alphavantage.co/query?function=MARKET_STATUS&apikey=2M4KMLTI2FDMB6WB'
            r = requests.get(url)
            data = r.json()
            print(data)

            dataframe = pd.DataFrame.from_dict(data)
            market_values = dataframe[['markets']].values


            #Creating thye dataframe
            cleaned_df = pd.DataFrame()
            temp_df = pd.DataFrame()
            for i in range(0,len(market_values),1):
                temp_df = pd.DataFrame(market_values[i][0], index=[i])
                if i == 0:
                    cleaned_df = temp_df
                else:
                    cleaned_df = pd.concat([cleaned_df,temp_df])
            

            return cleaned_df


        dataframe = get_data()
        cleaned_df = dataframe.copy()

        time_cols = list(cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'local')])
        print("Columns containing time:", time_cols)

        cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(lambda x: x.strip())

        def correct_date_time(cleaned_df):
            #Get region data from table
            cwd = os.getcwd()
            file_path = os.path.join(cwd, "Credentials.env")
            load_dotenv(file_path)
            hostname, port_id, database, username, password = (
                os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
            )
            print(hostname, port_id, database, username, password)

            hostname ="database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com" 
            database="dyDATA_new" 
            username='postgres'
            password='Proc2023awsrdspostgresql'
            port_id=5432

            ###################
            # Changing the time only values into datetime
            #this part need to be fixed!!! The fix is not to uncomment the format line, it is just there was future purposes.
            # Parse times with today's date to avoid future year
            today_str = date.today().strftime('%Y-%m-%d')
            cleaned_df['local_open'] = pd.to_datetime(cleaned_df['local_open'].apply(lambda x: f"{today_str} {x}"))
            cleaned_df['local_close'] = pd.to_datetime(cleaned_df['local_close'].apply(lambda x: f"{today_str} {x}"))
            print(cleaned_df['local_open'])
            # 2. Separate stock markets (FIXING THE SEQUENCE ERROR)
                # Logic to handle lists if already partially processed
            cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(
                lambda x: [item[1:-1] for sublist in x for item in sublist] if isinstance(x, list) else x
            )

                # CRITICAL FIX: Force column to object type so it can hold the list temporarily
            cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].astype(object)   
            for i in range(len(cleaned_df)):
             if cleaned_df['primary_exchanges'][i].find(',') == 0:
                cleaned_df['primary_exchanges'][i] = cleaned_df['primary_exchanges'][i].split(',')
            cleaned_df = cleaned_df.explode(column = 'primary_exchanges', ignore_index=True)
            # Removing whitespaces from starting and ending of the cells
            cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(lambda x: x.strip())

            # FIILING TIME RELATRED COLUMNS IN A LIST
            time_cols = list(cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'local')])

            cleaned_df['financial_market_PK'] = None
            cleaned_df['financial_market_ID'] = None
            cleaned_df['financial_market_timezone_region_city_PK'] = None
            missing_market_list = []
            for i in range(len(cleaned_df)):
                #Adding neccessary columns to the dataframe like PK and ID
                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        market = cleaned_df['primary_exchanges'][i]
                        print(f"now we in: {market}")
                        financial_market_PK= '''"financial_market_PK"'''
                        financial_market_ID= '''"financial_market_ID"'''
                        financial_market_name= '''"financial_market_name"'''
                        financial_market_timezone_region_city_PK = '''"financial_market_timezone_region_city_PK"'''

                        ################################################
                        query=f'''SELECT {financial_market_PK},{financial_market_ID},{financial_market_name},{financial_market_timezone_region_city_PK} 
                        from "dyLEARN".financial_market_list_view 
                        where financial_market_code='{market}' or 
                        financial_market_name='{market}' or 
                        financial_market_alphavantage_name='{market}'; '''
                        print(query)
                        cur.execute(query)
                        result = cur.fetchall()
                        print(result)
                        
                        if not result:
                            print(f"No market data found for: {market}")
                            cleaned_df.loc[i, 'financial_market_PK'] = None
                            cleaned_df.loc[i, 'financial_market_ID'] = None
                            cleaned_df.loc[i, 'financial_market_timezone_region_city_PK'] = None
                            missing_market_list.append(market)
                            if pd.isna(cleaned_df.loc[i, 'notes']):
                                cleaned_df.loc[i, 'notes'] = "Error: Market not found in database"
                            continue
                        
                        # Use first result row
                        row = result[0]
                        PK = row[0]
                        ID = row[1]
                        timezone_region_city_PK = row[3]
                        print(f"PK: {PK}")
                    

                        cleaned_df.loc[i, 'financial_market_PK'] = PK
                        cleaned_df.loc[i, 'financial_market_ID'] = ID
                        cleaned_df.loc[i, 'financial_market_timezone_region_city_PK'] = timezone_region_city_PK
                        
                        if timezone_region_city_PK is None:
                            print(f"Using UTC for {market} (no timezone)")
                            zone = "UTC"
                            cleaned_df.loc[i, 'notes'] = "UTC (no timezone in DB)"
                            continue  # Skip timezone lookup

                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        country_timezone_region_city_name = '''"timezone_region_city_name"'''
                        country_timezone_region_city_PK = '''"timezone_region_city_PK"'''
                        query=f'''SELECT {country_timezone_region_city_name} 
                        from "dyGEO".timezone_region_city_list
                        where {country_timezone_region_city_PK}='{timezone_region_city_PK}'; '''
                        print(query)
                        cur.execute(query)
                        result = cur.fetchall()
                        if not result:
                            print(f"No timezone data for PK: {timezone_region_city_PK}")
                            cleaned_df.loc[i, 'notes'] = "Error: No timezone data"
                            continue
                        print(result[0])
                        country_zone = str(result[0][0])
                        zone = country_zone


                
                
                print("now to convert the timezone")
                # Time correction to UTC
                for col in time_cols:
                    print("LocaL OPEN time:", cleaned_df['local_open'][i], "Market name:", cleaned_df['primary_exchanges'][i])
                    local  = str(cleaned_df[col][i])
                    print ("Got local time: ", local)
                    # Get timezone we're trying to convert from
                    local_tz = ZoneInfo(zone)
                    # UTC timezone
                    utc_tz = ZoneInfo("UTC")

                    #print((local_open))

                    dt = datetime.strptime(local,"%Y-%m-%d %H:%M:%S")
                    dt = dt.replace(tzinfo=local_tz)
                    dt_open_utc = dt.astimezone(utc_tz)
                    dt_open_utc = pd.Timestamp(dt_open_utc).tz_localize(None)
                    cleaned_df.loc[i, col] = dt_open_utc
                    print("Zone: ", zone, "Converted to UTC: ", cleaned_df.loc[i, col])
                    print("UTC time:", cleaned_df.loc[i, 'local_open'], "Market name:", cleaned_df.loc[i, 'primary_exchanges'])

                # #Removing timezones
            # Remove timezone info for entire column (inside loop now handled)
            cleaned_df['local_open'] = pd.to_datetime(cleaned_df['local_open']).dt.tz_localize(None)
            cleaned_df['local_close'] = pd.to_datetime(cleaned_df['local_close']).dt.tz_localize(None)

            print(cleaned_df)

            print("Missing market List:", missing_market_list)

            return (cleaned_df) 
        
        time_adjusted_dataframe = correct_date_time(cleaned_df)

        this_day = str(date.today())

        for i in range(len(time_adjusted_dataframe)):
            if time_adjusted_dataframe['notes'][i] == "":
                time_adjusted_dataframe['notes'][i] = "-"

        print(time_adjusted_dataframe)
        
        # De-duplicate Global markets
        time_adjusted_dataframe = time_adjusted_dataframe.drop_duplicates(subset=['financial_market_PK', 'region']).reset_index(drop=True)

        # "financial_market_opening_status_UUID"

        table_name = '''"dyTRADE".financial_market_session_time_log'''

        #Commenting for time till market_PK not ready time_adjusted_dataframe['financial_market_PK'][i],

        cwd = os.getcwd()
        file_path = os.path.join(cwd, "Credentials.env")
        cwd = os.getcwd()
        file_path = os.path.join(cwd, "Credentials.env")
        load_dotenv(file_path)
        hostname, port_id, database, username, password = (
            os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
        )
        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
        database = 'dyDATA_new' 
        username = 'postgres'
        password = 'Proc2023awsrdspostgresql'
        port_id = 5432
        print(hostname, port_id, database, username, password)
        print(hostname, port_id, database, username, password)
        print("\n=== CALCULATED SESSIONS (1=Pre, 2=Regular, 3=Post, 4=Overnight) ===")
        with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                for i in range(len(time_adjusted_dataframe)):
                    if pd.isna(time_adjusted_dataframe.loc[i, 'financial_market_PK']):
                        print(f"Skipping {time_adjusted_dataframe.loc[i, 'primary_exchanges']} - No PK")
                        continue
                    if time_adjusted_dataframe.loc[i, 'region'] == 'United States':
                        continue

                    current_status = time_adjusted_dataframe.loc[i, 'current_status']
                    status_str = "0" if str(current_status) == "closed" else "1"
                    time_adjusted_dataframe.loc[i, 'current_status'] = status_str
                    
                    notes_str = time_adjusted_dataframe.loc[i, 'notes'] or " "
                    ################################################
                    id= '''"financial_market_session_time_ID"'''
                    financial_market_PK= '''"financial_market_session_time_financial_market_PK"'''
                    session_time_log_utc_date= '''"financial_market_session_time_log_utc_date"'''
                    opening_UTC_time= '''"financial_market_session_time_opening_UTC_time"'''
                    closure_UTC_time= '''"financial_market_session_time_closure_UTC_time"'''
                    session_time_note= '''"financial_market_session_time_note"'''
                    market_status= '''"financial_market_session_time_activity_status"'''
                    market_session_PK =  '''"financial_market_session_time_market_session_PK"'''
                    
                    market_name = time_adjusted_dataframe.loc[i, 'primary_exchanges']
                    market_pk = time_adjusted_dataframe.loc[i, 'financial_market_PK']
                    
                    # Session 1: Pre-market (1.5h before)
                    pre_open = time_adjusted_dataframe.loc[i, 'local_open'] - pd.Timedelta(hours=1.5)
                    pre_close = time_adjusted_dataframe.loc[i, 'local_open']
                    print(f" SESSION 1 PRE  - {market_name} PK={market_pk}: {pre_open.strftime('%H:%M')}→{pre_close.strftime('%H:%M')} UTC")
                    cur.execute(f'''INSERT INTO {table_name} ("financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status") VALUES ({market_pk},1,'{this_day}','{pre_open}','{pre_close}','Pre {market_name}',{status_str})''')

                    # Session 2: Regular
                    print(f" SESSION 2 REGULAR - {market_name} (PK={market_pk}): {time_adjusted_dataframe.loc[i, 'local_open'].strftime('%H:%M')} → {time_adjusted_dataframe.loc[i, 'local_close'].strftime('%H:%M')} UTC")
                    cur.execute(f'''INSERT INTO {table_name} ("financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status") VALUES ({market_pk},2,'{this_day}','{time_adjusted_dataframe.loc[i, "local_open"]}','{time_adjusted_dataframe.loc[i, "local_close"]}','Regular {market_name}',{status_str})''')

                    # Session 3: Post-market (1h after)
                    post_open = time_adjusted_dataframe.loc[i, 'local_close']
                    post_close = time_adjusted_dataframe.loc[i, 'local_close'] + pd.Timedelta(hours=1)
                    print(f" SESSION 3 POST - {market_name} PK={market_pk}: {post_open.strftime('%H:%M')}→{post_close.strftime('%H:%M')} UTC")
                    cur.execute(f'''INSERT INTO {table_name} ("financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status") VALUES ({market_pk},3,'{this_day}','{post_open}','{post_close}','Post {market_name}',{status_str})''')

                    # Session 4: Overnight (to next pre)
                    overnight_open = post_close
                    overnight_close = pre_open + pd.Timedelta(days=1)
                    print(f" SESSION 4 OVERNIGHT - {market_name} PK={market_pk}: {overnight_open.strftime('%H:%M')}→{overnight_close.strftime('%H:%M')} UTC")
                    cur.execute(f'''INSERT INTO {table_name} ("financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status") VALUES ({market_pk},4,'{this_day}','{overnight_open}','{overnight_close}','Overnight {market_name}',{status_str})''')

        print(" ALL 4 SESSIONS (Pre/Regular/Post/Overnight) inserted for all valid markets!")

        def API_failure():
            
            eastern = pytz.timezone('US/Eastern')
            now_eastern = datetime.now(eastern)
            
            preMarketOpeningTime = now_eastern.replace(hour=4,minute=0,second=0,microsecond=0)
            preMarketOpeningTime_str = preMarketOpeningTime.strftime('%b %d, %Y %I:%M %p ET')
            preMarketClosingTime = now_eastern.replace(hour=9,minute=30,second=0,microsecond=0)
            preMarketClosingTime_str = preMarketClosingTime.strftime('%b %d, %Y %I:%M %p ET')
            
            marketOpeningTime = now_eastern.replace(hour=9,minute=30,second=0,microsecond=0)
            marketOpeningTime_str = marketOpeningTime.strftime('%b %d, %Y %I:%M %p ET')
            marketClosingTime = now_eastern.replace(hour=16,minute=0,second=0,microsecond=0)
            marketClosingTime_str = marketClosingTime.strftime('%b %d, %Y %I:%M %p ET')
            
            afterHoursMarketOpeningTime = now_eastern.replace(hour=16,minute=0,second=0,microsecond=0)
            afterHoursMarketOpeningTime_str = afterHoursMarketOpeningTime.strftime('%b %d, %Y %I:%M %p ET')
            afterHoursMarketClosingTime = now_eastern.replace(hour=20,minute=0,second=0,microsecond=0)
            afterHoursMarketClosingTime_str = afterHoursMarketClosingTime.strftime('%b %d, %Y %I:%M %p ET')
            
            if now_eastern < preMarketOpeningTime:
                marketIndicator = 'Market Closed'
                mrktStatus = 'Closed'
                marketCountDown_timestamp = marketOpeningTime - now_eastern
            
                if marketCountDown_timestamp.total_seconds() < 3600:
                    minutes, seconds = divmod(int(marketCountDown_timestamp.total_seconds()), 60)
                    market_countdown = f"Market Opens in {minutes}M {seconds}S"
                    mrktCountDown = f"Opens in {minutes}M {seconds}S"
                else:  # If the remaining time is 1 hour or more
                    hours, remainder = divmod(int(marketCountDown_timestamp.total_seconds()), 3600)
                    minutes, _ = divmod(remainder, 60)
                    market_countdown = f"Market Opens in {hours}H {minutes}M"
                    mrktCountDown = f"Opens in {hours}H {minutes}M"
            
            elif preMarketOpeningTime < now_eastern < preMarketClosingTime:
                marketIndicator = 'Pre Market'
                mrktStatus = 'Pre-Market'
                marketCountDown_timestamp = marketOpeningTime - now_eastern
            
                if marketCountDown_timestamp.total_seconds() < 3600:
                    minutes, seconds = divmod(int(marketCountDown_timestamp.total_seconds()), 60)
                    market_countdown = f"Market Opens in {minutes}M {seconds}S"
                    mrktCountDown = f"Opens in {minutes}M {seconds}S"
                else:  # If the remaining time is 1 hour or more
                    hours, remainder = divmod(int(marketCountDown_timestamp.total_seconds()), 3600)
                    minutes, _ = divmod(remainder, 60)
                    market_countdown = f"Market Opens in {hours}H {minutes}M"
                    mrktCountDown = f"Opens in {hours}H {minutes}M"
            
            elif marketOpeningTime < now_eastern < marketClosingTime:
                marketIndicator = 'Market Open'
                mrktStatus = 'Open'
                marketCountDown_timestamp = marketClosingTime - now_eastern
            
                if marketCountDown_timestamp.total_seconds() < 3600:
                    minutes, seconds = divmod(int(marketCountDown_timestamp.total_seconds()), 60)
                    market_countdown = f"Market Closes in {minutes}M {seconds}S"
                    mrktCountDown = f"Closes in {minutes}M {seconds}S"
                else:  # If the remaining time is 1 hour or more
                    hours, remainder = divmod(int(marketCountDown_timestamp.total_seconds()), 3600)
                    minutes, _ = divmod(remainder, 60)
                    market_countdown = f"Market Closes in {hours}H {minutes}M"
                    mrktCountDown = f"Closes in {hours}H {minutes}M"
            
            elif afterHoursMarketOpeningTime < now_eastern :
                marketIndicator = 'After Hours'
                mrktStatus = 'After-Hours'
                next_marketOpeningTime = marketOpeningTime + timedelta(days=1)
                marketCountDown_timestamp = next_marketOpeningTime - now_eastern
            
                if marketCountDown_timestamp.total_seconds() < 3600:
                    minutes, seconds = divmod(int(marketCountDown_timestamp.total_seconds()), 60)
                    market_countdown = f"Market Opens in {minutes}M {seconds}S"
                    mrktCountDown = f"Opens in {minutes}M {seconds}S"
                else:  # If the remaining time is 1 hour or more
                    hours, remainder = divmod(int(marketCountDown_timestamp.total_seconds()), 3600)
                    minutes, _ = divmod(remainder, 60)
                    market_countdown = f"Market Opens in {hours}H {minutes}M"
                    mrktCountDown = f"Opens in {hours}H {minutes}M"
            
            today = datetime.today()
            day_number = today.weekday()
            
            if day_number == 0:
                isBusinessDay = True
                today_date = today.date()
                previousTradeDate = today_date - timedelta(days=3)
                nextTradeDate = today_date + timedelta(days=1)
                previousTradeDate_str = previousTradeDate.strftime('%b %d, %Y')
                nextTradeDate_str = nextTradeDate.strftime('%b %d, %Y')

            elif day_number == 5:
                isBusinessDay = False
                today_date = today.date()
                previousTradeDate = today_date - timedelta(days=1)
                nextTradeDate = today_date + timedelta(days=2)
                previousTradeDate_str = previousTradeDate.strftime('%b %d, %Y')
                nextTradeDate_str = nextTradeDate.strftime('%b %d, %Y')

            elif day_number == 6:
                isBusinessDay = False
                today_date = today.date()
                previousTradeDate = today_date - timedelta(days=2)
                nextTradeDate = today_date + timedelta(days=1)
                previousTradeDate_str = previousTradeDate.strftime('%b %d, %Y')
                nextTradeDate_str = nextTradeDate.strftime('%b %d, %Y')

            else:
                isBusinessDay = True
                today_date = today.date()
                previousTradeDate = today_date - timedelta(days=1)
                nextTradeDate = today_date + timedelta(days=1)
                previousTradeDate_str = previousTradeDate.strftime('%b %d, %Y')
                nextTradeDate_str = nextTradeDate.strftime('%b %d, %Y')

            expected_response = {'country': 'U.S.', 'marketIndicator': marketIndicator, 'uiMarketIndicator': marketIndicator, 'marketCountDown': market_countdown, 'preMarketOpeningTime': preMarketOpeningTime_str, 'preMarketClosingTime': preMarketClosingTime_str, 'marketOpeningTime': marketOpeningTime_str,
            'marketClosingTime': marketClosingTime_str, 'afterHoursMarketOpeningTime': afterHoursMarketOpeningTime_str, 'afterHoursMarketClosingTime': afterHoursMarketClosingTime_str, 'previousTradeDate': previousTradeDate_str, 'nextTradeDate': nextTradeDate_str, 'isBusinessDay': isBusinessDay,
            'mrktStatus': mrktStatus, 'mrktCountDown': mrktCountDown}

            return expected_response

        ###########################################################
        # apicalls.io fetched dataframe is processed from here on.
        ###########################################################

        def apicalls_get_data():
            global data
            try:
                url = 'https://api.apicalls.io/v2/markets/market-info'
                headers = {
                'Authorization': 'Bearer 539|5d9M5TONvuHKNOVYKwrWKT88fsivCirNPSc9nXXf'
                }

                response = requests.request('GET', url, headers=headers, timeout=10)
                data = response.json()
                print(data)

                if data is None or ('body' not in data):
                    raise ValueError("Invalid API response")
                dict = data['body']
            except Exception as e:
                print(f"APICalls failed ({e}), using fallback")
                dict = API_failure()
            dataframe = pd.DataFrame(list(dict.items()))
            dataframe =  dataframe.transpose()

            return dataframe
        
        dataframe = apicalls_get_data()
        cleaned_df = dataframe.copy()
        
        def apicalls_correct_date_time(cleaned_df):

            # Get region data from table
            cwd = os.getcwd()
            file_path = os.path.join(cwd, "Credentials.env")
            load_dotenv(file_path)
            hostname, port_id, database, username, password = (
                os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
            )
            print(hostname, port_id, database, username, password)

            hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
            database = 'dyDATA_new' 
            username = 'postgres'
            password = 'Proc2023awsrdspostgresql'
            port_id = 5432

            cleaned_df. columns=cleaned_df. iloc[0]
            cleaned_df = (cleaned_df.drop(0))
            cleaned_df.reset_index()
            cleaned_df.loc[0, 'country'] = 'US'


            time_cols = list(cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'Time')])
            date_cols = (list([cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'Date')]]))

            for col in time_cols:
                cleaned_df[col] = pd.to_datetime(cleaned_df[col], format='%Y-%m-%d %H:%M:%S', errors='coerce')
            
            for col in date_cols:
                cleaned_df[col] = cleaned_df[col].apply(lambda x: pd.to_datetime(str(x), format="%b %d, %Y", errors='coerce').strftime("%d.%m.%Y") if pd.notna(pd.to_datetime(str(x), format="%b %d, %Y", errors='coerce')) else x)


            cleaned_df.assign(financial_market_name="")
            cleaned_df.assign(financial_market_PK="")
            print("Printing cleaned df", cleaned_df)
            market_df = pd.DataFrame()
            # Fallback US data - skip detailed processing, return directly
            print("Fallback US market data processed, returning")
            return cleaned_df
                
            try: 
                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                            query=f'''SELECT "PK"
                            from "dyGEO".country_list_view 
                            where alpha_2_code=%s; ''' # Use US
                            cur.execute(query, ('US',))
                            print(query)
                            cur.execute(query)
                            result = cur.fetchall()
                            print("counrty_PK = ", result)
            except:
                    raise Exception('Could not fetch the country PK.')
            finally:
                if conn is not None:
                    conn.close()

            try: 
                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        for pk in result:
                            query=f'''SELECT "timezone_region_city_PK"
                            from "dyGEO".country_timezone_region_city_rel_view 
                            where "country_PK" = {pk[0]}; ''' # The counrty name should be US and not U.S.
                            print(query)
                            cur.execute(query)
                            timezone_region_city_PK_list = cur.fetchall()
                            print("timezone_region_city_PK_list: ", timezone_region_city_PK_list)
            except:
                raise Exception('Could not fetch the timezone region city PK.')
            finally:
                if conn is not None:
                    conn.close()  
            try: 
                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        for tz_PK in range(len(timezone_region_city_PK_list)):
                            query=f''' SELECT "financial_market_PK", financial_market_name
                            from "dyLEARN".financial_market_list 
                            where "financial_market_timezone_region_city_PK" ='{timezone_region_city_PK_list[tz_PK][0]}'; ''' # The counrty name should be US and not U.S.
                            print(query)
                            cur.execute(query)
                            markets = cur.fetchall()
                            num = row
                            for market in markets:
                                financial_market_PK = market[0]
                                financial_market_name = market[1]
                                data_dict = {'financial_market_name': financial_market_name,'financial_market_PK': financial_market_PK,'country':cleaned_df['country'][row], 'marketIndicator':cleaned_df['marketIndicator'][row],
                                            'uiMarketIndicator':cleaned_df['uiMarketIndicator'][row],'marketCountDown':cleaned_df['marketCountDown'][row],
                                            'preMarketOpeningTime':cleaned_df['preMarketOpeningTime'][row], 'preMarketClosingTime':cleaned_df['preMarketClosingTime'][row],
                                            'marketOpeningTime':cleaned_df['marketOpeningTime'][row], 'marketClosingTime':cleaned_df['marketClosingTime'][row],
                                            'afterHoursMarketOpeningTime':cleaned_df['afterHoursMarketOpeningTime'][row], 'afterHoursMarketClosingTime':cleaned_df['afterHoursMarketClosingTime'][row],
                                            'previousTradeDate':cleaned_df['previousTradeDate'][row], 'nextTradeDate':cleaned_df['nextTradeDate'][row],
                                            'isBusinessDay':cleaned_df['isBusinessDay'][row], 'mrktStatus':cleaned_df['mrktStatus'][row], 'mrktCountDown':cleaned_df['mrktCountDown'][row] }
                                temp_df = pd.DataFrame(data_dict, index=[0])
                                num += 1
                                market_df = pd.concat([market_df,temp_df], ignore_index=True)
            except:
                    raise Exception('Could not fetch the market name')
            finally:
                if conn is not None:
                    conn.close()
                
            cleaned_df = pd.concat([cleaned_df, market_df], ignore_index=True)
            print("Concatinated dataframe:", cleaned_df)

            print(market_df)
            return (market_df)
        
        apicalls_time_adjusted_dataframe = apicalls_correct_date_time(cleaned_df)

        from datetime import date
        this_day = str(date.today())

        cwd = os.getcwd()
        file_path = os.path.join(cwd, "Credentials.env")
        load_dotenv(file_path)
        hostname, port_id, database, username, password = (
            os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
        )
        print(hostname, port_id, database, username, password)

        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
        database = 'dyDATA_new' 
        username = 'postgres'
        password = 'Proc2023awsrdspostgresql'
        port_id = 5432

        # "financial_market_opening_status_UUID"

        table_name = '''"dyTRADE".financial_market_session_time_log'''

        #Commenting for time till market_PK not ready apicalls_time_adjusted_dataframe['financial_market_PK'][i],
        ### For the overnight session logic ###
    
        with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                if 'financial_market_PK' not in apicalls_time_adjusted_dataframe.columns:
                    print("Skipping apicalls inserts - no financial_market_PK column")
                else:
                    for i in range(len(apicalls_time_adjusted_dataframe)):
                        if pd.isna(apicalls_time_adjusted_dataframe.loc[i, 'financial_market_PK']):
                            continue
                        if apicalls_time_adjusted_dataframe['mrktStatus'][i] == "Open":
                            apicalls_time_adjusted_dataframe['mrktStatus'][i]=1
                        else:
                            apicalls_time_adjusted_dataframe['mrktStatus'][i]=0
                        if 'notes' not in apicalls_time_adjusted_dataframe.columns:
                            apicalls_time_adjusted_dataframe['notes'] = ' '
                        if apicalls_time_adjusted_dataframe['notes'][i] is None:
                            apicalls_time_adjusted_dataframe['notes'][i] = " "
                        ################################################
                        id= '''"financial_market_session_time_ID"'''
                        financial_market_PK= '''"financial_market_session_time_financial_market_PK"'''
                        session_time_log_utc_date= '''"financial_market_session_time_log_utc_date"'''
                        opening_UTC_time= '''"financial_market_session_time_opening_UTC_time"'''
                        closure_UTC_time= '''"financial_market_session_time_closure_UTC_time"'''
                        session_time_note= '''"financial_market_session_time_note"'''
                        market_status= '''"financial_market_session_time_activity_status"'''
                        market_session_PK =  '''"financial_market_session_time_market_session_PK"'''
                        next_trade_session_date = '''"financial_market_session_next_market_trading_session_date"'''
                        
                        query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                        VALUES (%s,%s,2,'%s','%s','%s',%s,'%s')''', (apicalls_time_adjusted_dataframe['financial_market_PK'][i], apicalls_time_adjusted_dataframe['financial_market_PK'][i], this_day, apicalls_time_adjusted_dataframe['marketOpeningTime'][i], apicalls_time_adjusted_dataframe['marketClosingTime'][i], apicalls_time_adjusted_dataframe['mrktStatus'][i], apicalls_time_adjusted_dataframe['nextTradeDate'][i])
                        print(query)
                        cur.execute(query)
                    
                        # Adding the pre Market data
                        query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                        VALUES (%s,%s,1,'%s','%s','%s',%s, '%s')''', (apicalls_time_adjusted_dataframe['financial_market_PK'][i], apicalls_time_adjusted_dataframe['financial_market_PK'][i], this_day, apicalls_time_adjusted_dataframe['preMarketOpeningTime'][i], apicalls_time_adjusted_dataframe['preMarketClosingTime'][i], apicalls_time_adjusted_dataframe['mrktStatus'][i], apicalls_time_adjusted_dataframe['nextTradeDate'][i])
                        print(query)
                        cur.execute(query)

                        # Adding the values of after Market data
                        query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                        VALUES (%s,%s,3,'%s','%s','%s',%s, '%s')''', (apicalls_time_adjusted_dataframe['financial_market_PK'][i], apicalls_time_adjusted_dataframe['financial_market_PK'][i], this_day, apicalls_time_adjusted_dataframe['afterHoursMarketOpeningTime'][i], apicalls_time_adjusted_dataframe['afterHoursMarketClosingTime'][i], apicalls_time_adjusted_dataframe['mrktStatus'][i], apicalls_time_adjusted_dataframe['nextTradeDate'][i])
                        print(query)
                        cur.execute(query)
                        ##################################################
                        ######## Adding the overnight session data########
                        ##################################################
                        # Add 1 day to tomorrow's pre-market opening time for overnight closure
                        tomorrow_premarket = apicalls_time_adjusted_dataframe['preMarketOpeningTime'][i] + pd.Timedelta(days=1)

                        query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                        VALUES (%s,%s,4,'%s','%s','%s',%s, '%s')''', (apicalls_time_adjusted_dataframe['financial_market_PK'][i], apicalls_time_adjusted_dataframe['financial_market_PK'][i], this_day, apicalls_time_adjusted_dataframe['afterHoursMarketClosingTime'][i], tomorrow_premarket, apicalls_time_adjusted_dataframe['mrktStatus'][i], apicalls_time_adjusted_dataframe['nextTradeDate'][i])
                        print(query)
                        cur.execute(query)

                        # approach two
                        #query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                        #VALUES (%s,%s,4,'%s','%s','%s',%s, '%s')''', (apicalls_time_adjusted_dataframe['financial_market_PK'][i], apicalls_time_adjusted_dataframe['financial_market_PK'][i], this_day, apicalls_time_adjusted_dataframe['afterHoursMarketClosingTime'][i], apicalls_time_adjusted_dataframe['preMarketOpeningTime'][i], apicalls_time_adjusted_dataframe['mrktStatus'][i], apicalls_time_adjusted_dataframe['nextTradeDate'][i])          
                        #print(query)
                        #cur.execute(query)

        response = {
            'success':True,
            'errors':None
        }
        return response
        
        
    except Exception as error:
        print('Error: ', error)
        response = {
            'success':False,
            'errors': error
        }
        return response



if __name__=='__main__':
     resolve_FMU(None, None, None)


