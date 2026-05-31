import time
import threading
import requests
from flask import Flask, request, jsonify
from ariadne import make_executable_schema, graphql_sync, ObjectType
from IDE import resolve_IDE

# 1. Define the Schema with BOTH Query and Mutation types
type_defs = """
    type Query {
        status: String
    }

    type Mutation {
        resolve_IDE(financial_asset_list: [Int], environment_pk: Int): IDEResponse
    }

    type IDEResponse {
        success: Boolean
        error: String
    }
"""

# 2. Map the Query (Health Check)
query = ObjectType("Query")
@query.field("status")
def resolve_status(*_):
    return "Local Engine is Online"

# 3. Map the Mutation (The Scraper Trigger)
mutation = ObjectType("Mutation")
mutation.set_field("resolve_IDE", resolve_IDE)

# 4. Create the schema and EXPLICITLY pass both [query, mutation]
schema = make_executable_schema(type_defs, [query, mutation])

app = Flask(__name__)

@app.route("/graphql", methods=["POST"])
def graphql_server():
    data = request.get_json()
    success, result = graphql_sync(schema, data, context_value=request, debug=app.debug)
    return jsonify(result), 200 if success else 400

# 5. Automation Logic
def auto_trigger():
    """Waits for the server to boot, then sends the start command automatically."""
    time.sleep(5)  # Increased to 5 seconds to be safe for local PC boot
    print("\n[AUTO-SYSTEM] Sending trigger to start scrapers for Assets [1, 2, 3]...")
    payload = {
        "query": "mutation { resolve_IDE(financial_asset_list: [1, 2, 3], environment_pk: 1) { success error } }"
    }
    try:
        response = requests.post("http://127.0.0.1:3989/graphql", json=payload, timeout=10)
        if response.status_code == 200:
            print("[AUTO-SYSTEM] Scrapers started successfully.")
        else:
            print(f"[AUTO-SYSTEM] Failed to start. Status: {response.status_code}")
    except Exception as e:
        print(f"[AUTO-SYSTEM] Error during auto-trigger: {e}")

if __name__ == "__main__":
    print("\n--- SCRAPER ENGINE STARTING ---")
    
    # Run the trigger in the background so it doesn't block Flask
    threading.Thread(target=auto_trigger, daemon=True).start()

    # Run the actual Flask server
    app.run(host="0.0.0.0", port=3989, debug=False)