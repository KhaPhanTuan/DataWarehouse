WITH price_returns AS (
    SELECT
        transaction_date,
        ticker,
        close_price,
        -- Lấy giá đóng cửa của ngày T+1
        LEAD(close_price, 1) OVER (PARTITION BY ticker ORDER BY transaction_date) AS next_day_close
    FROM {{ ref('fact_daily_prices') }}
),
calculated_returns AS (
    SELECT
        transaction_date,
        ticker,
        close_price,
        next_day_close,
        ((next_day_close - close_price) / close_price) * 100 AS next_day_return_percentage
    FROM price_returns
    WHERE next_day_close IS NOT NULL
)
SELECT
    n.article_id,
    n.ticker,
    n.title,
    n.summary,
    n.published_at,
    CAST(n.published_at AS DATE) AS news_date,
    r.next_day_return_percentage
FROM {{ ref('fact_news') }} n
INNER JOIN calculated_returns r 
    ON n.ticker = r.ticker 
   AND CAST(n.published_at AS DATE) = r.transaction_date