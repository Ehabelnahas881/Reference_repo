def resolve_FMU(_,info,financial_market_pks):  
    try:
        print(financial_market_pks)
        import pandas as pd
        import requests
        import time
        import datetime
        from datetime import date
       
        import pandas_market_calendars as mcal

        import pytz
        from datetime import datetime, timezone, timedelta
        # from backports.zoneinfo import ZoneInfo
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

     
        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
        database = 'dyDATA_new' 
        username = 'postgres'
        password = 'Proc2023awsrdspostgresql'
        port_id = 5432
        # today = str(date.today())
        today = date.today()
        table_name='"dyTRADE".financial_market_session_time_log'
        # today=date(2026,8,18)
        with psycopg2.connect(host=hostname, dbname=database, user=username, password=password, port=port_id) as conn:

            with conn.cursor() as cur:
           

                if not financial_market_pks:
                    return {'success': True, 'errors': ["No PKs provided — nothing to update"]}
                us_pks = set()
             
                cur.execute("""
                    SELECT "financial_market_PK"
                    FROM "dyLEARN".financial_market_list
                    WHERE "financial_market_timezone_region_city_PK" IN (
                        SELECT "timezone_region_city_PK"
                        FROM "dyGEO".country_timezone_region_city_rel_view
                        WHERE "country_PK" = 237
                    )
                """)
                us_pks = {row[0] for row in cur.fetchall()}

                # ── 2. Split input PKs into US and non-US ──
                input_pks = set(financial_market_pks)

                non_us_pks = list(input_pks - us_pks)
                us_pks = list(input_pks - set(non_us_pks))
                print(f"US requested PKs: {us_pks}")
                print(f"Non-US requested PKs: {non_us_pks}")
            

                
                    
        
                        

                if non_us_pks:
                    pk_list_str = ",".join(map(str,non_us_pks))
                    delete_query = f"""
                        DELETE FROM {table_name}
                        WHERE financial_market_session_time_log_utc_date = '{today}'
                        AND "financial_market_session_time_financial_market_PK" IN ({pk_list_str})
                    """
                    cur.execute(delete_query)
                    print("deleting today's data for the respective markets ")
                    

                    def get_data():
                        # replace the "demo" apikey below with your own key from https://www.alphavantage.co/support/#api-key
                        url = 'https://www.alphavantage.co/query?function=MARKET_STATUS&apikey=E8VCMZJEKYQS5Q7W'
                        try:
                            r = requests.get(url)
                            data = r.json()
                            # print(data)

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
                        except Exception as e:
                            print(f"APICalls has failed ({e}), so now going with default values")
                            return None


                    dataframe = get_data()
                    if dataframe is not None:
                        print("Got data from API")
                        cleaned_df = dataframe.copy()

                        time_cols = list(cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'local')])
                        print("Columns containing time:", time_cols)

                        cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(lambda x: x.strip())

                        def correct_date_time(cleaned_df):


                            hostname ="database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com" 
                            database="dyDATA_new" 
                            username='postgres'
                            password='Proc2023awsrdspostgresql'
                            port_id=5432

                            ###################
                            # Changing the time only values into datetime
                            #this part need to be fixed!!! The fix is not to uncomment the format line, it is just there was future purposes.
                            cleaned_df['local_open'] = pd.to_datetime(cleaned_df['local_open'])#, format='%Y-%m-%d %H:%M:%S') #line 17
                            cleaned_df['local_close'] = pd.to_datetime(cleaned_df['local_close'])#, format='%y-%m-%d %H:%M:%S')
                            # print(cleaned_df['local_open'])

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

                            cleaned_df['financial_market_PK'] = ""
                            cleaned_df['financial_market_code'] = "" 
                            cleaned_df['financial_market_name'] = "" 
                            cleaned_df['financial_market_ID'] = ""
                            cleaned_df['financial_market_timezone_region_city_PK'] = ""
                            missing_market_list = []
                            for i in range(len(cleaned_df)):
                                #Adding neccessary columns to the dataframe like PK and ID
                                
                                market = cleaned_df['primary_exchanges'][i]
                                print(f"now we in: {market}")
                                financial_market_PK= '''"financial_market_PK"'''
                                financial_market_ID= '''"financial_market_ID"'''
                                financial_market_name= '''"financial_market_name"'''
                                financial_market_timezone_region_city_PK = '''"financial_market_timezone_region_city_PK"'''

                                ################################################
                                query=f'''SELECT {financial_market_PK},{financial_market_ID},{financial_market_name},{financial_market_timezone_region_city_PK},financial_market_code
                                from "dyLEARN".financial_market_list_view 
                                where (financial_market_code='{market}' or 
                                financial_market_name='{market}' or 
                                financial_market_alphavantage_name='{market}') and financial_market_code is not null; '''
                                # print(query)
                                cur.execute(query)
                                result = cur.fetchall()
                                # print(result)
                                
                                # cleaned_df['financial_market_timezone_region_city_PK'] = result[2]
                                for row in result:
                                    # row=result[0]
                                    PK=row[0]
                                    ID=row[1]
                                    name=row[2]
                                    timezone_region_city_PK = row[3]
                                    code=row[4]
                                    # print(PK)
                            

                                    cleaned_df.loc[i, 'financial_market_code'] = code
                                    cleaned_df.loc[i, 'financial_market_PK'] = PK
                                    cleaned_df.loc[i, 'financial_market_ID'] = ID
                                    cleaned_df.loc[i, 'financial_market_name'] = name
                                    cleaned_df.loc[i, 'financial_market_timezone_region_city_PK'] = timezone_region_city_PK
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
                                    continue

                               
                                country_timezone_region_city_name = '''"timezone_region_city_name"'''
                                country_timezone_region_city_PK = '''"timezone_region_city_PK"'''
                                query=f'''SELECT {country_timezone_region_city_name} 
                                from "dyGEO".timezone_region_city_list
                                where {country_timezone_region_city_PK}='{timezone_region_city_PK}'; '''
                                # print(query)
                                cur.execute(query)
                                result = cur.fetchall()
                                # print(result[0])
                                # country_zone = str(result[0][0])
                                # res = country_zone.split("-", 1)
                                zone = result[0][0] #res[1]


                                
                                
                                print("now to convert the timezone")
                                # Time correction to UTC
                                for col in time_cols:
                                    # print("LocaL OPEN time:", cleaned_df['local_open'][i], "Market name:", cleaned_df['primary_exchanges'][i])
                                    local  = str(cleaned_df[col][i])
                                    # print ("Got local time: ", local)
                                    # Get timezone we're trying to convert from
                                    local_tz = ZoneInfo(zone)
                                    # UTC timezone
                                    utc_tz = ZoneInfo("UTC")

                                    # print((local_open))

                                    dt = datetime.strptime(local,"%Y-%m-%d %H:%M:%S")
                                    dt = dt.replace(tzinfo=local_tz)
                                    dt_open_utc = dt.astimezone(utc_tz)
                                    dt_open_utc = pd.Timestamp(dt_open_utc)
                                    cleaned_df[col][i] = dt_open_utc.tz_convert('utc')
                                    # print("Zone: ", zone, "Converted to UTC: ", cleaned_df[col][i])
                                    

                            print("Missing market List:", missing_market_list)

                            return (cleaned_df) 
                        
                        time_adjusted_dataframe = correct_date_time(cleaned_df)
                        time_adjusted_dataframe = time_adjusted_dataframe[
                            time_adjusted_dataframe['financial_market_PK'].isin(non_us_pks)
                        ].reset_index(drop=True)
                        
                    
                        time_adjusted_dataframe = time_adjusted_dataframe.drop_duplicates(
                            subset=['financial_market_PK'],
                            keep='first'
                        )
                        print(time_adjusted_dataframe)
                        for i in range(len(time_adjusted_dataframe)):
                            if time_adjusted_dataframe['notes'][i] == "":
                                time_adjusted_dataframe['notes'][i] = "-"


                        table_name = '''"dyTRADE".financial_market_session_time_log'''

                    
                        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
                        database = 'dyDATA_new' 
                        username = 'postgres'
                        password = 'Proc2023awsrdspostgresql'
                        port_id = 5432
                    
                                
                        for i in range(len(time_adjusted_dataframe)):
                            
                            print(time_adjusted_dataframe['financial_market_code'][i])
                            last_logged_date = None
                            
                            cur.execute(f'''
                                SELECT MAX("financial_market_session_time_log_utc_date")::date
                                FROM {table_name} where "financial_market_session_time_financial_market_PK"= {time_adjusted_dataframe['financial_market_PK'][i]}
                            ''')
                            result = cur.fetchone()
                            if result and result[0]:
                                last_logged_date = result[0]
                            if last_logged_date is None:
                                    last_logged_date = date.today() - timedelta(days=1)
                            else:
                                last_logged_date = last_logged_date + timedelta(days=1)
                        
                            calendar = mcal.get_calendar(time_adjusted_dataframe['financial_market_code'][i])
                        
                            market_open_and_close_times= calendar.schedule(start_date=last_logged_date,end_date=today)
                        

                            dates_to_insert=(pd.DataFrame(market_open_and_close_times.index))
                            print(dates_to_insert)

                            for target_date in dates_to_insert.iloc[:, 0]:
                    
                                target_date_str = str(target_date)
                                open_time = pd.to_datetime(time_adjusted_dataframe['local_open'][i])
                                close_time = pd.to_datetime(time_adjusted_dataframe['local_close'][i])

                                # Shift to target date
                                open_utc = open_time.replace(year=target_date.year, month=target_date.month, day=target_date.day)
                                close_utc = close_time.replace(year=target_date.year, month=target_date.month, day=target_date.day)
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
                                VALUES ({time_adjusted_dataframe['financial_market_PK'][i]},{time_adjusted_dataframe['financial_market_PK'][i]},2,'{target_date_str}','{open_utc}','{close_utc}',
                                '{time_adjusted_dataframe['notes'][i]}',{time_adjusted_dataframe['current_status'][i]})'''
                                # print(query)
                                cur.execute(query)
                                conn.commit()
                                            
                                print("The query was successful in writing the values.")
                        present_pks = set(time_adjusted_dataframe['financial_market_PK'].dropna().astype(int))
                        missing_pks = sorted(set(non_us_pks) - present_pks)

                        if missing_pks:
                            fallback_code= '24/7'
                            
                            pk_list_str = ",".join(map(str,missing_pks))

                            print(f"Missing non-US PKs (will use defaults): {missing_pks}")
                            
                        
                            query_markets = f'''
                                        SELECT "financial_market_PK", financial_market_name, financial_market_code
                                        from "dyLEARN".financial_market_list
                                        where "financial_market_PK"  IN ({pk_list_str}); 
                                    '''
                            cur.execute(query_markets)
                            markets = cur.fetchall()
                            for market in markets:
                        
                                fin_pk = market[0]
                                market_name = market[1]
                                market_code = market[2]
                                last_logged_date = None
                            
                                cur.execute(f'''
                                    SELECT MAX("financial_market_session_time_log_utc_date")::date
                                    FROM {table_name} where "financial_market_session_time_financial_market_PK"= {fin_pk}
                                ''')
                                result = cur.fetchone()
                                if result and result[0]:
                                    last_logged_date = result[0]
                                if last_logged_date is None:
                                        last_logged_date = date.today() - timedelta(days=1)
                                else:
                                    last_logged_date = last_logged_date + timedelta(days=1)

                                # Get per-market last logged date
                                

                                # Get calendar
                                try:
                                    calendar = mcal.get_calendar(market_code)
                                except :
                                    print(f"Warning: '{market_code}' not supported → using fallback '{fallback_code}'")
                                    calendar = mcal.get_calendar(fallback_code)
                                    

                                # Get dates to insert
                                schedule = calendar.schedule(start_date=last_logged_date, end_date=today)
                                dates_to_insert = schedule.index.date

                                if len(dates_to_insert) == 0 :
                                    print(f"No dates to insert for {market_name}")
                                    continue

                                query_defaults = f'''
                                    SELECT 
                                    "financial_market_session_default_OM_opening_UTC_time",
                                    "financial_market_session_default_OM_closure_UTC_time"
                                    FROM "dyTRADE".financial_market_session_default_val
                                    WHERE "financial_market_session_default_financial_market_PK" = %s
                                '''
                                cur.execute(query_defaults, (fin_pk,))
                                defaults = cur.fetchone()
                                if not defaults:
                                    print(f"No defaults for {market_name}")
                                    continue

                                reg_open_time, reg_close_time = defaults
                                query=f'''SELECT {country_timezone_region_city_name} 
                                    from "dyGEO".timezone_region_city_list
                                    where {country_timezone_region_city_PK}='{timezone_region_city_PK}'; '''
                                    # print(query)
                                cur.execute(query)
                                result = cur.fetchall()
                                print(result[0])
                                # country_zone = str(result[0][0])
                                # res = country_zone.split("-", 1)
                                zone = result[0][0]
                                def is_dst(date_obj, tz_name=zone):
                                    tz = ZoneInfo(tz_name)
                                    dt = datetime(
                                        date_obj.year,
                                        date_obj.month,
                                        date_obj.day,
                                        tzinfo=tz
                                    )
                                    return dt.dst() != timedelta(0)

                                for target_date_only in dates_to_insert:
                                    target_date_str = target_date_only.isoformat()
                                    dst_active= is_dst(target_date_only)
                                

                                    # Combine times with date (times are already UTC with tz)
                                    def combine_with_date(t):
                                        if t is None:
                                            return None
                                        dt=datetime.combine(target_date_only, t)
                                        if dst_active:
                                            dt -= timedelta(hours=1)
                                        return dt.replace(tzinfo=timezone.utc)

                                
                                    reg_open = combine_with_date(reg_open_time)
                                    reg_close = combine_with_date(reg_close_time)
                                

                                    status = 1  # Assume open on trading day
                                    table_name = '''"dyTRADE".financial_market_session_time_log'''

                                    id= '''"financial_market_session_time_ID"'''
                                    financial_market_PK= '''"financial_market_session_time_financial_market_PK"'''
                                    session_time_log_utc_date= '''"financial_market_session_time_log_utc_date"'''
                                    opening_UTC_time= '''"financial_market_session_time_opening_UTC_time"'''
                                    closure_UTC_time= '''"financial_market_session_time_closure_UTC_time"'''
                                    market_status= '''"financial_market_session_time_activity_status"'''
                                    market_session_PK =  '''"financial_market_session_time_market_session_PK"'''


                                    # Insert regular (2)
                                    if reg_open and reg_close:
                                        query = f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status})
                                        VALUES ({fin_pk},{fin_pk},2,'{target_date_str}','{reg_open}','{reg_close}',{status})'''
                                        cur.execute(query)
                                        conn.commit()
                                print("default values for the missing pk are inserted")

                        
                        else:
                            print("All requested non-US PKs present — no defaults needed.")

                        

                        
                    else:
                        pk_list_str = ",".join(map(str,non_us_pks))
                        utc_tz = ZoneInfo("UTC")
                        fallback_code='24/7'

                        
                        query_markets = f'''
                                    SELECT "financial_market_PK", financial_market_name, financial_market_code
                                    from "dyLEARN".financial_market_list
                                    where "financial_market_PK"  IN ({pk_list_str}
                                    ); 
                                '''
                        cur.execute(query_markets)
                        markets = cur.fetchall()
                        for market in markets:
                    
                            fin_pk = market[0]
                            market_name = market[1]
                            market_code = market[2]
                            last_logged_date = None
                        
                            cur.execute(f'''
                                SELECT MAX("financial_market_session_time_log_utc_date")::date
                                FROM {table_name} where "financial_market_session_time_financial_market_PK"= {fin_pk}
                            ''')
                            result = cur.fetchone()
                            if result and result[0]:
                                last_logged_date = result[0]
                            if last_logged_date is None:
                                    last_logged_date = date.today() - timedelta(days=1)
                            else:
                                last_logged_date = last_logged_date + timedelta(days=1)

                            # Get per-market last logged date
                            

                            # Get calendar
                            try:
                                calendar = mcal.get_calendar(market_code)
                            except:
                                print(f"Warning: '{market_code}' not supported → using fallback '{fallback_code}'")
                                calendar = mcal.get_calendar(fallback_code)

                            # Get dates to insert
                            schedule = calendar.schedule(start_date=last_logged_date, end_date=today)
                            dates_to_insert = schedule.index.date

                            if len(dates_to_insert) == 0 :
                                print(f"No dates to insert for {market_name}")
                                continue

                
                            query_defaults = '''
                                SELECT 
                                    "financial_market_session_default_OM_opening_UTC_time",
                                    "financial_market_session_default_OM_closure_UTC_time"
                                FROM "dyTRADE".financial_market_session_default_val
                                WHERE "financial_market_session_default_financial_market_PK" = %s
                            '''
                            cur.execute(query_defaults, (fin_pk,))
                            defaults = cur.fetchone()
                            if not defaults:
                                print(f"No defaults for {market_name}")
                                continue

                            reg_open_time, reg_close_time = defaults
                            query=f'''SELECT {country_timezone_region_city_name} 
                                from "dyGEO".timezone_region_city_list
                                where {country_timezone_region_city_PK}='{timezone_region_city_PK}'; '''
                                # print(query)
                            cur.execute(query)
                            result = cur.fetchall()
                            print(result[0])
                            # country_zone = str(result[0][0])
                            # res = country_zone.split("-", 1)
                            zone = result[0][0]
                            def is_dst(date_obj, tz_name=zone):
                                tz = ZoneInfo(tz_name)
                                dt = datetime(
                                    date_obj.year,
                                    date_obj.month,
                                    date_obj.day,
                                    tzinfo=tz
                                )
                                return dt.dst() != timedelta(0)

                            for target_date_only in dates_to_insert:
                                target_date_str = target_date_only.isoformat()
                                dst_active= is_dst(target_date_only)
                            

                                # Combine times with date (times are already UTC with tz)
                                def combine_with_date(t):
                                    if t is None:
                                        return None
                                    dt=datetime.combine(target_date_only, t)
                                    if dst_active:
                                        dt -= timedelta(hours=1)
                                    return dt.replace(tzinfo=timezone.utc)

                            
                                reg_open = combine_with_date(reg_open_time)
                                reg_close = combine_with_date(reg_close_time)
                            

                                status = 1 
                                table_name = '''"dyTRADE".financial_market_session_time_log'''

                                id= '''"financial_market_session_time_ID"'''
                                financial_market_PK= '''"financial_market_session_time_financial_market_PK"'''
                                session_time_log_utc_date= '''"financial_market_session_time_log_utc_date"'''
                                opening_UTC_time= '''"financial_market_session_time_opening_UTC_time"'''
                                closure_UTC_time= '''"financial_market_session_time_closure_UTC_time"'''
                                market_status= '''"financial_market_session_time_activity_status"'''
                                market_session_PK =  '''"financial_market_session_time_market_session_PK"'''


                                # Insert regular (2)
                                if reg_open and reg_close:
                                    query = f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status})
                                    VALUES ({fin_pk},{fin_pk},2,'{target_date_str}','{reg_open}','{reg_close}',{status})'''
                                    cur.execute(query)
                                    conn.commit()
                            print("insert the data using the default values")

                if us_pks:
                    pk_list_str = ",".join(map(str,us_pks))
                    delete_query = f"""
                        DELETE FROM {table_name}
                        WHERE financial_market_session_time_log_utc_date = '{today}'
                        AND "financial_market_session_time_financial_market_PK" IN ({pk_list_str})
                    """ 
                    


                    def apicalls_get_data():
                        global data
                    
                        # url = 'https://api.apicalls.io/v2/markets/market-info'
                        url= 'https://api.steadyapi.com/v2/markets/market-info'
                        headers = {
                        'Authorization': 'Bearer 539|5d9M5TONvuHKNOVYKwrWKT88fsivCirNPSc9nXXf'
                        }
                        try:
                            response = requests.request('GET', url, headers=headers)
                            data = response.json()
                            
                            if data is None or ('body' not in data):
                                raise ValueError("No 'body' in response data")
                            dict = data['body']
                            dataframe = pd.DataFrame(list(dict.items()))
                            dataframe =  dataframe.transpose()
                            return dataframe

                        except Exception as e:
                            print(f"APICalls has failed ({e}), so now going with default values")
                            return None
                    
                    
                    dataframe = apicalls_get_data()
                    if dataframe is not None:
                        print("got the data from API")
                        cleaned_df = dataframe.copy()

                    
                

                        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
                        database = 'dyDATA_new' 
                        username = 'postgres'
                        password = 'Proc2023awsrdspostgresql'
                        port_id = 5432

                        cleaned_df. columns=cleaned_df. iloc[0]
                        cleaned_df = (cleaned_df.drop(0))
                        cleaned_df.reset_index()
                        cleaned_df['country'][1] = 'US'
                        # print(cleaned_df)


                        time_cols = list(cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'Time')])
                        date_cols = (list([cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'Date')]]))

                        for col in time_cols:
                            cleaned_df[col] = pd.to_datetime(cleaned_df[col])#, format='%Y-%m-%d %H:%M:%S') #line 17
                        
                        for col in date_cols:
                            cleaned_df[col] = cleaned_df[col] + ' 00:00 AM ET'
                            print(cleaned_df[col])
                            cleaned_df[col] = cleaned_df[col].apply(pd.to_datetime)#, format="%b %d, %Y", errors="coerce").dt.strftime("%d.%m.%Y")


                        cleaned_df.assign(financial_market_name="")
                        cleaned_df.assign(financial_market_code="")
                        cleaned_df.assign(financial_market_PK="")
                        # print("Printing cleaned df", cleaned_df)
                        market_df = pd.DataFrame()
                        for row in cleaned_df.index:
                            if row == 0:
                                continue
                            
                            
                        
                            query=f'''SELECT "PK"
                            from "dyGEO".country_list_view 
                            where alpha_2_code='{cleaned_df['country'][row]}'; ''' # The country name should be US and not U.S.
                            # print(query)
                            cur.execute(query)
                            result = cur.fetchall()
                            print("counrty_PK = ", result)
     
                           
                            for pk in result:
                                query=f'''SELECT "timezone_region_city_PK"
                                from "dyGEO".country_timezone_region_city_rel_view 
                                where "country_PK" = {pk[0]}; ''' # The counrty name should be US and not U.S.
                                # print(query)
                                cur.execute(query)
                                timezone_region_city_PK_list = cur.fetchall()
                                print("timezone_region_city_PK_list: ", timezone_region_city_PK_list)
                           
                           
                            for tz_PK in range(len(timezone_region_city_PK_list)):
                                query=f''' SELECT "financial_market_PK", financial_market_name,financial_market_code
                                from "dyLEARN".financial_market_list 
                                where "financial_market_timezone_region_city_PK" ='{timezone_region_city_PK_list[tz_PK][0]}'; ''' # The counrty name should be US and not U.S.
                                # print(query)
                                cur.execute(query)
                                markets = cur.fetchall()
                                num = row
                                for market in markets:
                                    financial_market_PK = market[0]
                                    financial_market_name = market[1]
                                    financial_market_code=market[2]
                                    data_dict = {'financial_market_name': financial_market_name,
                                                    'financial_market_code': financial_market_code,
                                                    'financial_market_PK': financial_market_PK,
                                                    'country':cleaned_df['country'][row], 
                                                    'marketIndicator':cleaned_df['marketIndicator'][row],
                                                'uiMarketIndicator':cleaned_df['uiMarketIndicator'][row],
                                                'marketCountDown':cleaned_df['marketCountDown'][row],
                                                'preMarketOpeningTime':cleaned_df['preMarketOpeningTime'][row], 
                                                'preMarketClosingTime':cleaned_df['preMarketClosingTime'][row],
                                                'marketOpeningTime':cleaned_df['marketOpeningTime'][row], 
                                                'marketClosingTime':cleaned_df['marketClosingTime'][row],
                                                'afterHoursMarketOpeningTime':cleaned_df['afterHoursMarketOpeningTime'][row],
                                                'afterHoursMarketClosingTime':cleaned_df['afterHoursMarketClosingTime'][row],
                                                'previousTradeDate':cleaned_df['previousTradeDate'][row], 
                                                'nextTradeDate':cleaned_df['nextTradeDate'][row],
                                                'isBusinessDay':cleaned_df['isBusinessDay'][row],
                                                'mrktStatus':cleaned_df['mrktStatus'][row],
                                                'mrktCountDown':cleaned_df['mrktCountDown'][row] }
                                    temp_df = pd.DataFrame(data_dict, index=[0])
                                    # num += 1
                                    market_df = pd.concat([market_df,temp_df], ignore_index=True)
                                # except:
                            #     raise Exception('Could not fetch the market name')
                            # finally:
                        
                    
                        apicalls_time_adjusted_dataframe = market_df
                        apicalls_time_adjusted_dataframe = apicalls_time_adjusted_dataframe[
                            apicalls_time_adjusted_dataframe['financial_market_PK'].isin(us_pks)
                        ].reset_index(drop=True)
                    
                        this_day = str(date.today())


                        hostname = 'database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com'
                        database = 'dyDATA_new' 
                        username = 'postgres'
                        password = 'Proc2023awsrdspostgresql'
                        port_id = 5432

                        # "financial_market_opening_status_UUID"

                        table_name = '''"dyTRADE".financial_market_session_time_log'''

                        #Commenting for time till market_PK not ready apicalls_time_adjusted_dataframe['financial_market_PK'][i],

                        fallback_code="NASDAQ"
                        local_tz = ZoneInfo("America/New_York")
                        utc_tz = ZoneInfo("UTC")
                        # today = date.today()
                       
                        for i in range(len(apicalls_time_adjusted_dataframe)):
                            if apicalls_time_adjusted_dataframe['mrktStatus'][i] == "Open":
                                apicalls_time_adjusted_dataframe['mrktStatus'][i]=1
                            else:
                                apicalls_time_adjusted_dataframe['mrktStatus'][i]=0
                            market_code=apicalls_time_adjusted_dataframe['financial_market_code'][i]
                            print(market_code)
                            # calendar = mcal.get_calendar(apicalls_time_adjusted_dataframe['financial_market_code'][i])
                            try:
                                # calendar = mcal.get_calendar("NASDAQ")
                                calendar = mcal.get_calendar(market_code)
                            except RuntimeError as e:
                                print(f"Warning: '{market_code}' not supported → using fallback '{fallback_code}'")
                                calendar = mcal.get_calendar(fallback_code)
                            last_logged_date = None
                            cur.execute(f'''
                            SELECT MAX("financial_market_session_time_log_utc_date")::date
                            FROM {table_name} where "financial_market_session_time_financial_market_PK"= {apicalls_time_adjusted_dataframe['financial_market_PK'][i]}
                            ''')
                            result = cur.fetchone()

                            last_logged_date = result[0] if result[0] else date.today() - timedelta(days=1)
                            last_logged_date = last_logged_date + timedelta(days=1)
                            # today = datetime.now(timezone.utc).date()
                            
                            
                            market_open_and_close_times= calendar.schedule(start_date=last_logged_date,end_date=today)
                            

                            dates_to_insert=(pd.DataFrame(market_open_and_close_times.index))
                            print(dates_to_insert)
                            full_schedule = calendar.schedule(
                                    start_date= last_logged_date - timedelta(days=1),  
                                    end_date=today +timedelta(days=10)   
                                )
                            all_trading_dates = full_schedule.index.date
                            next_trading_day_map = {}
                            for j in range(len(all_trading_dates) - 1):
                                next_trading_day_map[all_trading_dates[j]] = all_trading_dates[j + 1]
                            for target_date in dates_to_insert.iloc[:, 0]:
                                target_date_str = str(target_date)
                                target_date_only = target_date.date()
                                next_trading_day=next_trading_day_map[target_date_only]
                                # next_trading_day_str = f"{next_trading_day.isoformat()} 00:00:00+00"
                                next_trading_day_str = next_trading_day.isoformat()
                                
                                open_time=pd.to_datetime(apicalls_time_adjusted_dataframe['marketOpeningTime'][i])
                                close_time=pd.to_datetime(apicalls_time_adjusted_dataframe['marketClosingTime'][i])
                                open_utc = open_time.replace(year=target_date.year, month=target_date.month, day=target_date.day)
                                local  = str(open_utc)
                                # print ("Got local open time: ", local)
                            

                                dt = datetime.strptime(local,"%Y-%m-%d %H:%M:%S")
                                dt = dt.replace(tzinfo=local_tz)
                                dt_open_utc = dt.astimezone(utc_tz)
                                dt_open_utc = pd.Timestamp(dt_open_utc)
                                open_utc = dt_open_utc.tz_convert('utc')
                                close_utc = close_time.replace(year=target_date.year, month=target_date.month, day=target_date.day)
                                local  = str(close_utc)
                                # print ("Got local close time: ", local)
                            

                                dt = datetime.strptime(local,"%Y-%m-%d %H:%M:%S")
                                dt = dt.replace(tzinfo=local_tz)
                                dt_close_utc = dt.astimezone(utc_tz)
                                dt_open_utc = pd.Timestamp(dt_close_utc)
                                close_utc = dt_open_utc.tz_convert('utc')
                                

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
                                VALUES ({apicalls_time_adjusted_dataframe['financial_market_PK'][i]},{apicalls_time_adjusted_dataframe['financial_market_PK'][i]},2,'{target_date_str}','{open_utc}','{close_utc}'
                                ,{apicalls_time_adjusted_dataframe['mrktStatus'][i]},'{next_trading_day_str}')'''
                                # print(query)
                                cur.execute(query)
                                open_time=pd.to_datetime(apicalls_time_adjusted_dataframe['preMarketOpeningTime'][i])
                                close_time=pd.to_datetime(apicalls_time_adjusted_dataframe['preMarketClosingTime'][i])
                                open_utc = open_time.replace(year=target_date.year, month=target_date.month, day=target_date.day)
                                local  = str(open_utc)
                                # print ("Got local p.market open time: ", local)
                            

                                dt = datetime.strptime(local,"%Y-%m-%d %H:%M:%S")
                                dt = dt.replace(tzinfo=local_tz)
                                dt_open_utc = dt.astimezone(utc_tz)
                                dt_open_utc = pd.Timestamp(dt_open_utc)
                                open_utc = dt_open_utc.tz_convert('utc')
                                close_utc = close_time.replace(year=target_date.year, month=target_date.month, day=target_date.day)
                                local  = str(close_utc)
                                # print ("Got local p.market close time: ", local)
                            

                                dt = datetime.strptime(local,"%Y-%m-%d %H:%M:%S")
                                dt = dt.replace(tzinfo=local_tz)
                                dt_close_utc = dt.astimezone(utc_tz)
                                dt_open_utc = pd.Timestamp(dt_close_utc)
                                close_utc = dt_open_utc.tz_convert('utc')
                            
                                # Adding the pre Market data
                                query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                                VALUES ({apicalls_time_adjusted_dataframe['financial_market_PK'][i]},{apicalls_time_adjusted_dataframe['financial_market_PK'][i]},1,'{target_date_str}','{open_utc}','{close_utc}'
                                ,{apicalls_time_adjusted_dataframe['mrktStatus'][i]}, '{next_trading_day_str}')'''
                                # print(query)
                                cur.execute(query)
                                open_time=pd.to_datetime(apicalls_time_adjusted_dataframe['afterHoursMarketOpeningTime'][i])
                                close_time=pd.to_datetime(apicalls_time_adjusted_dataframe['afterHoursMarketClosingTime'][i])
                                open_utc = open_time.replace(year=target_date.year, month=target_date.month, day=target_date.day)
                                local  = str(open_utc)
                                # print ("Got local AH open time: ", local)
                            

                                dt = datetime.strptime(local,"%Y-%m-%d %H:%M:%S")
                                dt = dt.replace(tzinfo=local_tz)
                                dt_open_utc = dt.astimezone(utc_tz)
                                dt_open_utc = pd.Timestamp(dt_open_utc)
                                open_utc = dt_open_utc.tz_convert('utc')
                                close_utc = close_time.replace(year=target_date.year, month=target_date.month, day=target_date.day)
                                local  = str(close_utc)
                                # print ("Got local AH close time: ", local)
                            

                                dt = datetime.strptime(local,"%Y-%m-%d %H:%M:%S")
                                dt = dt.replace(tzinfo=local_tz)
                                dt_close_utc = dt.astimezone(utc_tz)
                                dt_open_utc = pd.Timestamp(dt_close_utc)
                                close_utc = dt_open_utc.tz_convert('utc')
                                

                                # Adding the values of after Market data
                                query=f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                                VALUES ({apicalls_time_adjusted_dataframe['financial_market_PK'][i]},{apicalls_time_adjusted_dataframe['financial_market_PK'][i]},3,'{target_date_str}','{open_utc}','{close_utc}'
                                ,{apicalls_time_adjusted_dataframe['mrktStatus'][i]}, '{next_trading_day_str}')'''
                                # print(query)
                                cur.execute(query)
                        print("The query was successful in writing the values for apicalls.io")
                    
                    
                        present_pks = set(apicalls_time_adjusted_dataframe['financial_market_PK'].dropna().astype(int))
                        missing_pks = sorted(set(us_pks) - present_pks)
                        if missing_pks:
                            fallback_code="NASDAQ"
                            local_tz = ZoneInfo("America/New_York")
                            utc_tz = ZoneInfo("UTC")
                            today = date.today()
               
                            
                            query_markets = f'''
                                        SELECT "financial_market_PK", financial_market_name, financial_market_code
                                        from "dyLEARN".financial_market_list
                                        where "financial_market_PK" in ({missing_pks}
                                        );
                                    '''
                            cur.execute(query_markets)
                            markets = cur.fetchall()
                            for market in markets:
                        
                                fin_pk = market[0]
                                market_name = market[1]
                                market_code = market[2]
                                last_logged_date = None

                                # Get per-market last logged date
                                query_last_date = f'''
                                    SELECT MAX("financial_market_session_time_log_utc_date")::date
                                    FROM {table_name}
                                    WHERE "financial_market_session_time_financial_market_PK" = {fin_pk}
                                '''
                                cur.execute(query_last_date)
                                result = cur.fetchone()
                                last_logged_date = result[0] if result[0] else date.today() - timedelta(days=1)
                                last_logged_date = last_logged_date + timedelta(days=1)
                                # last_logged_date=date(2026,8,17)

                                # Get calendarpython3 
                                try:
                                    calendar = mcal.get_calendar(market_code)
                                except:
                                    print(f"Warning: '{market_code}' not supported → using fallback '{fallback_code}'")
                                    calendar = mcal.get_calendar(fallback_code)

                                # Get dates to insert
                                schedule = calendar.schedule(start_date=last_logged_date, end_date=today)
                                dates_to_insert = schedule.index.date

                                if len(dates_to_insert) == 0 :
                                    print(f"No dates to insert for {market_name}")
                                    continue

                                # Get next trading day map
                                full_schedule = calendar.schedule(
                                    start_date=last_logged_date - timedelta(days=1),
                                    end_date=today + timedelta(days=10)
                                )
                                all_trading_dates = full_schedule.index.date
                                next_trading_day_map = {}
                                for j in range(len(all_trading_dates) - 1):
                                    next_trading_day_map[all_trading_dates[j]] = all_trading_dates[j + 1]

                                # Get default times
                                query_defaults = '''
                                    SELECT 
                                        "financial_market_session_default_PM_opening_UTC_time",
                                        "financial_market_session_default_PM_closure_UTC_time",
                                        "financial_market_session_default_OM_opening_UTC_time",
                                        "financial_market_session_default_OM_closure_UTC_time",
                                        "financial_market_session_default_AH_opening_UTC_time",
                                        "financial_market_session_default_AH_closure_UTC_time"
                                    FROM "dyTRADE".financial_market_session_default_val
                                    WHERE "financial_market_session_default_financial_market_PK" = %s
                                '''
                                cur.execute(query_defaults, (fin_pk,))
                                defaults = cur.fetchone()
                                if not defaults:
                                    print(f"No defaults for {market_name}")
                                    continue

                                pre_open_time, pre_close_time, reg_open_time, reg_close_time, ah_open_time, ah_close_time = defaults
                                def is_dst(date_obj, tz_name='America/New_York'):
                                    tz = ZoneInfo(tz_name)
                                    dt = datetime(
                                        date_obj.year,
                                        date_obj.month,
                                        date_obj.day,
                                        tzinfo=tz
                                    )
                                    return dt.dst() != timedelta(0)

                                for target_date_only in dates_to_insert:
                                    target_date_str = target_date_only.isoformat()
                                    next_trading_day = next_trading_day_map.get(target_date_only, target_date_only + timedelta(days=1))
                                    next_trading_day_str = next_trading_day.isoformat()
                                    dst_active = is_dst(target_date_only)

                                    # Combine times with date (times are already UTC with tz)
                                    def combine_with_date(t):
                                        if t is None:
                                            return None
                                        dt=datetime.combine(target_date_only, t)
                                        if dst_active:
                                            dt -= timedelta(hours=1)
                                        return dt.replace(tzinfo=timezone.utc)

                                    pre_open = combine_with_date(pre_open_time)
                                    pre_close = combine_with_date(pre_close_time)
                                    reg_open = combine_with_date(reg_open_time)
                                    reg_close = combine_with_date(reg_close_time)
                                    ah_open = combine_with_date(ah_open_time)
                                    ah_close = combine_with_date(ah_close_time)
                                    if ah_close and ah_open and ah_close < ah_open:
                                        ah_close += timedelta(days=1)

                                    status = 1  # Assume open on trading day
                                    table_name = '''"dyTRADE".financial_market_session_time_log'''

                                    id= '''"financial_market_session_time_ID"'''
                                    financial_market_PK= '''"financial_market_session_time_financial_market_PK"'''
                                    session_time_log_utc_date= '''"financial_market_session_time_log_utc_date"'''
                                    opening_UTC_time= '''"financial_market_session_time_opening_UTC_time"'''
                                    closure_UTC_time= '''"financial_market_session_time_closure_UTC_time"'''
                                    # session_time_note= '''"financial_market_session_time_note"'''
                                    market_status= '''"financial_market_session_time_activity_status"'''
                                    market_session_PK =  '''"financial_market_session_time_market_session_PK"'''
                                    next_trade_session_date = '''"financial_market_session_next_market_trading_session_date"'''


                                    # Insert pre-market (1)
                                    if pre_open and pre_close:
                                        query = f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                                        VALUES ({fin_pk},{fin_pk},1,'{target_date_str}','{pre_open}','{pre_close}',{status}, '{next_trading_day_str}')'''
                                        cur.execute(query)

                                    # Insert regular (2)
                                    if reg_open and reg_close:
                                        query = f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                                        VALUES ({fin_pk},{fin_pk},2,'{target_date_str}','{reg_open}','{reg_close}',{status}, '{next_trading_day_str}')'''
                                        cur.execute(query)

                                    # Insert after-hours (3)
                                    if ah_open and ah_close:
                                        query = f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                                        VALUES ({fin_pk},{fin_pk},3,'{target_date_str}','{ah_open}','{ah_close}',{status}, '{next_trading_day_str}')'''
                                        cur.execute(query)

                        
                    else:
                        fallback_code="NASDAQ"
                        local_tz = ZoneInfo("America/New_York")
                        utc_tz = ZoneInfo("UTC")
                        today = date.today()
                        # today=date(2026,8,18)
                 
                        pk_list_str = ",".join(map(str,us_pks))
                
                        query_markets = f'''
                                    SELECT "financial_market_PK", financial_market_name, financial_market_code
                                    from "dyLEARN".financial_market_list
                                    where "financial_market_PK" in ({pk_list_str}
                                    );
                                '''
                        cur.execute(query_markets)
                        markets = cur.fetchall()
                        for market in markets:
                    
                            fin_pk = market[0]
                            market_name = market[1]
                            market_code = market[2]
                            last_logged_date = None

                            # Get per-market last logged date
                            query_last_date = f'''
                                SELECT MAX("financial_market_session_time_log_utc_date")::date
                                FROM {table_name}
                                WHERE "financial_market_session_time_financial_market_PK" = {fin_pk}
                            '''
                            cur.execute(query_last_date)
                            result = cur.fetchone()
                            last_logged_date = result[0] if result[0] else date.today() - timedelta(days=1)
                            last_logged_date = last_logged_date + timedelta(days=1)
                            # last_logged_date=date(2026,8,17)

                            # Get calendarpython3 
                            try:
                                calendar = mcal.get_calendar(market_code)
                            except:
                                print(f"Warning: '{market_code}' not supported → using fallback '{fallback_code}'")
                                calendar = mcal.get_calendar(fallback_code)

                            # Get dates to insert
                            schedule = calendar.schedule(start_date=last_logged_date, end_date=today)
                            dates_to_insert = schedule.index.date

                            if len(dates_to_insert) == 0 :
                                print(f"No dates to insert for {market_name}")
                                continue

                            # Get next trading day map
                            full_schedule = calendar.schedule(
                                start_date=last_logged_date - timedelta(days=1),
                                end_date=today + timedelta(days=10)
                            )
                            all_trading_dates = full_schedule.index.date
                            next_trading_day_map = {}
                            for j in range(len(all_trading_dates) - 1):
                                next_trading_day_map[all_trading_dates[j]] = all_trading_dates[j + 1]

                            # Get default times
                            query_defaults = '''
                                SELECT 
                                    "financial_market_session_default_PM_opening_UTC_time",
                                    "financial_market_session_default_PM_closure_UTC_time",
                                    "financial_market_session_default_OM_opening_UTC_time",
                                    "financial_market_session_default_OM_closure_UTC_time",
                                    "financial_market_session_default_AH_opening_UTC_time",
                                    "financial_market_session_default_AH_closure_UTC_time"
                                FROM "dyTRADE".financial_market_session_default_val
                                WHERE "financial_market_session_default_financial_market_PK" = %s
                            '''
                            cur.execute(query_defaults, (fin_pk,))
                            defaults = cur.fetchone()
                            if not defaults:
                                print(f"No defaults for {market_name}")
                                continue

                            pre_open_time, pre_close_time, reg_open_time, reg_close_time, ah_open_time, ah_close_time = defaults
                            def is_dst(date_obj, tz_name='America/New_York'):
                                tz = ZoneInfo(tz_name)
                                dt = datetime(
                                    date_obj.year,
                                    date_obj.month,
                                    date_obj.day,
                                    tzinfo=tz
                                )
                                return dt.dst() != timedelta(0)

                            for target_date_only in dates_to_insert:
                                target_date_str = target_date_only.isoformat()
                                next_trading_day = next_trading_day_map.get(target_date_only, target_date_only + timedelta(days=1))
                                next_trading_day_str = next_trading_day.isoformat()
                                dst_active = is_dst(target_date_only)

                                # Combine times with date (times are already UTC with tz)
                                def combine_with_date(t):
                                    if t is None:
                                        return None
                                    dt=datetime.combine(target_date_only, t)
                                    if dst_active:
                                        dt -= timedelta(hours=1)
                                    return dt.replace(tzinfo=timezone.utc)

                                pre_open = combine_with_date(pre_open_time)
                                pre_close = combine_with_date(pre_close_time)
                                reg_open = combine_with_date(reg_open_time)
                                reg_close = combine_with_date(reg_close_time)
                                ah_open = combine_with_date(ah_open_time)
                                ah_close = combine_with_date(ah_close_time)
                                if ah_close and ah_open and ah_close < ah_open:
                                    ah_close += timedelta(days=1)

                                status = 1  # Assume open on trading day
                                table_name = '''"dyTRADE".financial_market_session_time_log'''

                                id= '''"financial_market_session_time_ID"'''
                                financial_market_PK= '''"financial_market_session_time_financial_market_PK"'''
                                session_time_log_utc_date= '''"financial_market_session_time_log_utc_date"'''
                                opening_UTC_time= '''"financial_market_session_time_opening_UTC_time"'''
                                closure_UTC_time= '''"financial_market_session_time_closure_UTC_time"'''
                                # session_time_note= '''"financial_market_session_time_note"'''
                                market_status= '''"financial_market_session_time_activity_status"'''
                                market_session_PK =  '''"financial_market_session_time_market_session_PK"'''
                                next_trade_session_date = '''"financial_market_session_next_market_trading_session_date"'''


                                # Insert pre-market (1)
                                if pre_open and pre_close:
                                    query = f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                                    VALUES ({fin_pk},{fin_pk},1,'{target_date_str}','{pre_open}','{pre_close}',{status}, '{next_trading_day_str}')'''
                                    cur.execute(query)

                                # Insert regular (2)
                                if reg_open and reg_close:
                                    query = f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                                    VALUES ({fin_pk},{fin_pk},2,'{target_date_str}','{reg_open}','{reg_close}',{status}, '{next_trading_day_str}')'''
                                    cur.execute(query)

                                # Insert after-hours (3)
                                if ah_open and ah_close:
                                    query = f'''INSERT INTO {table_name} ({id},{financial_market_PK},{market_session_PK},{session_time_log_utc_date},{opening_UTC_time},{closure_UTC_time},{market_status}, {next_trade_session_date})
                                    VALUES ({fin_pk},{fin_pk},3,'{target_date_str}','{ah_open}','{ah_close}',{status}, '{next_trading_day_str}')'''
                                    cur.execute(query)
                    print("data is inserted for US markets")

            
                response = {
                    'success':True,
                    'errors':[]
                }
                conn.commit()
        return response
        
        
    except Exception as error:
        print('Error: ', error)
        response = {
            'success':False,
            'errors': [str(error)]
        }
        return response



if __name__=='__main__':
    resolve_FMU(None,None,None)