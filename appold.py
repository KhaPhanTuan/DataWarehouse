"""
Dashboard Streamlit - Phân tích Chứng khoán VN & Tâm lý Thị trường
Bản cập nhật: Khôi phục và nâng cấp Biểu đồ số 3 (Biến động điểm Tâm lý theo ngày), Sửa màu sắc bộ lọc, Link mở tab mới & Tích hợp GenBI Chat RAG
"""

import duckdb
import streamlit as st
import pandas as pd
import os
import importlib
import sys
from datetime import date, datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Ép hệ thống nhận diện thư mục hiện tại làm gốc để nạp module mới tinh sạch sẽ
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from components import genbi_chat
importlib.reload(genbi_chat)

# =============================================================================
# CẤU HÌNH TRANG & TOKEN
# =============================================================================
st.set_page_config(
    page_title="VN Stock Intelligence Dashboard",

    layout="wide",
    initial_sidebar_state="expanded",
)

if "show_chat" not in st.session_state:
    st.session_state.show_chat = False

from dotenv import load_dotenv
load_dotenv()

# Hàm định dạng tiền tệ chuẩn VNĐ
def format_vnd(value: float) -> str:
    return f"{value * 1000:,.0f} ₫"

def format_dd_mm_yyyy(value: date | datetime | pd.Timestamp) -> str:
    if isinstance(value, pd.Timestamp):
        value = value.date()
    elif isinstance(value, datetime):
        value = value.date()
    return value.strftime("%d/%m/%Y")

def parse_dd_mm_yyyy(text: str) -> date | None:
    text = (text or "").strip()
    try:
        return datetime.strptime(text, "%d/%m/%Y").date()
    except ValueError:
        return None

# Kiểm tra nếu người dùng đang mở trang chat GenBI
if st.session_state.show_chat:
    selected_ticker = st.session_state.get("current_ticker", "HPG")
    genbi_chat.render_chat_page(selected_ticker)
    st.stop()

# =============================================================================
# TRUY VẤN DỮ LIỆU GIÁ CHÍNH TỪ MOTHERDUCK
# =============================================================================
@st.cache_data(ttl=3600)
def load_real_stock_data(ticker: str) -> pd.DataFrame:
    token = os.getenv("motherduck_token")
    if not token:
        st.error("Không tìm thấy biến 'motherduck_token' trong file .env!")
        return pd.DataFrame()
    try:
        con = duckdb.connect(f"md:vn_stock_analytics?motherduck_token={token}")
        query = f"""
            SELECT 
                transaction_date AS date,
                open_price AS open,
                high_price AS high,
                low_price AS low,
                close_price AS close,
                volume
            FROM vn_stock_analytics.main.fact_daily_prices
            WHERE UPPER(ticker) = UPPER('{ticker}')
            ORDER BY transaction_date ASC
        """
        df = con.execute(query).fetchdf()
        con.close()
        df['date'] = pd.to_datetime(df['date'])
        return df
    except Exception as e:
        st.error(f"Lỗi kết nối Data Giá: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=1800)
def load_real_market_news(ticker: str, start_date: date, end_date: date) -> pd.DataFrame:
    token = os.getenv("motherduck_token")
    if not token:
        return pd.DataFrame()
    try:
        con = duckdb.connect(f"md:vn_stock_analytics?motherduck_token={token}")
        query = f"""
            SELECT 
                f.title,
                f.published_at,
                COALESCE(f.sentiment_score, 0.0) AS sentiment_score,
                f.summary,
                COALESCE(b.url, '#') AS url,
                COALESCE(b.head, 'Tổng hợp') AS source
            FROM vn_stock_analytics.main.fact_news f
            LEFT JOIN vn_stock_analytics.main.bronze_market_news b
                ON f.article_id = b.article_id
            WHERE UPPER(f.ticker) = UPPER('{ticker}')
              AND CAST(f.published_at AS DATE) BETWEEN '{start_date}' AND '{end_date}'
            ORDER BY f.published_at DESC
        """
        df = con.execute(query).fetchdf()
        con.close()
        
        if not df.empty:
            df['published_at'] = pd.to_datetime(df['published_at'])
            df['sentiment_score'] = pd.to_numeric(df['sentiment_score']).fillna(0.0)
            df['sentiment_label'] = df['sentiment_score'].apply(
                lambda x: "Tích cực" if x > 0.1 else ("Tiêu cực" if x < -0.1 else "Trung lập")
            )
        return df
    except Exception as e:
        st.error(f"Lỗi kết nối Data Tin tức: {e}")
        return pd.DataFrame()

def map_sentiment_filter(selected: list[str]) -> set[int] | None:
    if not selected or "Tất cả" in selected:
        return None
    mapping = {"Tích cực": 1, "Trung lập": 0, "Tiêu cực": -1}
    return {mapping[s] for s in selected if s in mapping}

# =============================================================================
# BỘ LỌC SIDEBAR & ĐỔI MÀU UI CÁC TAG THEO MÀU PASTEL YÊU CẦU
# =============================================================================
TICKERS = ["HPG", "FPT", "VCB", "VNM", "MWG"]
DATA_PRICE_START = date(2015, 1, 5)
DATA_NEWS_START = date(2025, 10, 22)
DATA_MAX_DATE = date(2026, 6, 12)

st.markdown("""
    <style>
    span[data-baseweb="tag"]:has(span[title="Tất cả"]) { background-color: #e0e0e0 !important; color: #333333 !important; }
    span[data-baseweb="tag"]:has(span[title="Tích cực"]) { background-color: #d4edda !important; color: #155724 !important; }
    span[data-baseweb="tag"]:has(span[title="Tiêu cực"]) { background-color: #f8d7da !important; color: #721c24 !important; }
    span[data-baseweb="tag"]:has(span[title="Trung lập"]) { background-color: #d1ecf1 !important; color: #0c5460 !important; }
    </style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("Bộ lọc dữ liệu")
    selected_ticker = st.selectbox("Mã cổ phiếu", options=TICKERS, index=0)
    st.session_state["current_ticker"] = selected_ticker

    

    default_start_date = DATA_NEWS_START
    default_end_date = date(2026, 6, 8)

    start_text = st.text_input("Ngày bắt đầu", value=format_dd_mm_yyyy(default_start_date))
    end_text = st.text_input("Ngày kết thúc", value=format_dd_mm_yyyy(default_end_date))

    filter_start = parse_dd_mm_yyyy(start_text)
    filter_end = parse_dd_mm_yyyy(end_text)

    if not filter_start or not filter_end or filter_start > filter_end:
        st.error("Ngày nhập vào không hợp lệ hoặc sai định dạng dd/mm/yyyy.")
        st.stop()

    if filter_start < DATA_PRICE_START or filter_end > DATA_MAX_DATE:
        st.error(f"Hệ thống chỉ có dữ liệu từ {format_dd_mm_yyyy(DATA_PRICE_START)} đến {format_dd_mm_yyyy(DATA_MAX_DATE)}.")
        st.stop()

    if filter_start < DATA_NEWS_START:
        st.warning(
            f"Hệ thống bắt đầu phân tích tâm lý từ ngày 22/10/2025. "
            f"Giai đoạn trước đó sẽ chỉ hiển thị dữ liệu giá chứng khoán."
        )

    selected_sentiments = st.multiselect(
        "Sắc thái tâm lý", 
        options=["Tất cả", "Tích cực", "Tiêu cực", "Trung lập"], 
        default=["Tất cả"]
    )

    st.subheader("Lưu ý")
    st.caption(
        f"• Toàn bộ dữ liệu giá: **05/01/2015** → **{format_dd_mm_yyyy(DATA_MAX_DATE)}**\n\n"
        f"• Dữ liệu tâm lý & tin tức: **22/10/2025** → **08/06/2026**"
    )

# =============================================================================
# KHU VỰC HIỂN THỊ TIÊU ĐỀ LỚN & BODY
# =============================================================================
st.title("VN Stock Intelligence")
st.markdown("Hệ thống giám sát biến động giá thị trường tích hợp phân tích tâm lý theo thời gian thực.")

df_stock = load_real_stock_data(selected_ticker)
df_news = load_real_market_news(selected_ticker, filter_start, filter_end)

if df_stock.empty:
    st.warning(f"Không tìm thấy dữ liệu giá của mã {selected_ticker} trên MotherDuck.")
    st.stop()

df_prices = df_stock[(df_stock["date"].dt.date >= filter_start) & (df_stock["date"].dt.date <= filter_end)].sort_values("date")

if not df_news.empty:
    allowed_scores = map_sentiment_filter(selected_sentiments)
    if allowed_scores is not None:
        df_news = df_news[df_news["sentiment_score"].apply(lambda x: 1 if x > 0.1 else (-1 if x < -0.1 else 0)).isin(allowed_scores)]

# KHU VỰC GIAO DIỆN CHÍNH
overview_col, chat_btn_col = st.columns([5, 1.2])
with overview_col:
    st.subheader(f"Tổng quan mã cổ phiếu — {selected_ticker}")
    st.caption(f"Thời gian: **{format_dd_mm_yyyy(filter_start)}** → **{format_dd_mm_yyyy(filter_end)}**")
with chat_btn_col:
    st.write("")
    if st.button("GenBI Assistant", type="primary", use_container_width=True):
        st.session_state.show_chat = True
        st.rerun()

if df_prices.empty:
    st.warning("Không có dữ liệu giá trong khoảng thời gian đã chọn.")
    st.stop()

# Tính toán KPI an toàn chống NaN
latest_row = df_prices.iloc[-1]
prev_row = df_prices.iloc[-2] if len(df_prices) > 1 else latest_row
latest_close = latest_row["close"]
prev_close = prev_row["close"]
pct_change = ((latest_close - prev_close) / prev_close * 100) if prev_close else 0.0

total_volume = int(df_prices["volume"].sum())
total_news = len(df_news)
avg_sentiment = float(df_news["sentiment_score"].mean()) if not df_news.empty and total_news > 0 else 0.0

kpi1, kpi2, kpi3, kpi4 = st.columns(4)
with kpi1:
    st.metric("Giá đóng cửa gần nhất", format_vnd(latest_close), delta=f"{pct_change:+.2f}%")
with kpi2:
    st.metric("Tổng khối lượng", f"{total_volume:,} CP")
with kpi3:
    st.metric("Chỉ số Tâm lý TB", f"{avg_sentiment:+.2f}")
with kpi4:
    st.metric("Tổng tin tức thu thập", f"{total_news:,}")

st.divider()

# BIỂU ĐỒ DIỄN BIẾN GIÁ & TỶ LỆ TÂM LÝ
col_chart_main, col_chart_pie = st.columns([2.2, 1])

with col_chart_main:
    st.markdown("**Biểu đồ: Giá đóng cửa & Khối lượng giao dịch**")
    fig_combo = make_subplots(specs=[[{"secondary_y": True}]])
    fig_combo.add_trace(
        go.Scatter(
            x=df_prices["date"],
            y=df_prices["close"] * 1000,
            name="Giá đóng cửa",
            mode="lines",
            line=dict(color="#0068c9", width=2),
            hovertemplate="Ngày: %{x}<br>Giá: %{y:,.0f} ₫<extra></extra>",
        ),
        secondary_y=False,
    )
    fig_combo.add_trace(
        go.Bar(
            x=df_prices["date"],
            y=df_prices["volume"],
            name="Khối lượng",
            marker_color="rgba(0, 163, 255, 0.35)",
            hovertemplate="Ngày: %{x}<br>KL: %{y:,} CP<extra></extra>",
        ),
        secondary_y=True,
    )
    fig_combo.update_layout(height=350, margin=dict(l=10, r=10, t=20, b=10), hovermode="x unified")
    st.plotly_chart(fig_combo, use_container_width=True)

with col_chart_pie:
    st.markdown("**Biểu đồ: Tỷ lệ Sắc thái Tâm lý**")
    if df_news.empty:
        st.info("Không có dữ liệu sắc thái nào khớp kỳ lọc này.")
    else:
        sentiment_counts = df_news["sentiment_label"].value_counts().reset_index()
        sentiment_counts.columns = ["label", "count"]
        color_map = {"Tích cực": "#2ecc71", "Trung lập": "#3498db", "Tiêu cực": "#e74c3c"}
        fig_pie = go.Figure(data=[go.Pie(labels=sentiment_counts["label"], values=sentiment_counts["count"], hole=0.45, marker=dict(colors=[color_map.get(lbl, "#3498db") for lbl in sentiment_counts["label"]]))])
        fig_pie.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
        st.plotly_chart(fig_pie, use_container_width=True)

# =============================================================================
# BIỂU ĐỒ SỐ 3: BIẾN ĐỘNG ĐIỂM TÂM LÝ THEO NGÀY (CẬP NHẬT CHUẨN ĐÉT Ý BẠN)
# =============================================================================
st.divider()
st.markdown("Biểu đồ: Biến động điểm Tâm lý theo ngày")

if df_news.empty:
    st.info("Không có dữ liệu tin tức để tính toán điểm tâm lý theo chuỗi thời gian.")
else:
    # Gom nhóm tính điểm trung bình tâm lý của mã đó theo từng ngày
    df_news['publish_date'] = df_news['published_at'].dt.date
    daily_sentiment = df_news.groupby('publish_date')['sentiment_score'].mean().reset_index().sort_values('publish_date')
    
    fig_sentiment_line = go.Figure()
    fig_sentiment_line.add_trace(
        go.Scatter(
            x=daily_sentiment["publish_date"],
            y=daily_sentiment["sentiment_score"],
            name="Điểm tâm lý TB ngày",
            mode="lines+markers",
            line=dict(color="#2ecc71", width=2.5),
            marker=dict(size=6, color="#1abc9c"),
            hovertemplate="Ngày: %{x}<br>Điểm tâm lý: %{y:.2f}<extra></extra>"
        )
    )
    
    # Cấu hình đường biên hỗ trợ nhìn xu hướng âm / dương rõ ràng
    fig_sentiment_line.add_hline(y=0.1, line_dash="dash", line_color="rgba(46, 204, 113, 0.5)", annotation_text="Ngưỡng Tích cực")
    fig_sentiment_line.add_hline(y=-0.1, line_dash="dash", line_color="rgba(231, 76, 60, 0.5)", annotation_text="Ngưỡng Tiêu cực")
    
    fig_sentiment_line.update_layout(
        xaxis_title="Ngày công bố tin",
        yaxis_title="Điểm số Sentiment (-1 đến +1)",
        yaxis=dict(range=[-1.1, 1.1]),
        height=320,
        margin=dict(l=10, r=10, t=20, b=10)
    )
    st.plotly_chart(fig_sentiment_line, use_container_width=True)

# =============================================================================
# DANH SÁCH TIN TỨC & TRÌNH XEM CHI TIẾT (ĐƯA XUỐNG EXPANDER GỌN GÀNG)
# =============================================================================
st.write("")
with st.expander("Danh sách bài báo gần nhất"):
    if df_news.empty:
        st.write("Không tìm thấy bài báo nào trong khoảng thời gian được lọc.")
    else:
        top_news = df_news.sort_values("published_at", ascending=False).head(10).copy()
        top_news["Ngày đăng"] = top_news["published_at"].dt.strftime("%d/%m/%Y %H:%M")
        
        display_news = top_news[["Ngày đăng", "title", "source", "sentiment_label", "url", "summary"]].rename(
            columns={"title": "Tiêu đề tin tức", "source": "Nguồn báo", "sentiment_label": "Sắc thái tâm lý", "url": "Liên kết xem"}
        )
        
        selection = st.dataframe(
            display_news[["Ngày đăng", "Tiêu đề tin tức", "Nguồn báo", "Sắc thái tâm lý", "Liên kết xem"]],
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "Liên kết xem": st.column_config.LinkColumn(
                    "Liên kết xem",
                    display_text="Mở bài báo ↗"
                )
            }
        )
        
        selected_rows = selection.selection.rows if selection.selection else []
        if selected_rows:
            row_data = display_news.iloc[selected_rows[0]]
            st.markdown("---")
            st.markdown(f"#### Chi tiết nội dung tin tức")
            st.markdown(f"**Tiêu đề:** {row_data['Tiêu đề tin tức']}")
            st.markdown(f"**Nguồn:** {row_data['Nguồn báo']} | **Sắc thái:** {row_data['Sắc thái tâm lý']}")
            st.info(f"**Nội dung tóm tắt lý do:** \n{row_data['summary']}")