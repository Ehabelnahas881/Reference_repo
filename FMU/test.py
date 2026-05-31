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
        # cwd = os.getcwd()
        # file_path = os.path.join(cwd, "Credentials.env")
        # load_dotenv(file_path)
        # hostname, port_id, database, username, password = (
        #     os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
        # )
        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
        database = 'dyDATA_new' 
        username = 'postgres'
        password = 'Proc2023awsrdspostgresql'
        port_id = 5432
        this_day = str(date.today())
        with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                print("Deleting today's already registered data")
                cur.execute('DELETE FROM "dyTRADE".financial_market_session_time_log WHERE financial_market_session_time_log_utc_date = %s', (this_day,))

        def get_data():
            # replace the "demo" apikey below with your own key from https://www.alphavantage.co/support/#api-key
            url = 'https://www.alphavantage.co/query?function=MARKET_STATUS&apikey=YHMNI088FNU04Z0O'
            r = requests.get(url)
            data = r.json()
            print(data)

            if 'markets' in data:
                markets_list = data['markets']
            else:
                print("No markets data available (API rate limit?), using fallback")
                markets_list = []
            cleaned_df = pd.DataFrame(markets_list)
            

            return cleaned_df


        dataframe = get_data()
        cleaned_df = dataframe.copy()

        time_cols = list(cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'local')]) if len(cleaned_df) > 0 else []
        print("Columns containing time:", time_cols)

        if len(cleaned_df) > 0:
            cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].astype(str).str.strip()
        else:
            print("Empty DataFrame, skipping primary_exchanges processing")
            return pd.DataFrame()

        def correct_date_time(cleaned_df):
            # Get region data from table
            # cwd = os.getcwd()
            # file_path = os.path.join(cwd, "Credentials.env")
            # load_dotenv(file_path)
            # hostname, port_id, database, username, password = (
            #     os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
            # )
            # print(hostname, port_id, database, username, password)

            hostname ="database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com" 
            database="dyDATA_new" 
            username='postgres'
            password='Proc2023awsrdspostgresql'
            port_id=5432

            ###################
            # Changing the time only values into datetime
            #this part need to be fixed!!! The fix is not to uncomment the format line, it is just there was future purposes.
            cleaned_df['local_open'] = pd.to_datetime('1970-01-01 ' + cleaned_df['local_open'], format='%Y-%m-%d %H:%M')
            cleaned_df['local_close'] = pd.to_datetime('1970-01-01 ' + cleaned_df['local_close'], format='%Y-%m-%d %H:%M')
            print(cleaned_df['local_open'])

            #Separate the stock markets, as they are clubbed by country
            cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(lambda x: [item[1:-1] for sublist in x for item in sublist] if isinstance(x, list) else x)
            # print(cleaned_df['primary_exchanges'])
            for i in range(len(cleaned_df)):
                # if cleaned_df['primary_exchanges'][i].find(',') == 0:
                cleaned_df['primary_exchanges'][i] = cleaned_df['primary_exchanges'][i].split(',')
            cleaned_df = cleaned_df.explode(column = 'primary_exchanges', ignore_index=True)
            # Removing whitespaces from starting and ending of the cells
            cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(lambda x: x.strip())

            # FIILING TIME RELATRED COLUMNS IN A LIST
            time_cols = list(cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'local')])

            for col in ['financial_market_PK', 'financial_market_ID', 'financial_market_timezone_region_city_PK']:
                if col not in cleaned_df.columns:
                    cleaned_df[col] = None
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
                        
                        # cleaned_df['financial_market_timezone_region_city_PK'] = result[2]
                        if result:
                            row = result[0]
                            PK = row[0]
                            ID = row[1]
                            timezone_region_city_PK = row[3]
                            print(PK)

                            cleaned_df.loc[i, 'financial_market_PK'] = PK
                            cleaned_df.loc[i, 'financial_market_ID'] = ID
                            cleaned_df.loc[i, 'financial_market_timezone_region_city_PK'] = timezone_region_city_PK
                        else:
                            PK = None
                            ID = None
                            timezone_region_city_PK = None
                        # cleaned_df['financial_market_PK'][i] = result[0]
                        # cleaned_df['financial_market_ID'][i] = result[1]
                        if timezone_region_city_PK == None:
                            missing_market_list.append(market)
                            print("Continuing")
                            if cleaned_df['region'][i] == 'Global':
                                cleaned_df['notes'][i]=("This market is global")
                            else:
                                cleaned_df['notes'][i]=("Error fetching the timezone_ID")
                            continue

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
                        print(result[0])
                        # country_zone = str(result[0][0])
                        # res = country_zone.split("-", 1)
                        zone = result[0][0] #res[1]


                
                
                print("now to convert the timezone")
                # Time correction to UTC
                for col in time_cols:
                    # print("LocaL OPEN time:", cleaned_df['local_open'][i], "Market name:", cleaned_df['primary_exchanges'][i])
                    local  = str(cleaned_df[col][i])
                    print ("Got local time: ", local)
                    # Get timezone we're trying to convert from
                    local_tz = ZoneInfo(zone)
                    # UTC timezone
                    utc_tz = ZoneInfo("UTC")

                    # print((local_open))

                    dt = datetime.strptime(local,"%Y-%m-%d %H:%M:%S")
                    dt = dt.replace(tzinfo=local_tz)
                    dt_open_utc = dt.astimezone(utc_tz)
                    dt_open_utc = pd.Timestamp(dt_open_utc)
                    cleaned_df.at[i, col] = dt_open_utc.tz_convert('utc').replace(tzinfo=None)
                    print("Zone: ", zone, "Converted to UTC: ", cleaned_df[col][i])
                    # print("UTC time:", cleaned_df['local_open'][i], "Market name:", cleaned_df['primary_exchanges'][i])

                # #Removing timezones
                # cleaned_df['local_open'] = cleaned_df['local_open'][i].replace(tzinfo=None)
                # cleaned_df['local_close'] = cleaned_df['local_close'][i].replace(tzinfo=None)

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

        # cwd = os.getcwd()
        # file_path = os.path.join(cwd, "Credentials.env")
        # cwd = os.getcwd()
        # file_path = os.path.join(cwd, "Credentials.env")
        # load_dotenv(file_path)
        # hostname, port_id, database, username, password = (
        #     os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
        # )
        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
        database = 'dyDATA_new' 
        username = 'postgres'
        password = 'Proc2023awsrdspostgresql'
        port_id = 5432
        # print(hostname, port_id, database, username, password)
        # print(hostname, port_id, database, username, password)
        with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                for i in range(len(time_adjusted_dataframe)):
                    if time_adjusted_dataframe['region'][i] == 'United States':
                        continue
                    if time_adjusted_dataframe['current_status'][i] =="closed":
                        time_adjusted_dataframe['current_status'][i]=0
                    else:
                        time_adjusted_dataframe['current_status'][i]=1
                    if time_adjusted_dataframe['notes'][i] is None:
                        time_adjusted_dataframe['notes'][i] = " "
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
                    print(query)
                    cur.execute(query)
        print("The query was successful in writing the values.")

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
            url = 'https://api.apicalls.io/v2/markets/market-info'
            headers = {
            'Authorization': 'Bearer 539|5d9M5TONvuHKNOVYKwrWKT88fsivCirNPSc9nXXf'
            }

            response = requests.request('GET', url, headers=headers)
            data = response.json()
            print(data)

            if data is None or ('body' not in data):
                print("APICalls has failed so now going with default values")
                dict = API_failure()
            else:
                dict = data['body']
            dataframe = pd.DataFrame(list(dict.items()))
            dataframe =  dataframe.transpose()

            return dataframe
        
        dataframe = apicalls_get_data()
        cleaned_df = dataframe.copy()
        
        def apicalls_correct_date_time(cleaned_df):

            # Get region data from table
            # cwd = os.getcwd()
            # file_path = os.path.join(cwd, "Credentials.env")
            # load_dotenv(file_path)
            # hostname, port_id, database, username, password = (
            #     os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
            # )
            # print(hostname, port_id, database, username, password)

            hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
            database = 'dyDATA_new' 
            username = 'postgres'
            password = 'Proc2023awsrdspostgresql'
            port_id = 5432

            cleaned_df. columns=cleaned_df. iloc[0]
            cleaned_df = (cleaned_df.drop(0))
            cleaned_df.reset_index()
            cleaned_df['country'][1] = 'US'


            time_cols = list(cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'Time')])
            date_cols = (list([cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'Date')]]))

            for col in time_cols:
                cleaned_df[col] = pd.to_datetime(cleaned_df[col])#, format='%Y-%m-%d %H:%M:%S') #line 17
            
            for col in date_cols:
                cleaned_df[col] = cleaned_df[col] + ' 00:00 AM ET'
                print(cleaned_df[col])
                cleaned_df[col] = cleaned_df[col].apply(pd.to_datetime)#, format="%b %d, %Y", errors="coerce").dt.strftime("%d.%m.%Y")


            cleaned_df.assign(financial_market_name="")
            cleaned_df.assign(financial_market_PK="")
            print("Printing cleaned df", cleaned_df)
            market_df = pd.DataFrame()
            for row in cleaned_df.index:
                if row == 0:
                    continue
                
                print("now to convert the timezone")
                # Time correction to UTC
                for col in time_cols:
                    # print("LocaL OPEN time:", cleaned_df['local_open'][i], "Market name:", cleaned_df['primary_exchanges'][i])
                    local  = str(cleaned_df[col][row])
                    print ("Got local time: ", local)
                    # Get timezone we're trying to convert from
                    local_tz = ZoneInfo("America/New_York")
                    # UTC timezone
                    utc_tz = ZoneInfo("UTC")

                    dt = datetime.strptime(local,"%Y-%m-%d %H:%M:%S")
                    dt = dt.replace(tzinfo=local_tz)
                    dt_open_utc = dt.astimezone(utc_tz)
                    dt_open_utc = pd.Timestamp(dt_open_utc)
                    cleaned_df[col][row] = dt_open_utc.tz_convert('utc')
                    print("Converted to UTC: ", cleaned_df[col][row])
                
                # try: 
                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                            query=f'''SELECT "PK"
                            from "dyGEO".country_list_view 
                            where alpha_2_code='{cleaned_df['country'][row]}'; ''' # The country name should be US and not U.S.
                            print(query)
                            cur.execute(query)
                            result = cur.fetchall()
                            print("counrty_PK = ", result)
                # except:
                #     raise Exception('Could not fetch the country PK.')
                # finally:
                if conn is not None:
                    conn.close()

                # try: 
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
                # except:
                #     raise Exception('Could not fetch the timezone region city PK.')
                # finally:
                if conn is not None:
                    conn.close()  
                # try: 
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
                                # num += 1
                                market_df = pd.concat([market_df,temp_df], ignore_index=True)
                # except:
                #     raise Exception('Could not fetch the market name')
                # finally:
                if conn is not None:
                    conn.close()
                
            # cleaned_df = pd.concat([cleaned_df, market_df])#, ignore_index=True)
            # print("Concatinated dataframe:", cleaned_df)

            print(market_df)
            return (market_df)
        
        apicalls_time_adjusted_dataframe = apicalls_correct_date_time(cleaned_df)

        from datetime import date
        this_day = str(date.today())

        # cwd = os.getcwd()
        # file_path = os.path.join(cwd, "Credentials.env")
        # load_dotenv(file_path)
        # hostname, port_id, database, username, password = (
        #     os.getenv(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
        # )
        # print(hostname, port_id, database, username, password)

        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
        database = 'dyDATA_new' 
        username = 'postgres'
        password = 'Proc2023awsrdspostgresql'
        port_id = 5432

        # "financial_market_opening_status_UUID"

        table_name = '''"dyTRADE".financial_market_session_time_log'''

        #Commenting for time till market_PK not ready apicalls_time_adjusted_dataframe['financial_market_PK'][i],

    
        with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                for i in range(len(apicalls_time_adjusted_dataframe)):
                    if apicalls_time_adjusted_dataframe['mrktStatus'][i] == "Open":
                        apicalls_time_adjusted_dataframe['mrktStatus'][i]=1
                    else:
                        apicalls_time_adjusted_dataframe['mrktStatus'][i]=0
                    # if apicalls_time_adjusted_dataframe['notes'][i] is None:
                    #     apicalls_time_adjusted_dataframe['notes'][i] = " "
                    ################################################
                    id= '''"financial_market_session_time_ID"'''
                    financial_market_PK= '''"financial_market_session_time_financial_market_PK"'''
                    session_time_log_utc_date= '''"financial_market_session_time_log_utc_date"'''
                    opening_UTC_time= '''"financial_market_session_time_opening_UTC_time"'''
                    closure_UTC_time= '''"financial_market_session_time_closure_UTC_time"'''
                    # session_time_note= '''"financial_market_session_time_note"'''
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
        print("The query was successful in writing the values for apicalls.io")

    
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