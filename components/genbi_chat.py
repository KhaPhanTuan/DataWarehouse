import streamlit as st
import duckdb
import os
import requests

def get_groq_response(prompt: str, context: str) -> str:
    """Gửi ngữ cảnh dữ liệu và câu hỏi của người dùng sang Groq API"""
    api_key = os.getenv("groq_api_key")
    if not api_key:
        return "⚠️ Chưa cấu hình 'groq_api_key' trong file .env. Vui lòng bổ sung để chat với GenBI!"
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # NÂNG CẤP CHUYÊN SÂU: Prompt định hình phong cách Chuyên gia Phân tích Tài chính cao cấp
    system_prompt = f"""
    Bạn là một Chuyên viên Phân tích Khối Nghiên cứu Thị trường Chứng khoán cấp cao (VN Stock Intelligence Senior Analyst).
    
    QUY TẮC ĐỊNH DẠNG SỐ & ĐƠN VỊ:
    1. Dữ liệu giá trong bảng dưới đây đang ở đơn vị "nghìn đồng" (ví dụ: 72.25 nghĩa là 72,250 đồng). 
    2. Khi trả lời về giá, BẮT BUỘC phải nhân với 1000 và định dạng lại thành số đầy đủ (ví dụ: 72,250 ₫). TUYỆT ĐỐI KHÔNG trả lời 72.25 ₫.
    3. Luôn sử dụng ngôn ngữ tài chính chuyên nghiệp: "biên độ dao động", "thanh khoản", "xu hướng tích lũy".

    [BẢNG DỮ LIỆU GIAO DỊCH 15 PHIÊN GẦN NHẤT TỪ LAKEHOUSE]:
    {context}
    """
    
    payload = {
        "model": "openai/gpt-oss-20b", # Model giữ nguyên như cũ để đảm bảo tốc độ và độ thông minh
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.15 # Hạ thấp một chút để AI bám sát dữ liệu gốc chuẩn xác hơn, tránh trả lời bay bổng
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return f"Lỗi kết nối Groq API (Mã lỗi: {response.status_code}): {response.text}"
    except Exception as e:
        return f"Đã xảy ra lỗi khi gọi AI: {e}"

def render_chat_page(ticker: str):
    """Giao diện trang Chatbot GenBI Assistant"""
    st.title("GenBI Assistant — Trợ lý Dữ liệu thông minh")
    st.caption(f"Đang kết nối Lakehouse dữ liệu giá thực tế của mã cổ phiếu: **{ticker}**")
    
    if st.button("Quay lại Dashboard", type="secondary"):
        st.session_state.show_chat = False
        st.rerun()
        
    st.divider()
    
    # Khởi tạo lịch sử chat
    if "messages" not in st.session_state:
        st.session_state.messages = []
        
    # Hiển thị lịch sử chat
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    # Xử lý khi người dùng nhập câu hỏi
    if user_input := st.chat_input(f"Hỏi tôi bất kỳ điều gì về biến động giá của {ticker}..."):
        with st.chat_message("user"):
            st.markdown(user_input)
        st.session_state.messages.append({"role": "user", "content": user_input})
        
        # BƯỚC RAG: Truy vấn nhanh dữ liệu giá gần nhất từ MotherDuck để làm ngữ cảnh (Context)
        token = os.getenv("MOTHERDUCK_TOKEN")
        context_str = "Không tìm thấy dữ liệu giá."
        
        if token:
            try:
                con = duckdb.connect(f"md:vn_stock_analytics?token={token.strip()}")
                # Lấy 15 ngày giao dịch gần nhất của mã đó để AI phân tích xu hướng ngắn hạn
                query = f"""
                    SELECT transaction_date, open_price, high_price, low_price, close_price, volume
                    FROM vn_stock_analytics.main.fact_daily_prices
                    WHERE UPPER(ticker) = UPPER('{ticker}')
                    ORDER BY transaction_date DESC
                    LIMIT 15
                """
                df_context = con.execute(query).fetchdf()
                con.close()
                if not df_context.empty:
                    context_str = df_context.to_string(index=False)
            except Exception as e:
                context_str = f"Lỗi truy vấn database lấy ngữ cảnh: {e}"
        
        # Gọi Groq sinh câu trả lời
        with st.chat_message("assistant"):
            with st.spinner("GenBI đang phân tích dữ liệu trên Lakehouse..."):
                ai_response = get_groq_response(user_input, context_str)
                st.markdown(ai_response)
                
        st.session_state.messages.append({"role": "assistant", "content": ai_response})