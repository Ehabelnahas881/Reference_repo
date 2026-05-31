def FMU_apicalls():
    import pandas as pd
    import requests
    import time
    import datetime

    import pytz
    from datetime import datetime, timezone
    from backports.zoneinfo import ZoneInfo



    import psycopg2
    import psycopg2.extras
    from psycopg2.extensions import AsIs

    from datetime import datetime, timezone

    def get_data():
        global data
        url = 'https://apicalls.io/api/v2/markets/market-info'
        headers = {
        'Authorization': 'Bearer 539|5d9M5TONvuHKNOVYKwrWKT88fsivCirNPSc9nXXf'
        }

        response = requests.request('GET', url, headers=headers)
        data = response.json()
        print(data)

        dict = data['body']
        dataframe = pd.DataFrame(list(dict.items()))
        dataframe =  dataframe.transpose()

        return dataframe

    dataframe = get_data()
    cleaned_df = dataframe.copy()

    def correct_date_time(cleaned_df):

        #Creatiung the columns based on the names recieveded from the 
        cleaned_df. columns=cleaned_df. iloc[0]
        cleaned_df = (cleaned_df.drop(0))
        cleaned_df.reset_index()
            
        # Changing the time only values into datetime
        # cleaned_df['local_open'].apply(pd.Timestamp)
        # cleaned_df['local_close'].apply(pd.Timestamp)

        # Get region data from table
        hostname ="database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com" 
        database="dyDATA_new" 
        username='postgres'
        pwd='Proc2023awsrdspostgresql'
        port_id=5432

        table_name = '"dyLEARN".financial_market_list'

        # Below code is to add Date, but in this case it is already added so not required.
        # cleaned_df['local_open'] = pd.to_datetime(cleaned_df['local_open'])
        # cleaned_df['local_close'] = pd.to_datetime(cleaned_df['local_close'])


        # Separating markets of a region.
        # for i in range(len(cleaned_df)):
        #     # if cleaned_df['primary_exchanges'][i].find(',') == 0:
        #     cleaned_df['primary_exchanges'][i] = cleaned_df['primary_exchanges'][i].split(',')
            
        # cleaned_df = cleaned_df.explode(column = 'primary_exchanges', ignore_index=True)

        

        # this is the temporary code till the timezones table is ready,
        # you can skip it and uncomment the results QL query

        # result = ['IST', 'CET', 'EET', 'GMT', 'ATZ', 'BST', 'WET', 'EST', 'AEST', 'CAT', 
        #           'AFT', 'CST', 'PST', 'MST', 'AST', 'NST', 'NDT', 'ADT', 'EDT', 'CDT', 
        #           'MDT', 'PDT', 'WAT', 'NFT', 'MUT', 'MSK']

        time_cols = list(cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'Time')])
        date_cols = (list([cleaned_df.columns[cleaned_df.columns.str.contains(pat = 'Date')]]))

        for col in time_cols:
            cleaned_df[col] = pd.to_datetime(cleaned_df[col]).dt.strftime('%Y-%m-%d %H:%M:%S')
            str(cleaned_df[col])


        for i in range(1,len(cleaned_df)):


            # #Adding neccessary columns to the dataframe like PK and ID
            # with psycopg2.connect(host=hostname,dbname=database,user=username,password=pwd,port=port_id) as conn:
            #     with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            #         cur.execute(f'''SELECT financial_market_PK, financial_market_ID, timezone 
            #                     FROM {table_name}where WHERE 
            #                     financial_market_code={cleaned_df['primary_exchanges']} or 
            #                     financial_market_name={cleaned_df['primary_exchanges']}''')
            #         result = cur.fetchall()
            # cleaned_df['financial_market_PK'][i] = result[0]
            # cleaned_df['financial_market_ID'][i] = result[1]


            # Time correction to UTC    


            for col in time_cols:
                local_time_to_be_converted = str(cleaned_df[col][i])
                print("column to be converted to utc:",col)
                # Get timezone we're trying to convert from
                local_tz = ZoneInfo("America/New_York")#(cleaned_df['region'][i])
                # UTC timezone
                utc_tz = ZoneInfo("UTC")

                # print((local_open))

                dt = datetime.strptime(local_time_to_be_converted,"%Y-%m-%d %H:%M:%S")
                dt = dt.replace(tzinfo=local_tz)
                dt_open_utc = dt.astimezone(utc_tz)
                dt_open_utc = pd.Timestamp(dt_open_utc)
                cleaned_df[col] = dt_open_utc.tz_convert('utc')
        # print(cleaned_df['preMarketopeningTime'])

        return cleaned_df

    time_adjusted_dataframe = correct_date_time(cleaned_df)
    