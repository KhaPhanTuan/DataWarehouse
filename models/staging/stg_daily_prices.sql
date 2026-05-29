WITH raw_prices AS (
    SELECT * FROM {{ source('bronze_source', 'bronze_daily_prices') }}
)
SELECT
    CAST(time AS DATE) AS transaction_date,
    ticker,
    CAST(open AS DOUBLE) AS open_price,
    CAST(high AS DOUBLE) AS high_price,
    CAST(low AS DOUBLE) AS low_price,
    CAST(close AS DOUBLE) AS close_price,
    CAST(volume AS LONG) AS volume,
    ingested_at
FROM raw_prices
WHERE open_price > 0 AND volume >= 0