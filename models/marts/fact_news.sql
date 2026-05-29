SELECT
    article_id,
    ticker,
    title,
    summary,
    published_at,
    CAST(NULL AS DOUBLE) AS sentiment_score -- Ô dữ liệu chờ sẵn để mô hình AI điền vào ở Giai đoạn 3
FROM {{ ref('stg_market_news') }}