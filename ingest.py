import os
from vnstock import register_user, Market, Reference, Fundamental

# Hàm bọc thông minh hỗ trợ cả Colab và GitHub Actions
def get_secret_key(key_name):
    try:
        from google.colab import userdata
        return userdata.get(key_name)
    except ImportError:
        return os.environ.get(key_name)

VNSTOCK_KEY = get_secret_key('VNSTOCK_API_KEY')
if not VNSTOCK_KEY:
    raise ValueError("Thiếu cấu hình VNSTOCK_API_KEY!")

# 2. Đăng ký tài khoản hệ thống Vnstock
register_user(api_key=VNSTOCK_KEY)

# 3. Khởi tạo các miền dữ liệu (Unified UI) để chuẩn bị gọi hàm
market = Market()
ref = Reference()
fund = Fundamental()

print(f"Xác thực thành công")

import pandas as pd
from datetime import datetime
from google.colab import userdata

# =========================================================================
# 0. CẤU HÌNH THAM SỐ HỆ THỐNG
# Lấy 3 mã bất kỳ trong nhóm VN30
SYMBOLS = ['VHM']

# Quét dữ liệu 10 năm, tham số count = ~3000 (Một năm khoảng 250d giao dịch)
START_DATE = '2015-01-01'
END_DATE = '2026-12-31'
COUNT_DATA = 20000

print(f"[TẦNG BRONZE] Khởi động Pipeline tải dữ liệu 10 năm cho nhóm mã: {SYMBOLS}")

# Khởi tạo lists tạm thời để chứa dữ liệu của từng mã trước khi gộp
history_lists = []
realtime_lists = []
profile_lists = []
news_lists = []
event_lists = []
balance_sheet_lists = []
income_statement_lists = []
cash_flow_lists = []
ratios_lists = []

# Lấy mốc thời gian chạy pipeline (Dùng chung cho cả nhóm này)
pipeline_run_time = datetime.now()

try:
    # 1. TẢI DỮ LIỆU ĐỘC LẬP (THỊ TRƯỜNG CHUNG - CHỈ CHẠY 1 LẦN)
    print("Đang tải dữ liệu lịch sử VNINDEX...")
    df_vnindex = market.index('VNINDEX').ohlcv(start=START_DATE, end=END_DATE, count=COUNT_DATA)
    if df_vnindex is not None and not df_vnindex.empty:
        if 'date' in df_vnindex.columns:
            df_vnindex = df_vnindex.rename(columns={'date': 'time'})
        df_vnindex['ingested_at'] = pipeline_run_time

    # 2. VÒNG LẶP CRAWL DỮ LIỆU THEO TỪNG MÃ CỔ PHIẾU
    for SYMBOL in SYMBOLS:
        print(f"\n --------------------------------------------------")
        print(f"Đang tiến hành crawl dữ liệu cho mã: [{SYMBOL}]...")

        # --- 2.1 Dữ liệu Giá lịch sử & Thời gian thực ---
        df_h = market.equity(SYMBOL).ohlcv(start=START_DATE, end=END_DATE, count=COUNT_DATA)
        if df_h is not None and not df_h.empty:
            if 'date' in df_h.columns:
                df_h = df_h.rename(columns={'date': 'time'})
            df_h['ticker'] = SYMBOL
            df_h['ingested_at'] = pipeline_run_time
            history_lists.append(df_h)

        df_rt = market.equity(SYMBOL).quote()
        if df_rt is not None and not df_rt.empty:
            df_rt['ticker'] = SYMBOL
            df_rt['ingested_at'] = pipeline_run_time
            realtime_lists.append(df_rt)

        # --- 2.2 Thông tin tham chiếu, Tin tức & Sự kiện ---
        df_prof = ref.company(SYMBOL).info()
        if df_prof is not None and not df_prof.empty:
            df_prof['ticker'] = SYMBOL
            df_prof['ingested_at'] = pipeline_run_time
            profile_lists.append(df_prof)

        df_nw = ref.company(SYMBOL).news()
        if df_nw is not None and not df_nw.empty:
            df_nw['ticker'] = SYMBOL
            df_nw['ingested_at'] = pipeline_run_time
            news_lists.append(df_nw)

        df_ev = ref.company(SYMBOL).events()
        if df_ev is not None and not df_ev.empty:
            df_ev['ticker'] = SYMBOL
            df_ev['ingested_at'] = pipeline_run_time
            event_lists.append(df_ev)

        # --- 2.3 Báo cáo tài chính & Chỉ số doanh nghiệp ---
        df_bs = fund.equity(SYMBOL).balance_sheet(period='quarter')
        if df_bs is not None and not df_bs.empty:
            df_bs['ticker'] = SYMBOL
            df_bs['ingested_at'] = pipeline_run_time
            balance_sheet_lists.append(df_bs)

        df_ic = fund.equity(SYMBOL).income_statement(period='quarter')
        if df_ic is not None and not df_ic.empty:
            df_ic['ticker'] = SYMBOL
            df_ic['ingested_at'] = pipeline_run_time
            income_statement_lists.append(df_ic)

        df_cf = fund.equity(SYMBOL).cash_flow(period='quarter')
        if df_cf is not None and not df_cf.empty:
            df_cf['ticker'] = SYMBOL
            df_cf['ingested_at'] = pipeline_run_time
            cash_flow_lists.append(df_cf)

        df_rat = fund.equity(SYMBOL).ratios()
        if df_rat is not None and not df_rat.empty:
            df_rat['ticker'] = SYMBOL
            df_rat['ingested_at'] = pipeline_run_time
            ratios_lists.append(df_rat)

    # 3. GỘP DỮ LIỆU THÀNH ĐA TẦNG BRONZE ĐỒNG NHẤT (CONCATENATION)
    print(f"\n--------------------------------------------------")
    print("Đang gộp dữ liệu các mã cổ phiếu thành cấu trúc bảng tập trung...")

    df_history = pd.concat(history_lists, ignore_index=True) if history_lists else None
    df_realtime = pd.concat(realtime_lists, ignore_index=True) if realtime_lists else None
    df_profile = pd.concat(profile_lists, ignore_index=True) if profile_lists else None
    df_news = pd.concat(news_lists, ignore_index=True) if news_lists else None
    df_events = pd.concat(event_lists, ignore_index=True) if event_lists else None
    df_balance_sheet = pd.concat(balance_sheet_lists, ignore_index=True) if balance_sheet_lists else None
    df_income_statement = pd.concat(income_statement_lists, ignore_index=True) if income_statement_lists else None
    df_cash_flow = pd.concat(cash_flow_lists, ignore_index=True) if cash_flow_lists else None
    df_ratios = pd.concat(ratios_lists, ignore_index=True) if ratios_lists else None

    print(f"\n Tải và chuẩn hóa tập trung dữ liệu thành công!")
    print(f"Tổng số dòng dữ liệu lịch sử giá thu được: {len(df_history) if df_history is not None else 0} dòng.")

except Exception as e:
    print(f"Đã xảy ra lỗi trong quá trình: {e}")

import os
import duckdb

def load_to_motherduck_pipeline():
    #Nhận diện môi trường là Colab hay Git Act
    md_token = None
    
    try:
        # Thử Colab trước
        from google.colab import userdata
        md_token = userdata.get('MOTHERDUCK_TOKEN')
    except ImportError:
        # Nếu không có thì chuyển sang GitHub Actions
        #Nạp Token vào biến môi trường thông qua file .yml
        md_token = os.environ.get('MOTHERDUCK_TOKEN')
    except Exception as secret_err:
        raise ValueError("Có lỗi khi truy cập hệ thống bảo mật!") from secret_err

    # Kiểm tra xem có lấy được token từ bất kỳ nguồn nào không
    if not md_token:
        raise ValueError(
            " Không tìm thấy 'MOTHERDUCK_TOKEN'!\n"
            "- Nếu chạy ở Colab: Kiểm tra lại mục Secrets (Chìa khóa) và gạt nút 'Notebook access'.\n"
            "- Nếu chạy ở GitHub: Kiểm tra lại Settings > Secrets and variables > Actions."
        )

    md_token = md_token.strip()
    
    print("Đang thiết lập kết nối DuckDB cLoud")
    try:
        connection_string = f"md:?token={md_token}"
        conn = duckdb.connect(connection_string)

        print("Kết nối thành công! Đang chuyển hướng vào `vn_stock_db.main`...")
        conn.execute("CREATE DATABASE IF NOT EXISTS vn_stock_db;")
        conn.execute("USE vn_stock_db.main;")

        # 1. XỬ LÝ LŨY KẾ: Bảng giá lịch sử `bronze_daily_prices`
        if 'df_history' in globals() and df_history is not None and not df_history.empty:
            print("\n Đang xử lý lũy kế bảng giá lịch sử: [bronze_daily_prices]...")

            # BỎ LỆNH DROP TABLE! Chỉ tạo nếu bảng CHƯA TỒN TẠI
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bronze_daily_prices (
                    time TIMESTAMP,
                    open DOUBLE,
                    high DOUBLE,
                    low DOUBLE,
                    close DOUBLE,
                    volume LONG,
                    ticker VARCHAR,
                    ingested_at TIMESTAMP,
                    PRIMARY KEY (ticker, time)
                );
            """)

            conn.register("df_prices_view", df_history)

            # Chèn thêm data năm 2023. Nếu trùng ngày+mã của năm 2024-2025 cũ thì tự update đè lên.
            print("Đang tiến hành hợp nhất dữ liệu bằng chiến lược INSERT OR REPLACE...")
            conn.execute("""
                INSERT OR REPLACE INTO bronze_daily_prices (time, open, high, low, close, volume, ticker, ingested_at)
                SELECT CAST(time AS TIMESTAMP), open, high, low, close, CAST(volume AS LONG), ticker, CAST(ingested_at AS TIMESTAMP)
                FROM df_prices_view;
            """)
            print("Đã hợp nhất thành công vào bảng: [bronze_daily_prices]")
        else:
            print("\n- Bảng [bronze_daily_prices] không có dữ liệu trong RAM.")

        # 2. XỬ LÝ LŨY KẾ: Các bảng thông tin doanh nghiệp, tài chính, chỉ số...
        # Để lưu trữ lũy kế, các bảng này cũng cần một Khóa Chính (Primary Key) thích hợp
        table_schemas = {
            "bronze_realtime_quotes": "PRIMARY KEY (ticker, time)",
            "bronze_company_profiles": "PRIMARY KEY (ticker)",
            "bronze_balance_sheets": "PRIMARY KEY (ticker, \"Chỉ số\", \"Kỳ tài chính\")" if 'df_balance_sheet' in globals() and df_balance_sheet is not None and 'Chỉ số' in df_balance_sheet.columns else "PRIMARY KEY (ticker, time)",
            "bronze_income_statements": "PRIMARY KEY (ticker, \"Chỉ số\", \"Kỳ tài chính\")" if 'df_income_statement' in globals() and df_income_statement is not None and 'Chỉ số' in df_income_statement.columns else "PRIMARY KEY (ticker, time)",
            "bronze_cash_flows": "PRIMARY KEY (ticker, \"Chỉ số\", \"Kỳ tài chính\")" if 'df_cash_flow' in globals() and df_cash_flow is not None and 'Chỉ số' in df_cash_flow.columns else "PRIMARY KEY (ticker, time)",
            "bronze_financial_ratios": "PRIMARY KEY (ticker, ticker) -- Tạm thời tạo bảng động cho ratios",
            "bronze_market_news": "PRIMARY KEY (ticker, id)" if 'df_news' in globals() and df_news is not None and 'id' in df_news.columns else "",
            "bronze_corporate_events": "PRIMARY KEY (ticker, time)",
            "bronze_vnindex_prices": "PRIMARY KEY (time)"
        }

        other_tables = {
            "bronze_realtime_quotes": df_realtime if 'df_realtime' in globals() else None,
            "bronze_company_profiles": df_profile if 'df_profile' in globals() else None,
            "bronze_balance_sheets": df_balance_sheet if 'df_balance_sheet' in globals() else None,
            "bronze_income_statements": df_income_statement if 'df_income_statement' in globals() else None,
            "bronze_cash_flows": df_cash_flow if 'df_cash_flow' in globals() else None,
            "bronze_financial_ratios": df_ratios if 'df_ratios' in globals() else None,
            "bronze_market_news": df_news if 'df_news' in globals() else None,
            "bronze_corporate_events": df_events if 'df_events' in globals() else None,
            "bronze_vnindex_prices": df_vnindex if 'df_vnindex' in globals() else None
        }

        print("\n Đang tiến hành cập nhật lũy kế các bảng chỉ số và báo cáo tài chính...")
        for table_name, df_data in other_tables.items():
            if df_data is not None and not df_data.empty:
                conn.register("df_temp_view", df_data)

                # KIỂM TRA BẢNG ĐÃ TỒN TẠI CHƯA
                table_exists = conn.execute(f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table_name}'").fetchone()[0]

                if table_exists == 0:
                    # Nếu bảng chưa có, tạo mới
                    conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df_temp_view")
                    print(f"   + [TẠO MỚI] Đã khởi tạo thành công bảng: [{table_name}]")
                else:
                    # Nếu bảng ĐÃ CÓ SẴN dữ liệu cũ (như năm 2024-2025) -> nạp nối đuôi
                    # Dùng UNION/DISTINCT để làm sạch
                    conn.execute(f"""
                        CREATE TABLE temp_union_table AS
                        SELECT * FROM {table_name}
                        UNION BY NAME
                        SELECT * FROM df_temp_view;
                    """)
                    conn.execute(f"CREATE OR REPLACE TABLE {table_name} AS SELECT DISTINCT * FROM temp_union_table;")
                    conn.execute("DROP TABLE temp_union_table;")
                    print(f" Đã gộp thêm dữ liệu mới vào bảng: [{table_name}]")
            else:
                print(f"   Bảng [{table_name}] không có dữ liệu để xử lý.")

        print("\n Pipeline tích lũy tầng Bronze hoàn thành!")

    except Exception as e:
        print(f"\n Quá trình nạp dữ liệu thất bại. Chi tiết lỗi:\n{e}")
        raise e

load_to_motherduck_pipeline()
