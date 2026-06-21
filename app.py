"""
Dashboard Streamlit - Phân tích Chứng khoán VN & Tâm lý Thị trường
"""

import duckdb
import streamlit as st
import pandas as pd
import os
import importlib
import sys
import re
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

# Hàm bóc tách chuỗi phần trăm từ AI để vẽ biểu đồ tròn (Pie chart)
def parse_sentiment_percentages(score_str: str) -> dict:
    default_vals = {"Tích cực": 0.0, "Trung lập": 100.0, "Tiêu cực": 0.0}
    if not score_str or pd.isna(score_str):
        return default_vals
    try:
        pos_match = re.search(r'positive=([\d.]+)%', str(score_str))
        neu_match = re.search(r'neutral=([\d.]+)%', str(score_str))
        neg_match = re.search(r'negative=([\d.]+)%', str(score_str))
        
        return {
            "Tích cực": float(pos_match.group(1)) if pos_match else 0.0,
            "Trung lập": float(neu_match.group(1)) if neu_match else 100.0,
            "Tiêu cực": float(neg_match.group(1)) if neg_match else 0.0
        }
    except Exception:
        return default_vals

# Kiểm tra nếu người dùng đang mở trang chat GenBI
if st.session_state.show_chat:
    selected_ticker = st.session_state.get("current_ticker", "HPG")
    genbi_chat.render_chat_page(selected_ticker)
    st.stop()

# Lấy danh sách TOÀN BỘ 186 mã cổ phiếu thực tế có trong Data Warehouse
@st.cache_data(ttl=3600)
def load_all_tickers() -> list[str]:
    token = os.getenv("MOTHERDUCK_TOKEN")
    if not token:
        return ["HPG", "FPT", "VCB", "VNM", "MWG"]
    try:
        con = duckdb.connect(f"md:vn_stock_analytics")
        df = con.execute("SELECT DISTINCT ticker FROM vn_stock_analytics.main.analytics_wide_ai_ready ORDER BY ticker").fetchdf()
        con.close()
        return [str(t).upper() for t in df['ticker'].tolist() if t]
    except Exception:
        return ["HPG", "FPT", "VCB", "VNM", "MWG"]

ALL_AVAILABLE_TICKERS = load_all_tickers()

# =============================================================================
# TRUY VẤN DỮ LIỆU GIÁ CHÍNH TỪ MOTHERDUCK
# =============================================================================
@st.cache_data(ttl=3600)
def load_real_stock_data(ticker: str) -> pd.DataFrame:
    token = os.getenv("MOTHERDUCK_TOKEN")
    if not token:
        st.error("Không tìm thấy biến 'MOTHERDUCK_TOKEN' trong file .env!")
        return pd.DataFrame()
    try:
        con = duckdb.connect(f"md:vn_stock_analytics")
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
def load_real_market_news(ticker: str) -> pd.DataFrame:
    token = os.getenv("MOTHERDUCK_TOKEN")
    if not token:
        return pd.DataFrame()
    try:
        con = duckdb.connect(f"md:vn_stock_analytics")
        # THỰC HIỆN LEFT JOIN ĐỂ LẤY URL TỪ BẢNG THÔ CHUẨN XÁC
        query = f"""
            SELECT 
                ai.title,
                ai.published_at,
                ai.sentiment_label,
                ai.sentiment_score AS raw_sentiment_score,
                ai.summary,
                bn.url,
                'Tổng hợp' AS source
            FROM vn_stock_analytics.main.analytics_wide_ai_ready ai
            LEFT JOIN vn_stock_analytics.main.bronze_market_news bn ON ai.title = bn.title
            WHERE UPPER(ai.ticker) = UPPER('{ticker}')
            ORDER BY ai.published_at DESC
        """
        df = con.execute(query).fetchdf()
        con.close()
        
        if not df.empty:
            df['published_at'] = pd.to_datetime(df['published_at'])
            label_map = {"positive": "Tích cực", "negative": "Tiêu cực", "neutral": "Trung lập"}
            df['sentiment_label'] = df['sentiment_label'].str.lower().map(label_map).fillna("Trung lập")
        return df
    except Exception as e:
        st.error(f"Lỗi kết nối dữ liệu AI Ready & URL: {e}")
        return pd.DataFrame()

# =============================================================================
# BỘ LỌC SIDEBAR
# =============================================================================
DATA_PRICE_START = date(2015, 1, 5)
DATA_NEWS_START = date(2025, 10, 22)
DATA_MAX_DATE = date(2026, 6, 12)

with st.sidebar:
    st.header("Bộ lọc dữ liệu")
    
    # [NÂNG CẤP]: Tìm kiếm gợi ý (Autocomplete) từ 186 mã cổ phiếu, giao diện gọn gàng
    selected_ticker = st.selectbox(
        "Mã cổ phiếu", 
        options=ALL_AVAILABLE_TICKERS, 
        index=ALL_AVAILABLE_TICKERS.index("FPT") if "FPT" in ALL_AVAILABLE_TICKERS else 0,
        help="Nhập chữ cái để tìm kiếm nhanh mã cổ phiếu"
    )
    st.session_state["current_ticker"] = selected_ticker

    default_start_date = DATA_NEWS_START
    default_end_date = date(2026, 6, 8)

    start_text = st.text_input("Ngày bắt đầu giá", value=format_dd_mm_yyyy(default_start_date))
    end_text = st.text_input("Ngày kết thúc giá", value=format_dd_mm_yyyy(default_end_date))

    filter_start = parse_dd_mm_yyyy(start_text)
    filter_end = parse_dd_mm_yyyy(end_text)

    if not filter_start or not filter_end or filter_start > filter_end:
        st.error("Ngày nhập vào không hợp lệ hoặc sai định dạng dd/mm/yyyy.")
        st.stop()

    if filter_start < DATA_PRICE_START or filter_end > DATA_MAX_DATE:
        st.error(f"Hệ thống chỉ có dữ liệu giá từ {format_dd_mm_yyyy(DATA_PRICE_START)} đến {format_dd_mm_yyyy(DATA_MAX_DATE)}.")
        st.stop()

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
df_news = load_real_market_news(selected_ticker)

if df_stock.empty:
    st.warning(f"Không tìm thấy dữ liệu giá của mã {selected_ticker} trên MotherDuck.")
    st.stop()

df_prices = df_stock[(df_stock["date"].dt.date >= filter_start) & (df_stock["date"].dt.date <= filter_end)].sort_values("date")

# KHU VỰC GIAO DIỆN CHÍNH
overview_col, chat_btn_col = st.columns([5, 1.2])
with overview_col:
    st.subheader(f"Tổng quan mã cổ phiếu — {selected_ticker}")
    st.caption(f"Thời gian giá: **{format_dd_mm_yyyy(filter_start)}** → **{format_dd_mm_yyyy(filter_end)}**")
with chat_btn_col:
    st.write("")
    if st.button("💬 GenBI Assistant", type="primary", use_container_width=True):
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

# Lấy nhãn trạng thái từ bài báo duy nhất hiện tại
if not df_news.empty:
    current_label = df_news.iloc[0]["sentiment_label"]
    raw_score_string = df_news.iloc[0]["raw_sentiment_score"]
else:
    current_label = "Trung lập (Mặc định)"
    raw_score_string = "positive=0.0%; neutral=100.0%; negative=0.0%"

# Hiển thị 3 ô KPI gọn gàng
kpi1, kpi2, kpi3 = st.columns(3)
with kpi1:
    st.metric("Giá đóng cửa gần nhất", format_vnd(latest_close), delta=f"{pct_change:+.2f}%")
with kpi2:
    st.metric("Tổng khối lượng giao dịch", f"{total_volume:,} CP")
with kpi3:
    st.metric("Sắc thái tâm lý chủ đạo", current_label)

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
    st.markdown("**Biểu đồ: Phân rã sắc thái AI (%)**")
    pct_data = parse_sentiment_percentages(raw_score_string)
    labels = list(pct_data.keys())
    values = list(pct_data.values())
    
    color_map = {"Tích cực": "#2ecc71", "Trung lập": "#3498db", "Tiêu cực": "#e74c3c"}
    fig_pie = go.Figure(data=[go.Pie(
        labels=labels, 
        values=values, 
        hole=0.45, 
        marker=dict(colors=[color_map[l] for l in labels]),
        textinfo='label+percent'
    )])
    fig_pie.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
    st.plotly_chart(fig_pie, use_container_width=True)

# =============================================================================
# BIỂU ĐỒ NẾN KỸ THUẬT PHÂN TÍCH OHLC GIÁ TRỊ CAO TRÊN MOTHERDUCK
# =============================================================================
st.divider()
st.markdown(f"**Biểu đồ phân tích kỹ thuật: Biến động giá nến Nhật OHLC — {selected_ticker}**")
fig_candle = go.Figure(data=[go.Candlestick(
    x=df_prices["date"],
    open=df_prices["open"] * 1000,
    high=df_prices["high"] * 1000,
    low=df_prices["low"] * 1000,
    close=df_prices["close"] * 1000,
    increasing_line_color='#2ecc71', decreasing_line_color='#e74c3c',
    name="Nến giá"
)])
fig_candle.update_layout(
    height=360,
    margin=dict(l=10, r=10, t=20, b=10),
    xaxis_rangeslider_visible=False,
    yaxis_title="Giá giao dịch (₫)"
)
st.plotly_chart(fig_candle, use_container_width=True)

# =============================================================================
# BOX TIN TỨC: DANH SÁCH CÁC BÀI BÁO MỚI NHẤT & TÓM TẮT TỪ AI
# =============================================================================
st.write("")
st.subheader("Tin tức & Tóm tắt phân tích mới nhất")

if df_news.empty:
    st.info("Hiện hệ thống crawler đang đồng bộ tin tức cho mã cổ phiếu này.")
else:
    # Vòng lặp hiển thị toàn bộ danh sách bài báo thu thập được
    for _, article in df_news.iterrows():
        publish_time = article["published_at"].strftime("%d/%m/%Y %H:%M") if pd.notnull(article.get("published_at")) else "Không rõ ngày"
        
        badge_colors = {"Tích cực": "#2ecc71", "Tiêu cực": "#e74c3c", "Trung lập": "#3498db"}
        sentiment = article.get('sentiment_label', 'Trung lập')
        current_badge_color = badge_colors.get(sentiment, "#3498db")
        
        # 1. XỬ LÝ SUMMARY AI VỚI MODEL ĐÃ CẬP NHẬT (LLAMA-3.1-8B-INSTANT)
        raw_summary = article.get('summary', '')
        if pd.isna(raw_summary) or str(raw_summary).strip() in ['', 'None', 'nan']:
            groq_key = os.getenv("GROQ_API_KEY") or os.getenv("groq_api_key")
            if groq_key:
                try:
                    from groq import Groq
                    client = Groq(api_key=groq_key)
                    # Đổi sang model mới tinh 'llama-3.1-8b-instant' chạy siêu tốc và ổn định
                    completion = client.chat.completions.create(
                        model="llama-3.1-8b-instant",
                        messages=[
                            {"role": "system", "content": "Bạn là một trợ lý phân tích chứng khoán Việt Nam chuyên nghiệp. Hãy viết tóm tắt lý do hoặc bối cảnh cho tiêu đề bài báo bằng tiếng Việt ngắn gọn trong 1-2 câu."},
                            {"role": "user", "content": f"Tiêu đề: {article['title']}"}
                        ],
                        max_tokens=150,
                        temperature=0.3
                    )
                    ai_summary_html = f"<b>Tóm tắt:</b> {completion.choices[0].message.content}"
                except Exception as groq_err:
                    ai_summary_html = f"<i style='color: #e74c3c;'>Hệ thống AI đang bận (Lỗi: {groq_err}), vui lòng thử lại sau...</i>"
            else:
                ai_summary_html = "<i style='color: #8c98a5;'>Hệ thống AI đang chờ phân tích bổ sung (Thiếu GROQ_API_KEY)...</i>"
        else:
            ai_summary_html = f"<b>Tóm tắt lý do từ AI:</b> {raw_summary}"
            
        # 2. XỬ LÝ LINK URL CHUẨN XÁC VÀ VIẾT TRÊN 1 DÒNG ĐỂ TRANH LỖI MULTILINE MARKDOWN
        article_url = str(article.get('url', '')).strip()
        link_button_html = ""
        if article_url and article_url != 'None' and article_url != 'nan':
            full_url = f"https://vietstock.vn{article_url}" if article_url.startswith("/") else article_url
            # Viết chuỗi HTML gọn trên một dòng, tránh thụt đầu dòng làm vỡ markdown
            link_button_html = f'<div style="margin-top: 15px; text-align: right;"><a href="{full_url}" target="_blank" style="text-decoration: none; background-color: #3498db; color: white; padding: 6px 16px; border-radius: 4px; font-size: 13px; font-weight: 500; display: inline-block;">Xem bài báo gốc ↗</a></div>'
        
        # 3. RENDER DUY NHẤT 1 KHỐI HTML ĐỒNG NHẤT KHÔNG CÓ THỤT ĐẦU DÒNG TRONG CHUỖI
        st.markdown(f"""
<div style="background-color: #f8f9fa; padding: 20px; border-radius: 8px; border-left: 5px solid {current_badge_color}; margin-bottom: 15px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
        <span style="color: #6c757d; font-size: 13px;">Xuất bản: {publish_time}</span>
        <span style="background-color: {current_badge_color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">{sentiment}</span>
    </div>
    <h4 style="margin-top: 5px; margin-bottom: 10px; color: #2c3e50; font-weight: 600; line-height: 1.4;">{article['title']}</h4>
    <p style="font-size: 14px; color: #4f5f6f; line-height: 1.6; margin-bottom: 5px;">{ai_summary_html}</p>
    {link_button_html}
</div>
""", unsafe_allow_html=True)