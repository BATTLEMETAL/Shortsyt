"""Quick check: Medal local DB + API metadata for clips."""
import sqlite3, json, os, urllib.request

# 1. Check SQLite DB
db_path = r"C:\Users\mz100\AppData\Roaming\Medal\medal-630868187.db"
print("=== MEDAL SQLITE DB ===")
try:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in c.fetchall()]
    print(f"Tables: {tables}")
    for t in tables[:5]:
        c.execute(f"SELECT * FROM [{t}] LIMIT 2")
        rows = c.fetchall()
        cols = [d[0] for d in c.description]
        print(f"\n  Table [{t}]: cols={cols}")
        for r in rows:
            print(f"    {str(r)[:300]}")
    conn.close()
except Exception as e:
    print(f"DB Error: {e}")

# 2. Check Medal API for clip metadata
clip_ids = ["1780471794645", "1780471647631", "1780471734071"]
print("\n=== MEDAL API ===")
for cid in clip_ids:
    url = f"https://medal.tv/api/content?contentId={cid}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        # Print key fields
        if isinstance(data, dict):
            for key in ["contentTitle", "contentDescription", "gameName", "categoryName", "contentTags"]:
                if key in data:
                    print(f"  [{cid}] {key}: {data[key]}")
            if "contentTitle" not in data:
                print(f"  [{cid}] keys: {list(data.keys())[:15]}")
        print()
    except Exception as e:
        print(f"  [{cid}] API error: {e}")

# 3. Check store.json for clip references  
store_path = r"C:\Users\mz100\AppData\Roaming\Medal\store\store.json"
print("\n=== STORE.JSON clip refs ===")
try:
    with open(store_path, 'r', encoding='utf-8') as f:
        store = json.load(f)
    for key in ["outplayedClips", "shadowPlayClips", "steamClips", "xboxGameBarClips"]:
        val = store.get(key)
        if val:
            print(f"  {key}: {str(val)[:300]}")
except Exception as e:
    print(f"Store error: {e}")
