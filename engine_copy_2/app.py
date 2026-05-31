# from api import app
from ariadne import load_schema_from_path, make_executable_schema, \
    graphql_sync, snake_case_fallback_resolvers, ObjectType
from flask import request, jsonify, Flask
from flask_cors import CORS
from YFS import resolve_YFS
import settings, logging

query = ObjectType("Query")
query.set_field("YFS_Extractor", resolve_YFS)

type_defs = load_schema_from_path(settings.GRAPHQL_SCHEMA)
schema = make_executable_schema(type_defs, query, snake_case_fallback_resolvers)

app = Flask(__name__)
CORS(app)


@app.route("/graphql", methods=["POST"])
def graphql_server():
    data = request.get_json()
    success, result = graphql_sync(
        schema,
        data,
        context_value=request,
        debug=app.debug
    )
    status_code = 200 if success else 400
    return jsonify(result), status_code

@app.route("/health", methods=["GET"])
def health():
    return 'OK', 200

if __name__ == '__main__':
    # Log Flask hits to a separate file
    server_log = logging.getLogger('werkzeug')
    server_handler = logging.FileHandler('logs/server.log')
    server_log.addHandler(server_handler)
    
    app.run(host=settings.SERVER_HOST, port=settings.SERVER_PORT, debug=True, use_reloader=False)