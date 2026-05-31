import os
import urllib.parse
from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from ariadne import load_schema_from_path, make_executable_schema, \
    graphql_sync, snake_case_fallback_resolvers, ObjectType
from ariadne.explorer import ExplorerGraphiQL

app = Flask(__name__)

# --- AWS RDS DATABASE CONFIG ---
DB_USER = "ehab.elnahas"
DB_PASS = "test"
DB_HOST = "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com"
DB_PORT = "5432"
DB_NAME = "dyDATA_new"

safe_user = urllib.parse.quote_plus(DB_USER)
safe_pass = urllib.parse.quote_plus(DB_PASS)

# Construct URI with SSL requirements for AWS
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{safe_user}:{safe_pass}@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class StockPrice(db.Model):
    __tablename__ = 'tsla'
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(10))
    price_date = db.Column(db.DateTime)
    close = db.Column(db.Float)
    open = db.Column(db.Float)
    high = db.Column(db.Float)    
    low = db.Column(db.Float)
    volume = db.Column(db.BigInteger)

query = ObjectType("Query")

@query.field("latestPrice")
def resolve_latest_price(_, info, symbol):
    price = StockPrice.query.filter_by(symbol=symbol.upper()).order_by(StockPrice.price_date.desc()).first()
    return price

@query.field("priceHistory")
def resolve_price_history(_, info, symbol, limit=10):
    prices = StockPrice.query.filter_by(symbol=symbol.upper()).order_by(StockPrice.price_date.desc()).limit(limit).all()
    return prices

type_defs = load_schema_from_path("../schema.graphql")
schema = make_executable_schema(type_defs, query, snake_case_fallback_resolvers)

@app.route("/graphql", methods=["GET"])
def graphql_playground():
    return ExplorerGraphiQL().html(None), 200

@app.route("/graphql", methods=["POST"])
def graphql_server():
    data = request.get_json()
    success, result = graphql_sync(schema, data, context_value=request, debug=app.debug)
    return jsonify(result), 200 if success else 400

if __name__ == "__main__":
    app.run(debug=True, port=5000)