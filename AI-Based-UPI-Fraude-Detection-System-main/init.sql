DROP TABLE IF EXISTS transactions CASCADE;

CREATE TABLE transactions (
    txn_id TEXT PRIMARY KEY,
    sender_vpa TEXT,
    receiver_vpa TEXT,
    amount FLOAT,
    device_id TEXT,
    unix_timestamp FLOAT,
    created_at TIMESTAMP DEFAULT NOW(),

    -- VELOCITY
    txn_count_1min INT,
    txn_count_5min INT,
    txn_count_1hr INT,
    amount_sum_1hr FLOAT,
    unique_receivers_1hr INT,
    unique_devices_1hr INT,

    -- AMOUNT
    amount_zscore FLOAT,
    amount_vs_daily_avg FLOAT,
    history_size INT,
    is_round_number INT,

    -- TEMPORAL
    hour_of_day INT,
    day_of_week INT,
    is_weekend INT,
    is_night INT,
    days_since_last_txn FLOAT,
    is_first_txn_ever INT,

    -- DEVICE
    is_new_device INT,
    device_txn_count INT,
    device_vpa_count INT,
    device_last_seen_hours_ago FLOAT,
    device_risk_score FLOAT,
    sender_device_count INT,

    -- GEO
    distance_from_last_txn_km FLOAT,
    txn_speed_kmph FLOAT,
    is_geo_impossible INT,

    -- GRAPH
    sender_degree_1hr INT,
    receiver_degree_1hr INT,
    is_mule_account INT,
    is_high_sender INT,
    chain_length INT,

    -- VPA
    sender_vpa_age_days FLOAT,
    receiver_vpa_age_days FLOAT,
    sender_txn_count_total INT,
    receiver_txn_count_total INT,
    vpa_similarity_score FLOAT,

    -- MERCHANT
    is_merchant_txn INT,
    merchant_avg_txn_amount FLOAT,
    merchant_txn_count INT,
    merchant_category_risk FLOAT,
    merchant_age_days FLOAT,
    merchant_dispute_rate FLOAT,

    -- FRAUD
    fraud_flag TEXT,
    is_fraud INT
);

CREATE INDEX idx_sender ON transactions(sender_vpa);
CREATE INDEX idx_receiver ON transactions(receiver_vpa);
CREATE INDEX idx_time ON transactions(unix_timestamp);
CREATE INDEX idx_fraud ON transactions(is_fraud);

CREATE TABLE IF NOT EXISTS analyst_decisions (
    id SERIAL PRIMARY KEY,
    txn_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    analyst_note TEXT,
    decided_at TIMESTAMP DEFAULT NOW()
);