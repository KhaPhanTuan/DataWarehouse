import pandas as pd
import numpy as np
import re
import random
from copy import deepcopy
from collections import Counter

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import LabelEncoder, StandardScaler, normalize
from sklearn.svm import SVC
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import classification_report, accuracy_score, f1_score
from imblearn.over_sampling import SMOTE
import joblib, os, warnings
warnings.filterwarnings('ignore')


DATA_PATH  = "e:/DATAWAREHOUSE/DataWarehouse/models/sentiment/self_labels.csv"
SAVE_DIR   = "e:/DATAWAREHOUSE/DataWarehouse/models/sentiment"
TOKEN      = r'[a-zàáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]+'
N_REPEATS  = 10    # số lần lặp CV — tăng lên 20 nếu cần estimate chính xác hơn
N_FOLDS    = 5
AUG_RATIO  = {    # số biến thể tạo thêm cho mỗi mẫu theo class
    'positive': 4,
    'negative': 2,
    'neutral':  0,   # không augment majority
}
RANDOM_SEED = 42


# 1. LOAD & VALIDATE
df = pd.read_csv(DATA_PATH)
df['groq_label'] = df['groq_label'].str.strip().str.lower()
df = df[df['groq_label'].isin(['positive', 'negative', 'neutral'])].copy().reset_index(drop=True)

print("=== Data distribution (original) ===")
counts = df['groq_label'].value_counts()
print(counts)
print(f"Total: {len(df)}\n")

majority_baseline = counts.max() / len(df)
print(f"Majority-class baseline: {majority_baseline:.3f}  ('{counts.idxmax()}')")

if counts.min() < 50:
    print(f"⚠️  Smallest class = {counts.min()} samples — augmentation will help but collect real data too\n")

label_encoder = LabelEncoder()
y_orig = label_encoder.fit_transform(df['groq_label'])


# 2. TEXT PREPROCESSING
def extract_title_content(title: str) -> str:
    title = str(title)
    m = re.match(r'^[A-Z]{2,5}:\s*(.*)', title)
    return m.group(1).lower() if m else title.lower()

def clean_summary(s) -> str:
    if pd.isna(s) or str(s).strip() in ('', 'nan', 'None'):
        return ''
    return str(s).lower()

def normalize_numbers(text: str) -> str:
    text = re.sub(r'\d+[\.,]?\d*\s*%',                'PCT',   text)
    text = re.sub(r'\d+[\.,]?\d*\s*(tỷ|triệu|nghìn)', 'MONEY', text)
    text = re.sub(r'\d+',                              'NUM',   text)
    return text

def preprocess_row(row):
    tc       = extract_title_content(str(row.get('title', '')))
    sum_c    = clean_summary(row.get('summary', ''))
    return {
        'title_raw_lower': str(row.get('title', '')).lower(),
        'title_content':   tc,
        'title_clean':     normalize_numbers(tc),
        'summary_clean':   sum_c,
        'summary_norm':    normalize_numbers(sum_c),
        'full_raw':        tc + ' ' + sum_c,
        'full_norm':       normalize_numbers(tc) + ' ' + normalize_numbers(sum_c),
        'volatility_level': str(row.get('volatility_level', 'low')),
        'title':           str(row.get('title', '')),
    }

proc = [preprocess_row(r) for _, r in df.iterrows()]
for col in ['title_raw_lower','title_content','title_clean',
            'summary_clean','summary_norm','full_raw','full_norm']:
    df[col] = [p[col] for p in proc]


# 3. TEXT AUGMENTATION

# Synonym map — domain-specific Vietnamese finance
SYNONYMS = {
    # positive
    'tăng':        ['tăng trưởng', 'tăng lên', 'đi lên'],
    'lãi':         ['lợi nhuận', 'có lãi'],
    'cổ tức':      ['chia cổ tức', 'trả cổ tức'],
    'kỷ lục':      ['mức cao nhất', 'cao kỷ lục'],
    'vượt':        ['vượt qua', 'vượt mức'],
    'phục hồi':    ['hồi phục', 'cải thiện'],
    'tích cực':    ['khả quan', 'tốt'],
    'bứt phá':     ['tăng mạnh', 'vọt lên'],
    # negative
    'giảm':        ['sụt giảm', 'đi xuống', 'giảm sút'],
    'lỗ':          ['thua lỗ', 'lỗ ròng'],
    'phạt':        ['xử phạt', 'bị phạt'],
    'cảnh báo':    ['bị cảnh báo', 'nhận cảnh báo'],
    'vi phạm':     ['bị vi phạm', 'có vi phạm'],
    'giải chấp':   ['bán giải chấp', 'bị giải chấp'],
    # neutral
    'nghị quyết':  ['quyết nghị', 'ban hành nghị quyết'],
    'điều lệ':     ['quy chế', 'nội quy'],
    'thông báo':   ['công bố', 'thông tin'],
    'sửa đổi':     ['cập nhật', 'điều chỉnh'],
    'nhân sự':     ['cán bộ', 'lãnh đạo'],
}

def synonym_swap(text: str, rng: random.Random, p: float = 0.3) -> str:
    words = text.split()
    result = []
    for w in words:
        if rng.random() < p and w in SYNONYMS:
            result.append(rng.choice(SYNONYMS[w]))
        else:
            result.append(w)
    return ' '.join(result)

def random_deletion(text: str, rng: random.Random, p: float = 0.15) -> str:
    words = text.split()
    if len(words) <= 3:
        return text
    kept = [w for w in words if rng.random() > p]
    return ' '.join(kept) if len(kept) >= 3 else ' '.join(words[:3])

def number_perturb(text: str, rng: random.Random) -> str:
    def perturb(m):
        val = float(m.group().replace(',', '.'))
        delta = rng.uniform(0.85, 1.15)
        new_val = val * delta
        return f"{new_val:.1f}".rstrip('0').rstrip('.')
    return re.sub(r'\d+[\.,]?\d*', perturb, text)

def title_prefix_vary(title: str, rng: random.Random) -> str:
    m = re.match(r'^([A-Z]{2,5}):\s*(.*)', title)
    if not m:
        return title
    ticker, content = m.group(1), m.group(2)
    templates = [
        f"{ticker}: {content}",
        f"[{ticker}] {content}",
        f"{content} ({ticker})",
        content,           # bỏ ticker
    ]
    return rng.choice(templates)

def augment_text(title: str, summary: str, label: str,
                 rng: random.Random) -> tuple[str, str]:
    if label == 'positive':
        # Positive: synonym swap mạnh + number perturb
        new_title = synonym_swap(title, rng, p=0.35)
        new_title = number_perturb(new_title, rng)
        new_title = title_prefix_vary(new_title, rng)
        new_sum   = synonym_swap(summary, rng, p=0.25) if summary else ''

    elif label == 'negative':
        # Negative: synonym swap + random deletion nhẹ
        new_title = synonym_swap(title, rng, p=0.30)
        new_title = random_deletion(new_title, rng, p=0.10)
        new_title = title_prefix_vary(new_title, rng)
        new_sum   = random_deletion(synonym_swap(summary, rng, p=0.20), rng, p=0.10) if summary else ''

    else:
        # Neutral: chỉ deletion nhẹ
        new_title = random_deletion(title, rng, p=0.10)
        new_sum   = random_deletion(summary, rng, p=0.10) if summary else ''

    return new_title.strip(), new_sum.strip()


def augment_dataframe(df_train: pd.DataFrame,
                      y_train: np.ndarray,
                      aug_ratio: dict,
                      seed: int) -> tuple[pd.DataFrame, np.ndarray]:
    rng = random.Random(seed)
    new_rows, new_labels = [], []

    label_names = label_encoder.classes_

    for idx, (_, row) in enumerate(df_train.iterrows()):
        lbl = label_names[y_train[idx]]
        n_aug = aug_ratio.get(lbl, 0)
        title_orig   = row['title_content']    # chưa normalize số
        summary_orig = row['summary_clean']

        for _ in range(n_aug):
            new_title, new_sum = augment_text(title_orig, summary_orig, lbl, rng)
            new_row = {
                'title':           new_title,
                'title_content':   new_title,
                'title_clean':     normalize_numbers(new_title),
                'title_raw_lower': new_title.lower(),
                'summary_clean':   new_sum,
                'summary_norm':    normalize_numbers(new_sum),
                'full_raw':        new_title.lower() + ' ' + new_sum,
                'full_norm':       normalize_numbers(new_title) + ' ' + normalize_numbers(new_sum),
                'volatility_level': row.get('volatility_level', 'low'),
            }
            new_rows.append(new_row)
            new_labels.append(y_train[idx])

    if not new_rows:
        return df_train, y_train

    df_aug = pd.concat([df_train, pd.DataFrame(new_rows)], ignore_index=True)
    y_aug  = np.concatenate([y_train, np.array(new_labels)])
    return df_aug, y_aug


# 4. HAND-CRAFTED FEATURES
POS_KW = [
    'tăng trưởng', 'lợi nhuận tăng', 'doanh thu tăng', 'cổ tức', 'kỷ lục',
    'thành công', 'bứt phá', 'tích cực', 'phục hồi', 'tăng mạnh', 'hoàn tất',
    'ký kết', 'tăng vọt', 'chia cổ tức', 'lãi ròng tăng', 'vượt kế hoạch',
    'tăng', 'lãi', 'vượt', 'khả quan',
]
NEG_KW = [
    'thua lỗ', 'lỗ ròng', 'bán giải chấp', 'xử phạt', 'vi phạm', 'cảnh báo',
    'kiểm soát', 'lao dốc', 'bán ròng', 'sụt giảm', 'giảm sâu', 'tăng lỗ',
    'lỗ nặng', 'giảm mạnh', 'đình chỉ', 'hủy niêm yết',
    'lỗ', 'giảm', 'phạt', 'rủi ro',
]
NEU_KW = [
    'nghị quyết', 'điều lệ', 'đăng ký cuối cùng', 'thay đổi nhân sự',
    'đại hội đồng', 'niêm yết', 'cbtt', 'sửa đổi', 'báo cáo tài chính',
    'tài liệu họp', 'thông báo', 'bctc', 'giải trình',
]
POS_PATTERNS = [
    r'tăng\s+PCT', r'lợi nhuận.{0,20}tăng', r'chia cổ tức',
    r'kỷ lục', r'MONEY.{0,10}cổ tức', r'PCT\s*(so|tăng)', r'vượt\s+kế hoạch',
]
NEG_PATTERNS = [
    r'lỗ\s+MONEY', r'giảm\s+PCT', r'xử phạt', r'bán giải chấp',
    r'cảnh báo', r'kiểm soát', r'thua lỗ', r'lỗ nặng',
]

def hand_features(row) -> dict:
    raw       = str(row.get('full_raw', ''))
    norm      = str(row.get('full_norm', ''))
    title_raw = str(row.get('title', row.get('title_content', '')))

    pos_c = sum(1 for k in POS_KW if k in raw)
    neg_c = sum(1 for k in NEG_KW if k in raw)
    neu_c = sum(1 for k in NEU_KW if k in raw)
    tot   = pos_c + neg_c + neu_c + 1e-9

    strong_pos = sum(1 for p in POS_PATTERNS if re.search(p, norm))
    strong_neg = sum(1 for p in NEG_PATTERNS if re.search(p, norm))

    summary = str(row.get('summary_clean', ''))
    tc      = str(row.get('title_content', ''))

    return {
        'pos_c': pos_c, 'neg_c': neg_c, 'neu_c': neu_c,
        'pos_r': pos_c / tot,
        'neg_r': neg_c / tot,
        'neu_r': neu_c / tot,
        'net_sentiment':        (pos_c - neg_c) / tot,
        'sentiment_confidence': (pos_c + neg_c) / tot,
        'strong_pos':  strong_pos,
        'strong_neg':  strong_neg,
        'strong_net':  strong_pos - strong_neg,
        'is_ticker_title':  int(bool(re.match(r'^[A-Z]{2,5}:\s', title_raw))),
        'has_summary':       int(bool(summary.strip())),
        'has_pct':           int('%' in title_raw or 'PCT' in norm),
        'has_money':         int(bool(re.search(r'tỷ|triệu|MONEY', norm))),
        'title_content_len': len(tc.split()),
        'summary_len':       len(summary.split()) if summary.strip() else 0,
        'volatility_high':   int(str(row.get('volatility_level', '')).lower() == 'high'),
    }

feat_df = pd.DataFrame([hand_features(r) for _, r in df.iterrows()])
FEAT_COLS = feat_df.columns.tolist()
print(f"Hand features: {feat_df.shape}")

print("\n=== Feature means by label ===")
feat_df['label'] = df['groq_label'].values
print(feat_df.groupby('label')[
    ['pos_c','neg_c','neu_c','strong_pos','strong_neg','net_sentiment']
].mean().round(3))
feat_df.drop('label', axis=1, inplace=True)
X_hand_raw_orig = feat_df.values

# 5. GLOBAL TF-IDF (for topic inspection only)
N = len(df)
N_TITLE_COMP = min(int(np.sqrt(N) * 2), 60)
N_SUM_COMP   = min(int(np.sqrt(N) * 1.5), 40)
print(f"\nAuto LSA → title={N_TITLE_COMP}, summary={N_SUM_COMP}")

_tfidf_t = TfidfVectorizer(ngram_range=(1,2), min_df=1, max_df=0.90,
                            max_features=2000, sublinear_tf=True, token_pattern=TOKEN)
_tfidf_s = TfidfVectorizer(ngram_range=(1,3), min_df=2, max_df=0.85,
                            max_features=1500, sublinear_tf=True, token_pattern=TOKEN)
_lsa_t = TruncatedSVD(n_components=N_TITLE_COMP, random_state=42, n_iter=10)
_lsa_s = TruncatedSVD(n_components=N_SUM_COMP,   random_state=42, n_iter=10)
_lsa_t.fit_transform(_tfidf_t.fit_transform(df['title_clean']))
_lsa_s.fit_transform(_tfidf_s.fit_transform(df['summary_norm']))
print(f"Title  var={_lsa_t.explained_variance_ratio_.sum():.3f}")
print(f"Summary var={_lsa_s.explained_variance_ratio_.sum():.3f}")

# 6. REPEATED STRATIFIED CV WITH AUGMENTATION (leak-free)
WEIGHT_GRID = [
    (1.0, 0.5, 2.0),
    (1.0, 1.0, 2.0),
    (2.0, 1.0, 2.0),
    (2.0, 1.5, 2.0),
    (3.0, 1.0, 2.0),
    (1.0, 0.0, 3.0),
    (2.0, 0.0, 3.0),
    (1.5, 1.0, 3.0),
]

CLF_CONFIGS = {
    'SVM_C0.3':    dict(kernel='linear', C=0.3,  class_weight='balanced',
                        probability=True, random_state=42),
    'SVM_C1.0':    dict(kernel='linear', C=1.0,  class_weight='balanced',
                        probability=True, random_state=42),
    'LogReg_C0.3': dict(C=0.3,  class_weight='balanced', max_iter=2000,
                        random_state=42, solver='lbfgs', multi_class='auto'),
    'LogReg_C1.0': dict(C=1.0,  class_weight='balanced', max_iter=2000,
                        random_state=42, solver='lbfgs', multi_class='auto'),
}

def make_clf(name, params):
    if name.startswith('SVM'):
        return SVC(**params)
    return LogisticRegression(**params)

def build_X(X_t, X_s, X_h, wt, ws, wh):
    return np.hstack([X_t * wt, X_s * ws, X_h * wh])

def fit_fold_transforms(df_tr, df_val, X_hand_tr, X_hand_val):
    """Fit tất cả transforms trên train, transform cả hai."""
    tfidf_t = TfidfVectorizer(ngram_range=(1,2), min_df=1, max_df=0.90,
                               max_features=2000, sublinear_tf=True, token_pattern=TOKEN)
    tfidf_s = TfidfVectorizer(ngram_range=(1,3), min_df=2, max_df=0.85,
                               max_features=1500, sublinear_tf=True, token_pattern=TOKEN)
    lsa_t = TruncatedSVD(n_components=N_TITLE_COMP, random_state=42, n_iter=10)
    lsa_s = TruncatedSVD(n_components=N_SUM_COMP,   random_state=42, n_iter=10)
    sc    = StandardScaler()

    X_t_tr = normalize(lsa_t.fit_transform(tfidf_t.fit_transform(df_tr['title_clean'])))
    X_s_tr = normalize(lsa_s.fit_transform(tfidf_s.fit_transform(df_tr['summary_norm'])))
    X_h_tr = sc.fit_transform(X_hand_tr)

    X_t_val = normalize(lsa_t.transform(tfidf_t.transform(df_val['title_clean'])))
    X_s_val = normalize(lsa_s.transform(tfidf_s.transform(df_val['summary_norm'])))
    X_h_val = sc.transform(X_hand_val)

    return (X_t_tr, X_s_tr, X_h_tr), (X_t_val, X_s_val, X_h_val)

print(f"\n=== Repeated CV ({N_REPEATS} repeats × {N_FOLDS} folds) with augmentation ===")
print(f"Aug ratio: positive×{AUG_RATIO['positive']}, negative×{AUG_RATIO['negative']}, neutral×{AUG_RATIO['neutral']}")
print("Running...\n")

all_results = []
best_f1     = 0
best_config = None

total_configs = len(WEIGHT_GRID) * len(CLF_CONFIGS)
config_idx = 0

for wt, ws, wh in WEIGHT_GRID:
    for clf_name, clf_params in CLF_CONFIGS.items():
        config_idx += 1
        all_fold_f1s = []

        for repeat in range(N_REPEATS):
            seed = RANDOM_SEED + repeat * 100
            skf  = StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed)

            for tr_idx, val_idx in skf.split(np.zeros(len(y_orig)), y_orig):
                df_tr_orig = df.iloc[tr_idx].copy()
                df_val     = df.iloc[val_idx].copy()
                y_tr_orig  = y_orig[tr_idx]
                y_val      = y_orig[val_idx]

                X_hand_tr_orig = X_hand_raw_orig[tr_idx]
                X_hand_val     = X_hand_raw_orig[val_idx]

                aug_seed = seed + hash((wt, ws, wh, clf_name)) % 10000
                df_tr_aug, y_tr_aug = augment_dataframe(
                    df_tr_orig, y_tr_orig, AUG_RATIO, seed=aug_seed
                )

                n_orig = len(df_tr_orig)
                if len(df_tr_aug) > n_orig:
                    aug_rows_feats = pd.DataFrame([
                        hand_features(r) for _, r in df_tr_aug.iloc[n_orig:].iterrows()
                    ])[FEAT_COLS].values
                    X_hand_tr_aug = np.vstack([X_hand_tr_orig, aug_rows_feats])
                else:
                    X_hand_tr_aug = X_hand_tr_orig

                (X_t_tr, X_s_tr, X_h_tr), (X_t_val, X_s_val, X_h_val) = \
                    fit_fold_transforms(df_tr_aug, df_val, X_hand_tr_aug, X_hand_val)

                X_tr  = build_X(X_t_tr, X_s_tr, X_h_tr, wt, ws, wh)
                X_val = build_X(X_t_val, X_s_val, X_h_val, wt, ws, wh)

                # SMOTE 
                k = max(1, min(5, Counter(y_tr_aug).most_common()[-1][1] - 1))
                try:
                    X_sm, y_sm = SMOTE(random_state=seed, k_neighbors=k).fit_resample(X_tr, y_tr_aug)
                except Exception:
                    X_sm, y_sm = X_tr, y_tr_aug

                # ── 5. Fit & eval ──
                clf = make_clf(clf_name, clf_params)
                clf.fit(X_sm, y_sm)
                y_pred = clf.predict(X_val)
                all_fold_f1s.append(
                    f1_score(y_val, y_pred, average='macro', zero_division=0)
                )

        mean_f1 = float(np.mean(all_fold_f1s))
        std_f1  = float(np.std(all_fold_f1s))
        result = {
            'w_title': wt, 'w_sum': ws, 'w_hand': wh,
            'clf':    clf_name,
            'f1':     round(mean_f1,  4),
            'f1_std': round(std_f1,   4),
            'f1_ci':  f"±{round(1.96*std_f1/np.sqrt(N_REPEATS*N_FOLDS),4)}",
        }
        all_results.append(result)

        if mean_f1 > best_f1:
            best_f1     = mean_f1
            best_config = result

        if config_idx % 4 == 0:
            print(f"  [{config_idx}/{total_configs}] wt={wt} ws={ws} wh={wh} {clf_name:12s} "
                  f"f1={mean_f1:.4f} ±{std_f1:.4f}")

results_df = pd.DataFrame(all_results).sort_values('f1', ascending=False)
print("\n=== Top 10 configs ===")
print(results_df.head(10).to_string(index=False))
print(f"\n→ Best: {best_config}")
print(f"  Majority baseline: {majority_baseline:.3f}")

# 7. FINAL MODEL — train trên TOÀN BỘ data + augmentation
W_T = best_config['w_title']
W_S = best_config['w_sum']
W_H = best_config['w_hand']

print(f"\n=== Training final model (w_title={W_T}, w_sum={W_S}, w_hand={W_H}) ===")

# Augment full dataset
rng_final = random.Random(RANDOM_SEED)
new_rows_f, new_labels_f = [], []
for idx, (_, row) in enumerate(df.iterrows()):
    lbl   = label_encoder.classes_[y_orig[idx]]
    n_aug = AUG_RATIO.get(lbl, 0)
    for _ in range(n_aug):
        new_t, new_s = augment_text(
            row['title_content'], row['summary_clean'], lbl, rng_final)
        new_rows_f.append({
            'title':           new_t,
            'title_content':   new_t,
            'title_clean':     normalize_numbers(new_t),
            'title_raw_lower': new_t.lower(),
            'summary_clean':   new_s,
            'summary_norm':    normalize_numbers(new_s),
            'full_raw':        new_t.lower() + ' ' + new_s,
            'full_norm':       normalize_numbers(new_t) + ' ' + normalize_numbers(new_s),
            'volatility_level': row.get('volatility_level', 'low'),
        })
        new_labels_f.append(y_orig[idx])

df_final = pd.concat([df, pd.DataFrame(new_rows_f)], ignore_index=True)
y_final  = np.concatenate([y_orig, np.array(new_labels_f)])

X_hand_aug = np.vstack([
    X_hand_raw_orig,
    pd.DataFrame([hand_features(r) for _, r in pd.DataFrame(new_rows_f).iterrows()]
    )[FEAT_COLS].values if new_rows_f else np.empty((0, len(FEAT_COLS)))
])

tfidf_title_f = TfidfVectorizer(ngram_range=(1,2), min_df=1, max_df=0.90,
                                 max_features=2000, sublinear_tf=True, token_pattern=TOKEN)
tfidf_sum_f   = TfidfVectorizer(ngram_range=(1,3), min_df=2, max_df=0.85,
                                 max_features=1500, sublinear_tf=True, token_pattern=TOKEN)
lsa_title_f   = TruncatedSVD(n_components=N_TITLE_COMP, random_state=42, n_iter=10)
lsa_sum_f     = TruncatedSVD(n_components=N_SUM_COMP,   random_state=42, n_iter=10)
scaler_f      = StandardScaler()

X_t_f = normalize(lsa_title_f.fit_transform(tfidf_title_f.fit_transform(df_final['title_clean'])))
X_s_f = normalize(lsa_sum_f.fit_transform(tfidf_sum_f.fit_transform(df_final['summary_norm'])))
X_h_f = scaler_f.fit_transform(X_hand_aug)
X_all  = build_X(X_t_f, X_s_f, X_h_f, W_T, W_S, W_H)

k = max(1, min(5, Counter(y_final).most_common()[-1][1] - 1))
X_sm_f, y_sm_f = SMOTE(random_state=RANDOM_SEED, k_neighbors=k).fit_resample(X_all, y_final)

final_clf = make_clf(best_config['clf'], CLF_CONFIGS[best_config['clf']])
final_clf.fit(X_sm_f, y_sm_f)

aug_counts = Counter(label_encoder.classes_[l] for l in y_final)
print(f"Training set after augmentation: {dict(aug_counts)}")
print(f"Total training samples: {len(y_final)}")

print("\n=== Train-set report (reference only) ===")
y_pred_orig = final_clf.predict(build_X(
    normalize(lsa_title_f.transform(tfidf_title_f.transform(df['title_clean']))),
    normalize(lsa_sum_f.transform(tfidf_sum_f.transform(df['summary_norm']))),
    scaler_f.transform(X_hand_raw_orig),
    W_T, W_S, W_H
))
print(classification_report(y_orig, y_pred_orig,
      target_names=label_encoder.classes_, digits=3, zero_division=0))


# 8. SAVE
os.makedirs(SAVE_DIR, exist_ok=True)
joblib.dump({
    'tfidf_title':       tfidf_title_f,
    'tfidf_summary':     tfidf_sum_f,
    'lsa_title':         lsa_title_f,
    'lsa_summary':       lsa_sum_f,
    'scaler':            scaler_f,
    'clf':               final_clf,
    'label_encoder':     label_encoder,
    'weights':           {'title': W_T, 'summary': W_S, 'hand': W_H},
    'feat_cols':         FEAT_COLS,
    'cv_f1':             best_config['f1'],
    'cv_f1_std':         best_config['f1_std'],
    'cv_f1_ci':          best_config['f1_ci'],
    'majority_baseline': majority_baseline,
    'aug_ratio':         AUG_RATIO,
    'n_repeats':         N_REPEATS,
}, f"{SAVE_DIR}/pipeline.pkl")
print(f"\nSaved → {SAVE_DIR}/pipeline.pkl")


# 9. INFERENCE
def load_pipeline(save_dir=SAVE_DIR):
    return joblib.load(f"{save_dir}/pipeline.pkl")

def predict(title: str,
            summary: str = '',
            volatility: str = 'Low',
            pipeline: dict = None) -> dict:
    if pipeline is None:
        pipeline = load_pipeline()

    tc       = extract_title_content(title)
    tc_norm  = normalize_numbers(tc)
    sum_c    = clean_summary(summary)
    sum_norm = normalize_numbers(sum_c)

    row = {
        'title':           title,
        'title_content':   tc,
        'title_clean':     tc_norm,
        'title_raw_lower': title.lower(),
        'summary_clean':   sum_c,
        'summary_norm':    sum_norm,
        'full_raw':        tc + ' ' + sum_c,
        'full_norm':       tc_norm + ' ' + sum_norm,
        'volatility_level': volatility,
    }

    w = pipeline['weights']
    X_t = normalize(pipeline['lsa_title'].transform(
                    pipeline['tfidf_title'].transform([tc_norm])))
    X_s = normalize(pipeline['lsa_summary'].transform(
                    pipeline['tfidf_summary'].transform([sum_norm])))
    hf  = hand_features(row)
    X_h = pipeline['scaler'].transform(
              pd.DataFrame([hf])[pipeline['feat_cols']].values)

    X_in  = np.hstack([X_t * w['title'], X_s * w['summary'], X_h * w['hand']])
    pred  = pipeline['clf'].predict(X_in)[0]
    proba = pipeline['clf'].predict_proba(X_in)[0]
    le    = pipeline['label_encoder']

    return {
        'label':      le.classes_[pred],
        'confidence': round(float(proba.max()), 4),
        'scores':     {c: round(float(p), 4)
                       for c, p in zip(le.classes_, proba)},
    }


if __name__ == '__main__':
    p = load_pipeline()
    tests = [
        ("Nhựa Bình Minh chia cổ tức tiền mặt kỷ lục 148.6%", ""),
        ("DIG: Gia đình Chủ tịch bị bán giải chấp khi cổ phiếu giảm giá", ""),
        ("VCB: Điều lệ công ty sửa đổi 2026", ""),
        ("Lợi nhuận ròng quý 1 của Vĩnh Hoàn tăng 38%",
         "BCTC quý đầu năm cho thấy kết quả kinh doanh khởi đầu tích cực"),
        ("HPG: Doanh thu giảm 12% do giá thép lao dốc", ""),
        ("MSN: ĐHĐCĐ thường niên 2026 thông qua kế hoạch tăng vốn", ""),
    ]
    print("\n=== Inference tests ===")
    for title, summary in tests:
        r = predict(title, summary, pipeline=p)
        scores = ' | '.join(f"{k}={v:.2f}" for k, v in r['scores'].items())
        print(f"  [{r['label']:8s} {r['confidence']:.2f}]  {title[:60]}")
        print(f"   scores: {scores}")