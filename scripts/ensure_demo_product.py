import os, sqlite3

DB = os.path.join(os.getcwd(), "erp_pos.db")
conn = sqlite3.connect(DB); cur = conn.cursor()

def has_col(table, col):
    cur.execute(f"PRAGMA table_info('{table}')")
    return any(r[1] == col for r in cur.fetchall())

# A) columna product.barcode
if not has_col("product","barcode"):
    cur.execute("ALTER TABLE product ADD COLUMN barcode VARCHAR(50)")

# B) tabla product_barcode
cur.execute("""
CREATE TABLE IF NOT EXISTS product_barcode (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL REFERENCES product(id),
    code VARCHAR(50) NOT NULL UNIQUE
)""")
cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_product_barcode_code ON product_barcode(code)")
cur.execute("CREATE INDEX IF NOT EXISTS ix_product_barcode_product ON product_barcode(product_id)")

# C) asegurar un producto y su barcode
cur.execute("SELECT id, COALESCE(barcode,'') FROM product ORDER BY id LIMIT 1")
row = cur.fetchone()
if row is None:
    cur.execute("INSERT INTO product (name, barcode, uom) VALUES (?,?,?)",
                ("Demo Product","7501234567890","unit"))
    pid = cur.lastrowid
    barcode = "7501234567890"
else:
    pid, barcode = row
    if not barcode:
        barcode = "7501234567890"
        cur.execute("UPDATE product SET barcode=? WHERE id=?", (barcode, pid))

# asegurar que también exista en product_barcode
try:
    cur.execute("INSERT INTO product_barcode (product_id, code) VALUES (?,?)", (pid, barcode))
except sqlite3.IntegrityError:
    pass

# D) asegurar lista de precios y precio
cur.execute("SELECT id FROM price_list ORDER BY id LIMIT 1")
pl = cur.fetchone()
plid = pl[0] if pl else None
if plid is None:
    cur.execute("INSERT INTO price_list (name) VALUES ('General')")
    plid = cur.lastrowid

cur.execute("SELECT 1 FROM price_list_item WHERE price_list_id=? AND product_id=?", (plid, pid))
if cur.fetchone() is None:
    cur.execute("INSERT INTO price_list_item (price_list_id, product_id, price) VALUES (?,?,?)",
                (plid, pid, 129.00))

conn.commit(); conn.close()

# IMPORTANTE: imprime SOLO el barcode
print(barcode)
