#!/bin/bash

# Sets the FLASK_APP environment variable.
export FLASK_APP=/kns-dta-data-kubernetes-namespace-ppd-ppd-kct/FMU-Financial_Market_Updater.Bot-API_2.0/FMU_Bot/app.py

# Ensures the Flask application is executable.
chmod +x /kns-dta-data-kubernetes-namespace-ppd-ppd-kct/FMU-Financial_Market_Updater.Bot-API_2.0/FMU_Bot/app.py

# Runs the Flask application.
nohup flask run --debug --host=0.0.0.0 --port=4574 > /kns-dta-data-kubernetes-namespace-ppd-ppd-kct/FMU-Financial_Market_Updater.Bot-API_2.0/FMU_Bot/flask.log 2>&1 &
# python3 app.py

# flask --debug run -h 0.0.0.0 -p 4574