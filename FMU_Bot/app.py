from ariadne import graphql_sync, make_executable_schema, gql, snake_case_fallback_resolvers, load_schema_from_path, ObjectType, ScalarType
from ariadne.constants import PLAYGROUND_HTML
from flask import request, jsonify, Flask
import json 
from api import settings
from api.financial_market_session import resolve_FMU

json_scalar = ScalarType('JSON')
@json_scalar.serializer
def serialize_json(value):
    return value
@json_scalar.value_parser
def parse_json_value(value):
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None
@json_scalar.literal_parser
def parse_json_literal(ast):
    # Assuming AST is a string representing a JSON object
    try:
        return json.loads(ast.value)
    except (json.JSONDecodeError, TypeError):
        return None

app = Flask(__name__)

query = ObjectType("Query")
query.set_field("resolve_FMU", resolve_FMU)

type_defs =load_schema_from_path('/kns-dta-data-kubernetes-namespace-tst-tst-kct/FMU-Financial_Market_Updater.Bot-API_2.0/FMU_Bot/schema.graphql')
schema = make_executable_schema(type_defs,query,snake_case_fallback_resolvers)

@app.route("/graphql", methods=["GET"])
def graphql_playground():
    return PLAYGROUND_HTML, 200

@app.route("/health", methods=["GET"]) 
def health_check(): 
  return {"status": "healthy"}, 200

# GraphQL endpoint
@app.route('/graphql', methods=["POST"])
def graphql():
    data = request.get_json()
    success, result = graphql_sync(schema, data)
    status_code = 200 if success else 400 
    return jsonify(result), status_code


if __name__ == '__main__':
    app.run(host=settings.SERVER_HOST,port=settings.SERVER_PORT,debug=True)