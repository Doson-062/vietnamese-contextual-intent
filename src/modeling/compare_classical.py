"""So sánh các mô hình truyền thống (cùng mẫu, cùng cách chấm với cấu hình A).

Mỗi mô hình: học trên train, chọn tham số theo macro-F1 trên dev, chấm test một lần.
Ghi reports/classical_compare/{report.txt, results.json}.

Chạy từ thư mục gốc dự án:
    python -m src.modeling.compare_classical
"""
import itertools
import json
import time

from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.naive_bayes import ComplementNB
from sklearn.pipeline import make_pipeline, make_union
from sklearn.svm import LinearSVC

from src.config import REPORTS_DIR, SEED
from src.dataset import load_samples
from src.modeling.evaluate import accuracy_by_context, evaluate


def words():
    return TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"(?u)\b\w+\b")


def chars():
    return TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True)


WEIGHTS = [None, "balanced"]
MODELS = {  # tên: (hàm dựng mô hình từ tham số, lưới tham số thử trên dev)
    "TF-IDF từ + Logistic Regression (A)": (
        lambda c, w: make_pipeline(words(), LogisticRegression(C=c, class_weight=w, max_iter=3000, random_state=SEED)),
        list(itertools.product([0.5, 1, 2, 5, 10, 20], WEIGHTS))),
    "TF-IDF từ + SGD (modified_huber)": (
        lambda a, w: make_pipeline(words(), SGDClassifier(loss="modified_huber", alpha=a, class_weight=w, max_iter=50, random_state=SEED)),
        list(itertools.product([1e-5, 1e-4, 1e-3], WEIGHTS))),
    "TF-IDF từ + LinearSVC (SVM)": (
        lambda c, w: make_pipeline(words(), LinearSVC(C=c, class_weight=w, random_state=SEED)),
        list(itertools.product([0.05, 0.1, 0.3, 1, 3], WEIGHTS))),
    "TF-IDF từ + ký tự + LinearSVC": (
        lambda c: make_pipeline(make_union(words(), chars()), LinearSVC(C=c, class_weight="balanced", random_state=SEED)),
        [(c,) for c in [0.05, 0.1, 0.3, 1]]),
    "TF-IDF từ + RandomForest": (
        lambda leaf: make_pipeline(words(), RandomForestClassifier(n_estimators=300, min_samples_leaf=leaf, class_weight="balanced", random_state=SEED, n_jobs=-1)),
        [(1,), (2,)]),
    "TF-IDF ký tự (2-5) + Logistic Regression": (
        lambda c: make_pipeline(chars(), LogisticRegression(C=c, class_weight="balanced", max_iter=3000, random_state=SEED)),
        [(c,) for c in [1, 2, 5, 10]]),
    "TF-IDF từ + Naive Bayes (ComplementNB)": (
        lambda a: make_pipeline(words(), ComplementNB(alpha=a)),
        [(a,) for a in [0.01, 0.05, 0.1, 0.3, 1]]),
}


def main():
    data = {s: load_samples(s) for s in ("train", "dev", "test")}
    X = {s: [x["text"] for x in v] for s, v in data.items()}
    y = {s: [x["label"] for x in v] for s, v in data.items()}

    results = []
    for name, (build, grid) in MODELS.items():
        t = time.time()
        dev = {p: evaluate(y["dev"], build(*p).fit(X["train"], y["train"]).predict(X["dev"]))["macro_f1"] for p in grid}
        best = max(dev, key=dev.get)
        pred = build(*best).fit(X["train"], y["train"]).predict(X["test"])
        m = evaluate(y["test"], pred)
        results.append({"model": name, "best_params": list(best), "dev_macro_f1": dev[best], "test": m,
                        "test_by_context": accuracy_by_context(X["test"], y["test"], pred), "seconds": round(time.time() - t, 1)})
        print(f"{name:<42} tham số {best}  test macro-F1 {m['macro_f1']:.4f}", flush=True)

    results.sort(key=lambda r: -r["test"]["macro_f1"])
    out = REPORTS_DIR / "classical_compare"
    out.mkdir(parents=True, exist_ok=True)
    json.dump(results, open(out / "results.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    head = f"{'Mô hình':<42}{'Acc':>7}{'MacroF1':>9}{'F1 book_train':>15}{'Câu cần ngữ cảnh':>18}{'Tham số (chọn trên dev)':>28}"
    lines = ["SO SÁNH MÔ HÌNH TRUYỀN THỐNG — chỉ câu hiện tại, cùng mẫu và cách chấm với cấu hình A",
             f"Mẫu: train {len(y['train'])} / dev {len(y['dev'])} / test {len(y['test'])} (đã bỏ LOAI và đa nhãn)",
             "Mỗi mô hình chọn tham số theo macro-F1 trên dev, chấm test một lần. Sắp xếp theo macro-F1 trên test.", "", head]
    for r in results:
        m, ctx = r["test"], r["test_by_context"]["can_ngu_canh"]
        lines.append(f"{r['model']:<42}{m['accuracy']:>7.4f}{m['macro_f1']:>9.4f}{m['per_label']['book_train']['f1']:>15.4f}"
                     f"{ctx['accuracy']:>17.1%} {str(r['best_params']):>27}")
    n_ctx = results[0]["test_by_context"]["can_ngu_canh"]["n"]
    lines += ["", f"'Câu cần ngữ cảnh': {n_ctx} lượt test có ý định nhưng câu không nhắc từ khóa domain (ước lượng bằng từ khóa)."]
    (out / "report.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()
