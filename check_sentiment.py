import duckdb
import os
import pandas as pd  # Đã thêm dòng này để hết lỗi NameError
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("motherduck_token")

con = duckdb.connect(f"md:vn_stock_analytics?motherduck_token={token}")

print("--- 1. KIỂM TRA ĐẦY ĐỦ CẤU TRÚC BẢNG AI READY ---")
schema = con.execute("DESCRIBE vn_stock_analytics.main.analytics_wide_ai_ready").fetchdf()
print(schema[['column_name', 'column_type']])

print("\n--- 2. THỐNG KÊ SỐ LƯỢNG TIN THEO TỪNG MÃ CỔ PHIẾU (TÌM LỖI 1 BÀI) ---")
# Đếm xem mỗi ticker thực tế đang có bao nhiêu dòng trong bảng AI Ready này
ticker_counts = con.execute("""
    SELECT ticker, COUNT(*) as total_articles
    FROM vn_stock_analytics.main.analytics_wide_ai_ready
    GROUP BY ticker
""").fetchdf()
print(ticker_counts)

print("--- 3. XEM CHI TIẾT 3 DÒNG DỮ LIỆU ĐỂ LẤY LOGIC CẮT CHUỖI ---")
sample = con.execute("""
    SELECT ticker, sentiment_label, sentiment_score, title
    FROM vn_stock_analytics.main.analytics_wide_ai_ready
    WHERE sentiment_score IS NOT NULL
    LIMIT 3
""").fetchdf()

pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)
print(sample)

con.close()