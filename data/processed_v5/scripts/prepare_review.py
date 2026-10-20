"""Liệt kê các lượt user có từ 2 intent trong processed_v3, kèm gợi ý nhãn.

Gợi ý dựa trên trạng thái gốc của MultiWOZ 2.2: intent nào thuộc domain có
slot/requested_slots thay đổi ở lượt này thì được giữ; intent còn lại được
coi là "treo" (đã active từ lượt trước) hoặc "bật sớm" (mới active nhưng
không có thông tin gì).

Cách chạy:
    python scripts/prepare_review.py processed_v3 multiwoz_2.2 review_items.json
"""
import json, re, sys, pathlib

KW = {
    "hotel": r"\b(?:hotels?|guest ?houses?|place to stay|lodging|accommodations?|rooms?|stay(?:ing)?|stars?|parking|wifi|internet|b ?& ?b|bed and breakfast|nights?)\b",
    "restaurant": r"\b(?:restaurants?|food|eat(?:ing)?|dine|dining|table|cuisine|lunch|dinner|breakfast|meal)\b",
    "train": r"\b(?:trains?|tickets?|depart\w*|leav(?:e|ing)|arriv\w*|travel\w*|station|journey|trip)\b",
}


def load_orig(orig_dir):
    orig = {}
    for split in ("train", "dev", "test"):
        for f in sorted((orig_dir / split).glob("*.json")):
            for d in json.load(open(f, encoding="utf-8")):
                orig[d["dialogue_id"]] = d
    return orig


def main(proc, orig_dir, out_path):
    orig = load_orig(orig_dir)
    empty = {"active_intent": "NONE", "slot_values": {}, "requested_slots": []}
    items = []
    for split in ("test", "dev", "train"):
        for line in open(proc / f"{split}.jsonl", encoding="utf-8"):
            d = json.loads(line)
            prev = {}
            for t in orig[d["id"]]["turns"]:
                if t["speaker"] != "USER":
                    continue
                i = int(t["turn_id"])
                cur = {fr["service"]: fr["state"] for fr in t["frames"] if "state" in fr}
                label = d["turns"][i]["intent"]
                if "|" in label:
                    active = {s: st["active_intent"] for s, st in cur.items() if st["active_intent"] != "NONE"}
                    changed = [s for s in active
                               if cur[s]["slot_values"] != prev.get(s, empty)["slot_values"]
                               or sorted(cur[s].get("requested_slots", [])) != sorted(prev.get(s, empty).get("requested_slots", []))]
                    extra = [s for s in active if s not in changed]
                    if len(changed) == 1:
                        group = "1doi"
                        mentioned = [s for s in extra if re.search(KW.get(s, r"$^"), t["utterance"], re.I)]
                        if mentioned:
                            group = "1doi_rui_ro"
                        suggestion = active[changed[0]]
                    elif changed:
                        group = "2doi"
                        suggestion = "|".join(sorted(active[s] for s in changed))
                    else:
                        group = "0doi"
                        suggestion = label
                    extra_kind = {s: ("treo" if prev.get(s, empty)["active_intent"] != "NONE" else "bat_som") for s in extra}
                    sys_prev = d["turns"][i - 1]["en"] if i > 0 else ""
                    items.append({
                        "n": len(items) + 1, "split": split, "id": d["id"], "luot": i,
                        "nhan_goc": label, "nhom": group, "goi_y": suggestion,
                        "intent_thua": {active[s]: k for s, k in extra_kind.items()},
                        "he_thong_truoc": sys_prev, "en": t["utterance"], "vi": d["turns"][i]["vi"],
                    })
                prev = cur
    json.dump(items, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(len(items), "items;", dict(Counter(x["nhom"] for x in items)), dict(Counter(x["split"] for x in items)))


if __name__ == "__main__":
    main(pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]), sys.argv[3])
