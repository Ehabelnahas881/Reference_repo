def resolve_FMU(_,info,dum):
    try:
        #Importing libraries
        import pandas as pd
        import requests
        import time
        import datetime

        import pytz
        from datetime import datetime, timezone, timedelta
        from backports.zoneinfo import ZoneInfo
        from datetime import date

        import psycopg2
        import psycopg2.extras
        from psycopg2.extensions import AsIs

        from datetime import datetime, timezone

        import warnings
        warnings.filterwarnings("ignore")

        #Delete any previous day
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

            #Creating the dataframe
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
            # Get region data from table
            hostname ="database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com" 
            database="dyDATA_new" 
            username='postgres'
            password='Proc2023awsrdspostgresql'
            port_id=5432

            # Changing the time only values into datetime
            cleaned_df['local_open'] = pd.to_datetime(cleaned_df['local_open'])
            cleaned_df['local_close'] = pd.to_datetime(cleaned_df['local_close'])
            print(cleaned_df['local_open'])

            #Separate the stock markets, as they are clubbed by country
            cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(lambda x: [item[1:-1] for sublist in x for item in sublist] if isinstance(x, list) else x)
            for i in range(len(cleaned_df)):
                cleaned_df['primary_exchanges'][i] = cleaned_df['primary_exchanges'][i].split(',')
            cleaned_df = cleaned_df.explode(column = 'primary_exchanges', ignore_index=True)
            # Removing whitespaces from starting and ending of the cells
            cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(lambda x: x.strip())

            # FIILING TIME RELATRED COLUMNS IN A LIST
            time_cols = list(cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'local')])

            cleaned_df['financial_market_PK'] = ""
            cleaned_df['financial_market_ID'] = ""
            cleaned_df['financial_market_timezone_region_city_PK'] = ""
            missing_market_list = []
            for i in range(len(cleaned_df)):
                #Adding neccessary columns to the dataframe like PK and ID
                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        market = cleaned_df['primary_exchanges'][i]
                        print(f"now we in: {market}")
                        financial_market_PK= '"financial_market_PK"'
                        financial_market_ID= '"financial_market_ID"'
                        financial_market_name= '"financial_market_name"'
                        financial_market_timezone_region_city_PK = '"financial_market_timezone_region_city_PK"'

                        query=f'''SELECT {financial_market_PK},{financial_market_ID},{financial_market_name},{financial_market_timezone_region_city_PK} 
                        from "dyLEARN".financial_market_list_view 
                        where financial_market_code='{market}' or 
                        financial_market_name='{market}' or 
                        financial_market_alphavantage_name='{market}'; '''
                        print(query)
                        cur.execute(query)
                        result = cur.fetchall()
                        print(result)
                        
                        for row in result:
                            PK=row[0]
                            ID=row[1]
                            timezone_region_city_PK = row[3]
                            print(PK)

                        cleaned_df['financial_market_PK'][i] = PK
                        cleaned_df['financial_market_ID'][i] = ID
                        cleaned_df['financial_market_timezone_region_city_PK'][i] = timezone_region_city_PK

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
                        country_timezone_region_city_name = '"timezone_region_city_name"'
                        country_timezone_region_city_PK = '"timezone_region_city_PK"'
                        query=f'''SELECT {country_timezone_region_city_name} 
                        from "dyGEO".timezone_region_city_list
                        where {country_timezone_region_city_PK}='{timezone_region_city_PK}'; '''
                        print(query)
                        cur.execute(query)
                        result = cur.fetchall()
                        print(result[0])
                        zone = result[0][0]

                print("now to convert the timezone")
                # Time correction to UTC
                for col in time_cols:
                    local  = str(cleaned_df[col][i])
                    print ("Got local time: ", local)
                    # Get timezone we're trying to convert from
                    local_tz = ZoneInfo(zone)
                    # UTC timezone
                    utc_tz = ZoneInfo("UTC")

                    dt = datetime.strptime(local,"%Y-%m-%d %H:%M:%S")
                    dt = dt.replace(tzinfo=local_tz)
                    dt_open_utc = dt.astimezone(utc_tz)
                    dt_open_utc = pd.Timestamp(dt_open_utc)
                    cleaned_df[col][i] = dt_open_utc.tz_convert('utc')
                    print("Zone: ", zone, "Converted to UTC: ", cleaned_df[col][i])

            print(cleaned_df)
            print("Missing market List:", missing_market_list)

            return (cleaned_df) 
        
        time_adjusted_dataframe = correct_date_time(cleaned_df)

        this_day = str(date.today())

        for i in range(len(time_adjusted_dataframe)):
            if time_adjusted_dataframe['notes'][i] == "":
                time_adjusted_dataframe['notes'][i] = "-"

        print(time_adjusted_dataframe)

        table_name = '"dyTRADE".financial_market_session_time_log'

        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
        database = 'dyDATA_new' 
        username = 'postgres'
        password = 'Proc2023awsrdspostgresql'
        port_id = 5432
        
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
                    id= '"financial_market_session_time_ID"'
                    financial_market_PK= '"financial_market_session_time_financial_market_PK"'
                    session_time_log_utc_date= '"financial_market_session_time_log_utc_date"'
                    opening_UTC_time= '"financial_market_session_time_opening_UTC_time"'
                    closure_UTC_time= '"financial_market_session_time_closure_UTC_time"'
                    session_time_note= '"financial_market_session_time_note"'
                    market_status= '"financial_market_session_time_activity_status"'
                    market_session_PK =  '"financial_market_session_time_market_session_PK"'
                    
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
                else:  
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
                else:  
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
                else:  
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
                else:  
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