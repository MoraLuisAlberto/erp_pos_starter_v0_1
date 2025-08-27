from app.db import SessionLocal
from sqlalchemy import text

# Utilidades
def table_exists(s, name):
    return bool(s.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"), {"n": name}).fetchone())

def pick_first_existing(s, candidates):
    for n in candidates:
        if table_exists(s, n):
            return n
    return None

def columns(s, table):
    return s.execute(text(f"PRAGMA table_info({table})")).fetchall()  # [(cid, name, type, notnull, dflt, pk),...]

def has_col(cols, name):
    return any(c[1] == name for c in cols)

def notnull_cols_without_default(cols):
    return [c for c in cols if c[3] == 1 and (c[4] is None) and c[5] == 0]  # NOT NULL, sin default y no PK

def ensure_row_by_id(s, table, id_value, suggest: dict):
    cols = columns(s, table)
    # ¿ya existe?
    row = s.execute(text(f"SELECT id FROM {table} WHERE id=:id"), {"id": id_value}).fetchone()
    if row:
        return "exists"
    # INSERT sólo con columnas que existan
    data = {"id": id_value}
    for k, v in suggest.items():
        if has_col(cols, k):
            data[k] = v
    # Evita NOT NULL sin default
    for c in notnull_cols_without_default(cols):
        cname = c[1]
        if cname not in data and cname != "id":
            ctype = (c[2] or "").lower()
            if "char" in ctype or "text" in ctype:
                data[cname] = ""
            elif "int" in ctype:
                data[cname] = 0
            elif "real" in ctype or "floa" in ctype or "doub" in ctype or "num" in ctype:
                data[cname] = 0.0
            else:
                data[cname] = ""
    cols_ins = ",".join(data.keys())
    params = ",".join(f":{k}" for k in data.keys())
    s.execute(text(f"INSERT INTO {table} ({cols_ins}) VALUES ({params})"), data)
    s.commit()
    return "inserted"

def main():
    s = SessionLocal()
    try:
        # Detecta tablas
        product_tbl   = pick_first_existing(s, ["product", "products", "prod"])
        pricelist_tbl = pick_first_existing(s, ["price_list", "pricelist", "price_lists"])
        pli_tbl       = pick_first_existing(s, ["price_list_item", "pricelist_item", "price_list_items", "pricelist_items"])

        if not product_tbl:
            raise SystemExit("ERROR: No se encontró ninguna tabla de producto (product/products).")
        if not pricelist_tbl:
            # crea tabla mínima si no existe
            s.execute(text("CREATE TABLE IF NOT EXISTS pricelist (id INTEGER PRIMARY KEY, name TEXT)"))
            s.commit()
            pricelist_tbl = "pricelist"
        if not pli_tbl:
            # crea tabla mínima si no existe
            s.execute(text("""
                CREATE TABLE IF NOT EXISTS price_list_item (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    price_list_id INTEGER NOT NULL,
                    product_id INTEGER NOT NULL,
                    price REAL NOT NULL DEFAULT 0
                )
            """))
            s.commit()
            pli_tbl = "price_list_item"

        # 1) Producto id=1
        prod_state = ensure_row_by_id(s, product_tbl, 1, {
            "name": "Demo Product 1",
            "active": 1,
            "barcode": "000000000001",
            "sku": "SKU-1",
            "code": "SKU-1",
        })

        # 2) PriceList id=1
        pl_state = ensure_row_by_id(s, pricelist_tbl, 1, {
            "name": "Standard",
            "active": 1,
            "code": "STD",
        })

        # 3) PriceListItem (lista=1, producto=1, precio=129.00)
        pli_cols = columns(s, pli_tbl)
        list_col  = "price_list_id" if has_col(pli_cols, "price_list_id") else ("pricelist_id" if has_col(pli_cols, "pricelist_id") else "list_id")
        prod_col  = "product_id"    if has_col(pli_cols, "product_id")    else ("prod_id"     if has_col(pli_cols, "prod_id")     else None)
        price_col = "price"         if has_col(pli_cols, "price")         else ("unit_price"  if has_col(pli_cols, "unit_price")  else "amount")
        if not prod_col:
            raise SystemExit(f"ERROR: No se encontró columna de producto en {pli_tbl}")

        row = s.execute(text(f"SELECT id, {price_col} FROM {pli_tbl} WHERE {list_col}=:l AND {prod_col}=:p"),
                        {"l": 1, "p": 1}).fetchone()
        if row:
            s.execute(text(f"UPDATE {pli_tbl} SET {price_col}=:pr WHERE id=:id"), {"pr": 129.00, "id": row[0]})
            s.commit()
            pli_state = "updated"
        else:
            s.execute(text(f"INSERT INTO {pli_tbl} ({list_col}, {prod_col}, {price_col}) VALUES (:l,:p,:pr)"),
                      {"l": 1, "p": 1, "pr": 129.00})
            s.commit()
            pli_state = "inserted"

        # Índice único (lista, producto)
        try:
            s.execute(text(f"CREATE UNIQUE INDEX IF NOT EXISTS ux_{pli_tbl}_lp ON {pli_tbl}({list_col}, {prod_col})"))
            s.commit()
        except Exception:
            pass

        print(f"SEEDED_PRODUCT  -> table={product_tbl} state={prod_state}")
        print(f"SEEDED_PL       -> table={pricelist_tbl} state={pl_state}")
        print(f"SEEDED_PLI      -> table={pli_tbl} list_col={list_col} prod_col={prod_col} price_col={price_col} state={pli_state} price=129.00")
    finally:
        s.close()

if __name__ == "__main__":
    main()
