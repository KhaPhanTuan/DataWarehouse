WITH base_prices AS (
    SELECT *,
        -- Lấy giá đóng cửa của ngày hôm trước để tính thay đổi
        LAG(close_price, 1) OVER (PARTITION BY ticker ORDER BY transaction_date) AS prev_close
    FROM "vn_stock_analytics"."main"."stg_daily_prices"
)
SELECT
    md5(cast(coalesce(cast(transaction_date as TEXT), '_dbt_utils_surrogate_key_null_') || '-' || coalesce(cast(ticker as TEXT), '_dbt_utils_surrogate_key_null_') as TEXT)) AS price_key,
    transaction_date,
    ticker,
    open_price,
    high_price,
    low_price,
    close_price,
    volume,
    -- Lấy trị tuyệt đối phần trăm thay đổi giá so với hôm qua
    CASE 
        WHEN prev_close IS NOT NULL THEN ABS((close_price - prev_close) / prev_close) * 100
        ELSE 0 
    END AS daily_variance
FROM base_prices