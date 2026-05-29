SELECT
    {{ dbt_utils.generate_surrogate_key(['transaction_date', 'ticker']) }} AS price_key,
    transaction_date,
    ticker,
    open_price,
    high_price,
    low_price,
    close_price,
    volume,
    (close_price - open_price) AS daily_variance
FROM {{ ref('stg_daily_prices') }}