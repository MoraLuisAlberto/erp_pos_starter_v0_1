import os
import sqlite3

DB = os.path.join(os.getcwd(), "erp_pos.db")
conn = sqlite3.connect(DB)
cur = conn.cursor()


def table_exists(name: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def cols(name: str):
    cur.execute(f"PRAGMA table_info('{name}')")
    return [r[1] for r in cur.fetchall()]


# 1) Asegurar tabla product con columna barcode
if not table_exists("product"):
    cur.execute(
        """CREATE TABLE product (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(120) NOT NULL,
        barcode VARCHAR(50),
        uom VARCHAR(20) DEFAULT 'unit'
    )"""
    )
else:
    if "barcode" not in cols("product"):
        cur.execute("ALTER TABLE product ADD COLUMN barcode VARCHAR(50)")

# 2) Asegurar tabla product_barcode con columna code
if not table_exists("product_barcode"):
    cur.execute(
        """CREATE TABLE product_barcode (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL REFERENCES product(id),
        code VARCHAR(50) NOT NULL
    )"""
    )
else:
    c = cols("product_barcode")
    if "code" not in c:
        # añadir columna code
        cur.execute("ALTER TABLE product_barcode ADD COLUMN code VARCHAR(50)")
        # migrar desde columna 'barcode' si existiera
        c = cols("product_barcode")
        if "barcode" in c:
            cur.execute("UPDATE product_barcode SET code = barcode WHERE code IS NULL OR code=''")
        else:
            # rellenar desde product.barcode cuando sea posible
            cur.execute(
                """UPDATE product_barcode
                           SET code = (SELECT p.barcode FROM product p WHERE p.id = product_barcode.product_id)
                           WHERE (code IS NULL OR code='')"""
            )

# 3) Índices (mejores esfuerzos; ignora si ya existen o si hay duplicados)
try:
    cur.execute("CREATE UNIQUE INDEX ix_product_barcode_code ON product_barcode(code)")
except sqlite3.OperationalError:
    pass
try:
    cur.execute("CREATE INDEX ix_product_barcode_product ON product_barcode(product_id)")
except sqlite3.OperationalError:
    pass

# 4) Asegurar un producto y su barcode
cur.execute("SELECT id, COALESCE(barcode,'') FROM product ORDER BY id LIMIT 1")
row = cur.fetchone()
if row is None:
    cur.execute(
        "INSERT INTO product (name, barcode, uom) VALUES (?,?,?)",
        ("Demo Product", "7501234567890", "unit"),
    )
    pid = cur.lastrowid
    barcode = "7501234567890"
else:
    pid, barcode = row
    if not barcode:
        barcode = "7501234567890"
        cur.execute("UPDATE product SET barcode=? WHERE id=?", (barcode, pid))

# 5) Asegurar registro en product_barcode
cur.execute("SELECT id, COALESCE(code,'') FROM product_barcode WHERE product_id=? LIMIT 1", (pid,))
alt = cur.fetchone()
if alt is None:
    # insertar alterno con el mismo code
    cur.execute("INSERT INTO product_barcode (product_id, code) VALUES (?,?)", (pid, barcode))
else:
    alt_id, alt_code = alt
    if not alt_code:
        cur.execute("UPDATE product_barcode SET code=? WHERE id=?", (barcode, alt_id))

# 6) Price list + item de 129.00
if not table_exists("price_list"):
    cur.execute(
        """CREATE TABLE price_list (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name VARCHAR(80) NOT NULL
    )"""
    )
if not table_exists("price_list_item"):
    cur.execute(
        """CREATE TABLE price_list_item (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        price_list_id INTEGER NOT NULL REFERENCES price_list(id),
        product_id INTEGER NOT NULL REFERENCES product(id),
        price NUMERIC(10,2) NOT NULL
    )"""
    )
cur.execute("SELECT id FROM price_list ORDER BY id LIMIT 1")
pl = cur.fetchone()
if pl is None:
    cur.execute("INSERT INTO price_list (name) VALUES ('General')")
    plid = cur.lastrowid
else:
    plid = pl[0]
cur.execute("SELECT 1 FROM price_list_item WHERE price_list_id=? AND product_id=?", (plid, pid))
if cur.fetchone() is None:
    cur.execute(
        "INSERT INTO price_list_item (price_list_id, product_id, price) VALUES (?,?,?)",
        (plid, pid, 129.00),
    )

conn.commit()
conn.close()

# imprime SOLO el código de barras semilla
print(barcode)
