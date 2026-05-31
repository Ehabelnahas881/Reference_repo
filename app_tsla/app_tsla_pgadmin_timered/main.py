import os
import urllib.parse
from flask import Flask, request, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)

# --- DATABASE CONFIG ---
DB_USER = "ehab.elnahas"
DB_PASS = "test"
DB_HOST = "database-1.ctzm0hf7fhri.eu-central-1.rds.amazonaws.com"
DB_PORT = "5432"
DB_NAME = "dyDATA_new"

safe_user = urllib.parse.quote_plus(DB_USER)
safe_pass = urllib.parse.quote_plus(DB_PASS)
app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{safe_user}:{safe_pass}@{DB_HOST}:{DB_PORT}/{DB_NAME}?sslmode=require'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class StockPrice(db.Model):
    __tablename__ = 'tsla_timered'
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(10))
    price_date = db.Column(db.DateTime)
    close = db.Column(db.Float)
    high = db.Column(db.Float)    
    low = db.Column(db.Float)
    volume = db.Column(db.BigInteger)

# --- PROFESSIONAL DASHBOARD HTML ---
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>TSLA Data Engine | Live</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background-color: #f4f7f6; font-family: 'Inter', sans-serif; }
        .hero { background: linear-gradient(135deg, #0f2027, #203a43, #2c5364); color: white; padding: 60px 0; border-radius: 0 0 50px 50px; }
        .live-card { border: none; border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); margin-top: -50px; }
        .feature-card { border: none; border-radius: 15px; transition: transform 0.3s; height: 100%; }
        .feature-card:hover { transform: translateY(-5px); }
        .status-dot { height: 10px; width: 10px; background-color: #28a745; border-radius: 50%; display: inline-block; margin-right: 5px; }
    </style>
</head>
<body>

<div class="hero text-center">
    <h1 class="display-4 fw-bold">🚀 TSLA High-Frequency Engine</h1>
    <p class="lead">Real-time AWS RDS Pipeline & Adaptive Scraper</p>
</div>

<div class="container">
    <div class="row justify-content-center">
        <div class="col-md-10">
            <div class="card live-card p-5 bg-white">
                <div class="d-flex justify-content-between align-items-center mb-4">
                    <h4 class="m-0 text-muted uppercase small fw-bold">Live Extraction Stream</h4>
                    <span class="badge bg-success-subtle text-success border border-success px-3 py-2">
                        <span class="status-dot"></span> System Live
                    </span>
                </div>
                
                <div id="data-container" class="text-center py-4">
                    <div class="spinner-border text-primary" role="status"></div>
                    <p>Connecting to AWS RDS...</p>
                </div>
            </div>
        </div>
    </div>

    <div class="row mt-5 g-4">
        <div class="col-md-4">
            <div class="card feature-card p-4 shadow-sm">
                <h5 class="fw-bold text-primary">🌐 Driver Technology</h5>
                <p class="text-muted small">Powered by <b>Undetected-Chromedriver</b>. Uses Eager loading strategies and resource blocking to bypass bot detection while saving bandwidth.</p>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card feature-card p-4 shadow-sm">
                <h5 class="fw-bold text-danger">🛡️ Stealth Security</h5>
                <p class="text-muted small">Features <b>Adaptive Jitter</b> (randomized sleep) and <b>User-Agent Rotation</b> to mimic human behavior across different browser sessions.</p>
            </div>
        </div>
        <div class="col-md-4">
            <div class="card feature-card p-4 shadow-sm">
                <h5 class="fw-bold text-success">📊 AWS RDS Sync</h5>
                <p class="text-muted small">Automated PostgreSQL pipeline. Includes <b>Market-Aware logic</b>: the engine sleeps during weekends and holidays to optimize AWS costs.</p>
            </div>
        </div>
    </div>
</div>

<script>
    function updateData() {
        fetch('/api/latest')
            .then(response => response.json())
            .then(data => {
                const container = document.getElementById('data-container');
                if (data.error) {
                    container.innerHTML = `<div class="alert alert-warning">${data.error}</div>`;
                } else {
                    container.innerHTML = `
                        <div class="row align-items-center">
                            <div class="col-md-4">
                                <h1 class="display-2 fw-bold text-dark m-0">${data.symbol}</h1>
                                <p class="text-muted">NASDAQ Real-Time</p>
                            </div>
                            <div class="col-md-4 border-start border-end">
                                <h2 class="display-3 fw-bold text-success">$${data.close.toFixed(2)}</h2>
                                <p class="small text-muted">Last Updated: ${data.price_date}</p>
                            </div>
                            <div class="col-md-4 text-start ps-5">
                                <p class="mb-1"><strong>📈 High:</strong> $${data.high}</p>
                                <p class="mb-1"><strong>📉 Low:</strong> $${data.low}</p>
                                <p class="mb-0"><strong>📦 Vol:</strong> ${data.volume.toLocaleString()}</p>
                            </div>
                        </div>
                    `;
                }
            })
            .catch(err => console.log("Fetch Error:", err));
    }

    // Update every 5 seconds
    setInterval(updateData, 5000);
    updateData(); // Initial call
</script>

</body>
</html>
"""

# --- BACKEND ROUTES ---

@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route("/api/latest")
def get_latest_data():
    try:
        record = StockPrice.query.order_by(StockPrice.price_date.desc()).first()
        if not record:
            return jsonify({"error": "Waiting for scraper to save first record..."})
        
        return jsonify({
            "symbol": record.symbol,
            "close": record.close,
            "high": record.high,
            "low": record.low,
            "volume": record.volume,
            "price_date": record.price_date.strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5050)