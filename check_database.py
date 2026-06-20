import duckdb
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("motherduck_token")
con = duckdb.connect(f"md:vn_stock_analytics?motherduck_token={token}")

print("--- [1] KIỂM TRA CẤU TRÚC CỘT THỰC TẾ ---")
df_cols = con.execute("DESCRIBE vn_stock_analytics.main.analytics_wide_ai_ready").df()
print(df_cols[['column_name', 'column_type']])

print("\n--- [2] DÒNG DỮ LIỆU MẪU CỦA FPT HOẶC KDH KHÔNG LỌC NGÀY ---")
df_sample = con.execute("""
    SELECT ticker, title, published_at, sentiment_label, sentiment_score, url 
    FROM vn_stock_analytics.main.analytics_wide_ai_ready 
    WHERE sentiment_score IS NOT NULL 
    LIMIT 3
""").df()
print(df_sample)

con.close()