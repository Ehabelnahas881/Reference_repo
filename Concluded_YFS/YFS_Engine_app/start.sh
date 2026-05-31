#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=$(python3 -c "import sys; sys.path.insert(0, '$SCRIPT_DIR'); import settings; print(settings.SERVER_PORT)")
export FLASK_APP=$SCRIPT_DIR/app.py
chmod +x $SCRIPT_DIR/app.py
nohup flask run --host=0.0.0.0 --port="$PORT" > $SCRIPT_DIR/flask.log 2>&1 &