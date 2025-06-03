ATTACH TABLE _ UUID '0fa0a1d0-2a73-4dd5-8c22-a27994afb94a'
(
    `timestamp` DateTime64(3),
    `exchange` String,
    `symbol` String,
    `data_type` String,
    `price` Float64,
    `volume` Float64,
    `raw_data` String,
    `created_at` DateTime64(3) DEFAULT now()
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(timestamp)
ORDER BY (exchange, symbol, data_type, timestamp)
SETTINGS index_granularity = 8192
