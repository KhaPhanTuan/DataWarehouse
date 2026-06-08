SELECT
    md5(cast(coalesce(cast(transaction_date as TEXT), '_dbt_utils_surrogate_key_null_') || '-' || coalesce(cast(ticker as TEXT), '_dbt_utils_surrogate_key_null_') as TEXT)) AS price_key,
    transaction_date,
    ticker,
    open_price,
    high_price,
    low_price,
    close_price,
    volume,
    (close_price - open_price) AS daily_variance
FROM "vn_stock_analytics"."main"."stg_daily_prices"