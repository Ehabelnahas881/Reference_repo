import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from ariadne import load_schema_from_path, make_executable_schema, graphql_sync, ObjectType
from waitress import serve
import settings
from YFS import resolve_YFS
import threading

# Load Schema
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.graphql")

# Setup Query
query = ObjectType("Query")
query.set_field("YFS_Extractor", resolve_YFS)

try:
    type_defs = load_schema_from_path(settings.GRAPHQL_SCHEMA)
except Exception:
    type_defs = load_schema_from_path("schema.graphql")

# Create executable schema (Removed fallback_resolvers to avoid ImportErrors)
schema = make_executable_schema(type_defs, query)

app = Flask(__name__)
CORS(app)

@app.route("/graphql", methods=["POST"])
def graphql_server():
    data = request.get_json()
    success, result = graphql_sync(schema, data, context_value=request, debug=app.debug)
    return jsonify(result), 200 if success else 400

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy"}), 200

def run_server():
    print(f"Server starting on http://{settings.waitress_host}:{settings.waitress_port}/graphql")
    serve(app, host=settings.waitress_host, port=settings.waitress_port)

if __name__ == "__main__":
    # 1. Start the API Server in background
    threading.Thread(
        target=lambda: serve(app, host=settings.waitress_host, port=settings.waitress_port),
        daemon=True
    ).start()
