WITH raw_prices AS (
    SELECT
        CAST(time AS DATE) AS transaction_date,
        ticker,
        CAST(open AS DOUBLE) AS open_price,
        CAST(high AS DOUBLE) AS high_price,
        CAST(low AS DOUBLE) AS low_price,
        CAST(close AS DOUBLE) AS close_price,
        CAST(volume AS LONG) AS volume,
        ingested_at,
        -- khử trùng theo mã và ngày giao dịch, lấy bản ghi mới nhất
        ROW_NUMBER() OVER (
            PARTITION BY ticker, CAST(time AS DATE) 
            ORDER BY ingested_at DESC
        ) AS row_num
    FROM {{ source('bronze_source', 'bronze_daily_prices') }}
)
SELECT
    transaction_date,
    ticker,
    open_price,
    high_price,
    low_price,
    close_price,
    volume,
    ingested_at
FROM raw_prices

WHERE row_num = 1 
  AND open_price > 0 
  AND volume >= 0