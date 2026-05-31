#!/bin/bash

# FETCH THE DIRECTORY WHERE THE API FILES ARE LOCATED / WORKING DIRECTORY
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Fetch the port number from a Python script in a specific directory

# TO MAKE THIS SCRIPT WORK 
# In the settings file in the api folder of the root directory add a new variable with the name SERVER PORT (PORT FOR THE API) OR  CHANGE THE PATHS IN THE  BELOW LINE 
PORT=$(python3 -c "import sys; sys.path.insert(0, '$SCRIPT_DIR'); import settings; print(settings.SERVER_PORT)")

# Sets the FLASK_APP environment variable.

# ADD THE VARIABLE SCRIPT_DIR INSTEAD OF CHANGING THE PATH 
export FLASK_APP=$SCRIPT_DIR/app.py

# Ensures the Flask application is executable.
# ADD THE VARIABLE SCRIPT_DIR INSTEAD OF CHANGING THE PATH 
chmod +x $SCRIPT_DIR/app.py

# Runs the Flask application.
# ADD THE VARIABLE SCRIPT_DIR AND DYNAMIC PORT NMBER  INSTEAD OF CHANGING THE PATH  AND THE PORT
nohup flask run --debug --host=0.0.0.0 --port="$PORT" > $SCRIPT_DIR/flask.log 2>&1 &  