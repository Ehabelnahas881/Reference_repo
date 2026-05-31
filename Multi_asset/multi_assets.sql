CREATE TABLE IF NOT EXISTS "TEST_TSLA".multi_assets (
    id SERIAL,
    asset_ticker VARCHAR(10) NOT NULL,
    minute_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    open_price DECIMAL(16, 4) NOT NULL,
    high_price DECIMAL(16, 4) NOT NULL,
    low_price DECIMAL(16, 4) NOT NULL,
    close_price DECIMAL(16, 4) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Prevents duplicate data for the same asset at the same minute
    CONSTRAINT pk_asset_time PRIMARY KEY (asset_ticker, minute_timestamp)
);

CREATE INDEX IF NOT EXISTS idx_market_time ON "TEST_TSLA".multi_assets (minute_timestamp DESC);

-- Grant permissions (Required based on your previous error)
GRANT ALL PRIVILEGES ON TABLE "TEST_TSLA".multi_assets TO "ehab.elnahas";
GRANT USAGE, SELECT ON SEQUENCE "TEST_TSLA".multi_assets_id_seq TO "ehab.elnahas";