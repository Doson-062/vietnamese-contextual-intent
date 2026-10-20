"""Cấu hình A: TF-IDF + Logistic Regression, chỉ câu hiện tại (không ngữ cảnh).

Học trên train, chọn tham số (C, class_weight) theo macro-F1 trên dev,
chấm test đúng một lần. Ghi:
  models/baseline_a/model.joblib
  reports/baseline_a/metrics.json, report.txt

Chạy từ thư mục gốc dự án:
    python -m src.modeling.train_a
"""
import itertools
import json

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

from src.config import LABELS, MODELS_DIR, REPORTS_DIR, SEED
from src.dataset import load_samples
from src.modeling.evaluate import evaluate, format_report

GRID_C = [0.5, 1, 2, 5, 10, 20]
GRID_WEIGHT = [None, "balanced"]


def build(C, class_weight):
    # token_pattern giữ cả âm tiết 1 chữ ("ở", "ạ"), mặc định của sklearn bỏ mất
    return make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"(?u)\b\w+\b"),
        LogisticRegression(C=C, class_weight=class_weight, max_iter=3000, random_state=SEED),
    )


def top_features(model, n=8):
    vec, clf = model.steps[0][1], model.steps[1][1]
    names = vec.get_feature_names_out()
    return {lab: [names[j] for j in clf.coef_[list(clf.classes_).index(lab)].argsort()[::-1][:n]] for lab in LABELS}


def main():
    data = {s: load_samples(s, k=0) for s in ("train", "dev", "test")}
    X = {s: [x["text"] for x in v] for s, v in data.items()}
    y = {s: [x["label"] for x in v] for s, v in data.items()}

    tried = []
    for C, w in itertools.product(GRID_C, GRID_WEIGHT):
        dev = evaluate(y["dev"], build(C, w).fit(X["train"], y["train"]).predict(X["dev"]))
        tried.append({"C": C, "class_weight": w, "dev_macro_f1": dev["macro_f1"], "dev_accuracy": dev["accuracy"]})
        print(f"C={C:<4} class_weight={str(w):<9} dev macro-F1={dev['macro_f1']:.4f} acc={dev['accuracy']:.4f}")
    best = max(tried, key=lambda t: t["dev_macro_f1"])

    model = build(best["C"], best["class_weight"]).fit(X["train"], y["train"])
    test = evaluate(y["test"], model.predict(X["test"]))

    (MODELS_DIR / "baseline_a").mkdir(parents=True, exist_ok=True)
    out = REPORTS_DIR / "baseline_a"
    out.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODELS_DIR / "baseline_a" / "model.joblib")
    json.dump({"config": "A: TF-IDF (1-2 gram) + Logistic Regression, k=0", "best": best, "grid": tried,
               "n_train": len(y["train"]), "n_dev": len(y["dev"]), "test": test},
              open(out / "metrics.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    feats = top_features(model)
    report = "\n".join([
        "CẤU HÌNH A — TF-IDF (1-2 gram) + Logistic Regression, chỉ câu hiện tại",
        f"Mẫu: train {len(y['train'])} / dev {len(y['dev'])} / test {len(y['test'])} (đã bỏ LOAI và đa nhãn)",
        f"Tham số chọn trên dev: C={best['C']}, class_weight={best['class_weight']} (dev macro-F1 {best['dev_macro_f1']:.4f})",
        "", "=== KẾT QUẢ TRÊN TEST ===", format_report(test), "",
        "=== Từ/cụm từ quyết định nhất cho mỗi nhãn ===",
        *[f"{lab:<17}{', '.join(v)}" for lab, v in feats.items()],
    ])
    (out / "report.txt").write_text(report, encoding="utf-8")
    print("\n" + report)


if __name__ == "__main__":
    main()
