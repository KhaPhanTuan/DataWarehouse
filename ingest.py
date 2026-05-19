import os
import datetime
import duckdb
import pandas as pd
from vnstock3 import Vnstock

def get_current_date_strings():
    """Lấy ngày hôm nay dưới dạng chuỗi YYYY-MM-DD"""
    today = datetime.date.today()
    return today.strftime('%Y-%m-%d')

def ingest_stock_data():
    # 1. Kết nối nguồn dữ liệu vnstock3
    stock = Vnstock()
    
    # Định nghĩa danh sách các mã cổ phiếu tiêu biểu cần theo dõi (Ví dụ rổ VN30 hoặc tùy chọn)
    ticker_list = ['VCB', 'FPT', 'HPG', 'VIC', 'VNM', 'STB', 'MWG', 'TCB', 'SSI', 'VHM']
    
    today_str = get_current_date_strings()
    print(f"--- Bắt đầu cào dữ liệu cho ngày: {today_str} ---")
    
    # Lấy dữ liệu giá giao dịch lịch sử của ngày hôm nay
    # (vnstock3 sẽ trả về dataframe chứa: open, high, low, close, volume,...)
    df_prices_list = []
    for ticker in ticker_list:
        try:
            # Lấy dữ liệu giá của ngày hôm nay (từ today_str đến today_str)
            df_p = stock.stock_historical_data(symbol=ticker, start_date=today_str, end_date=today_str, resolution='1D', type='stock')
            if df_p is not None and not df_p.empty:
                df_prices_list.append(df_p)
        except Exception as e:
            print(f"Lỗi khi lấy giá mã {ticker}: {e}")
            
    # Lấy dữ liệu tin tức thị trường tổng hợp
    df_news = pd.DataFrame()
    try:
        # Lấy các tin tức mới nhất (Ví dụ: 30 tin mới nhất trong ngày)
        df_news = stock.stock_news(symbol='ALL', page_size=30)
        if df_news is not None and not df_news.empty:
            # Lọc sơ bộ chỉ lấy các tin xuất hiện trong ngày hôm nay để tránh trùng lặp lớn ở tầng Bronze
            # Lưu ý: Tùy thuộc cấu trúc cột thời gian của vnstock3, bạn có thể ép kiểu để lọc
            df_news['ingest_date'] = today_str
    except Exception as e:
        print(f"Lỗi khi lấy tin tức: {e}")

    # 2. Kết nối tới MotherDuck bằng Token lấy từ môi trường (Environment Variable)
    motherduck_token = os.getenv("MOTHERDUCK_TOKEN")
    if not motherduck_token:
        raise ValueError("Không tìm thấy MOTHERDUCK_TOKEN trong biến môi trường!")
        
    # Tạo chuỗi kết nối Cloud DuckDB
    con = duckdb.connect(f"md:vn_stock_db?motherduck_token={motherduck_token}")
    
    # 3. Đẩy dữ liệu vào tầng Bronze (Khởi tạo nếu chưa có, hoặc chèn nối đuôi nếu đã tồn tại)
    print("Đang nạp dữ liệu vào MotherDuck...")
    
    # Nạp dữ liệu giá
    if df_prices_list:
        df_prices_all = pd.concat(df_prices_list, ignore_index=True)
        df_prices_all['ingestion_timestamp'] = datetime.datetime.now()
        
        # Kiểm tra bảng tồn tại chưa để dùng cơ chế Append
        con.execute("CREATE TABLE IF NOT EXISTS bronze_daily_prices AS SELECT * FROM df_prices_all WHERE 1=0")
        con.execute("INSERT INTO bronze_daily_prices SELECT * FROM df_prices_all")
        print(f"Đã nạp thành công {len(df_prices_all)} dòng vào bảng bronze_daily_prices.")
    else:
        print("Không có dữ liệu giá giao dịch mới cho hôm nay (có thể là ngày nghỉ).")

    # Nạp dữ liệu tin tức
    if df_news is not None and not df_news.empty:
        df_news['ingestion_timestamp'] = datetime.datetime.now()
        
        con.execute("CREATE TABLE IF NOT EXISTS bronze_market_news AS SELECT * FROM df_news WHERE 1=0")
        con.execute("INSERT INTO bronze_market_news SELECT * FROM df_news")
        print(f"Đã nạp thành công {len(df_news)} dòng vào bảng bronze_market_news.")
    else:
        print("Không thu thập được tin tức mới.")
        
    # Đóng kết nối
    con.close()
    print("--- Hoàn thành Pipeline Ingestion thành công! ---")

if __name__ == "__main__":
    ingest_stock_data()