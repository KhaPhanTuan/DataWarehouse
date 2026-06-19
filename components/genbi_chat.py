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
    
    # Xây dựng Prompt hệ thống ép AI trả lời dựa trên Data thực tế
    system_prompt = f"""
    Bạn là một trợ lý phân tích dữ liệu chứng khoán chuyên nghiệp (VN Stock Intelligence Assistant).
    Hãy sử dụng thông tin dữ liệu giá thực tế được cung cấp dưới đây để trả lời câu hỏi của người dùng một cách chính xác, ngắn gọn, đi thẳng vào vấn đề.
    Nếu dữ liệu không có thông tin yêu cầu, hãy thẳng thắn báo là không có trong cơ sở dữ liệu, tuyệt đối không tự bịa ra con số.
    
    [DỮ LIỆU THỰC TẾ TỪ MOTHERDUCK KHỚP BỘ LỌC]:
    {context}
    """
    
    payload = {
        "model": "llama-3.3-70b-versatile", # Model mạnh và chạy cực nhanh của Groq
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            return response.json()['choices'][0]['message']['content']
        else:
            return f"❌ Lỗi kết nối Groq API (Mã lỗi: {response.status_code}): {response.text}"
    except Exception as e:
        return f"❌ Đã xảy ra lỗi khi gọi AI: {e}"

def render_chat_page(ticker: str):
    """Giao diện trang Chatbot GenBI Assistant"""
    st.title("🤖 GenBI Assistant — Trợ lý Dữ liệu thông minh")
    st.caption(f"Đang kết nối Lakehouse dữ liệu giá thực tế của mã cổ phiếu: **{ticker}**")
    
    if st.button("⬅️ Quay lại Dashboard", type="secondary"):
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
        
        # 🤖 BƯỚC RAG: Truy vấn nhanh dữ liệu giá gần nhất từ MotherDuck để làm ngữ cảnh (Context)
        token = os.getenv("motherduck_token")
        context_str = "Không tìm thấy dữ liệu giá."
        
        if token:
            try:
                con = duckdb.connect(f"md:vn_stock_analytics?motherduck_token={token}")
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