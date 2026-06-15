
  
    
    

    create  table
      "vn_stock_analytics"."main"."analytics_wide_ai_ready__dbt_tmp"
  
    as (
      WITH price_returns AS (
    SELECT
        transaction_date,
        ticker,
        close_price,
        LEAD(close_price, 1) OVER (PARTITION BY ticker ORDER BY transaction_date) AS next_day_close
    FROM "vn_stock_analytics"."main"."fact_daily_prices"
),

calculated_returns AS (
    SELECT
        transaction_date,
        ticker,
        close_price,
        next_day_close,
        ((next_day_close - close_price) / close_price) * 100 AS next_day_return_percentage,
        -- 1 ngày chỉ có 1 dòng return sạch
        ROW_NUMBER() OVER (PARTITION BY ticker, transaction_date ORDER BY transaction_date) AS rn
    FROM price_returns
    WHERE next_day_close IS NOT NULL
),

calculated_returns_clean AS (
    SELECT * FROM calculated_returns WHERE rn = 1
),

volatility_features AS (
    SELECT 
        p.ticker,
        p.transaction_date,
        p.daily_variance,
        AVG(p.daily_variance) OVER (
            PARTITION BY p.ticker 
            ORDER BY p.transaction_date 
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) AS variance_threshold,
        --  1 ngày chỉ có 1 dòng biến động
        ROW_NUMBER() OVER (PARTITION BY p.ticker, p.transaction_date ORDER BY p.transaction_date) AS rn
    FROM "vn_stock_analytics"."main"."fact_daily_prices" p
),

volatility_labeled AS (
    SELECT 
        ticker,
        transaction_date,
        CASE 
            WHEN daily_variance > variance_threshold THEN 'High'
            ELSE 'Low'
        END AS volatility_level
    FROM volatility_features
    WHERE rn = 1
),

news_with_date AS (
    SELECT 
        *,
        CAST(published_at AS DATE) AS news_date
    FROM "vn_stock_analytics"."main"."fact_news"
),

news_mapped_to_trading_date AS (
    SELECT 
        n.article_id,
        n.ticker,
        n.title,
        n.summary,
        n.published_at,
        n.news_date,
        MIN(r.transaction_date) AS mapped_transaction_date
    FROM news_with_date n
    LEFT JOIN calculated_returns_clean r 
        ON n.ticker = r.ticker 
       AND r.transaction_date >= n.news_date
    GROUP BY 
        n.article_id, n.ticker, n.title, n.summary, n.published_at, n.news_date
)

SELECT
    m.article_id,
    m.ticker,
    m.title,
    m.summary,
    m.published_at,
    m.news_date,
    m.mapped_transaction_date,
    cr.next_day_return_percentage,
    v.volatility_level
FROM news_mapped_to_trading_date m
LEFT JOIN calculated_returns_clean cr
    ON m.ticker = cr.ticker
   AND m.mapped_transaction_date = cr.transaction_date
LEFT JOIN volatility_labeled v
    ON m.ticker = v.ticker
   AND m.mapped_transaction_date = v.transaction_date
    );
  
  