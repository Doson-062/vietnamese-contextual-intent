"""Dich tap con MultiWOZ 2.2 sang tieng Viet noi tu nhien bang Claude (ca hoi thoai mot lan goi).

Chay tu thu muc goc du an:
  python src/translate.py extract                         # loc domain, ban dia hoa ten/dia danh -> JSONL tieng Anh
  python src/translate.py translate --limit 1500          # dich qua `claude -p` (goi Pro), chay lai thi tiep cho do
  python src/translate.py check                           # danh dau tu dong cac cau dich nghi ngo (mat so, mat ten...)
  python src/translate.py review --inp ... --out ...      # xuat TSV de tu cham chat luong
"""
import argparse
import collections
import csv
import glob
import json
import os
import random
import re
import time

SRC_CANDIDATES = ["data/raw/MultiWOZ_2.2", "multiwoz/data/MultiWOZ_2.2"]
DOMAINS = "restaurant,hotel,train,attraction"  # mac dinh cua --domains; "all" = khong loc
PRIORITY = {"restaurant", "hotel", "train"}  # hoi thoai chi gom cac domain nay duoc dich truoc
# Ban dia hoa nhu ViWOZ: ga/thanh pho Anh -> dia danh Viet Nam (dung chung cho ca USER va SYSTEM).
# Xep theo thoi gian tau tu Cambridge (phut) de ga Viet gan/xa tuong ung: Ely 17, Stansted 28, Bishops Stortford 38,
# Stevenage ~50, Peterborough/Kings Cross ~50, Kings Lynn ~50, Broxbourne ~60, Norwich 79, Liverpool St 88,
# Leicester ~105, Birmingham 163. ponytail: chi giu thu tu xa/gan, khong khop thoi gian that cua tau Viet Nam.
CITY = {
    "cambridge": "Hanoi",
    "ely": "Bac Ninh", "stansted airport": "Noi Bai Airport", "stansted": "Noi Bai Airport",
    "bishops stortford": "Tu Son", "bishop's stortford": "Tu Son", "stevenage": "Hung Yen",
    "peterborough": "Hai Duong", "kings lynn": "Vinh Phuc", "king's lynn": "Vinh Phuc",
    "london kings cross": "Hai Phong", "london king's cross": "Hai Phong", "kings cross": "Hai Phong",
    "king's cross": "Hai Phong", "london": "Hai Phong", "broxbourne": "Phu Ly",
    "norwich": "Nam Dinh", "london liverpool street": "Ninh Binh", "liverpool street": "Ninh Binh",
    "leicester": "Thanh Hoa", "birmingham new street": "Vinh", "birmingham": "Vinh",
}
CITY_RE = re.compile(r"\b(" + "|".join(map(re.escape, sorted(CITY, key=len, reverse=True))) + r")\b", re.I)

# Ban dia hoa ten nha hang / khach san / diem tham quan (ViWOZ dung CSDL Ha Noi crawl tu trang dat cho;
# o day sinh TEN GIA LAP kieu Viet, co dinh theo seed, luu o data/interim/entity_map.json de kiem tra).
ENT_SLOTS = ("restaurant-name", "hotel-name", "attraction-name")
SYL = list(dict.fromkeys(
    "Hương Sen Trúc Lan Cúc Mai Đào Liễu Hạc Vân Phong Thủy Sơn Hải Nguyệt Tinh Long Phụng Lân Bình An Phúc Lộc "
    "Thọ Hỷ Tài Thanh Minh Quang Lâm Nam Bắc Xuân Hạ Thu Kim Ngọc Bích Hồng Lam Tùng Bách".split()))
# (tu khoa trong ten tieng Anh) -> tien to tieng Viet; khop dau tien thang
TYPE_WORDS = {
    "restaurant-name": [({"noodle", "noodles"}, "Quán Mì"), ({"pizza", "pizzeria"}, "Tiệm Pizza"),
                        ({"cafe", "coffee"}, "Quán Cà Phê"),
                        ({"bakery"}, "Tiệm Bánh"), ({"grill"}, "Quán Nướng")],
    "hotel-name": [({"guest", "guesthouse", "house", "lodge", "hostel", "breakfast"}, "Nhà nghỉ"),
                   ({"hotel", "inn"}, "Khách sạn")],
    "attraction-name": [({"church", "cathedral", "chapel", "minster"}, "Nhà thờ"), ({"college"}, "Học viện"),
                        ({"museum"}, "Bảo tàng"), ({"gallery", "galleries", "artworks", "art", "arts"}, "Phòng tranh"),
                        ({"park", "gardens", "garden", "common", "meadows"}, "Công viên"),
                        ({"theatre", "theater"}, "Nhà hát"), ({"pool", "swimming"}, "Bể bơi"),
                        ({"cinema"}, "Rạp chiếu phim"), ({"club", "nightclub"}, "Câu lạc bộ"),
                        ({"boat", "boats", "punting", "cruise", "river"}, "Du thuyền"),
                        ({"stadium", "ground"}, "Sân vận động")],
}
DEFAULT_PREFIX = {"restaurant-name": ("Nhà hàng", "Quán ăn", "Bếp"), "hotel-name": ("Khách sạn",),
                  "attraction-name": ("Điểm tham quan",)}


# Dia chi, dien thoai, ma buu chinh, tien: doi bang code (bang tra co dinh) de moi thuc the nhat quan tren ca bo du lieu.
HANOI_STREETS = list(dict.fromkeys(
    """Hàng Bài|Hàng Bông|Hàng Gai|Hàng Đào|Hàng Ngang|Hàng Buồm|Hàng Mã|Hàng Bạc|Hàng Trống|Hàng Cót|Hàng Chiếu|Hàng Da|
    Hàng Điếu|Hàng Khay|Hàng Vải|Hàng Bồ|Hàng Thiếc|Hàng Quạt|Hàng Giầy|Hàng Gà|Lý Thường Kiệt|Tràng Tiền|Tràng Thi|
    Phan Bội Châu|Phan Chu Trinh|Phan Đình Phùng|Điện Biên Phủ|Quán Thánh|Thanh Niên|Nguyễn Du|Nguyễn Trãi|Nguyễn Thái Học|
    Nguyễn Khuyến|Nguyễn Công Trứ|Nguyễn Lương Bằng|Nguyễn Chí Thanh|Nguyễn Văn Cừ|Nguyễn Văn Huyên|Nguyễn Phong Sắc|
    Trần Hưng Đạo|Trần Phú|Trần Duy Hưng|Trần Quốc Toản|Trần Nhân Tông|Trần Khát Chân|Trần Xuân Soạn|Lê Duẩn|Lê Thánh Tông|
    Lê Văn Lương|Lê Đức Thọ|Lê Quang Đạo|Lê Trọng Tấn|Lê Lai|Lê Văn Hưu|Láng Hạ|Giảng Võ|Kim Mã|Liễu Giai|Đội Cấn|Văn Cao|
    Hoàng Hoa Thám|Hoàng Quốc Việt|Hoàng Cầu|Hoàng Diệu|Hoàng Văn Thái|Đê La Thành|Xã Đàn|Tây Sơn|Thái Hà|Chùa Bộc|Khâm Thiên|
    Cát Linh|Ngọc Khánh|Đường Thành|Cửa Nam|Bà Triệu|Đại Cồ Việt|Giải Phóng|Trương Định|Minh Khai|Bạch Mai|Hai Bà Trưng|Lò Đúc|
    Tô Hiến Thành|Thi Sách|Yên Phụ|Thụy Khuê|Nghi Tàm|Âu Cơ|Lạc Long Quân|Xuân Diệu|Tô Ngọc Vân|Trích Sài|Võng Thị|Hồ Tùng Mậu|
    Phạm Hùng|Phạm Văn Đồng|Phạm Ngọc Thạch|Phạm Ngũ Lão|Tống Duy Tân|Ngô Quyền|Ngô Thì Nhậm|Ngô Sĩ Liên|Lương Văn Can|
    Lý Nam Đế|Lý Quốc Sư|Nhà Chung|Cầu Gỗ|Hàng Bè|Chân Cầm|Cao Thắng|Bát Sứ|Đinh Tiên Hoàng|Yết Kiêu|Quang Trung|Bảo Khánh""".split("|")))
HANOI_STREETS = [x.strip() for x in HANOI_STREETS if x.strip()]
AREAS = ("city centre", "city center", "chesterton", "fen ditton", "cherry hinton", "newnham")  # bo sau dia chi
STREET_RX = re.compile(r"\b\d{1,3}[a-z]?\s+([a-z']+(?:\s[a-z']+)?)\s(road|street|lane)\b", re.I)
PHONE_RE = re.compile(r"\b0\d{4}\s?\d{5,6}\b|\b0\d{9}\b")
POST_RE = re.compile(r"\bcb\s?\d{1,2}\s?\d[a-z]{2}\b", re.I)
MONEY_RE = re.compile(r"£\s?(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s*(?:pounds?|gbp)\b", re.I)
RATE = 25000  # 1 bang = 25.000 dong, lam tron nghin (ghi vao bao cao)
STREETS, STREET_PAT, MULTI_PAT = {}, None, None  # ponytail: bien toan cuc do extract() dien; doi sang tham so neu can chay song song


def street_keys(text):
    return [" ".join(m.group(1).lower().split()) + " " + m.group(2).lower() for m in STREET_RX.finditer(text)]


DB_STREET_RX = re.compile(r"((?:[a-z']+\s)?[a-z']+)\s(road|street|lane|hill|row|way|place|court|close|square|gardens|"
                          r"walk|parade|yard|drive|avenue|passage)\b")


def db_street_keys(addrs):
    """Ten duong trong dia chi CSDL (sach, khong can so nha), vd "market hill city centre" -> "market hill"."""
    out = []
    for a in addrs:
        for m in DB_STREET_RX.finditer(a):
            words = [w for w in m.group(1).split() if w not in {"off", "the", "and", "at", "of", "on"}]
            if words:
                out += [" ".join(words) + " " + m.group(2)] * 3  # x3: luon vuot nguong tan suat cua build_streets
    return out


def build_streets(keys, seed=42):
    """keys: moi lan thay 'ten duong' co so nha -> {key: 'phố X'}; gop loi chinh ta (chesteron~chesterton) bang difflib."""
    import difflib
    cnt = collections.Counter(keys)
    main = sorted(k for k, n in cnt.items() if n >= 3)
    assert len(main) <= len(HANOI_STREETS), "can them ten pho Ha Noi"
    pool = HANOI_STREETS[:]
    random.Random(seed).shuffle(pool)
    out = {k: "phố " + pool.pop() for k in main}
    for k in cnt:
        if k not in out:
            near = difflib.get_close_matches(k, main, n=1, cutoff=0.85)
            if near:
                out[k] = out[near[0]]
    return out


def set_streets(streets):
    global STREETS, STREET_PAT
    STREETS = streets
    STREET_PAT = re.compile(r"\b(?:(\d{1,3}[a-z]?)\s+)?(" + "|".join(map(re.escape, sorted(streets, key=len, reverse=True)))
                            + r")\b(?:\s+(" + "|".join(AREAS) + r"))?", re.I) if streets else None


def _street(m):
    # bo cum khu vuc tieng Anh sau dia chi ("City Centre"), khong doi thanh quan: tranh mau thuan voi slot area
    # (vd nha hang "phia nam" nhung dia chi ghi "City Centre")
    num = m.group(1)
    return (num + " " if num else "") + STREETS[m.group(2).lower()]


def _digits(key, n, seed):  # n chu so co dinh theo key (cung so cu -> cung so moi)
    return "".join(random.Random(f"{seed}{key}").choices("0123456789", k=n))


def _phone(m):
    d = re.sub(r"\D", "", m.group(0))
    x = _digits(d, 8, "tel")
    return f"024 {'36'[int(x[0]) % 2]}{x[1:4]} {x[4:]}"


def _post(m):
    return "10" + _digits(re.sub(r"\s", "", m.group(0).lower()), 4, "zip")


def _money(m):
    # doi chinh xac (0,01 bang = 250 dong), khong lam tron: don gia x so ve van khop tong tien nhu ban goc
    v = round(float((m.group(1) or m.group(2)).replace(",", "")) * RATE)
    return f"{v:,}".replace(",", ".") + " VND"


# Nhan span cua MultiWOZ co nhieu: dinh dau cham cau ("bedouin,which"), hoac "ten" la tu thuong ("yes", "free").
GENERIC = set("a an the it that this any one two three yes no free good south north east west centre center place "
              "places restaurant restaurants hotel hotels guesthouse guest house houses cheap expensive moderate "
              "food wifi parking star stars and or of in".split())
AMBIGUOUS = {"ask", "city", "pizza", "curry", "riverside", "vue",  # nhan span nham: cum tu thuong, khong phai ten
             "city centre", "city center", "restaurant and bar", "other oriental restaurant", "restaurant called two two",
             "pizza hut in the city center",
             # ten 1 tu trung tu thuong / thanh pho / ten duong / ten truong (vd "cambridge", "milton road", "trinity")
             "cambridge", "art", "artworks", "bistro", "boat", "brasserie", "bridge", "called", "chinese", "college",
             "fun", "gallery", "india", "indian", "junction", "museum", "museums", "nil", "reference", "royal", "sala",
             "salsa", "taj", "tandoori", "punter", "riverboat", "shanghai", "hotpot", "mahal", "binh", "loch", "uno",
             "charlie", "alexander", "milton", "downing", "trinity", "magdalene", "lensfield", "warkworth", "parkside",
             "queen's", "church's", "corpus", "clare"}  # ten trung tu thong thuong: giu nguyen tieng Anh


def clean_form(form):
    form = re.sub(r"[,;?!\"].*$", "", form.lower())  # cat tu dau cau dau tien
    form = re.sub(r"\.(?=\w).*$", "", form)  # "b.reference" -> "b"
    form = re.sub(r"^the\s+", "", form.strip(" .'\""))
    return form


def valid_form(form):
    return len(form) > 2 and form not in AMBIGUOUS and not set(re.findall(r"[a-z']+", form)) <= GENERIC


def dialogue_forms(d):
    """Cac cach viet ten thuc the (lower) duoc danh dau span trong hoi thoai -> {form: slot}."""
    out = {}
    for t in d["turns"]:
        for fr in t["frames"]:
            for sp in fr.get("slots", []):
                if sp["slot"] in ENT_SLOTS and "start" in sp:
                    form = clean_form(t["utterance"][sp["start"]:sp["exclusive_end"]])
                    if valid_form(form):
                        out.setdefault(form, sp["slot"])
    return out


DB_DIR = "data/raw/multiwoz_db"  # hotel/restaurant/attraction_db.json tai tu repo MultiWOZ (thu muc db/)
ATTR_TYPE = {"architecture": "Công trình", "boat": "Du thuyền", "cinema": "Rạp chiếu phim", "college": "Học viện",
             "concerthall": "Nhà hát", "entertainment": "Khu vui chơi", "museum": "Bảo tàng",
             "multiple sports": "Trung tâm thể thao", "nightclub": "Câu lạc bộ", "park": "Công viên",
             "swimmingpool": "Bể bơi", "theatre": "Nhà hát"}


def load_db():
    """{(domain, ten chuan): tien to theo loai THAT} va danh sach dia chi; thieu CSDL -> rong."""
    db, addrs = {}, []
    for dom in ("hotel", "restaurant", "attraction"):
        path = f"{DB_DIR}/{dom}_db.json"
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for r in json.load(f):
                if dom == "hotel":
                    p = "Nhà nghỉ" if r.get("type") == "guesthouse" else "Khách sạn"
                elif dom == "attraction":
                    p = ATTR_TYPE.get(r.get("type"))
                else:
                    p = "Quán ăn" if r.get("pricerange") == "cheap" else "Nhà hàng"
                db[(dom, clean_form(r["name"]))] = p
                addrs.append(r.get("address", "").lower())
    return db, addrs


def canon(form, slot, db):
    """Gop bien the cua cung mot co so ve ten chuan trong CSDL: sai chinh ta ("allenball"~"allenbell"),
    ten rut gon ("kirkwood" -> "kirkwood house", "peking" -> "peking restaurant")."""
    import difflib
    names = [n for d, n in db if d == slot.split("-")[0]]
    if form in names:
        return form
    near = difflib.get_close_matches(form, names, n=1, cutoff=0.85)
    if near:
        return near[0]
    longer = [n for n in names if n.startswith(form + " ")]
    return longer[0] if len(longer) == 1 else form


def build_emap(forms, seed=42, db=None):
    """forms: {form: slot} -> {form: ten tieng Viet}; cac bien the cung mot co so dung chung mot ten."""
    db = db or {}
    rng = random.Random(seed)
    pairs = [(a, b) for a in SYL for b in SYL if a != b]
    rng.shuffle(pairs)
    by_canon = {}
    for form, slot in sorted(forms.items()):
        by_canon.setdefault((slot, canon(form, slot, db)), []).append(form)
    assert len(by_canon) <= len(pairs), "can them am tiet trong SYL"
    emap = {}
    for (slot, c), group in sorted(by_canon.items()):
        kw = next((p for kws, p in TYPE_WORDS[slot] if kws & set(re.findall(r"[a-z]+", c))), None)
        typ = db.get((slot.split("-")[0], c))  # loai that trong CSDL uu tien hon doan theo tu khoa
        prefix = ((kw or typ) if slot == "restaurant-name" else (typ or kw)) or rng.choice(DEFAULT_PREFIX[slot])
        a, b = pairs.pop()
        for form in group:
            emap[form] = f"{prefix} {a} {b}"
    return emap


assert canon("kirkwood", "hotel-name", {("hotel", "kirkwood house"): "Nhà nghỉ"}) == "kirkwood house"
assert build_emap({"home from home": "hotel-name"}, 1, {("hotel", "home from home"): "Nhà nghỉ"})[
    "home from home"].startswith("Nhà nghỉ ")


def make_pat(forms):
    if not forms:
        return None
    # (?!\s+hotel): "Cambridge Lodge Hotel" khong bi thay boi ten nha hang "cambridge lodge"
    return re.compile(r"\b(?:the\s+)?(" + "|".join(map(re.escape, sorted(forms, key=len, reverse=True)))
                      + r")\b(?!\s+(?:hotel|guest\s*house|road|street|lane)\b)", re.I)


def localize(text, pat=None, emap=None):
    if pat:  # ten thuc the truoc, dia danh sau
        text = pat.sub(lambda m: emap[m.group(1).lower()], text)
    text = CITY_RE.sub(lambda m: CITY[m.group(0).lower()], text)
    if STREET_PAT:
        text = STREET_PAT.sub(_street, text)
    return MONEY_RE.sub(_money, POST_RE.sub(_post, PHONE_RE.sub(_phone, text)))


assert localize("a train from London Kings Cross to Cambridge") == "a train from Hai Phong to Hanoi"
assert localize("leave Ely, arrive Stansted Airport") == "leave Bac Ninh, arrive Noi Bai Airport"
assert localize("Lodge Hotel at Cambridge Lodge Hotel", make_pat(["cambridge lodge"]), {"cambridge lodge": "X"}) \
    == "Lodge Hotel at Hanoi Lodge Hotel"
assert localize("Try the Curry Garden.", make_pat(["curry garden"]), {"curry garden": "Quán X Y"}) == "Try Quán X Y."
set_streets({"milton road": "phố Hàng Bài"})
assert localize("63 Milton Road Chesterton, phone 01223 360966, cb41uy") == localize("63 milton road chesterton, phone 01223360966, CB4 1UY")
assert localize("63 Milton Road City Centre.") == "63 phố Hàng Bài."
assert localize("It costs 17.90 pounds, total 143.19 GBP, £5") == "It costs 447.500 VND, total 3.579.750 VND, 125.000 VND"
assert re.fullmatch(r"024 [36]\d{3} \d{4}", localize("call 01223 360966")[5:]) and not PHONE_RE.search(localize("call 0123366552"))
set_streets({})
assert clean_form("Bedouin,which") == "bedouin" and clean_form("'The Good Luck'") == "good luck"
assert not valid_form("yes") and not valid_form("a guesthouse") and not valid_form("ask") and valid_form("allenbell")


def parse(d, emap):
    """Doi hoi thoai MultiWOZ 2.2 -> dict gon. Domain lay tu nhan intent that, vi truong `services` thieu/rong."""
    # ten 1 tu chi thay trong chinh hoi thoai co danh dau (tranh thay nham tu thuong, vd "peking");
    # ten >= 2 tu la ten rieng ro rang -> thay o moi hoi thoai (MULTI_PAT), ke ca khi du lieu goc thieu danh dau
    forms = [f for f in dialogue_forms(d) if f in emap]
    # ten rut gon cua co so da nhac trong hoi thoai ("Kirkwood" khi co "Kirkwood House") -> cung ten Viet,
    # chi khi dang rut gon do tung duoc danh dau la ten o dau do trong du lieu (an toan, tranh tu thuong)
    if MULTI_PAT:
        for t in d["turns"]:
            for m in MULTI_PAT.finditer(t["utterance"]):
                head = m.group(1).lower().split()[0]
                if head in emap and head not in forms:
                    forms.append(head)
    pat = make_pat(forms)
    turns, abbr = [], {}
    for i, t in enumerate(d["turns"]):
        intents = sorted({fr.get("state", {}).get("active_intent", "NONE") for fr in t["frames"]} - {"NONE"})
        found = set()

        def sub(m):
            found.add(emap[m.group(1).lower()])
            return emap[m.group(1).lower()]
        text = MULTI_PAT.sub(sub, t["utterance"]) if MULTI_PAT else t["utterance"]
        for w, vi_name in abbr.items():  # "the Express" sau khi da nhac "Express by Holiday Inn" trong hoi thoai nay
            text = re.sub(r"\b(?:the\s+)?" + re.escape(w) + r"\b(?!\s+(?:road|street|lane|hotel|guest\s*house)\b)", lambda _: (found.add(vi_name), vi_name)[1], text, flags=re.I)
        if MULTI_PAT:  # luot sau moi ap dung: ghi nho dau ten (tu dau) cua cac ten day du vua gap o luot nay
            for m in MULTI_PAT.finditer(t["utterance"]):
                w = m.group(1).lower().split()[0]
                if (len(w) > 3 and w not in GENERIC and w not in AMBIGUOUS and w not in emap
                        and not CITY_RE.fullmatch(w) and w != "the"):
                    abbr.setdefault(w, emap[m.group(1).lower()])
        src = localize(text, pat, emap)
        turns.append({
            "i": i, "speaker": t["speaker"], "en": t["utterance"], "src": src,
            "ents": sorted(found | {emap[f] for f in forms if emap[f] in src}),
            "intent": "|".join(intents) if t["speaker"] == "USER" else None,
        })
    domains = sorted({x.split("_", 1)[1] for t in turns if t["intent"] for x in t["intent"].split("|")})
    return {"id": d["dialogue_id"], "domains": domains, "turns": turns}


def load(src, split):
    for f in sorted(glob.glob(f"{src}/{split}/dialogues_*.json")):
        with open(f, encoding="utf-8") as fh:
            yield from json.load(fh)


def extract(a):
    src = a.src or next(p for p in SRC_CANDIDATES if os.path.isdir(p))
    random.seed(a.seed)
    n_by_split = {"train": a.train, "dev": a.dev, "test": a.test}
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    forms, keys = {}, []  # luot 1: gom ten thuc the va ten duong o ca 3 tap de tao ban do nhat quan
    for split in n_by_split:
        for d in load(src, split):
            for f, s in dialogue_forms(d).items():
                forms.setdefault(f, s)
            for t in d["turns"]:
                keys += street_keys(t["utterance"])
    db, addrs = load_db()
    print(f"CSDL MultiWOZ: {len(db)} co so" if db else f"CANH BAO: khong co {DB_DIR}, tien to ten doan theo tu khoa")
    emap = build_emap(forms, a.seed, db)
    global MULTI_PAT
    # thay o moi hoi thoai: ten >= 2 tu, hoac ten 1 tu trung DUNG ten trong CSDL (vd "eraina", "panahar")
    db_names = {n for _, n in db}
    MULTI_PAT = make_pat([f for f in emap if len(f.split()) >= 2 or f in db_names])
    set_streets(build_streets(keys + db_street_keys(addrs), a.seed))
    with open(os.path.join(os.path.dirname(a.out) or ".", "street_map.json"), "w", encoding="utf-8") as fm:
        json.dump(STREETS, fm, ensure_ascii=False, indent=1)
    print(f"ban do duong: {len(set(STREETS.values()))} pho")
    with open(os.path.join(os.path.dirname(a.out) or ".", "entity_map.json"), "w", encoding="utf-8") as fm:
        json.dump({f: {"slot": forms[f], "vi": v} for f, v in emap.items()}, fm, ensure_ascii=False, indent=1)
    print(f"ban do thuc the: {len(emap)} ten")
    total = 0
    with open(a.out, "w", encoding="utf-8") as fo:
        for split, n in n_by_split.items():
            pool = [p for p in (parse(d, emap) for d in load(src, split))
                    if p["domains"] and (a.domains == "all" or set(p["domains"]) <= set(a.domains.split(",")))]
            random.shuffle(pool)
            pool = pool if n <= 0 else pool[:n]  # n = 0: lay het
            pool.sort(key=lambda p: not set(p["domains"]) <= PRIORITY)  # on dinh: nhom uu tien dich truoc
            for p in pool:
                fo.write(json.dumps({**p, "split": split}, ensure_ascii=False) + "\n")
            total += len(pool)
            print(f"{split}: {len(pool)} hoi thoai")
    print(f"xong: {total} hoi thoai -> {a.out}")


def fake(d):  # kiem tra luong doc/ghi/resume ma khong ton tien API
    return ["[VI] " + t["src"] for t in d["turns"]]


PROMPT = """Bạn là biên dịch viên người Việt, chuyển hội thoại đặt chỗ (nhà hàng, khách sạn, tàu, điểm tham quan) từ tiếng Anh sang tiếng Việt sao cho đọc lên giống hệt cuộc trò chuyện thật giữa khách và nhân viên tổng đài ở Việt Nam.
Đầu vào là JSON gồm "ten_rieng" (tên riêng, phải giữ NGUYÊN VĂN) và "luot" (các lượt theo thứ tự).

Cách làm: đọc HẾT hội thoại trước để hiểu ngữ cảnh, rồi mới dịch từng lượt.
- Dịch ĐẦY ĐỦ ý của từng lượt, không rút gọn, không lược chi tiết, không thêm ý mới. Không gộp hay tách lượt; số phần tử đầu ra bằng số lượt đầu vào.
- KHÔNG suy diễn, giải thích hay bổ sung (vd "same price range as the restaurant" → "cùng mức giá với nhà hàng", không tự thêm "tức là loại cao cấp"). Bản gốc có chỗ nhầm lẫn hay vô lý (nhân viên nhầm trạng thái đặt chỗ, mã sai, trả lời lệch câu hỏi...) thì vẫn dịch đúng như vậy, KHÔNG tự sửa nội dung hội thoại.
- Thời gian ở khách sạn/nhà nghỉ tính bằng "đêm" theo mạch hội thoại, kể cả khi bản gốc lỡ viết "days".
- Diễn đạt lại theo cách người Việt thực sự nói, không bám cấu trúc câu tiếng Anh. Câu trọn vẹn, mạch lạc, lịch sự; không cộc lốc, không viết tắt, không dùng tiếng lóng.
- Dùng từ đầy đủ, chuẩn mực: "sang trọng" (không viết "sang"), "giá cả phải chăng", "món ăn Giáng sinh"... Không dùng văn dịch máy ("xin vui lòng" cuối câu, "thị trấn" cho thành phố).
- Câu nào phụ thuộc lượt trước (đại từ "nó", "ở đó", "chỗ đó", câu trả lời ngắn "Có", "Không", "Vậy cũng được") thì dịch sao cho vẫn rõ nghĩa trong mạch hội thoại, nhưng không tự thêm thông tin không có trong câu gốc.
- Xưng hô nhất quán suốt hội thoại: khách xưng "mình" và gọi nhân viên là "bạn"; nhân viên xưng "em" và gọi khách là "anh" (không viết "anh/chị"). LUÔN gọi khách là "anh". CHỈ gọi "chị" khi chính bản gốc gọi khách là nữ ("ma'am", "madam", "Mrs", "Ms", "Miss", "lady") hoặc khách tự nói mình là phụ nữ. Khách nhắc tới chị gái, vợ, mẹ, con gái hay bất kỳ người nữ nào khác KHÔNG làm khách thành nữ. Không có dấu hiệu rõ ràng thì dùng "anh".
- Câu hỏi lịch sự của nhân viên kết thúc bằng "ạ" hoặc "nhé" thì KHÔNG thêm dấu "?" (vd "Anh cần em hỗ trợ gì thêm không ạ"). Các câu hỏi khác giữ dấu "?" như bình thường.
- Giữ nguyên mọi con số, giờ (giữ dạng 08:15), mã đặt chỗ, số điện thoại, địa chỉ, mã bưu chính. Tiền dạng "448.000 VND" viết là "448.000 đồng" (giữ nguyên số); tiền "pounds" viết bằng chữ thì đổi theo 1 bảng = 25.000 đồng. "postcode" là "mã bưu chính".
- Địa danh viết không dấu (Hanoi, Hai Phong, Noi Bai Airport...) thì viết lại có dấu (Hà Nội, Hải Phòng, sân bay Nội Bài).

- Mức giá dịch thống nhất cả bộ dữ liệu: "expensive" → "sang trọng" hoặc "cao cấp" (vd "nhà hàng sang trọng", "khách sạn cao cấp"; "in the expensive price range" → "thuộc loại sang trọng/cao cấp"), KHÔNG dịch là "giá cao"/"đắt"; "cheap" → "giá rẻ" hoặc "bình dân"; "moderate"/"moderately priced" → "giá vừa phải" hoặc "tầm trung".
- Loại chỗ ở: "hotel" (loại hình) → "khách sạn"; "guesthouse"/"guest house"/"b&b" → "nhà nghỉ". Tiếng Anh hay dùng "hotel" làm TỪ CHUNG cho mọi chỗ ở (vd "The hotel should be ... and should be a guesthouse"): khi đó KHÔNG dịch là "khách sạn" mà dịch theo loại đang được nói tới trong hội thoại, hoặc "chỗ ở" nếu khách chưa chọn loại. Đã xác định là nhà nghỉ thì gọi "nhà nghỉ" suốt; là khách sạn thì gọi "khách sạn" suốt. Chỉ dùng cả hai khi hội thoại gốc thật sự đổi loại (vd hết khách sạn, gợi ý nhà nghỉ) và câu dịch phải nói rõ việc đổi đó. Không dùng "nhà khách".
- Tên cơ sở trong "ten_rieng" đã mang sẵn loại hình ở đầu tên ("Nhà nghỉ Thu Trúc", "Khách sạn Lâm Hạ", "Nhà hàng Cúc Hồng", "Quán ăn ..."). Khi nhắc tới cơ sở đó ở BẤT KỲ lượt nào (kể cả "the hotel", "it", "there", "the place") phải gọi đúng loại hình ấy: là "Nhà nghỉ X" thì gọi "nhà nghỉ", là "Khách sạn Y" thì gọi "khách sạn". Không bao giờ gọi một nhà nghỉ là khách sạn hay ngược lại.
- Món ăn: "asian oriental"/"oriental" → "món châu Á"; "modern european" → "món châu Âu hiện đại"; "british" → "món Anh".
- MẠCH HỘI THOẠI: trước khi dịch, lập bảng thuật ngữ cho cả hội thoại (mỗi đối tượng: khách sạn, nhà hàng, chuyến tàu, mức giá, khu vực... chỉ gọi bằng MỘT cách) rồi dùng đúng bảng đó ở mọi lượt. Lượt sau phải khớp logic với lượt trước: cùng một đối tượng không được lúc gọi thế này lúc gọi thế khác; đại từ ("nó", "chỗ đó", "chuyến đó") phải chỉ đúng đối tượng đang nói tới.

Ví dụ (CỨNG → TỐT):
- "I need a cheap place to eat in the centre." → CỨNG: "Tôi cần chỗ ăn rẻ ở trung tâm." → TỐT: "Tôi đang cần tìm một quán ăn giá rẻ ở khu trung tâm."
- "Do you have a preference for the area?" → CỨNG: "Anh có ưu tiên khu vực không?" → TỐT: "Anh có muốn tìm ở khu vực nào cụ thể không ạ"
- "That sounds great, book it for 2 people at 18:30." → CỨNG: "Nghe hay, đặt cho 2 người 18:30." → TỐT: "Nghe được đấy, em đặt giúp tôi bàn cho 2 người lúc 18:30 nhé."
- "Booking was successful. Reference number is : ABC123 ." → CỨNG: "Đặt thành công. Mã là ABC123." → TỐT: "Em đã đặt bàn thành công cho anh rồi ạ. Mã đặt chỗ của anh là ABC123."
- "We will be 2 people staying 4 nights, arriving Sunday." → CỨNG: "Bên mình có 2 người, ở 4 đêm và sẽ đến vào Chủ nhật." → TỐT: "Bọn mình đi 2 người, ở 4 đêm và sẽ đến vào Chủ nhật nhé."
- "I don't care about the price." → CỨNG: "Mức giá thì mình không câu nệ." → TỐT: "Mình không có yêu cầu cụ thể về giá."
- "I need a guesthouse with free parking." → CỨNG: "Mình đang tìm một chỗ ở là nhà nghỉ có chỗ đỗ xe miễn phí." → TỐT: "Mình muốn tìm một nhà nghỉ có chỗ đỗ xe miễn phí."
- "How about 3 nights instead?" → CỨNG: "Vậy thì đặt 3 đêm thay vào đó được không?" → TỐT: "Vậy mình đổi xuống 3 đêm được không?"

Bản gốc tiếng Anh vốn có lỗi do người thu thập dữ liệu (nhân viên nhầm trạng thái đặt chỗ, đưa mã sai, chưa hỏi đủ thông tin đã gợi ý, tổng tiền lệch...). KHÔNG sửa các lỗi đó trong bản dịch; ghi lại vào "loi_goc" để người kiểm tra biết đó là lỗi của dữ liệu gốc.
Chỉ trả về MỘT object JSON dạng {"thuat_ngu": {"<từ tiếng Anh>": "<cách dịch thống nhất>", ...}, "dich": ["<lượt 1>", "<lượt 2>", ...], "loi_goc": [{"luot": <số thứ tự lượt, tính từ 0>, "mo_ta": "<lỗi trong bản gốc>"}]}; "dich" có đúng một phần tử cho mỗi lượt; "loi_goc" là [] nếu không có; không giải thích gì thêm."""


def json_list(txt, n):
    """Lay mang JSON trong cau tra loi cua LLM; sai so luot thi bao loi de goi lai."""
    out = json.loads(txt[txt.find("{"):txt.rfind("}") + 1])["dich"] if "{" in txt else json.loads(txt[txt.find("["):txt.rfind("]") + 1])
    if len(out) != n or not all(isinstance(x, str) and x.strip() for x in out):
        raise ValueError(f"can {n} luot, nhan {len(out)}")
    return out


assert json_list('Day:\n["a", "b"]', 2) == ["a", "b"]


def claude_bin():
    """claude.exe: tren PATH, hoac ban kem extension Claude Code cua VS Code (ban moi nhat)."""
    import shutil
    found = sorted(glob.glob(os.path.expanduser(
        "~/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude*")))
    path = shutil.which("claude") or (found[-1] if found else None)
    assert path, "khong tim thay claude: cai Claude Code hoac extension VS Code"
    return path


def claude(model):
    """Goi Claude Code o che do khong tuong tac (-p): tinh vao han muc goi Pro/Max, khong can khoa API."""
    import subprocess
    exe = claude_bin()

    def run(d):  # ca hoi thoai mot lan goi, de LLM giu mach (dai tu, xung ho)
        inp = {"ten_rieng": sorted({e for t in d["turns"] for e in t["ents"]}),
               "luot": [{"nguoi_noi": "khach" if t["speaker"] == "USER" else "nhan_vien", "cau": t["src"]}
                        for t in d["turns"]]}
        r = subprocess.run([exe, "-p", "--model", model, "--system-prompt", PROMPT, "--tools", ""],
                           input=json.dumps(inp, ensure_ascii=False), capture_output=True,
                           text=True, encoding="utf-8", timeout=300)
        if r.returncode != 0 or "[" not in r.stdout:  # het han muc / chua dang nhap -> dung han, chay lai sau
            raise RuntimeError(f"claude loi (ma {r.returncode}): {(r.stdout + r.stderr).strip()[:300]}")
        out = json_list(r.stdout, len(d["turns"]))
        female = re.search(r"\b(ma'?am|madam|mrs|ms|miss|lady)\b", " ".join(t["en"] for t in d["turns"]), re.I)
        if not female and any(re.search(r"\bchị\b", v) for t, v in zip(d["turns"], out) if t["speaker"] == "SYSTEM"):
            raise ValueError('goi khach la "chi" khong co dau hieu nu trong ban goc')
        try:  # ghi chu loi co san trong ban goc (khong bat buoc)
            d["loi_goc"] = json.loads(r.stdout[r.stdout.find("{"):r.stdout.rfind("}") + 1]).get("loi_goc", [])
        except (ValueError, AttributeError):
            d["loi_goc"] = []
        # luat da chot: cau hoi lich su cua nhan vien ket thuc bang "a"/"nhe" khong co dau hoi (LLM doi khi quen)
        return [re.sub(r"(ạ|nhé)\s*\?$", r"\1", v.strip()) if t["speaker"] == "SYSTEM" else v
                for t, v in zip(d["turns"], out)]

    return run


QUOTA = {"train": 1000, "dev": 150, "test": 350}  # voi limit=1500; limit khac thi chia theo cung ti le


def pick(rows, limit):
    """Lay `limit` hoi thoai chia train/dev/test theo QUOTA (0 = lay het, giu ti le goc), xep xen ke de dung giua chung
    van duoc mot tap con can bang. Trong moi tap giu thu tu uu tien (restaurant/hotel/train truoc)."""
    by = collections.defaultdict(list)
    for d in rows:
        by[d["split"]].append(d)
    if limit:
        by = {s: g[:round(QUOTA[s] * limit / sum(QUOTA.values()))] for s, g in by.items()}
    order = sorted((i / len(g), s, i) for s, g in by.items() for i in range(len(g)))
    return [by[s][i] for _, s, i in order]


def single_instance(out):
    """Khoa file <out>.lock (chua PID): chi mot tien trinh dich cho moi file ket qua, chong ghi trung."""
    import atexit
    import ctypes
    lock = out + ".lock"
    if os.path.exists(lock):
        try:
            pid = int(open(lock).read().strip())
            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(0x1000, 0, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            code = ctypes.c_ulong()
            alive = bool(h) and bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE
            if h:
                k32.CloseHandle(h)
        except (ValueError, OSError, AttributeError):
            alive = False
        if alive:
            raise SystemExit(f"DUNG: tien trinh dich khac (PID {pid}) dang ghi {out}. Khong chay hai tien trinh cung luc.")
    with open(lock, "w") as f:
        f.write(str(os.getpid()))
    atexit.register(lambda: os.path.exists(lock) and os.remove(lock))


def translate(a):
    from concurrent.futures import ThreadPoolExecutor
    single_instance(a.out)
    done = set()
    if os.path.exists(a.out):
        with open(a.out, encoding="utf-8") as f:
            done = {json.loads(l)["id"] for l in f}
    with open(a.inp, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f]
    todo = [d for d in pick(rows, a.limit) if d["id"] not in done]
    n_done = len(done)
    print(f"da xong {n_done}, con {len(todo)} hoi thoai")
    run = fake if a.fake else claude(a.model)

    tries = {}

    def job(d):
        for _ in range(3):  # LLM doi khi tra sai so luot -> goi lai
            try:
                return d, run(d)
            except ValueError as e:
                print("goi lai", d["id"], e)
            except RuntimeError as e:  # het han muc goi Pro ("session limit ... resets 3:30pm"): cho roi lam tiep
                if not re.search(r"limit|resets|rate", str(e), re.I):  # loi la (claude.exe sap...): thu lai 2 lan roi bo qua
                    tries[d["id"]] = tries.get(d["id"], 0) + 1
                    print(time.strftime("%H:%M"), "loi claude:", str(e)[:100], "| lan", tries[d["id"]], flush=True)
                    time.sleep(30)
                    return job(d) if tries[d["id"]] < 3 else (d, None)
                print(time.strftime("%H:%M"), "het han muc, cho 10 phut:", str(e)[:120], flush=True)
                time.sleep(600)
                return job(d)
        return d, None

    t0, bad = time.time(), 0
    with ThreadPoolExecutor(a.workers) as ex, open(a.out, "a", encoding="utf-8") as fo:
        for k, (d, vi) in enumerate(ex.map(job, todo), 1):
            if vi is None:
                bad += 1  # khong ghi -> lan chay sau tu dich lai
                continue
            if d["id"] in done:  # da co trong file (vd tien trinh khac vua ghi): khong ghi lai
                continue
            done.add(d["id"])
            for t, v in zip(d["turns"], vi):
                t["vi"] = v
            fo.write(json.dumps(d, ensure_ascii=False) + "\n")
            fo.flush()
            if k % 10 == 0 or k == len(todo):
                eta = (len(todo) - k) * (time.time() - t0) / k / 60
                print(f"{n_done + k}/{n_done + len(todo)} hoi thoai | loi {bad} | con ~{eta:.0f} phut")


def check(a):
    """Kiem tra tu dong sau khi dich: mat so/gio, mat ten thuc the da ban dia hoa, do dai bat thuong."""
    num = re.compile(r"\d+(?::\d+)?")
    norm = lambda s: {x.lstrip("0") for x in num.findall(s)}  # "08:15" == "8:15"
    with open(a.inp, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f]
    flags, n_turns, out = collections.Counter(), 0, []
    for d in rows:
        for t in d["turns"]:
            n_turns += 1
            why = []
            if norm(t["src"]) - norm(t["vi"]):
                why.append("so/gio")
            if any(e.lower() not in t["vi"].lower() for e in t.get("ents", [])):
                why.append("ten")
            w_en, w_vi = len(t["src"].split()), len(t["vi"].split())
            if w_en >= 4 and not 0.6 <= w_vi / w_en <= 2.2:
                why.append("do dai")
            flags.update(why)
            if why:
                out.append([d["id"], t["i"], t["speaker"], t["src"], t["vi"], ",".join(why)])
    with open(a.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["id", "turn", "speaker", "src", "vi", "loi"])
        w.writerows(out)
    print(f"{n_turns} cau, bi danh dau {len(out)} ({len(out) / max(n_turns, 1):.1%}); theo loai: {dict(flags)} -> {a.out}")


def review(a):
    with open(a.inp, encoding="utf-8") as f:
        rows = [json.loads(l) for l in f]
    random.seed(a.seed)
    with open(a.out, "w", encoding="utf-8-sig", newline="") as f:  # utf-8-sig de Excel doc dung tieng Viet
        w = csv.writer(f, delimiter="\t")
        w.writerow(["id", "turn", "speaker", "en", "vi", "loi_goc (co san trong MultiWOZ)", "tu_nhien_1-3", "dung_nghia_1-3"])
        for d in random.sample(rows, min(a.n, len(rows))):
            notes = collections.defaultdict(list)
            for x in d.get("loi_goc", []):
                if isinstance(x, dict):
                    notes[x.get("luot")].append(str(x.get("mo_ta", "")))
            for t in d["turns"]:
                w.writerow([d["id"], t["i"], t["speaker"], t["en"], t["vi"], "; ".join(notes[t["i"]]), "", ""])
    print("xong ->", a.out)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--src")
    e.add_argument("--out", default="data/interim/mwoz_en.jsonl")
    e.add_argument("--domains", default=DOMAINS, help='vd "restaurant,hotel,train" hoac "all"')
    e.add_argument("--train", type=int, default=0, help="so hoi thoai moi tap; 0 = lay het")
    e.add_argument("--dev", type=int, default=0)
    e.add_argument("--test", type=int, default=0)
    e.add_argument("--seed", type=int, default=42)
    e.set_defaults(fn=extract)
    t = sub.add_parser("translate")
    t.add_argument("--inp", default="data/interim/mwoz_en.jsonl")
    t.add_argument("--out", default="data/interim/mwoz_vi.jsonl")
    t.add_argument("--fake", action="store_true", help="khong goi API, chi kiem tra luong chay")
    t.add_argument("--model", default="sonnet", help="ten mo hinh cho claude -p: haiku / sonnet / opus")
    t.add_argument("--limit", type=int, default=0, help="chi dich N hoi thoai (chia theo ti le train/dev/test); 0 = het")
    t.add_argument("--workers", type=int, default=2, help="so hoi thoai dich song song")
    t.set_defaults(fn=translate)
    c = sub.add_parser("check")
    c.add_argument("--inp", default="data/interim/mwoz_vi.jsonl")
    c.add_argument("--out", default="data/interim/check_flags.tsv")
    c.set_defaults(fn=check)
    r = sub.add_parser("review")
    r.add_argument("--inp", default="data/interim/mwoz_vi.jsonl")
    r.add_argument("--out", default="data/interim/review_sample.tsv")
    r.add_argument("--n", type=int, default=100)
    r.add_argument("--seed", type=int, default=42)
    r.set_defaults(fn=review)
    args = p.parse_args()
    args.fn(args)
