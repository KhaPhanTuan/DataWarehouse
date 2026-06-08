SELECT
    symbol AS ticker,
    company_type,
    exchange,
    ceo_name,
    charter_capital,
    CAST(listing_date AS DATE) AS listing_date
FROM "vn_stock_analytics"."main"."stg_company_profiles"