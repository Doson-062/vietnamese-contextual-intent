"""Kiểm nguyên tắc find/book trên data_v1 (CHỈ ĐỌC, không sửa dữ liệu).

Nguyên tắc (người dùng chốt 19/10/2026): book_X chỉ khi đã có cơ sở / chuyến tàu
CỤ THỂ (có tên hoặc mã/giờ chuyến) và khách đang đặt; chưa có tên (hỏi đặt chung
chung, chọn theo đặc điểm, nhờ nhân viên chọn, đòi tìm chỗ khác) thì là find_X.

Nhận tên: bảng tên cơ sở data/interim/entity_map.json + CSDL data/raw/multiwoz_db,
mã tàu TR\\d{4}, giờ tàu nhân viên đưa ra. Kết quả là danh sách ỨNG VIÊN, phải đọc
tay trước khi ghi vào sua_nhan.csv (đợt 3 đã dùng script này).
Sau đợt 4 còn 16 ứng viên ĐÃ DUYỆT, không phải lỗi: 15 find->book (khách chỉ hỏi
thông tin, giữ find) và PMUL0585 lượt 18 (người dùng duyệt là book_restaurant).

Cách chạy (từ thư mục gốc dự án):
    python data/processed_v5/scripts/kiem_find_book.py [ung_vien.json]
"""
import json, glob, re, collections as C, sys
sys.stdout.reconfigure(encoding="utf-8")
RAW = "multiwoz/data/MultiWOZ_2.2"; V5 = "data/processed_v5/data_v1/"
raw = {}
for f in glob.glob(RAW + "/*/dialogues_*.json"):
    for d in json.load(open(f, encoding="utf-8")): raw[d["dialogue_id"]] = d

GENERIC = {"the", "city", "cambridge", "university", "express", "hotel", "house", "guest", "golden", "royal", "little",
           "good", "lucky", "gourmet", "restaurant", "cafe", "pizza", "curry", "river", "green", "north", "south", "east",
           "west", "centre", "lodge", "grand", "bed", "and", "breakfast", "tandoori", "saint", "charlie", "cherry"}
BAD = {"ali", "caffe", "clown", "ask", "city", "pizza", "curry", "riverside"}


def norm(x):
    x = re.sub(r"guesthouse", "guest house", x.lower())
    return re.sub(r"\bb ?(and|&) ?b\b|\bbed ?& ?breakfast\b", "bed and breakfast", x)


EM = json.load(open("data/interim/entity_map.json", encoding="utf-8"))
names = {"hotel": set(), "restaurant": set()}
for k, v in EM.items():
    D = v["slot"].split("-")[0]
    if D in names: names[D].add(k)
for D in names:
    names[D] |= {x["name"] for x in json.load(open(f"data/raw/multiwoz_db/{D}_db.json", encoding="utf-8"))}
    names[D] = {norm(n) for n in names[D]}
    names[D] |= {n.split()[0] for n in list(names[D]) if len(n.split()) > 1 and len(n.split()[0]) > 4 and n.split()[0] not in GENERIC}
    names[D] -= BAD
NAMERE = {D: re.compile(r"(?<![\w-])(" + "|".join(sorted(map(re.escape, names[D]), key=len, reverse=True)) + r")(?![\w-])") for D in names}
TRAIN_U = re.compile(r"\bTR ?\d{4}\b|\b\d{1,2}[:.]\d{2}( ?am| ?pm)? (train|one|departure)\b|\bthe (first|earliest|latest|last) (one|train)\b", re.I)
TRAIN_S = re.compile(r"\bTR ?\d{4}\b|\b(leaves?|leaving|departs?|departing|arrives?|arriving)\b[^.?!]{0,40}\b\d{1,2}[:.]\d{2}", re.I)
RESEARCH = re.compile(r"\b(another|different|any other|other)\s+(\w+\s+){0,3}?(restaurants?|hotels?|guest ?houses?|places?|ones?|areas?|trains?|options?)\b"
                      r"|\b(something else|look again|search again|find (me )?(another|something))\b", re.I)
REQ = re.compile(r"(please book|book (it|that|this|them|one|a |me|for|the)|(make|like) a (reservation|booking)|reserve (it|that|a|me|seats?)|go ahead and book|can you book|could you book|book a table|book seats?|go ahead)", re.I)
OFFER = re.compile(r"(would you like|shall i|should i|do you want|want me to|can i|may i)[^?.]*(book|reserv)", re.I)
YES = re.compile(r"^\s*(yes|yeah|yep|sure|please|ok|okay|that would be|that sounds|go ahead)", re.I)
NEG = re.compile(r"\b(no|not|don'?t|later|myself|n't|yet|before)\b", re.I)


def mentioned(en, spk):
    n = norm(en)
    out = {D for D in names if NAMERE[D].search(n)}
    if (TRAIN_S if spk == "SYSTEM" else TRAIN_U).search(en): out.add("train")
    return out


def run():
    ch = []; S = C.Counter()
    for sp in ("train", "dev", "test"):
        for ln, d in enumerate(map(json.loads, open(V5 + sp + ".jsonl", encoding="utf-8")), 1):
            did = d["id"]; R = raw[did]["turns"]; known = set(); prev = {}
            for t in d["turns"]:
                i = t["i"]; en = t["en"]
                if t["speaker"] == "SYSTEM":
                    known |= mentioned(en, "SYSTEM"); continue
                sv = {}
                for fr in R[i]["frames"]: sv.update(fr["state"]["slot_values"])
                new = {k for k, v in sv.items() if prev.get(k) != v}; prev = sv
                here = mentioned(en, "USER"); lab = t["intent"]
                research = bool(RESEARCH.search(en))
                if research:  # khách đòi tìm chỗ khác -> tên cũ hết hiệu lực
                    for p in lab.split("|"):
                        if "_" in p and p.split("_")[1] not in here: known.discard(p.split("_")[1])
                known |= here
                if lab in ("NONE", "LOAI"): continue
                sysp = d["turns"][i - 1]["en"] if i else ""
                newp = []
                for p in lab.split("|"):
                    kind, D = p.split("_")
                    booking = any(k.startswith(D + "-book") for k in new) or (not NEG.search(en) and (REQ.search(en) or (YES.match(en) and OFFER.search(sysp))))
                    if kind == "book" and D not in known: newp.append("find_" + D); S["book->find"] += 1
                    elif kind == "find" and D in known and booking and not research: newp.append("book_" + D); S["find->book"] += 1
                    else: newp.append(p)
                nl = "|".join(sorted(set(newp)))
                if nl != lab: ch.append((sp, ln, did, i, t["intent_goc"], lab, nl, sysp, en, t["vi"]))
    return ch, S


if __name__ == "__main__":
    ch, S = run()
    print(dict(S), "ứng viên:", len(ch))
    for c in ch: print(c[0], "dòng", c[1], c[2], "lượt", c[3], c[5], "->", c[6], "| U:", c[8][:100])
    if len(sys.argv) > 1: json.dump(ch, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False)
