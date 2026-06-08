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
),

news_with_date AS (
    SELECT 
        *,
        CAST(published_at AS DATE) AS news_date
    FROM {{ ref('fact_news') }}
),

-- Ánh xạ mọi ngày ra tin về ngày giao dịch hợp lệ kế tiếp vì t7, cn không có gd tại ttVN
news_mapped_to_trading_date AS (
    SELECT 
        n.article_id,
        n.ticker,
        n.title,
        n.summary,
        n.published_at,
        n.news_date,
        -- Tìm ngày giao dịch nhỏ nhất nhưng phải lớn hơn hoặc bằng ngày ra tin
        MIN(r.transaction_date) AS mapped_transaction_date
    FROM news_with_date n
    INNER JOIN calculated_returns r 
        ON n.ticker = r.ticker 
       AND r.transaction_date >= n.news_date
    GROUP BY 
        n.article_id, n.ticker, n.title, n.summary, n.published_at, n.news_date
)

-- Kết nối để lấy tỷ suất sinh lời của ngày giao dịch kế tiếp
SELECT
    m.article_id,
    m.ticker,
    m.title,
    m.summary,
    m.published_at,
    m.news_date,
    m.mapped_transaction_date,
    cr.next_day_return_percentage
FROM news_mapped_to_trading_date m
INNER JOIN calculated_returns cr
    ON m.ticker = cr.ticker
   AND m.mapped_transaction_date = cr.transaction_date