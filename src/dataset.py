"""Đọc data_v1 và tạo mẫu huấn luyện/đánh giá. Dùng chung cho A, B, C.

Mỗi lượt khách là một mẫu. Bỏ khỏi tập mẫu (nhưng vẫn giữ làm ngữ cảnh):
  - LOAI: câu không xác định được ý định
  - đa nhãn (có "|"): bài toán là phân loại đơn nhãn 7 lớp
"""
import json

from src.config import DATA_DIR, LABELS


def load_dialogues(split):
    with open(DATA_DIR / f"{split}.jsonl", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def load_samples(split, k=0):
    """Trả về list mẫu {id, turn, text, context, label}.

    context: k lượt ngay trước (cả khách và nhân viên), dạng [(speaker, câu)];
    k=0 là không ngữ cảnh (A, B), k=None là toàn bộ lịch sử.
    """
    samples = []
    for d in load_dialogues(split):
        turns = d["turns"]
        for t in turns:
            if t["speaker"] != "USER" or t["intent"] not in LABELS:
                continue
            i = t["i"]
            start = 0 if k is None else max(0, i - k)
            samples.append({
                "id": d["id"], "turn": i, "text": t["vi"],
                "context": [(u["speaker"], u["vi"]) for u in turns[start:i]],
                "label": t["intent"],
            })
    return samples


if __name__ == "__main__":
    for split in ("train", "dev", "test"):
        s = load_samples(split, k=2)
        assert all(x["label"] in LABELS for x in s)
        assert all(len(x["context"]) <= 2 for x in s)
        print(split, len(s), "mẫu")
