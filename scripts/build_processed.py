"""Tao data/processed/{train,dev,test}.jsonl tu data/interim/mwoz_vi.jsonl.

- nhan rong (khong co intent) -> "NONE"; chi lut khach co nhan (nhan viec dung "|" cho da nhan)
- bo hoi thoai trung noi dung giua cac tap (giu ban o train)
Chay: python scripts/build_processed.py [nguon.jsonl] [thu_muc_ra]
  mac dinh: data/interim/mwoz_vi.jsonl -> data/processed
"""
import collections
import hashlib
import json
import os
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else "data/interim/mwoz_vi.jsonl"
OUT = sys.argv[2] if len(sys.argv) > 2 else "data/processed"
os.makedirs(OUT, exist_ok=True)
rows = [json.loads(l) for l in open(SRC, encoding="utf-8") if l.strip()]
sig = lambda d: hashlib.md5(" ".join(t["en"] for t in d["turns"]).encode()).hexdigest()
rank = {"train": 0, "dev": 1, "test": 2}
seen, out = {}, collections.defaultdict(list)
for d in sorted(rows, key=lambda d: rank[d["split"]]):  # train truoc: ban trung o tap sau bi bo
    if sig(d) in seen:
        print("bo hoi thoai trung", d["id"], "voi", seen[sig(d)])
        continue
    seen[sig(d)] = d["id"]
    turns = [{"i": t["i"], "speaker": t["speaker"], "vi": t["vi"], "en": t["en"],
              "intent": (t["intent"] or "NONE") if t["speaker"] == "USER" else None} for t in d["turns"]]
    out[d["split"]].append({"id": d["id"], "split": d["split"], "domains": d["domains"], "turns": turns})
for sp, rs in out.items():
    with open(f"{OUT}/{sp}.jsonl", "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rs)
    print(sp, len(rs), "hoi thoai")
