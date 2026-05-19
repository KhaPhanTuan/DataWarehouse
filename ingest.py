!pip install vnstock3 duckdb
pip install vnstock -U

import os
import datetime
import pandas as pd
import time
from vnstock import register_user, Market

def get_ticker_list():
    """Định nghĩa danh sách 50 cổ phiếu hàng đầu thị trường"""
    vn30 = [
        "ACB", "BCM", "BID", "BVH", "CTG", "FPT", "GAS", "GVR", "HDB", "HPG", 
        "MBB", "MSN", "MWG", "PLX", "POW", "SAB", "SHB", "SSB", "SSI", "STB", 
        "TCB", "TPB", "VCB", "VHM", "VIB", "VIC", "VJC", "VNM", "VPB", "VRE"
    ]
    thanh_khoan_cao = [
        "VND", "VCI", "HCM", "MBS", "SHS", "DIG", "DXG", "NLG", "PDR", "CEO",  
        "NKG", "HSG", "PVD", "PVS", "DGC", "DCM", "DPM", "KBC", "VGC", "IDC"                 
    ]
    return list(set(vn30 + thanh_khoan_cao))[:50]

def extract_and_transform():
    from google.colab import userdata
    os.environ["VNSTOCK_API_KEY"] = userdata.get('VNSTOCK_API_KEY')
    vns_key = os.getenv("VNSTOCK_API_KEY")
    
    if not vns_key:
        raise ValueError("Thiếu cấu hình VNSTOCK_API_KEY tại mục Secrets!")

    register_user(api_key=vns_key)

    start_dt = "2025-01-01"
    end_dt = datetime.date.today().strftime("%Y-%m-%d")
    ticker_list = get_ticker_list()
    
    print(f"=== Bắt đầu tải dữ liệu {len(ticker_list)} mã từ {start_dt} ===")
    df_list = []
    market = Market()
    
    for ticker in ticker_list:
        try:
            df_single = market.equity(ticker).ohlcv(start=start_dt, end=end_dt)
            if df_single is not None and not df_single.empty:
                df_single['ticker'] = ticker
                df_list.append(df_single)
                print(f"✓ Đã tải xong dữ liệu mã: {ticker}")
                time.sleep(1.0) # Tránh rate limit
        except Exception as single_err:
            print(f"Bỏ qua lỗi tại mã {ticker}: {single_err}")
            continue
            
    if not df_list:
        print("Không nhận được bất kỳ dữ liệu nào.")
        return None
        
    df_prices = pd.concat(df_list, ignore_index=True)
    if 'date' in df_prices.columns:
        df_prices = df_prices.rename(columns={'date': 'time'})
        
    df_prices = df_prices.reset_index(drop=True)
    print(f"\n[XONG BƯỚC 1] Tải dữ liệu thành công! Tổng cộng thu về {len(df_prices)} dòng dữ liệu.")
    return df_prices

# Chạy hàm và gán dữ liệu vào biến toàn cục để ô code sau sử dụng
GLOBAL_DF = extract_and_transform()

import os
import duckdb

def load_to_existing_table_global_env(df_prices):
    if df_prices is None or df_prices.empty:
        print("❌ Lỗi: Không có dữ liệu trong bộ nhớ! Hãy chạy lại Ô Code 1.")
        return

    from google.colab import userdata
    # Lấy token từ mục Secrets của Colab
    md_token = userdata.get('MOTHERDUCK_TOKEN')

    if not md_token:
        raise ValueError("Thiếu cấu hình MOTHERDUCK_TOKEN tại mục Secrets!")

    md_token = md_token.strip()
    
    # GIẢI PHÁP GỐC: Ép Token thẳng vào biến môi trường của hệ điều hành Linux ngầm định.
    os.environ["MOTHERDUCK_TOKEN"] = md_token

    print("=== [PHẦN 2] Đang thiết lập kết nối DuckDB Đám mây ===")

    try:
        # Khởi tạo kết nối trực tiếp, DuckDB tự lấy Token từ os.environ để liên kết
        print("Đang gửi yêu cầu xác thực định danh lên máy chủ MotherDuck...")
        conn = duckdb.connect("md:")

        # Chuyển ngữ cảnh làm việc vào thẳng Database và Schema mục tiêu
        print("Kết nối thành công! Đang chuyển hướng vào `vn_stock_db.main`...")
        conn.execute("USE vn_stock_db.main;")

        # TỰ ĐỘNG KHỞI TẠO BẢNG: Đảm bảo cấu trúc bảng khớp hoàn toàn với câu lệnh INSERT bên dưới
        conn.execute("""
            CREATE TABLE IF NOT EXISTS raw_daily_prices (
                time TIMESTAMP,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume LONG,
                ticker VARCHAR
            );
        """)

        # Đăng ký biến DataFrame thành một View ảo tạm thời trong RAM của DuckDB
        conn.register("df_prices_view", df_prices)

        # 1. CHIẾN LƯỢC IDEMPOTENT: Xóa dữ liệu trùng ngày + mã để tránh nhân đôi data
        print("Đang quét và dọn dẹp các bản ghi trùng lặp ngày cũ...")
        conn.execute("""
            DELETE FROM raw_daily_prices
            WHERE CAST(time AS DATE) IN (SELECT DISTINCT CAST(time AS DATE) FROM df_prices_view)
              AND ticker IN (SELECT DISTINCT ticker FROM df_prices_view);
        """)

        # 2. INSERT: Tiến hành chèn dữ liệu mới từ DataFrame vào bảng raw_daily_prices
        print("Đang tiến hành chèn dữ liệu mới vào bảng `raw_daily_prices`...")
        conn.execute("""
            INSERT INTO raw_daily_prices (time, open, high, low, close, volume, ticker)
            SELECT CAST(time AS TIMESTAMP), open, high, low, close, CAST(volume AS LONG), ticker FROM df_prices_view;
        """)

        print("\n🎉 [SUCCESS] Quá trình Pipeline hoàn thành rực rỡ!")
        total_rows = conn.execute("SELECT count(*) FROM raw_daily_prices;").fetchone()
        print(f"📊 Tổng số lượng dòng thực tế hiện có trong bảng Cloud của bạn: {total_rows[0]}")

        # Giải phóng cổng kết nối an toàn
        conn.close()
        
    except Exception as e:
        print(f"\n❌ Quá trình nạp dữ liệu thất bại tại Phần 2. Chi tiết lỗi: {e}")
        raise e

# SỬA LỖI TẠI ĐÂY: Truyền đúng biến toàn cục GLOBAL_DF được tạo ra từ Cell 1
load_to_existing_table_global_env(GLOBAL_DF)
