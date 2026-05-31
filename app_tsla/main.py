import os
from flask import Flask, request, jsonify
from ariadne import load_schema_from_path, make_executable_schema, \
    graphql_sync, snake_case_fallback_resolvers, ObjectType
from ariadne.explorer import ExplorerGraphiQL # Updated Import
from neo4j import GraphDatabase

# --- CONFIGURATION ---
AURA_URI = "neo4j+s://911d884c.databases.neo4j.io"
AURA_USER = "neo4j"
AURA_PASS = "yUlQfnahT3pYB6uL0YoH5Rk4HpJgBL9XxyMZsjYp5ec" 

driver = GraphDatabase.driver(AURA_URI, auth=(AURA_USER, AURA_PASS))
query = ObjectType("Query")

@query.field("latestPrice")
def resolve_latest_price(_, info, symbol):
    with driver.session(database="neo4j") as session:
        cypher = """
        MATCH (s:Stock {symbol: $symbol})-[:HAS_PRICE]->(p:Price)
        RETURN p {.*, id: elementId(p)} AS price 
        ORDER BY p.timestamp DESC LIMIT 1
        """
        result = session.run(cypher, symbol=symbol.upper()).single()
        return result["price"] if result else None

@query.field("priceHistory")
def resolve_price_history(_, info, symbol, limit=10):
    with driver.session(database="neo4j") as session:
        cypher = """
        MATCH (s:Stock {symbol: $symbol})-[:HAS_PRICE]->(p:Price)
        RETURN p {.*, id: elementId(p)} AS price 
        ORDER BY p.timestamp DESC LIMIT $limit
        """
        result = session.run(cypher, symbol=symbol.upper(), limit=limit)
        return [record["price"] for record in result]

type_defs = load_schema_from_path("schema.graphql")
schema = make_executable_schema(type_defs, query, snake_case_fallback_resolvers)

app = Flask(__name__)

# Updated: Serves the modern GraphQL Explorer
@app.route("/graphql", methods=["GET"])
def graphql_playground():
    return ExplorerGraphiQL().html(None), 200

@app.route("/graphql", methods=["POST"])
def graphql_server():
    data = request.get_json()
    success, result = graphql_sync(schema, data, context_value=request, debug=app.debug)
    return jsonify(result), 200 if success else 400

if __name__ == "__main__":
    print("🚀 API Running at http://localhost:5000/graphql")
    app.run(debug=True, port=5000)