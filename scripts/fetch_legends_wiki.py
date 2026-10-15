"""Fetches the Wikipedia infobox for each name in scripts/legends_wishlist.txt and writes data/_legends_raw.json.

Runs in GitHub Actions (the build sandbox can't reach Wikipedia). The output is raw material: career totals,
size, college and draft are reviewed and turned into legend entries by scripts/add_old_legends.py.
"""
import json, os, re, urllib.request, urllib.parse, urllib.error, time
HERE = os.path.dirname(os.path.abspath(__file__))
API = "https://en.wikipedia.org/w/api.php?action=parse&prop=wikitext&format=json&redirects=1&page="

def wikitext(title):
    req = urllib.request.Request(API + urllib.parse.quote(title), headers={"User-Agent": "our-guys/1.0 (personal fan app; github.com/TDiBella-Personal/NFLplayerstats)"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                d = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as ex:
            if ex.code != 429 or attempt == 5: raise
            wait = int(ex.headers.get("Retry-After") or 0) or 20 * (attempt + 1)
            print("   throttled, waiting", wait); time.sleep(wait); continue
        if "parse" in d or (d.get("error") or {}).get("code") == "missingtitle": break
        print("   retrying:", (d.get("error") or {}).get("code"))
        time.sleep(5 * (attempt + 1))
    return (d.get("parse") or {}).get("wikitext", {}).get("*", ""), (d.get("parse") or {}).get("title", "")

def infobox(text):
    m = re.search(r"\{\{\s*infobox[ _](nfl|american[ _]football|gridiron[ _]football)", text, re.I)
    if not m: return None
    i = m.start()
    depth, j = 0, i
    while j < len(text):
        if text.startswith("{{", j): depth += 1; j += 2; continue
        if text.startswith("}}", j):
            depth -= 1; j += 2
            if depth == 0: break
            continue
        j += 1
    body = text[i:j]
    fields, cur = {}, None
    for line in body.split("\n"):
        m = re.match(r"\s*\|\s*([A-Za-z_0-9]+)\s*=\s*(.*)$", line)
        if m: cur = m.group(1); fields[cur] = m.group(2).strip()
        elif cur: fields[cur] += "\n" + line.strip()
    return fields

def main():
    path = os.path.join(HERE, "..", "data", "_legends_raw.json")
    try: done = {r["name"]: r for r in json.load(open(path)) if r.get("ok")}
    except Exception: done = {}
    out = []
    for line in open(os.path.join(HERE, "legends_wishlist.txt")):
        line = line.strip()
        if not line or line.startswith("#"): continue
        name, _, title = line.partition("|")
        if name in done: out.append(done[name]); continue
        tries = [title] if title else [name, name + " (American football)"]
        rec = {"name": name, "ok": False}
        for t in tries:
            try:
                text, real = wikitext(t)
                box = infobox(text)
                if box:
                    rec.update({"ok": True, "title": real, "box": box}); break
            except Exception as ex:
                rec["err"] = str(ex)
            time.sleep(4)
        out.append(rec)
        print(("ok  " if rec["ok"] else "MISS"), name, rec.get("title", ""))
    json.dump(out, open(path, "w"), indent=0, ensure_ascii=False)

if __name__ == "__main__":
    main()
