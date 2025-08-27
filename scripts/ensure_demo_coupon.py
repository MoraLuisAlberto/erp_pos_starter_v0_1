import os, sqlite3, datetime, json
from app.db import engine

db = engine.url.database
if not os.path.isabs(db): db = os.path.abspath(db)
con = sqlite3.connect(db); cur = con.cursor()

code = "WELCOME10"
row = cur.execute("SELECT id FROM coupon WHERE UPPER(code)=UPPER(?)", (code,)).fetchone()
if not row:
    now = datetime.datetime.utcnow()
    vf = (now - datetime.timedelta(days=1)).isoformat(timespec="seconds")
    vt = (now + datetime.timedelta(days=30)).isoformat(timespec="seconds")
    cur.execute("""INSERT INTO coupon
      (code, type, value, min_amount, max_uses, used_count, valid_from, valid_to,
       valid_days_mask, valid_hours_json, segment_id, is_active, created_at)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
      (code, "percent", 10, 100, 100, 0, vf, vt, 127, json.dumps([]), None, 1, now.isoformat(timespec="seconds"))
    )
    con.commit()
    cid = cur.lastrowid
    print(f"{code}|{cid}")
else:
    print(f"{code}|{row[0]}")
con.close()
