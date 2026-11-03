"""Tính chỉ số đánh giá. A, B, C cùng dùng hàm này để so sánh công bằng."""
import re

from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support

from src.config import LABELS

# ponytail: ước lượng bằng từ khóa domain; thay bằng phân loại dạng ngữ cảnh (tuần 8) khi có
DOMAIN_KW = {"restaurant": r"nhà hàng|quán|món|ăn|bàn",
             "hotel": r"khách sạn|nhà nghỉ|phòng|chỗ ở|ở lại|đêm|sao",
             "train": r"tàu|chuyến|vé|ga|khởi hành|đến nơi"}


def needs_context(text, label):
    """Lượt có ý định nhưng câu không nhắc từ khóa nào của domain đó."""
    return label != "NONE" and not re.search(DOMAIN_KW[label.split("_")[1]], text, re.I)


def accuracy_by_context(texts, y_true, y_pred):
    groups = {"co_nhac_domain": [], "can_ngu_canh": [], "NONE": []}
    for t, y, p in zip(texts, y_true, y_pred):
        g = "NONE" if y == "NONE" else ("can_ngu_canh" if needs_context(t, y) else "co_nhac_domain")
        groups[g].append(y == p)
    return {g: {"n": len(v), "accuracy": sum(v) / len(v)} for g, v in groups.items() if v}


def evaluate(y_true, y_pred):
    p, r, f, n = precision_recall_fscore_support(y_true, y_pred, labels=LABELS, zero_division=0)
    mp, mr, mf, _ = precision_recall_fscore_support(y_true, y_pred, labels=LABELS, average="macro", zero_division=0)
    _, _, wf, _ = precision_recall_fscore_support(y_true, y_pred, labels=LABELS, average="weighted", zero_division=0)
    return {
        "n": len(y_true),
        "accuracy": accuracy_score(y_true, y_pred),
        "macro_precision": mp, "macro_recall": mr, "macro_f1": mf, "weighted_f1": wf,
        "per_label": {lab: {"precision": p[j], "recall": r[j], "f1": f[j], "support": int(n[j])}
                      for j, lab in enumerate(LABELS)},
        "confusion": confusion_matrix(y_true, y_pred, labels=LABELS).tolist(),
    }


def format_report(m):
    lines = [f"Số mẫu: {m['n']}",
             f"Accuracy: {m['accuracy']:.4f}",
             f"Macro    P / R / F1: {m['macro_precision']:.4f} / {m['macro_recall']:.4f} / {m['macro_f1']:.4f}",
             f"Weighted F1: {m['weighted_f1']:.4f}", "",
             f"{'Nhãn':<17}{'P':>8}{'R':>8}{'F1':>8}{'Số mẫu':>9}"]
    for lab, v in m["per_label"].items():
        lines.append(f"{lab:<17}{v['precision']:>8.4f}{v['recall']:>8.4f}{v['f1']:>8.4f}{v['support']:>9}")
    short = [lab.replace("restaurant", "res").replace("hotel", "hot").replace("train", "tra") for lab in LABELS]
    lines += ["", "Ma trận nhầm lẫn (hàng = nhãn đúng, cột = nhãn đoán):",
              " " * 10 + "".join(f"{s:>10}" for s in short)]
    for s, row in zip(short, m["confusion"]):
        lines.append(f"{s:<10}" + "".join(f"{x:>10}" for x in row))
    return "\n".join(lines)


if __name__ == "__main__":
    y = ["find_hotel", "book_hotel", "NONE", "NONE"]
    m = evaluate(y, ["find_hotel", "find_hotel", "NONE", "NONE"])
    assert m["accuracy"] == 0.75 and m["per_label"]["NONE"]["f1"] == 1.0
    assert m["confusion"][LABELS.index("book_hotel")][LABELS.index("find_hotel")] == 1
    assert needs_context("Có, bạn đặt giúp mình nhé", "book_hotel")
    assert not needs_context("Mình cần một khách sạn rẻ", "find_hotel")
    print(format_report(m))
