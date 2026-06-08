WITH ranked_profiles AS (
    SELECT
        symbol,
        company_type,
        exchange,
        ceo_name,
        charter_capital,
        listing_date,
        ingested_at,
        -- Khử trùng lặp
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY ingested_at DESC) AS row_num
    FROM "vn_stock_analytics"."main"."bronze_company_profiles"
)
SELECT
    symbol,
    company_type,
    exchange,
    ceo_name,
    CAST(charter_capital AS DOUBLE) AS charter_capital,
    -- KỸ THUẬT: Sử dụng STRPTIME để parse chuỗi 'ngày/tháng/năm' của VN về dạng DATE
    TRY_CAST(STRPTIME(listing_date, '%d/%m/%Y') AS DATE) AS listing_date,
    ingested_at
FROM ranked_profiles
WHERE row_num = 1