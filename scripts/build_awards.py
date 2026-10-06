"""Builds data/awards.json and data/stars.json from scripts/awards_src.txt (hand-checked winner lists).

Run by hand each offseason after adding the new winners: python3 scripts/build_awards.py
A winner is matched to a player id by name and career years. Anyone who can't be matched to exactly
one player gets no badge (and is printed), never a guess.
"""
import json, os, re, sys
from collections import defaultdict
HERE = os.path.dirname(os.path.abspath(__file__)); DATA = os.path.join(HERE, "..", "data")

def norm(n):
    n = n.lower().replace(".", "").replace("'", "").replace("’", "")
    n = re.sub(r"\b(jr|sr|ii|iii|iv|v)$", "", n.strip()).strip()
    return re.sub(r"[^a-z]", "", n)

def main():
    cands = defaultdict(list)
    for p in json.load(open(os.path.join(DATA, "players.json"))):
        past = p.get("past") or []
        try: first = int(str(past[0][1])[:4])
        except Exception: first = None
        cands[norm(p["name"])].append({"id": p["id"], "f": first, "l": 9999, "act": True})
    for r in json.load(open(os.path.join(DATA, "retired.json"))):
        cands[norm(r["n"])].append({"id": r["id"], "f": r.get("f"), "l": r.get("l") or 0, "act": False})

    out = defaultdict(lambda: {"a": defaultdict(list)}); missed = []; award = None; ids = {}
    for line in open(os.path.join(HERE, "awards_src.txt")):
        line = line.strip()
        if not line or line.startswith("#"): continue
        if line.startswith("["): award = line.strip("[]"); continue
        parts = line.split("|")
        if award == "IDS": ids[parts[0]] = parts[1]; continue
        yr = int(parts[0]); name = parts[1]
        if name in ids:
            if award == "HOF": out[ids[name]]["h"] = yr
            else: out[ids[name]]["a"][award].append(yr)
            continue
        c = [x for x in cands.get(norm(name), []) if x["f"]]
        if award == "HOF":
            last = int(parts[2]); c = [x for x in c if not x["act"] and abs(x["l"] - last) <= 1]
        elif award == "HEISMAN":
            c = [x for x in c if 0 <= x["f"] - yr <= 6]
        else:
            c = [x for x in c if x["f"] <= yr <= x["l"]]
        if len(c) != 1: missed.append((award, yr, name, len(c))); continue
        if award == "HOF": out[c[0]["id"]]["h"] = yr
        else: out[c[0]["id"]]["a"][award].append(yr)

    order = ["MVP", "SBMVP", "OPOY", "DPOY", "OROY", "DROY", "CPOY", "WPMOY", "HEISMAN"]
    res = {}
    for pid, v in out.items():
        rec = {}
        if "h" in v: rec["h"] = v["h"]
        a = [[k, sorted(v["a"][k])] for k in order if k in v["a"]]
        if a: rec["a"] = a
        res[pid] = rec
    json.dump(res, open(os.path.join(DATA, "awards.json"), "w"), separators=(",", ":"))
    print(len(res), "players with awards;", sum(1 for r in res.values() if "h" in r), "Hall of Famers")
    # data/stars.json: the retired players shown in search without pressing the button
    def star(r):
        s = r.get("s") or {}; g = lambda k: s.get(k) or 0
        n = (r.get("l") or 0) - (r.get("f") or 0) + 1
        return (r.get("x") == 2 or r["id"] in res or g("passing_yards") >= 12000 or g("rushing_yards") >= 4000
                or g("receiving_yards") >= 5000 or g("def_sacks") >= 40 or g("def_interceptions") >= 20 or g("tackles") >= 600
                or g("fg_made") >= 150 or (n >= 10 and g("gp") >= 120) or (r["p"] == "OL" and n >= 11))
    stars = [r for r in json.load(open(os.path.join(DATA, "retired.json"))) if star(r)]
    json.dump(stars, open(os.path.join(DATA, "stars.json"), "w"), separators=(",", ":"), ensure_ascii=False)
    print(len(stars), "retired stars")
    print("not matched (no badge):")
    for m in missed: print("  ", *m)

if __name__ == "__main__":
    main()
