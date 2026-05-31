import requests

API_KEY = "E8VCMZJEKYQS5Q7W"

# Function to convert currency using Alpha Vantage API
def convert_currency(amount, from_currency, to_currency):
    # Base URL for Alpha Vantage API
    url = "https://www.alphavantage.co/query"

    # Required parameters for fetching the exchange rate
    params = {
        "function": "CURRENCY_EXCHANGE_RATE",
        "from_currency": from_currency.upper(),
        "to_currency": to_currency.upper(),
        "apikey": API_KEY
    }

    try:
        # Send the GET request to the API
        response = requests.get(url, params=params)
        data = response.json()

        # Extract the exchange rate from the JSON response
        exchange_rate_info = data.get("Realtime Currency Exchange Rate", {})
        exchange_rate_str = exchange_rate_info.get("5. Exchange Rate")

        if exchange_rate_str:
            exchange_rate = float(exchange_rate_str)
            # Calculate the converted amount
            converted_amount = amount * exchange_rate
            return {
                "success": True,
                "from": from_currency.upper(),
                "to": to_currency.upper(),
                "rate": exchange_rate,
                "original_amount": amount,
                "converted_amount": converted_amount
            }
        else:
            # Handle API errors or invalid currency codes
            error_message = data.get("Error Message", "Data not found. Please check your API Key or currency symbols.")
            return {"success": False, "error": error_message}

    except Exception as e:
        return {"success": False, "error": str(e)}

# Convert 100 USD to EUR
result = convert_currency(100, "USD", "EUR")
print(result)