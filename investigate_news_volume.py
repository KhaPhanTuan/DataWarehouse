# import duckdb
# import os
# import pandas as pd
# from dotenv import load_dotenv

# load_dotenv()
# token = os.getenv("motherduck_token")
# con = duckdb.connect(f"md:vn_stock_analytics?motherduck_token={token}")

# print("="*60)
# print("🔍 QUÉT TÌM CỘT 'URL' HOẶC 'LINK' TRÊN TOÀN BỘ MOTHERDUCK")
# print("="*60)

# try:
#     # Lấy danh sách tất cả các bảng bằng câu lệnh chuẩn DuckDB
#     tables_df = con.execute("SHOW ALL TABLES").df()
#     print(f"📌 Tìm thấy {len(tables_df)} bảng/view trong hệ thống.")
    
#     found_any = False
#     for _, row in tables_df.iterrows():
#         # Chỉ quét các bảng thuộc database vn_stock_analytics
#         if row['database'] != 'vn_stock_analytics':
#             continue
            
#         t_name = row['name']
#         s_name = row['schema']
#         full_path = f'"{row["database"]}"."{s_name}"."{t_name}"'
        
#         try:
#             # Lấy thông tin cột của từng bảng
#             cols_df = con.execute(f"PRAGMA table_info({full_path})").fetchall()
#             cols = [c[1].lower() for c in cols_df]
            
#             # Kiểm tra xem có cột nào chứa chữ 'url' hoặc 'link' không
#             match_cols = [c for c in cols if 'url' in c or 'link' in c]
#             if match_cols:
#                 found_any = True
#                 print(f"\n🎯 PHÁT HIỆN BẢNG CÓ CHỨA LINK/URL: {full_path}")
#                 print(f"   -> Các cột khớp: {match_cols}")
                
#                 # Đếm thử xem bảng này có dữ liệu URL không
#                 total = con.execute(f"SELECT COUNT(*) FROM {full_path}").fetchone()[0]
#                 print(f"   -> Tổng số dòng: {total}")
                
#                 # Kiểm tra ngẫu nhiên xem có dữ liệu không rỗng không
#                 for col_target in match_cols:
#                     not_null = con.execute(f"SELECT COUNT(*) FROM {full_path} WHERE {col_target} IS NOT NULL AND {col_target} != ''").fetchone()[0]
#                     print(f"   -> Cột `{col_target}` có {not_null} dòng có dữ liệu thực tế.")
                    
#         except Exception as e_col:
#             pass # Bỏ qua các bảng hệ thống hoặc không có quyền truy cập

#     if not found_any:
#         print("\n❌ KẾT QUẢ: Toàn bộ database trên MotherDuck không có bất kỳ bảng nào chứa cột mang tên 'url' hoặc 'link'!")

# except Exception as e:
#     print(f"❌ Lỗi hệ thống khi quét bảng: {e}")

# con.close()








# import duckdb
# import os
# import pandas as pd
# from dotenv import load_dotenv

# # Load Token từ file .env
# load_dotenv()
# token = os.getenv("motherduck_token")

# if not token:
#     print("❌ LỖI: Không tìm thấy 'motherduck_token' trong file .env!")
#     print("Vui lòng kiểm tra lại file .env của bạn.")
#     exit()

# print("="*60)
# print("☁️ ĐANG KẾT NỐI TỚI MOTHERDUCK CLOUD...")
# print("="*60)

# try:
#     # Kết nối chuẩn tới MotherDuck theo cách của bạn
#     con = duckdb.connect(f"md:vn_stock_analytics?motherduck_token={token}")
#     print("✅ Kết nối MotherDuck THÀNH CÔNG!\n")
# except Exception as e:
#     print(f"❌ Kết nối thất bại: {e}")
#     exit()

# print("="*60)
# print("🔍 BƯỚC 1: KIỂM TRA SỰ TỒN TẠI CỦA CÁC BẢNG TRÊN CLOUD")
# print("="*60)

# # Quét danh sách bảng thực tế trên catalog vn_stock_analytics
# try:
#     tables_df = con.execute("""
#         SELECT table_schema, table_name 
#         FROM vn_stock_analytics.information_schema.tables 
#         WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
#     """).df()
#     print("📌 Các bảng thực tế đang nằm trên MotherDuck:")
#     print(tables_df.to_string())
#     print("-" * 50)
#     actual_tables = tables_df['table_name'].tolist()
# except Exception as e:
#     print(f"❌ Không thể quét thông tin bảng từ information_schema: {e}")
#     actual_tables = []

# # Tìm chính xác bảng để quét dữ liệu
# target_table = "analytics_wide_ai_ready"

# print("\n" + "="*60)
# print(f"🔍 BƯỚC 2: QUÉT CỘT & KIỂM TRA DỮ LIỆU TRÊN BẢNG `{target_table}`")
# print("="*60)

# try:
#     # 1. Kiểm tra cấu trúc cột thực tế xem có URL và SUMMARY không
#     cols_df = con.execute(f"DESCRIBE vn_stock_analytics.main.{target_table}").df()
#     columns_list = cols_df['column_name'].tolist()
#     print("📋 Cấu trúc cột phát hiện được:")
#     print(cols_df[['column_name', 'column_type']].to_string())
#     print("-" * 50)
    
#     # 2. Đếm tổng số dòng dữ liệu
#     total_rows = con.execute(f"SELECT COUNT(*) FROM vn_stock_analytics.main.{target_table}").fetchone()[0]
#     print(f"📊 Tổng số dòng hiện có: {total_rows}")
    
#     # 3. Kiểm tra trường URL
#     if 'url' in columns_list:
#         url_count = con.execute(f"""
#             SELECT COUNT(*) FROM vn_stock_analytics.main.{target_table} 
#             WHERE url IS NOT NULL AND url != '' AND url != 'None' AND url != 'nan'
#         """).fetchone()[0]
#         print(f"🔗 Số dòng CÓ URL thực sự: {url_count} / {total_rows} (Tỷ lệ: {(url_count/total_rows)*100 if total_rows > 0 else 0:.2f}%)")
#     else:
#         print("❌ CẢNH BÁO: Không có cột nào tên là 'url' trong bảng này!")

#     # 4. Kiểm tra trường SUMMARY (Tóm tắt AI)
#     if 'summary' in columns_list:
#         summary_count = con.execute(f"""
#             SELECT COUNT(*) FROM vn_stock_analytics.main.{target_table} 
#             WHERE summary IS NOT NULL AND summary != '' AND summary != 'None' AND summary != 'nan' AND summary NOT LIKE '%đang chờ%'
#         """).fetchone()[0]
#         print(f"🤖 Số dòng CÓ AI SUMMARY (Đã phân tích): {summary_count} / {total_rows} (Tỷ lệ: {(summary_count/total_rows)*100 if total_rows > 0 else 0:.2f}%)")
#     else:
#         print("❌ CẢNH BÁO: Không có cột nào tên là 'summary' (Tóm tắt AI) trong bảng này!")

#     # 5. Xuất demo dữ liệu nếu có
#     print("\n📰 DEMO 3 DÒNG DỮ LIỆU THỰC TẾ:")
#     select_cols = [c for c in ['ticker', 'title', 'url', 'summary'] if c in columns_list]
#     select_str = ", ".join(select_cols)
    
#     df_demo = con.execute(f"SELECT {select_str} FROM vn_stock_analytics.main.{target_table} LIMIT 3").df()
#     print(df_demo.to_string())

# except Exception as e:
#     print(f"❌ Lỗi khi phân tích sâu bảng dữ liệu: {e}")

# con.close()
# print("\n" + "="*60)
# print("🏁 HOÀN THÀNH QUÉT CƠ SỞ DỮ LIỆU CLOUD.")
# print("="*60)






import duckdb
import os
import pandas as pd
from dotenv import load_dotenv

# Load cấu hình token từ .env
load_dotenv()
token = os.getenv("motherduck_token")

if not token:
    print("❌ Không tìm thấy motherduck_token trong file .env!")
    exit()

# Kết nối MotherDuck
con = duckdb.connect(f"md:vn_stock_analytics?motherduck_token={token}")
print("✅ Kết nối thành công tới MotherDuck Cloud!")

# Câu lệnh SQL kết nối bảng AI Ready và bảng Bronze để lấy URL và Summary
query = """
    SELECT 
        ai.ticker,
        ai.title,
        ai.published_at,
        bn.url,
        ai.summary
    FROM vn_stock_analytics.main.analytics_wide_ai_ready ai
    LEFT JOIN vn_stock_analytics.main.bronze_market_news bn 
        ON ai.title = bn.title -- Khớp theo tiêu đề bài báo để lấy URL chuẩn xác
    ORDER BY ai.published_at DESC
"""

try:
    print("\n🔄 Đang thực hiện JOIN dữ liệu từ 2 bảng...")
    df_result = con.execute(query).df()
    
    print("\n" + "="*70)
    print("📊 KẾT QUẢ KIỂM TRA DỮ LIỆU SAU KHI JOIN (MAPPING)")
    print("="*70)
    print(f"Tổng số dòng lấy được: {len(df_result)}")
    
    # Đếm số lượng thực tế
    urls_found = df_result['url'].notna().sum()
    summaries_found = df_result['summary'].apply(lambda x: str(x).strip() != '' and str(x) != 'None' and str(x) != 'nan').sum()
    
    print(f"🔗 Số dòng khớp được URL thành công: {urls_found} / {len(df_result)}")
    print(f"🤖 Số dòng đã có sẵn AI Summary: {summaries_found} / {len(df_result)}")
    
    print("\n📰 HIỂN THỊ KIỂM TRA 5 DÒNG DỮ LIỆU ĐẦU TIÊN:")
    for idx, row in df_result.head(5).iterrows():
        print(f"\n[{idx+1}] Mã: {row['ticker']} | Ngày: {row['published_at']}")
        print(f"   - Tiêu đề: {row['title']}")
        print(f"   - Link URL: {row['url'] if row['url'] else '❌ Trống Link'}")
        
        # Kiểm tra nội dung tóm tắt
        sum_val = str(row['summary']).strip()
        if sum_val == '' or sum_val == 'None' or sum_val == 'nan':
            print("   - Tóm tắt AI: ⏳ ĐANG CHỜ PHÂN TÍCH (Sẽ cấu hình gọi Groq trực tiếp)")
        else:
            print(f"   - Tóm tắt AI: {sum_val[:100]}...")
            
except Exception as e:
    print(f"❌ Lỗi trong quá trình truy vấn dữ liệu: {e}")

con.close()
print("\n" + "="*70)
print("🏁 ĐÃ HOÀN THÀNH CHECK LINK.")
print("="*70)