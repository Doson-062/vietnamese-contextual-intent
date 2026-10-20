"""Liệt kê lượt đang là book_ nhưng khách chỉ hỏi thông tin (CHỈ ĐỌC, không sửa dữ liệu).

Nguyên tắc (người dùng chốt 19/10/2026): hỏi thông tin về cơ sở đã có tên (địa chỉ,
giá, giờ tàu...), đòi tìm chỗ khác, chỉnh tiêu chí tìm -> find_; còn đồng ý đặt kèm
câu hỏi, đổi giờ/ngày đặt, chọn chỗ để đặt -> giữ book_. Kết quả là danh sách ỨNG VIÊN
theo từ khóa, phải đọc tay trước khi ghi vào sua_nhan.csv (đợt 4 đã dùng script này).
Sau đợt 4 chỉ còn 2 lượt cố ý giữ book_: SNG01538 lượt 6, MUL0624 lượt 10.

Cách chạy (từ thư mục gốc dự án):
    python data/processed_v5/scripts/kiem_hoi_thong_tin.py
"""
import json, glob, re, sys
sys.stdout.reconfigure(encoding="utf-8")
RAW = "multiwoz/data/MultiWOZ_2.2"
raw = {}
for f in glob.glob(RAW + "/*/dialogues_*.json"):
    for d in json.load(open(f, encoding="utf-8")): raw[d["dialogue_id"]] = d
INFO = re.compile(r"\b(address|phone|number|post ?code|area|part of town|price|cost|how much|fee|stars?|rating|parking|wifi|internet|travel time|how long|duration|train id|id|depart\w*|leave|leaves|arriv\w*|what time|food|cuisine|type|located|location|where)\b", re.I)
BOOKING = re.compile(r"\b(book|booking|reserv\w*|reference|ref|confirm\w*|people|persons?|guests?|nights?|tickets?|seats?|table for|party of|try|instead|for \d|at \d{1,2}[:.]\d{2})\b", re.I)
YES = re.compile(r"^\s*(yes|yeah|yep|sure|ok|okay|go ahead|please do|that would be|that sounds|that works|perfect|great, book)", re.I)
out = []
for s in ("train", "dev", "test"):
    for ln, d in enumerate(map(json.loads, open(f"data/processed_v5/data_v1/{s}.jsonl", encoding="utf-8")), 1):
        prev = {}; R = raw[d["id"]]["turns"]
        for t in d["turns"]:
            if t["speaker"] != "USER": continue
            sv = {}
            for fr in R[t["i"]]["frames"]: sv.update(fr["state"]["slot_values"])
            new = {k for k, v in sv.items() if prev.get(k) != v}; prev = sv
            if "book_" not in t["intent"]: continue
            en = t["en"]
            for p in t["intent"].split("|"):
                if not p.startswith("book_"): continue
                D = p[5:]
                if any(k.startswith(D + "-book") for k in new): continue  # khách đưa thông tin đặt -> đúng là book
                if INFO.search(en) and not BOOKING.search(en) and not YES.match(en):
                    out.append((s, ln, d["id"], t["i"], t["intent"], d["turns"][t["i"] - 1]["en"][:80], en))
for n, o in enumerate(out, 1): print(n, o[0], "dòng", o[1], o[2], "lượt", o[3], o[4], "| S:", o[5], "| U:", o[6][:120])
print("ứng viên:", len(out))
