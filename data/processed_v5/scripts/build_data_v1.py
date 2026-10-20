"""Tạo data_v1/ từ processed_v3/ bằng cách áp dụng sua_nhan.csv và sua_dich.csv.

processed_v3/ không bị thay đổi. Mỗi lượt user trong data_v1 có thêm:
  - intent_goc: nhãn của processed_v3 (giống active_intent của MultiWOZ 2.2)
  - intent:     nhãn sau khi sửa; nhiều intent nối bằng "|",
                "LOAI" = không dùng làm mẫu (câu vẫn được giữ làm ngữ cảnh)

Cách chạy (từ thư mục project):
    python scripts/build_data_v1.py
"""
import csv, json, pathlib, collections, sys

sys.stdout.reconfigure(encoding="utf-8")

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC, OUT = ROOT.parent / "processed_v3", ROOT / "data_v1"
SPLITS = ("train", "dev", "test")
VALID = {"find_hotel", "find_restaurant", "find_train", "book_hotel", "book_restaurant", "book_train", "NONE"}


def read_csv(name):
    with open(ROOT / name, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def main():
    label_fix = {(r["id"], int(r["luot"])): r for r in read_csv("sua_nhan.csv")}
    text_fix = {(r["id"], int(r["luot"])): r for r in read_csv("sua_dich.csv")}
    used_label, used_text = set(), set()
    OUT.mkdir(exist_ok=True)
    stats = {}

    for split in SPLITS:
        n_dlg, c = 0, collections.Counter()
        with open(SRC / f"{split}.jsonl", encoding="utf-8") as fin, \
             open(OUT / f"{split}.jsonl", "w", encoding="utf-8") as fout:
            for line in fin:
                d = json.loads(line)
                n_dlg += 1
                for t in d["turns"]:
                    key = (d["id"], t["i"])
                    if key in text_fix:
                        fix = text_fix[key]
                        if t["vi"] != fix["vi_cu"]:
                            raise ValueError(f"{key}: vi không khớp vi_cu trong sua_dich.csv")
                        t["vi"] = fix["vi_moi"]
                        used_text.add(key)
                    if t["speaker"] != "USER":
                        continue
                    t["intent_goc"] = t["intent"]
                    if "|" in t["intent"] and key not in label_fix:
                        raise ValueError(f"{key}: lượt nhiều intent chưa có trong sua_nhan.csv")
                    if key in label_fix:
                        fix = label_fix[key]
                        if fix["nhan_goc"] != t["intent"]:
                            raise ValueError(f"{key}: nhan_goc không khớp processed_v3")
                        t["intent"] = fix["nhan_moi"]
                        used_label.add(key)
                    lab = t["intent"]
                    if lab == "LOAI":
                        c["loai"] += 1
                    else:
                        if not all(p in VALID for p in lab.split("|")):
                            raise ValueError(f"{key}: nhãn không hợp lệ {lab}")
                        c["da_nhan" if "|" in lab else "mot_nhan"] += 1
                fout.write(json.dumps(d, ensure_ascii=False) + "\n")
        stats[split] = (n_dlg, c)

    missing = (set(label_fix) - used_label) | (set(text_fix) - used_text)
    if missing:
        raise ValueError(f"Các dòng sửa không tìm thấy lượt tương ứng: {sorted(missing)[:5]}")

    print(f"{'tap':<6}{'hoi_thoai':>10}{'mau_1_nhan':>12}{'mau_da_nhan':>12}{'loai':>6}")
    for split, (n, c) in stats.items():
        print(f"{split:<6}{n:>10}{c['mot_nhan']:>12}{c['da_nhan']:>12}{c['loai']:>6}")
    print(f"Đã áp dụng {len(used_label)} dòng sửa nhãn, {len(used_text)} dòng sửa bản dịch -> {OUT}")


if __name__ == "__main__":
    main()
