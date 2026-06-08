
  
  create view "vn_stock_analytics"."main"."stg_market_news__dbt_tmp" as (
    WITH ranked_news AS (
    SELECT 
        ticker,
        title,
        head,
        publish_time,
        article_id,
        ingested_at,
        ROW_NUMBER() OVER (PARTITION BY article_id ORDER BY ingested_at DESC) AS row_num
    FROM "vn_stock_analytics"."main"."bronze_market_news"
)
SELECT
    article_id,
    ticker,
    title,
    COALESCE(head, 'Không có tóm tắt') AS summary,
    CAST(publish_time AS TIMESTAMP) AS published_at,
    ingested_at
FROM ranked_news
WHERE row_num = 1
  );
