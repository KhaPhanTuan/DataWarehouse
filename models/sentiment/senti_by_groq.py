import duckdb
import pandas as pd
import requests
import time
# 1. Kết nối MotherDuck và lấy dữ liệu
con = duckdb.connect("md:vn_stock_analytics", config={"motherduck_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJlbWFpbCI6InBoYW50dWFua2hhMTQ3QGdtYWlsLmNvbSIsIm1kUmVnaW9uIjoiYXdzLWV1LWNlbnRyYWwtMSIsInNlc3Npb24iOiJwaGFudHVhbmtoYTE0Ny5nbWFpbC5jb20iLCJwYXQiOiJRQlpFU2ZCQThJSnVfUGtWdDgxUTQtZDhyRnRoRV8tbE4yZjdwQmhFVXdvIiwidXNlcklkIjoiODFhODJlZjAtZTA5OC00M2M2LTkxYWUtMzMyMTk4YzMzNDEwIiwiaXNzIjoibWRfcGF0IiwicmVhZE9ubHkiOmZhbHNlLCJ0b2tlblR5cGUiOiJyZWFkX3dyaXRlIiwiaWF0IjoxNzgwODk3MTU0fQ.fw3Je9PFz3ocmqXIlEjirjovTN9MB7LfZLfBZmgliB8"})
df = con.execute("SELECT * FROM analytics_wide_ai_ready LIMIT 200").fetchdf()

# 2. Gọi Groq API
GROQ_API_KEY = "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"
url = "https://api.groq.com/openai/v1/chat/completions"


def groq_label(text, return_pct, volatility_level):
    prompt = f"""
    Phân loại cảm xúc của tin tức sau đây thành đúng một từ duy nhất:
    Positive
    Negative
    Neutral

    Văn bản: {text}
    Return: {return_pct}
    Volatility: {volatility_level}

    Chỉ trả về một từ duy nhất trong ba lựa chọn trên.
    """
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0
    }
    response = requests.post(url, headers=headers, json=payload)
    result = response.json()
    time.sleep(2)  # nghỉ 2 giây để tránh vượt limit

    if "choices" not in result:
        print("Groq API error:", result)
        return "Neutral"
    return result["choices"][0]["message"]["content"].strip()
# 3. Áp dụng gán nhãn
df['groq_label'] = df.apply(
    lambda row: groq_label(
        str(row['title']) + " " + str(row['summary']),
        row['next_day_return_percentage'],
        row['volatility_level']
    ),
    axis=1
)

# 4. Lưu ra CSV
df.to_csv("e:/DATAWAREHOUSE/DataWarehouse/models/sentiment/self_labels.csv", index=False, encoding="utf-8-sig")
print("Đã gán nhãn và lưu vào self_labels.csv")