import os
import re
import duckdb
import joblib
import pandas as pd
import numpy as np
from sklearn.preprocessing import normalize

# 1. Khởi tạo cấu hình và đường dẫn
SAVE_DIR = "./scripts/sentiment"
PIPELINE_PATH = f"{SAVE_DIR}/pipeline.pkl"

def get_secret_key(key_name):
    return os.environ.get(key_name) or os.getenv(key_name.lower())

# 2. text đồng bộ với lsa_pipeline_v5.py
def extract_title_content(title: str) -> str:
    title = str(title)
    m = re.match(r'^[A-Z]{2,5}:\s*(.*)', title)
    return m.group(1).lower() if m else title.lower()

def clean_summary(s) -> str:
    if pd.isna(s) or str(s).strip() in ('', 'nan', 'None'):
        return ''
    return str(s).lower()

def normalize_numbers(text: str) -> str:
    text = re.sub(r'\d+[\.,]?\d*\s*%', 'PCT', text)
    text = re.sub(r'\d+[\.,]?\d*\s*(tỷ|triệu|nghìn)', 'MONEY', text)
    text = re.sub(r'\d+', 'NUM', text)
    return text

def hand_features(row, feat_cols) -> dict:
    raw = str(row.get('full_raw', ''))
    norm = str(row.get('full_norm', ''))
    title_raw = str(row.get('title', ''))
    
    pos_kw = ['tăng trưởng', 'lợi nhuận tăng', 'doanh thu tăng', 'cổ tức', 'kỷ lục', 'thành công', 'bứt phá', 'tích cực', 'phục hồi']
    neg_kw = ['thua lỗ', 'lỗ ròng', 'bán giải chấp', 'xử phạt', 'vi phạm', 'cảnh báo', 'lao dốc', 'bán ròng', 'sụt giảm']
    neu_kw = ['nghị quyết', 'điều lệ', 'đăng ký cuối cùng', 'thay đổi nhân sự', 'thông báo', 'bctc', 'giải trình']
    
    pos_c = sum(1 for k in pos_kw if k in raw)
    neg_c = sum(1 for k in neg_kw if k in raw)
    neu_c = sum(1 for k in neu_kw if k in raw)
    tot = pos_c + neg_c + neu_c + 1e-9
    
    strong_pos = sum(1 for p in [r'tăng\s+PCT', r'lợi nhuận.{0,20}tăng'] if re.search(p, norm))
    strong_neg = sum(1 for p in [r'lỗ\s+MONEY', r'giảm\s+PCT'] if re.search(p, norm))
    
    return {
        'pos_c': pos_c, 'neg_c': neg_c, 'neu_c': neu_c,
        'pos_r': pos_c / tot, 'neg_r': neg_c / tot, 'neu_r': neu_c / tot,
        'net_sentiment': (pos_c - neg_c) / tot,
        'sentiment_confidence': (pos_c + neg_c) / tot,
        'strong_pos': strong_pos, 'strong_neg': strong_neg, 'strong_net': strong_pos - strong_neg,
        'is_ticker_title': int(bool(re.match(r'^[A-Z]{2,5}:\s', title_raw))),
        'has_summary': int(bool(str(row.get('summary_clean', '')).strip())),
        'has_pct': int('%' in title_raw or 'PCT' in norm),
        'has_money': int(bool(re.search(r'tỷ|triệu|MONEY', norm))),
        'title_content_len': len(str(row.get('title_content', '')).split()),
        'summary_len': len(str(row.get('summary_clean', '')).split()),
        'volatility_high': int(str(row.get('volatility_level', '')).lower() == 'high'),
    }

# 3. quét dữ liệu Delta và chấm điểm bằng AI
def execute_automation_inference():
    md_token = get_secret_key('MOTHERDUCK_TOKEN')
    if not md_token:
        raise ValueError("Không tìm thấy MOTHERDUCK_TOKEN trong biến môi trường!")
        
    if not os.path.exists(PIPELINE_PATH):
        print(f"Chưa tìm thấy file mô hình đóng gói [{PIPELINE_PATH}]. Vui lòng chạy file lsa_pipeline_v5.py để huấn luyện và lưu mô hình trước!")
        return

    print("Đang tải mô hình LSA Sentiment Pipeline...")
    pipeline = joblib.load(PIPELINE_PATH)
    
    print("Kết nối tới kho đám mây MotherDuck...")
    conn = duckdb.connect(f"md:vn_stock_analytics?token={md_token.strip()}")
    conn.execute("USE vn_stock_analytics.main;")
    
    # lưu trữ trên Cloud nếu chưa tồn tại
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bronze_news_sentiment (
            article_id LONG PRIMARY KEY,
            sentiment_label VARCHAR,
            sentiment_score VARCHAR,
            calculated_at TIMESTAMP
        );
    """)
    
    # chỉ bốc các bài báo xuất hiện ở fact_news mà chưa được chấm điểm
    print("Quét tìm các tin tức mới chưa được chấm điểm...")
    df_new_articles = conn.execute("""
        SELECT article_id, ticker, title, summary
        FROM fact_news
        WHERE article_id NOT IN (SELECT article_id FROM bronze_news_sentiment);
    """).fetchdf()
    
    if df_new_articles.empty:
        print("Giám sát hoàn tất: Tất cả tin tức trong kho dữ liệu hiện tại đều đã được chấm điể!")
        conn.close()
        return
        
    print(f"Phát hiện {len(df_new_articles)} bài báo mới cần xử lý. Tiến hành dự báo trên fly...")
    
    results = []
    run_time = pd.Timestamp.now()
    w = pipeline['weights']
    feat_cols = pipeline['feat_cols']
    le = pipeline['label_encoder']
    
    for _, row in df_new_articles.iterrows():
        title = str(row['title'])
        summary = str(row['summary'])
        
        tc = extract_title_content(title)
        tc_norm = normalize_numbers(tc)
        sum_c = clean_summary(summary)
        sum_norm = normalize_numbers(sum_c)
        
        proc_row = {
            'title': title, 'title_content': tc, 'title_clean': tc_norm,
            'summary_clean': sum_c, 'summary_norm': sum_norm,
            'full_raw': tc + ' ' + sum_c, 'full_norm': tc_norm + ' ' + sum_norm,
            'volatility_level': 'Low' # Default fallback an toàn
        }
        
        # Biến đổi vector thông qua TF-IDF và TruncatedSVD đã fit lúc train
        X_t = normalize(pipeline['lsa_title'].transform(pipeline['tfidf_title'].transform([tc_norm])))
        X_s = normalize(pipeline['lsa_summary'].transform(pipeline['tfidf_summary'].transform([sum_norm])))
        hf = hand_features(proc_row, feat_cols)
        X_h = pipeline['scaler'].transform(pd.DataFrame([hf])[feat_cols].values)
        
        X_in = np.hstack([X_t * w['title'], X_s * w['summary'], X_h * w['hand']])
        
        pred = pipeline['clf'].predict(X_in)[0]
        proba = pipeline['clf'].predict_proba(X_in)[0]
        
        pred_label = le.classes_[pred]
        scores_dict = {c: float(p) for c, p in zip(le.classes_, proba)}
        
        # Khớp 100% cấu hình biểu đồ tròn của Dashboard app.py
        score_string = f"positive={scores_dict.get('positive', 0.0)*100:.2f}%; neutral={scores_dict.get('neutral', 0.0)*100:.2f}%; negative={scores_dict.get('negative', 0.0)*100:.2f}%"
        
        results.append({
            "article_id": int(row['article_id']),
            "sentiment_label": str(pred_label),
            "sentiment_score": score_string,
            "calculated_at": run_time
        })
        
    df_inference_out = pd.DataFrame(results)
    conn.register("df_inference_view", df_inference_out)
    
    # Lưu lũy kế nối đuôi kết quả phân tích vào Cloud
    conn.execute("INSERT INTO bronze_news_sentiment SELECT * FROM df_inference_view;")
    conn.close()
    print(f"THÀNH CÔNG! Đã cập nhật và đồng bộ nhãn sắc thái AI của {len(df_inference_out)} tin tức lên MotherDuck.")

if __name__ == '__main__':
    execute_automation_inference()