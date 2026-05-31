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
            hostname = "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com" 
            database="dyDATA_new" 
            username='postgres'
            password='Proc2023awsrdspostgresql'
            port_id=5432

            cleaned_df['local_open'] = pd.to_datetime(cleaned_df['local_open'])
            cleaned_df['local_close'] = pd.to_datetime(cleaned_df['local_close'])
            print(cleaned_df['local_open'])

            cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(lambda x: [item[1:-1] for sublist in x for item in sublist] if isinstance(x, list) else x)
            for i in range(len(cleaned_df)):
                cleaned_df['primary_exchanges'][i] = cleaned_df['primary_exchanges'][i].split(',')
            cleaned_df = cleaned_df.explode('primary_exchanges', ignore_index=True)
            cleaned_df['primary_exchanges'] = cleaned_df['primary_exchanges'].apply(lambda x: x.strip())

            time_cols = list(cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'local')])

            cleaned_df['financial_market_PK'] = ""
            cleaned_df['financial_market_ID'] = ""
            cleaned_df['financial_market_timezone_region_city_PK'] = ""
            missing_market_list = []
            for i in range(len(cleaned_df)):
                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        market = cleaned_df['primary_exchanges'][i]
                        print(f"now we in: {market}")
                        query=f'''SELECT "financial_market_PK","financial_market_ID","financial_market_name","financial_market_timezone_region_city_PK" 
                        from "dyLEARN".financial_market_list_view 
                        where financial_market_code='{market}' or 
                        financial_market_name='{market}' or 
                        financial_market_alphavantage_name='{market}'; '''
                        print(query)
                        cur.execute(query)
                        result = cur.fetchall()
                        print(result)
                        
                        if result:
                            row = result[0]
                            PK=row[0]
                            ID=row[1]
                            timezone_region_city_PK = row[3]
                            print(PK)
                            cleaned_df.at[i, 'financial_market_PK'] = PK
                            cleaned_df.at[i, 'financial_market_ID'] = ID
                            cleaned_df.at[i, 'financial_market_timezone_region_city_PK'] = timezone_region_city_PK
                        else:
                            timezone_region_city_PK = None

                        if timezone_region_city_PK is None:
                            missing_market_list.append(market)
                            print("Continuing")
                            if cleaned_df['region'][i] == 'Global':
                                cleaned_df.at[i, 'notes'] = ("This market is global")
                            else:
                                cleaned_df.at[i, 'notes'] = ("Error fetching the timezone_ID")
                            continue

                with psycopg2.connect(host=hostname,dbname=database,user=username,password=password,port=port_id) as conn:
                    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                        query=f'''SELECT "timezone_region_city_name" 
                        from "dyGEO".timezone_region_city_list
                        where "timezone_region_city_PK"=%s; '''
                        cur.execute(query, (timezone_region_city_PK,))
                        result = cur.fetchall()
                        print(result[0])
                        zone = result[0][0]

                print("now to convert the timezone")
                # Time correction to UTC
                for col in time_cols:
                    local  = str(cleaned_df[col][i])
                    print ("Got local time: ", local)
                    local_tz = ZoneInfo(zone)
                    utc_tz = ZoneInfo("UTC")

                    dt = datetime.strptime(local,"%Y-%m-%d %H:%M:%S")
                    dt = dt.replace(tzinfo=local_tz)
                    dt_open_utc = dt.astimezone(utc_tz)
                    dt_open_utc = pd.Timestamp(dt_open_utc)
                    cleaned_df.at[i, col] = dt_open_utc.tz_convert('utc')
                    print("Zone: ", zone, "Converted to UTC: ", cleaned_df.at[i, col])

            print(cleaned_df)
            print("Missing market List:", missing_market_list)

            return cleaned_df 
        
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
                    
                    query=f'''INSERT INTO {table_name} ("financial_market_session_time_financial_market_PK","financial_market_session_time_market_session_PK","financial_market_session_time_log_utc_date","financial_market_session_time_opening_UTC_time","financial_market_session_time_closure_UTC_time","financial_market_session_time_note","financial_market_session_time_activity_status")
                    VALUES (%s,%s,%s,%s,%s,%s,%s)'''
                    cur.execute(query, (time_adjusted_dataframe['financial_market_PK'][i],2,this_day,time_adjusted_dataframe['local_open'][i],time_adjusted_dataframe['local_close'][i],time_adjusted_dataframe['notes'][i],time_adjusted_dataframe['current_status'][i]))
        print("The query was successful in writing the values.")

        response = {
            'success':True,
            'errors':None
        }
        return response
        
    except Exception as error:
        print('Error: ', error)
        response = {
            'success':False,
            'errors': str(error)
        }
        return response



if __name__=='__main__':
     resolve_FMU(None, None, None)

