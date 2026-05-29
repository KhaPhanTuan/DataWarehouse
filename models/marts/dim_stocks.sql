SELECT
    symbol AS ticker,
    company_type,
    exchange,
    ceo_name,
    charter_capital,
    CAST(listing_date AS DATE) AS listing_date
FROM {{ ref('stg_company_profiles') }}