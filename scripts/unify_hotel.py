"""Thong nhat "nha nghi" -> "khach san" trong <thu_muc>/{train,dev,test}.jsonl (ghi de tai cho).

Nhan MultiWOZ chi co hotel (khach san va nha nghi cung nhan), nen thong nhat thanh "khach san".
Bo qua hoi thoai co cau noi ca hai tu trong CUNG mot cau (so sanh loai hinh): thay het se vo nghia.
Chay: python scripts/unify_hotel.py data/processed_v3
"""
import json
import re
import sys

D = sys.argv[1]
NN, KS = re.compile(r"nhà nghỉ", re.I), re.compile(r"khách sạn", re.I)
fix = lambda s: NN.sub(lambda m: "Khách sạn" if m.group(0)[0].isupper() else "khách sạn", s)
assert fix("Nhà nghỉ A và nhà nghỉ B") == "Khách sạn A và khách sạn B"
n_dlg = n_sent = n_skip = 0
for sp in ("train", "dev", "test"):
    rows = [json.loads(l) for l in open(f"{D}/{sp}.jsonl", encoding="utf-8")]
    for d in rows:
        if not any(NN.search(t["vi"]) for t in d["turns"]):
            continue
        if any(NN.search(t["vi"]) and KS.search(t["vi"]) for t in d["turns"]):
            n_skip += 1  # giu nguyen: hoi thoai so sanh khach san / nha nghi
            continue
        n_dlg += 1
        for t in d["turns"]:
            if NN.search(t["vi"]):
                t["vi"] = fix(t["vi"])
                n_sent += 1
    with open(f"{D}/{sp}.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
print(f"da thong nhat {n_dlg} hoi thoai ({n_sent} cau); giu nguyen {n_skip} hoi thoai co cau so sanh")
