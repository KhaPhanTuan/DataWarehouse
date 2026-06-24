import os
from vnstock import register_user, Market, Reference, Fundamental
import time
import pandas as pd
from datetime import datetime, timedelta

# 1. Hàm bọc thông minh hỗ trợ cả Colab và GitHub Actions
def get_secret_key(key_name):
    try:
        from google.colab import userdata
        return userdata.get(key_name)
    except ImportError:
        return os.environ.get(key_name)

VNSTOCK_KEY = get_secret_key('VNSTOCK_API_KEY')
if not VNSTOCK_KEY:
    raise ValueError("Thiếu cấu hình VNSTOCK_API_KEY!")

# Đăng ký tài khoản hệ thống Vnstock
register_user(api_key=VNSTOCK_KEY)

# Khởi tạo các miền dữ liệu (Unified UI) để chuẩn bị gọi hàm
market = Market()
ref = Reference()
fund = Fundamental()

print(f"Xác thực thành công hệ thống Vnstock API.")

# =========================================================================
# 0. CẤU HÌNH TỰ ĐỘNG QUÉT MÃ TỪ CLOUD & TỐI ƯU HÓA NGÀY DELTA
# =========================================================================
# Danh sách mã dự phòng tối thiểu nếu kho dữ liệu thô trống hoàn toàn
FALLBACK_SYMBOLS = ['HPG', 'FPT', 'VCB', 'VNM', 'MWG']

def dynamic_load_warehouse_tickers():
    md_token = get_secret_key('MOTHERDUCK_TOKEN')
    if not md_token:
        print("Không tìm thấy MOTHERDUCK_TOKEN, sử dụng danh sách mã dự phòng.")
        return FALLBACK_SYMBOLS
    try:
        import duckdb
        conn = duckdb.connect(f"md:?token={md_token.strip()}")
        df_tickers = conn.execute("""
            SELECT DISTINCT ticker 
            FROM vn_stock_analytics.main.bronze_daily_prices 
            ORDER BY ticker
        """).fetchdf()
        conn.close()
        
        if not df_tickers.empty:
            active_tickers = [str(t).upper() for t in df_tickers['ticker'].tolist() if t]
            print(f"Lấy mã từ Cloud thành công! Hệ thống tự động điều phối cập nhật cho {len(active_tickers)} mã.")
            return active_tickers
    except Exception as e:
        print(f"Không thể lấy mã động từ Cloud ({e}). Chuyển sang danh sách dự phòng.")
    return FALLBACK_SYMBOLS

# Kích nổ luồng lấy danh sách mã từ kho lưu trữ đám mây
SYMBOLS = dynamic_load_warehouse_tickers()

# TỐI ƯU HÓA CHÍ MẠNG: Tự động tính toán cửa sổ lùi 3 ngày gần nhất để chạy hằng ngày
# Giúp triệt tiêu thời gian tải dữ liệu lớn 10 năm lặp lại vô nghĩa
START_DATE = (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')
END_DATE = datetime.now().strftime('%Y-%m-%d')
COUNT_DATA = 50 # Giảm số lượng dòng quét tối đa xuống mức tối thiểu (3 ngày chỉ có 3 nến giá)

print(f"[TẦNG BRONZE] Khởi động Incremental Pipeline hằng ngày (Từ ngày {START_DATE} -> {END_DATE})")

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

# Lấy mốc thời gian chạy pipeline (Dùng chung cho cả phiên gộp)
pipeline_run_time = datetime.now()

try:
    # 1. TẢI DỮ LIỆU ĐỘC LẬP (THỊ TRƯỜNG CHUNG - CHỈ CHẠY 1 LẦN)
    print(f"Đang quét dữ liệu VNINDEX từ {START_DATE}...")
    df_vnindex = market.index('VNINDEX').ohlcv(start=START_DATE, end=END_DATE, count=COUNT_DATA)
    if df_vnindex is not None and not df_vnindex.empty:
        if 'date' in df_vnindex.columns:
            df_vnindex = df_vnindex.rename(columns={'date': 'time'})
        df_vnindex['ingested_at'] = pipeline_run_time

    # 2. VÒNG LẶP CRAWL DỮ LIỆU TĂNG TRƯỞNG THEO TỪNG MÃ CỔ PHIẾU
    for SYMBOL in SYMBOLS:
        print(f"\n --------------------------------------------------")
        print(f"Đang tiến hành crawl dữ liệu Delta cho mã: [{SYMBOL}]...")

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

        print(f"Đã hoàn thành bốc dữ liệu phiên mới cho mã [{SYMBOL}]. Nghỉ 20 giây chống chặn hệ thống...")
        time.sleep(20)

    # 3. GỘP DỮ LIỆU THÀNH ĐA TẦNG BRONZE ĐỒNG NHẤT (CONCATENATION)
    print(f"\n--------------------------------------------------")
    print("Đang tiến hành gom cụm dữ liệu phân tán...")

    df_history = pd.concat(history_lists, ignore_index=True) if history_lists else None
    df_realtime = pd.concat(realtime_lists, ignore_index=True) if realtime_lists else None
    df_profile = pd.concat(profile_lists, ignore_index=True) if profile_lists else None
    df_news = pd.concat(news_lists, ignore_index=True) if news_lists else None
    df_events = pd.concat(event_lists, ignore_index=True) if event_lists else None
    df_balance_sheet = pd.concat(balance_sheet_lists, ignore_index=True) if balance_sheet_lists else None
    df_income_statement = pd.concat(income_statement_lists, ignore_index=True) if income_statement_lists else None
    df_cash_flow = pd.concat(cash_flow_lists, ignore_index=True) if cash_flow_lists else None
    df_ratios = pd.concat(ratios_lists, ignore_index=True) if ratios_lists else None

    print(f"\n Tải dữ liệu tăng trưởng hằng ngày thành công!")

except Exception as e:
    print(f"Đã xảy ra lỗi trong quá trình crawl dữ liệu: {e}")

import duckdb

def load_to_motherduck_pipeline():
    md_token = None
    try:
        from google.colab import userdata
        md_token = userdata.get('MOTHERDUCK_TOKEN')
    except ImportError:
        md_token = os.environ.get('MOTHERDUCK_TOKEN')
    except Exception as secret_err:
        raise ValueError("Có lỗi khi truy cập hệ thống bảo mật!") from secret_err

    if not md_token:
        raise ValueError("Không tìm thấy 'MOTHERDUCK_TOKEN'!")

    md_token = md_token.strip()
    
    print("Đang thiết lập kết nối DuckDB Cloud...")
    try:
        connection_string = f"md:?token={md_token}"
        conn = duckdb.connect(connection_string)

        conn.execute("CREATE DATABASE IF NOT EXISTS vn_stock_analytics;")
        conn.execute("USE vn_stock_analytics.main;")

        # 1. XỬ LÝ LŨY KẾ NỐI ĐUÔI: bronze_daily_prices
        if 'df_history' in globals() and df_history is not None and not df_history.empty:
            print("\n  Tiến hành cơ chế gộp lũy kế tăng trưởng: [bronze_daily_prices]...")
            conn.register("df_prices_view", df_history)

            table_exists = conn.execute("""
                SELECT COUNT(*) FROM information_schema.tables 
                WHERE table_catalog = current_database() AND table_schema = 'main' AND table_name = 'bronze_daily_prices'
            """).fetchone()[0]

            if table_exists == 0:
                conn.execute("""
                    CREATE TABLE bronze_daily_prices AS 
                    SELECT CAST(time AS TIMESTAMP) AS time, open, high, low, close, CAST(volume AS LONG) AS volume, ticker, CAST(ingested_at AS TIMESTAMP) AS ingested_at 
                    FROM df_prices_view;
                """)
                print("   + [TẠO MỚI] Đã khởi tạo bảng: [bronze_daily_prices]")
            else:
                # Gộp nối đuôi dữ liệu 3 ngày mới vào kho dữ liệu vĩnh viễn cũ
                conn.execute("DROP TABLE IF EXISTS temp_union_prices;")
                conn.execute("""
                    CREATE TABLE temp_union_prices AS
                    SELECT * FROM bronze_daily_prices
                    UNION BY NAME
                    SELECT CAST(time AS TIMESTAMP) AS time, open, high, low, close, CAST(volume AS LONG) AS volume, ticker, CAST(ingested_at AS TIMESTAMP) AS ingested_at 
                    FROM df_prices_view;
                """)

                # QUALIFY ROW_NUMBER: Bảo vệ kho không bị trùng lặp, ép lấy bản ghi mới nhất của ngày đó nếu trùng mốc thời gian
                conn.execute("""
                    CREATE OR REPLACE TABLE bronze_daily_prices AS 
                    SELECT * FROM temp_union_prices
                    QUALIFY ROW_NUMBER() OVER (
                        PARTITION BY ticker, time 
                        ORDER BY ingested_at DESC
                    ) = 1;
                """)
                conn.execute("DROP TABLE temp_union_prices;")
                print("   + [HỢP NHẤT KHỬ TRÙNG] Cập nhật tăng trưởng thành công cho bảng: [bronze_daily_prices]")

        # 2. XỬ LÝ LŨY KẾ CHO CÁC BẢNG CÒN LẠI
        table_schemas = {
            "bronze_realtime_quotes": "PRIMARY KEY (ticker, time)",
            "bronze_company_profiles": "PRIMARY KEY (ticker)",
            "bronze_balance_sheets": "PRIMARY KEY (ticker, item_id)",
            "bronze_income_statements": "PRIMARY KEY (ticker, item_id)",
            "bronze_cash_flows": "PRIMARY KEY (ticker, item_id)",
            "bronze_financial_ratios": "PRIMARY KEY (ticker, item_id)",
            "bronze_market_news": "PRIMARY KEY (article_id)",
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

        for table_name, df_data in other_tables.items():
            if df_data is not None and not df_data.empty:
                conn.register("df_temp_view", df_data)
                table_exists = conn.execute(f"""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_catalog = current_database() AND table_schema = 'main' AND table_name = '{table_name}'
                """).fetchone()[0]

                if table_exists == 0:
                    conn.execute(f"CREATE TABLE {table_name} AS SELECT * FROM df_temp_view")
                    print(f"   + [TẠO MỚI] Khởi tạo thành công bảng: [{table_name}]")
                else:
                    conn.execute("DROP TABLE IF EXISTS temp_union_table;")
                    conn.execute(f"""
                        CREATE TABLE temp_union_table AS
                        SELECT * FROM {table_name}
                        UNION BY NAME
                        SELECT * FROM df_temp_view;
                    """)

                    pk_string = table_schemas.get(table_name, "")
                    partition_cols = pk_string.split("(")[1].split(")")[0] if "PRIMARY KEY" in pk_string else ("ticker, time" if "ticker" in df_data.columns else "time")
                        
                    conn.execute(f"""
                        CREATE OR REPLACE TABLE {table_name} AS 
                        SELECT * FROM temp_union_table
                        QUALIFY ROW_NUMBER() OVER (
                            PARTITION BY {partition_cols} 
                            ORDER BY ingested_at DESC
                        ) = 1;
                    """)
                    conn.execute("DROP TABLE temp_union_table;")
                    print(f"   + [HỢP NHẤT KHỬ TRÙNG] Đồng bộ tăng trưởng thành công cho bảng: [{table_name}]")

        print("\n[THÀNH CÔNG] Pipeline tích lũy tầng Bronze hoàn thành xuất sắc!")
        conn.close()

    except Exception as e:
        print(f"\n Quá trình nạp dữ liệu thất bại: {e}")
        raise e

load_to_motherduck_pipeline()
